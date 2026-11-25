"""
Orquestracao da analise de healthcheck.

Concentra a leitura do formulario, o laco de analise por pergunta e a
montagem da planilha de saida. Os endpoints (controllers) apenas adaptam
esse fluxo para o formato de resposta HTTP desejado (arquivo ou SSE).
"""
import io
import os
import shutil
import sys
import tempfile
from typing import Callable, Iterator, Optional

import pandas as pd

from src.services.agent import ANALISE_HEALTHCHECK
from src.services.utils import authenticate_apim, extrair_evidencias

# Colunas preenchidas pela analise. Sao criadas vazias quando ausentes no
# formulario de entrada, garantindo que a planilha de saida tenha o mesmo
# formato independente do arquivo recebido.
COLUNAS_ANALISE = [
    "O que a pergunta avalia",
    "O que a evidência realmente comprova",
    "Onde essa evidência é forte",
    "Onde essa evidência é fraca para o SH",
    "Analise do texto de justificativa de ausência de evidência",
    "Analise objetiva da resposta ",
    "Nota",
    "justificativa da nota",
    "Obs.:",
    "Dica",
]


class FormularioInvalidoError(Exception):
    """Formulario .xlsx ausente, corrompido ou em formato nao suportado."""


def ler_formulario(formulario_bytes: bytes) -> pd.DataFrame:
    """Le os bytes de um .xlsx e devolve o DataFrame de entrada."""
    try:
        return pd.read_excel(io.BytesIO(formulario_bytes))
    except Exception as e:
        raise FormularioInvalidoError(f"Nao foi possivel ler o formulario .xlsx: {e}") from e


def preparar_saida(entrada: pd.DataFrame) -> pd.DataFrame:
    """Copia o formulario de entrada e normaliza as colunas de analise."""
    saida = entrada.copy()
    for coluna in COLUNAS_ANALISE:
        saida[coluna] = saida[coluna].astype(str) if coluna in saida.columns else ""
    return saida


def dataframe_para_xlsx(df: pd.DataFrame) -> io.BytesIO:
    """Serializa o DataFrame em um buffer .xlsx posicionado no inicio."""
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer


def _registrar_evidencias(saida: pd.DataFrame, linha: int, agent) -> None:
    """Grava o resultado da analise de evidencias na linha correspondente."""
    if agent.EVIDENCIAS == {}:
        saida.loc[linha, "Analise do texto de justificativa de ausência de evidência"] = agent.ANALISE_EVIDENCIAS[0]
    else:
        saida.loc[linha, "O que a evidência realmente comprova"] = agent.ANALISE_EVIDENCIAS[0]
        saida.loc[linha, "Onde essa evidência é forte"] = agent.ANALISE_EVIDENCIAS[1]
        saida.loc[linha, "Onde essa evidência é fraca para o SH"] = agent.ANALISE_EVIDENCIAS[2]


def analisar_formulario(
    formulario_bytes: bytes,
    evidencias_bytes: bytes,
    on_progress: Optional[Callable[[], Iterator[str]]] = None,
) -> Iterator[object]:
    """
    Executa a analise completa do formulario.

    Gera, em ordem: zero ou mais str (mensagens de log, quando on_progress
    e fornecido) e, por ultimo, o DataFrame de saida. Quem consome decide
    se repassa os logs (streaming) ou apenas aguarda o resultado final.

    on_progress e chamado depois de cada etapa do agente e deve devolver as
    mensagens de log acumuladas ate o momento.
    """
    entrada = ler_formulario(formulario_bytes)
    saida = preparar_saida(entrada)

    temp_root = tempfile.mkdtemp()
    temp_dir_evidencias = None

    try:
        zip_path = os.path.join(temp_root, "evidencias.zip")
        with open(zip_path, "wb") as f:
            f.write(evidencias_bytes)

        temp_dir_evidencias = extrair_evidencias(zip_path)
        token_apim = authenticate_apim()

        def _logs():
            if on_progress is None:
                return iter(())
            return on_progress()

        for linha in range(entrada.shape[0]):
            agent = ANALISE_HEALTHCHECK(token_apim=token_apim, input_data=entrada.iloc[linha])

            agent.analise_pergunta()
            yield from _logs()
            saida.loc[linha, "O que a pergunta avalia"] = agent.ANALISE_PERGUNTA

            agent.upload_evidencias(temp_dir_evidencias)
            agent.transcrever_evidencias()
            agent.deletar_evidencias()
            agent.analisar_evidencias()
            yield from _logs()
            _registrar_evidencias(saida, linha, agent)

            agent.analisar_resposta()
            yield from _logs()
            saida.loc[linha, "Analise objetiva da resposta "] = agent.ANALISE_RESPOSTA

            agent.calcular_nota()
            yield from _logs()
            saida.loc[linha, "Nota"] = agent.NOTA
            saida.loc[linha, "justificativa da nota"] = agent.JUSTIFICATIVA_NOTA
            saida.loc[linha, "Obs.:"] = agent.OBSERVACAO_NOTA
            saida.loc[linha, "Dica"] = agent.PLANO_DE_ACAO

        yield saida
    finally:
        if temp_dir_evidencias and os.path.isdir(temp_dir_evidencias):
            shutil.rmtree(temp_dir_evidencias, ignore_errors=True)
        shutil.rmtree(temp_root, ignore_errors=True)


class CapturaLogs:
    """
    Redireciona sys.stdout para coletar os prints emitidos pelo agente,
    preservando a escrita no stdout original.

    O agente reporta progresso via print(); este utilitario permite expor
    essas mensagens no streaming SSE sem alterar o agente.
    """

    def __init__(self):
        self._mensagens: list[str] = []
        self._stdout_original = None

    def __enter__(self):
        self._stdout_original = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.stdout = self._stdout_original
        return False

    def write(self, message):
        if message.strip():
            self._mensagens.append(message.strip())
        if self._stdout_original is not None:
            self._stdout_original.write(message)

    def flush(self):
        if self._stdout_original is not None:
            self._stdout_original.flush()

    def drenar(self) -> Iterator[str]:
        """Devolve as mensagens acumuladas e limpa o buffer."""
        pendentes = list(self._mensagens)
        self._mensagens.clear()
        return iter(pendentes)
