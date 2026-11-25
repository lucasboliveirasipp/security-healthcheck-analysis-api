# tests/unit/test_analise_service_cover.py
#
# Cobre a orquestracao da analise isoladamente, sem HTTP: leitura do
# formulario, normalizacao de colunas, laco por pergunta, limpeza de
# diretorios temporarios e captura de logs.
import io
import os
import zipfile

import pandas as pd
import pytest

import src.services.analise_service as analise_mod
from src.services.analise_service import (
    COLUNAS_ANALISE,
    CapturaLogs,
    FormularioInvalidoError,
    analisar_formulario,
    dataframe_para_xlsx,
    ler_formulario,
    preparar_saida,
)


def _formulario_bytes(linhas=1):
    df = pd.DataFrame(
        [
            {
                "Ref": f"AC 1.1.{i}",
                "Pergunta": "Pergunta de teste",
                "Informações da Pergunta e Orientações": "Contexto",
                "Resposta": "Em todos os casos",
            }
            for i in range(1, linhas + 1)
        ]
    )
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer.read()


def _evidencias_zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("AC 1.1.1/.keep", "")
    buffer.seek(0)
    return buffer.read()


class FakeAgent:
    COM_EVIDENCIAS = False

    def __init__(self, token_apim, input_data):
        self.token_apim = token_apim
        self.input_data = input_data
        if self.COM_EVIDENCIAS:
            self.EVIDENCIAS = {"norma.pdf": {"file_id": "f1", "file_path": "healthcheck/norma.pdf"}}
            self.ANALISE_EVIDENCIAS = ["comprova X", "fortes Y", "fracos Z"]
        else:
            self.EVIDENCIAS = {}
            self.ANALISE_EVIDENCIAS = ["Sem evidências."]
        self.ANALISE_PERGUNTA = "pergunta analisada"
        self.ANALISE_RESPOSTA = "resposta analisada"
        self.NOTA = "3"
        self.JUSTIFICATIVA_NOTA = "justificativa"
        self.OBSERVACAO_NOTA = "observacao"
        self.PLANO_DE_ACAO = "plano"

    def analise_pergunta(self):
        print("etapa: pergunta")

    def upload_evidencias(self, temp_dir):
        print("etapa: upload")

    def transcrever_evidencias(self):
        print("etapa: transcricao")

    def deletar_evidencias(self):
        print("etapa: delete")

    def analisar_evidencias(self):
        print("etapa: evidencias")

    def analisar_resposta(self):
        print("etapa: resposta")

    def calcular_nota(self):
        print("etapa: nota")


class FakeAgentComEvidencias(FakeAgent):
    COM_EVIDENCIAS = True


@pytest.fixture
def deps(monkeypatch):
    """Substitui autenticacao, extracao de zip e agente por fakes."""
    criados = []

    def _extrair(zip_path):
        import tempfile
        d = tempfile.mkdtemp()
        criados.append(d)
        return d

    def _apply(agent_cls=FakeAgent):
        monkeypatch.setattr(analise_mod, "authenticate_apim", lambda: "fake-token")
        monkeypatch.setattr(analise_mod, "extrair_evidencias", _extrair)
        monkeypatch.setattr(analise_mod, "ANALISE_HEALTHCHECK", agent_cls)
        return criados

    _apply()
    return _apply


def _consumir(gerador):
    """Separa os logs (str) do DataFrame final produzido pelo gerador."""
    logs, saida = [], None
    for item in gerador:
        if isinstance(item, pd.DataFrame):
            saida = item
        else:
            logs.append(item)
    return logs, saida


# ─── ler_formulario ─────────────────────────────────────────────────────────────

def test_ler_formulario_success():
    df = ler_formulario(_formulario_bytes(linhas=3))
    assert len(df) == 3
    assert list(df.columns)[:2] == ["Ref", "Pergunta"]


def test_ler_formulario_invalido_levanta_erro_especifico():
    with pytest.raises(FormularioInvalidoError) as exc:
        ler_formulario(b"nao-e-um-xlsx")
    assert "Nao foi possivel ler o formulario" in str(exc.value)


# ─── preparar_saida ─────────────────────────────────────────────────────────────

def test_preparar_saida_cria_todas_as_colunas_de_analise():
    entrada = ler_formulario(_formulario_bytes())
    saida = preparar_saida(entrada)

    for coluna in COLUNAS_ANALISE:
        assert coluna in saida.columns


def test_preparar_saida_nao_altera_o_dataframe_de_entrada():
    entrada = ler_formulario(_formulario_bytes())
    colunas_originais = list(entrada.columns)

    preparar_saida(entrada)

    assert list(entrada.columns) == colunas_originais


def test_preparar_saida_converte_coluna_existente_para_str():
    entrada = ler_formulario(_formulario_bytes())
    entrada["Nota"] = 5

    saida = preparar_saida(entrada)

    # Validamos o conteúdo, não o dtype: pandas 2.x usa `object` para strings,
    # enquanto pandas 3.x introduz o dtype dedicado `str`. Comparar com um
    # dtype específico acoplaria o teste à versão da lib.
    assert saida.loc[0, "Nota"] == "5"
    assert isinstance(saida.loc[0, "Nota"], str)


