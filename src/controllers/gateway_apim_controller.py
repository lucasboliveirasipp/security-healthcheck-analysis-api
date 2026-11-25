import base64
import json
import os
import queue
import threading

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from src.services.analise_service import (
    CapturaLogs,
    FormularioInvalidoError,
    analisar_formulario,
    dataframe_para_xlsx,
)

gateway_apim_route = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Intervalo maximo sem enviar nada ao cliente durante o streaming.
KEEPALIVE_SEGUNDOS = float(os.getenv("SSE_KEEPALIVE_SEGUNDOS", "15"))

# Marca o fim da analise na fila de eventos do streaming.
_FIM = object()


def _sse(payload: dict) -> str:
    """Formata um evento no protocolo Server-Sent Events."""
    return f"data: {json.dumps(payload)}\n\n"


@gateway_apim_route.post(
    "/analisar_healthcheck_stream",
    summary="Analisa o healthcheck com streaming de logs em tempo real.",
    tags=["Análise Healthcheck"],
)
async def api_analisar_healthcheck_stream(
    formulario: UploadFile = File(..., description="Planilha .xlsx do formulario"),
    evidencias: UploadFile = File(..., description="Arquivo .zip com as evidencias"),
):
    formulario_bytes = await formulario.read()
    evidencias_bytes = await evidencias.read()

    fila: queue.Queue = queue.Queue()

    def executar():
        """Roda a analise numa thread e publica cada evento SSE na fila."""
        try:
            with CapturaLogs() as captura:
                resultados = analisar_formulario(
                    formulario_bytes,
                    evidencias_bytes,
                    on_progress=captura.drenar,
                )
                for item in resultados:
                    if isinstance(item, pd.DataFrame):
                        buffer = dataframe_para_xlsx(item)
                        excel_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                        fila.put(_sse({"status": "complete", "excel": excel_base64}))
                    else:
                        fila.put(_sse({"log": item}))
        except FormularioInvalidoError as e:
            fila.put(_sse({"error": str(e)}))
        except Exception as e:
            fila.put(_sse({"error": f"Erro ao processar: {str(e)}"}))
        finally:
            fila.put(_FIM)

    def generate():
        # Algumas etapas (analise das evidencias, calculo da nota) passam mais
        # de 60 s sem emitir log, e o proxy da esteira derruba a conexao ociosa
        # nesse prazo: o front recebia "Failed to fetch" e a analise morria no
        # meio. O comentario SSE mantem a conexao viva e o front o ignora, pois
        # so processa linhas iniciadas por "data: ".
        threading.Thread(target=executar, daemon=True).start()
        while True:
            try:
                evento = fila.get(timeout=KEEPALIVE_SEGUNDOS)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if evento is _FIM:
                return
            yield evento

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@gateway_apim_route.post(
    "/analisar_healthcheck",
    summary="Analisa o formulário de healthcheck com base nas evidências.",
    tags=["Análise Healthcheck"],
)
async def api_analisar_healthcheck(
    formulario: UploadFile = File(..., description="Planilha .xlsx do formulario"),
    evidencias: UploadFile = File(..., description="Arquivo .zip com as evidencias"),
):
    formulario_bytes = await formulario.read()
    evidencias_bytes = await evidencias.read()

    try:
        saida = None
        for item in analisar_formulario(formulario_bytes, evidencias_bytes):
            if isinstance(item, pd.DataFrame):
                saida = item

        if saida is None:
            raise HTTPException(status_code=500, detail="A análise não produziu resultado.")

        return StreamingResponse(
            dataframe_para_xlsx(saida),
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": 'attachment; filename="Formulario analisado.xlsx"'},
        )
    except FormularioInvalidoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar o healthcheck: {e}")
