# tests/unit/test_gateway_apim_controller.py
#
# Testa os dois endpoints de analise: contratos HTTP, formato de resposta
# (xlsx x SSE) e traducao de erro. A orquestracao em si e coberta por
# test_analise_service_cover.py; aqui o agente e sempre substituido por um
# fake, sem nenhuma chamada de rede.
import base64
import io
import json
import zipfile

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import src.services.analise_service as analise_mod
from src.main import app

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _make_formulario_bytes(linhas=1):
    """Gera os bytes de uma planilha .xlsx valida no formato esperado."""
    df = pd.DataFrame(
        [
            {
                "Ref": f"AC 1.1.{i}",
                "Pergunta": "Pergunta de teste",
                "Informações da Pergunta e Orientações": "Contexto de teste",
                "Resposta": "Em todos os casos",
            }
            for i in range(1, linhas + 1)
        ]
    )
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer.read()


def _make_evidencias_zip_bytes():
    """Gera os bytes de um .zip valido com a estrutura <Ref>/<arquivo>."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("AC 1.1.1/.keep", "")
    buffer.seek(0)
    return buffer.read()


def _files(formulario_bytes=None, linhas=1):
    if formulario_bytes is None:
        formulario_bytes = _make_formulario_bytes(linhas=linhas)
    return {
        "formulario": ("formulario.xlsx", formulario_bytes, XLSX_CONTENT_TYPE),
        "evidencias": ("evidencias.zip", _make_evidencias_zip_bytes(), "application/zip"),
    }


class FakeAgent:
    """
    Stub de ANALISE_HEALTHCHECK com o mesmo contrato consumido pelo
    analise_service, sem chamadas externas. Cada metodo emite um print para
    que o streaming SSE tenha logs a repassar.
    """

    COM_EVIDENCIAS = False

    def __init__(self, token_apim, input_data):
        self.token_apim = token_apim
        self.input_data = input_data
        if self.COM_EVIDENCIAS:
            self.EVIDENCIAS = {"norma.pdf": {"file_id": "file-1", "file_path": "healthcheck/norma.pdf"}}
            self.ANALISE_EVIDENCIAS = ["comprova X", "pontos fortes Y", "pontos fracos Z"]
        else:
            self.EVIDENCIAS = {}
            self.ANALISE_EVIDENCIAS = ["Sem evidências anexadas."]
        self.ANALISE_PERGUNTA = "Análise fake da pergunta"
        self.ANALISE_RESPOSTA = "Análise fake da resposta"
        self.NOTA = "3"
        self.JUSTIFICATIVA_NOTA = "Justificativa fake"
        self.OBSERVACAO_NOTA = "Observação fake"
        self.PLANO_DE_ACAO = "1. Ação fake"

    def analise_pergunta(self):
        print("log: analisando pergunta")

    def upload_evidencias(self, temp_dir):
        print("log: upload de evidencias")

    def transcrever_evidencias(self):
        print("log: transcrevendo evidencias")

    def deletar_evidencias(self):
        print("log: deletando evidencias")

    def analisar_evidencias(self):
        print("log: analisando evidencias")

    def analisar_resposta(self):
        print("log: analisando resposta")

    def calcular_nota(self):
        print("log: calculando nota")


class FakeAgentComEvidencias(FakeAgent):
    COM_EVIDENCIAS = True


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_agent(monkeypatch):
    """
    Substitui as dependencias externas do analise_service por fakes.
    Devolve uma funcao que permite trocar a classe de agente usada.
    """
    def _apply(agent_cls=FakeAgent):
        monkeypatch.setattr(analise_mod, "authenticate_apim", lambda: "fake-token")
        monkeypatch.setattr(
            analise_mod, "extrair_evidencias", lambda zip_path: __import__("tempfile").mkdtemp()
        )
        monkeypatch.setattr(analise_mod, "ANALISE_HEALTHCHECK", agent_cls)

    _apply()
    return _apply


def _parse_sse_events(raw_text):
    """Extrai os payloads JSON de um corpo text/event-stream."""
    eventos = []
    for linha in raw_text.splitlines():
        if linha.startswith("data: "):
            eventos.append(json.loads(linha[len("data: "):]))
    return eventos


# ─── /analisar_healthcheck ───────────────────────────────────────────────────────

def test_analisar_healthcheck_success(client, fake_agent):
    resp = client.post("/analisar_healthcheck", files=_files(linhas=2))

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(XLSX_CONTENT_TYPE)

    # NOTA: o service grava a nota como string ("3"), mas pandas.read_excel faz
    # inferencia de tipo por coluna; como todos os valores sao numericos, a
    # coluna retorna como int64. Por isso comparamos via str().
    output_df = pd.read_excel(io.BytesIO(resp.content))
    assert len(output_df) == 2
    assert str(output_df.loc[0, "Nota"]) == "3"
    assert output_df.loc[0, "O que a pergunta avalia"] == "Análise fake da pergunta"
    assert output_df.loc[0, "Analise objetiva da resposta "] == "Análise fake da resposta"


def test_analisar_healthcheck_sem_evidencias_grava_justificativa(client, fake_agent):
    resp = client.post("/analisar_healthcheck", files=_files())

    assert resp.status_code == 200
    output_df = pd.read_excel(io.BytesIO(resp.content))
    coluna = "Analise do texto de justificativa de ausência de evidência"
    assert output_df.loc[0, coluna] == "Sem evidências anexadas."


def test_analisar_healthcheck_com_evidencias_grava_tres_colunas(client, fake_agent):
    fake_agent(FakeAgentComEvidencias)

    resp = client.post("/analisar_healthcheck", files=_files())

    assert resp.status_code == 200
    output_df = pd.read_excel(io.BytesIO(resp.content))
    assert output_df.loc[0, "O que a evidência realmente comprova"] == "comprova X"
    assert output_df.loc[0, "Onde essa evidência é forte"] == "pontos fortes Y"
    assert output_df.loc[0, "Onde essa evidência é fraca para o SH"] == "pontos fracos Z"


def test_analisar_healthcheck_invalid_xlsx_returns_400(client, fake_agent):
    resp = client.post("/analisar_healthcheck", files=_files(formulario_bytes=b"nao-e-xlsx"))

    assert resp.status_code == 400
    assert "Nao foi possivel ler o formulario" in resp.json()["detail"]


def test_analisar_healthcheck_unexpected_error_returns_500(client, monkeypatch):
    monkeypatch.setattr(
        analise_mod,
        "authenticate_apim",
        lambda: (_ for _ in ()).throw(RuntimeError("auth indisponível")),
    )
    monkeypatch.setattr(
        analise_mod, "extrair_evidencias", lambda zip_path: __import__("tempfile").mkdtemp()
    )
    monkeypatch.setattr(analise_mod, "ANALISE_HEALTHCHECK", FakeAgent)

    resp = client.post("/analisar_healthcheck", files=_files())

    assert resp.status_code == 500
    assert "Erro ao analisar o healthcheck" in resp.json()["detail"]


# ─── /analisar_healthcheck_stream ────────────────────────────────────────────────

def test_stream_success_emits_logs_and_final_excel(client, fake_agent):
    resp = client.post("/analisar_healthcheck_stream", files=_files())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    eventos = _parse_sse_events(resp.text)
    evento_final = eventos[-1]
    assert evento_final["status"] == "complete"
    assert isinstance(evento_final["excel"], str)

    # Os prints do FakeAgent devem ter sido capturados e repassados como logs.
    assert any("log" in ev for ev in eventos)


def test_stream_excel_final_e_valido(client, fake_agent):
    fake_agent(FakeAgentComEvidencias)

    resp = client.post("/analisar_healthcheck_stream", files=_files())

    eventos = _parse_sse_events(resp.text)
    evento_final = eventos[-1]
    assert evento_final["status"] == "complete"

    output_df = pd.read_excel(io.BytesIO(base64.b64decode(evento_final["excel"])))
    assert output_df.loc[0, "O que a evidência realmente comprova"] == "comprova X"
    assert output_df.loc[0, "Onde essa evidência é forte"] == "pontos fortes Y"
    assert output_df.loc[0, "Onde essa evidência é fraca para o SH"] == "pontos fracos Z"


def test_stream_invalid_xlsx_emits_error_event(client, fake_agent):
    resp = client.post(
        "/analisar_healthcheck_stream", files=_files(formulario_bytes=b"nao-e-xlsx")
    )

    # O streaming sempre devolve 200: o erro viaja como evento SSE.
    assert resp.status_code == 200
    eventos = _parse_sse_events(resp.text)
    assert any("error" in ev and "Nao foi possivel ler o formulario" in ev["error"] for ev in eventos)


def test_stream_unexpected_error_emits_error_event(client, monkeypatch):
    monkeypatch.setattr(analise_mod, "authenticate_apim", lambda: "fake-token")
    monkeypatch.setattr(
        analise_mod,
        "extrair_evidencias",
        lambda zip_path: (_ for _ in ()).throw(RuntimeError("zip corrompido")),
    )
    monkeypatch.setattr(analise_mod, "ANALISE_HEALTHCHECK", FakeAgent)

    resp = client.post("/analisar_healthcheck_stream", files=_files())

    assert resp.status_code == 200
    eventos = _parse_sse_events(resp.text)
    assert any("error" in ev and "Erro ao processar" in ev["error"] for ev in eventos)


# ─── guardas de erro do endpoint sincrono ────────────────────────────────────────

def test_analisar_healthcheck_sem_dataframe_final_returns_500(client, monkeypatch):
    # Se a orquestracao terminar sem emitir DataFrame (situacao anomala), o
    # endpoint deve falhar explicitamente em vez de devolver corpo vazio.
    import src.controllers.gateway_apim_controller as controller_mod

    monkeypatch.setattr(
        controller_mod, "analisar_formulario", lambda *args, **kwargs: iter(["apenas um log"])
    )

    resp = client.post("/analisar_healthcheck", files=_files())

    assert resp.status_code == 500
    assert resp.json()["detail"] == "A análise não produziu resultado."


def test_analisar_healthcheck_http_exception_nao_e_reetiquetada(client, monkeypatch):
    # Uma HTTPException levantada durante a orquestracao deve preservar status e
    # detalhe originais, sem ser engolida e convertida em 500 genérico.
    import src.controllers.gateway_apim_controller as controller_mod
    from fastapi import HTTPException

    def _explode(*args, **kwargs):
        raise HTTPException(status_code=422, detail="entrada rejeitada a montante")
        yield  # pragma: no cover - torna a funcao um gerador

    monkeypatch.setattr(controller_mod, "analisar_formulario", _explode)

    resp = client.post("/analisar_healthcheck", files=_files())

    assert resp.status_code == 422
    assert resp.json()["detail"] == "entrada rejeitada a montante"


# ─── keepalive do streaming ──────────────────────────────────────────────────────

class FakeAgentLento(FakeAgent):
    def analisar_evidencias(self):
        __import__("time").sleep(0.3)
        super().analisar_evidencias()


def test_stream_envia_keepalive_durante_etapa_longa(client, fake_agent, monkeypatch):
    # Regressao: etapas com mais de 60 s sem log faziam o proxy derrubar a
    # conexao. O stream precisa emitir algo enquanto a etapa roda.
    import src.controllers.gateway_apim_controller as controller_mod

    monkeypatch.setattr(controller_mod, "KEEPALIVE_SEGUNDOS", 0.05)
    fake_agent(FakeAgentLento)

    resp = client.post("/analisar_healthcheck_stream", files=_files())

    assert ": keepalive" in resp.text
    assert resp.headers["x-accel-buffering"] == "no"
    # O comentario nao vira evento: o ultimo evento continua sendo o Excel.
    assert _parse_sse_events(resp.text)[-1]["status"] == "complete"