# ─── dataframe_para_xlsx ────────────────────────────────────────────────────────

def test_dataframe_para_xlsx_gera_buffer_relegivel():
    df = pd.DataFrame([{"a": 1, "b": "x"}])
    buffer = dataframe_para_xlsx(df)

    assert buffer.tell() == 0
    relido = pd.read_excel(buffer)
    assert relido.loc[0, "a"] == 1
    assert relido.loc[0, "b"] == "x"


# ─── analisar_formulario ────────────────────────────────────────────────────────

def test_analisar_formulario_preenche_todas_as_linhas(deps):
    logs, saida = _consumir(analisar_formulario(_formulario_bytes(linhas=3), _evidencias_zip_bytes()))

    assert saida is not None
    assert len(saida) == 3
    assert logs == []  # sem on_progress, nenhum log e emitido
    for linha in range(3):
        assert saida.loc[linha, "O que a pergunta avalia"] == "pergunta analisada"
        assert saida.loc[linha, "Nota"] == "3"
        assert saida.loc[linha, "Dica"] == "plano"


def test_analisar_formulario_sem_evidencias_usa_coluna_de_justificativa(deps):
    _, saida = _consumir(analisar_formulario(_formulario_bytes(), _evidencias_zip_bytes()))

    coluna = "Analise do texto de justificativa de ausência de evidência"
    assert saida.loc[0, coluna] == "Sem evidências."
    assert saida.loc[0, "O que a evidência realmente comprova"] == ""


def test_analisar_formulario_com_evidencias_usa_as_tres_colunas(deps):
    deps(FakeAgentComEvidencias)

    _, saida = _consumir(analisar_formulario(_formulario_bytes(), _evidencias_zip_bytes()))

    assert saida.loc[0, "O que a evidência realmente comprova"] == "comprova X"
    assert saida.loc[0, "Onde essa evidência é forte"] == "fortes Y"
    assert saida.loc[0, "Onde essa evidência é fraca para o SH"] == "fracos Z"


def test_analisar_formulario_formulario_invalido_propaga_erro(deps):
    with pytest.raises(FormularioInvalidoError):
        _consumir(analisar_formulario(b"nao-e-xlsx", _evidencias_zip_bytes()))


def test_analisar_formulario_emite_logs_quando_on_progress_fornecido(deps):
    captura = CapturaLogs()

    with captura:
        logs, saida = _consumir(
            analisar_formulario(
                _formulario_bytes(),
                _evidencias_zip_bytes(),
                on_progress=captura.drenar,
            )
        )

    assert saida is not None
    assert any("etapa: pergunta" in log for log in logs)
    assert any("etapa: nota" in log for log in logs)


def test_analisar_formulario_limpa_diretorios_temporarios(deps):
    criados = deps()

    _consumir(analisar_formulario(_formulario_bytes(), _evidencias_zip_bytes()))

    assert criados, "extrair_evidencias deveria ter sido chamado"
    for d in criados:
        assert not os.path.isdir(d), f"diretorio temporario nao removido: {d}"


def test_analisar_formulario_limpa_temporarios_mesmo_com_erro(deps, monkeypatch):
    criados = deps()
    monkeypatch.setattr(
        analise_mod,
        "authenticate_apim",
        lambda: (_ for _ in ()).throw(RuntimeError("auth falhou")),
    )

    with pytest.raises(RuntimeError):
        _consumir(analisar_formulario(_formulario_bytes(), _evidencias_zip_bytes()))

    for d in criados:
        assert not os.path.isdir(d)


# ─── CapturaLogs ────────────────────────────────────────────────────────────────

def test_captura_logs_coleta_prints_e_restaura_stdout():
    import sys

    stdout_antes = sys.stdout
    with CapturaLogs() as captura:
        print("mensagem um")
        print("mensagem dois")
        coletadas = list(captura.drenar())

    assert sys.stdout is stdout_antes
    assert coletadas == ["mensagem um", "mensagem dois"]


def test_captura_logs_ignora_linhas_em_branco():
    with CapturaLogs() as captura:
        print("")
        print("   ")
        print("conteudo")
        coletadas = list(captura.drenar())

    assert coletadas == ["conteudo"]


def test_captura_logs_drenar_limpa_o_buffer():
    with CapturaLogs() as captura:
        print("primeira")
        primeira = list(captura.drenar())
        segunda = list(captura.drenar())

    assert primeira == ["primeira"]
    assert segunda == []


def test_captura_logs_restaura_stdout_mesmo_com_excecao():
    import sys

    stdout_antes = sys.stdout
    with pytest.raises(ValueError):
        with CapturaLogs():
            raise ValueError("falha no meio do bloco")

    assert sys.stdout is stdout_antes


def test_captura_logs_flush_nao_levanta():
    with CapturaLogs() as captura:
        captura.flush()


def test_captura_logs_write_e_flush_sem_stdout_original():
    # write() e flush() protegem contra _stdout_original None (instância usada
    # fora do bloco `with`). Cobre o ramo negativo desses dois guards.
    captura = CapturaLogs()

    captura.write("mensagem fora do contexto")
    captura.flush()

    assert list(captura.drenar()) == ["mensagem fora do contexto"]
