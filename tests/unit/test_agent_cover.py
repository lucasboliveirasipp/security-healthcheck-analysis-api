# tests/unit/test_agent_cover.py
import os

import pandas as pd
import pytest

import src.services.agent as agent_mod
from src.services.agent import ANALISE_HEALTHCHECK


def _make_input_data(**overrides):
    """
    Constrói uma pandas.Series simulando uma linha do formulário de healthcheck,
    tal como é consumida em main.py via INPUT.iloc[i].
    """
    base = {
        "Ref": "AC 1.1.1",
        "Pergunta": "Existe uma política de controle de acesso?",
        "Informações da Pergunta e Orientações": "Contexto das orientações.",
        "Resposta": "Em todos os casos",
    }
    base.update(overrides)
    return pd.Series(base)


def _workflow_output(texto):
    """Monta a estrutura de retorno de execute_workflow no formato esperado pelo agent."""
    return {
        "output_collection": {
            "output_datas": [
                {
                    "workflow_step_output_collection": {
                        "output": {"json_data": {"output_text": texto}}
                    }
                }
            ]
        }
    }


@pytest.fixture
def agent():
    return ANALISE_HEALTHCHECK(token_apim="tok-123", input_data=_make_input_data())


# ─── __init__ ────────────────────────────────────────────────────────────────────

def test_init_sets_initial_state(agent):
    assert agent.TOKEN_APIM == "tok-123"
    assert agent.CONTAINER == "healthcheck"
    assert agent.EVIDENCIAS == {}
    assert agent.INPUT["Ref"] == "AC 1.1.1"
    assert agent.OUTPUT["Ref"] == "AC 1.1.1"


# ─── analise_pergunta ────────────────────────────────────────────────────────────

def test_analise_pergunta_success(agent, monkeypatch):
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output("Análise da pergunta X"))

    agent.analise_pergunta()

    assert agent.ANALISE_PERGUNTA == "Análise da pergunta X"


def test_analise_pergunta_error_is_swallowed(agent, monkeypatch, capsys):
    # execute_workflow retorna estrutura incompleta (KeyError esperado internamente).
    # O método captura a exceção via try/except e apenas imprime o erro, não propaga.
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: {})

    agent.analise_pergunta()

    assert not hasattr(agent, "ANALISE_PERGUNTA")
    saida = capsys.readouterr().out
    assert "Falha ao analisar a pergunta" in saida


# ─── upload_evidencias ───────────────────────────────────────────────────────────

def test_upload_evidencias_uploads_allowed_files(agent, monkeypatch, tmp_path):
    referencia_dir = tmp_path / "AC 1.1.1"
    referencia_dir.mkdir()
    (referencia_dir / "norma.pdf").write_bytes(b"conteudo-pequeno")

    chamadas_upload = []

    def _fake_upload_file(file_path, token_apim, container_name, create_container, overwrite):
        chamadas_upload.append(file_path)
        # Formato real do File Manager (confirmado no log do pod em DSV).
        return {"id": "file-1", "path": "healthcheck/norma.pdf"}

    monkeypatch.setattr(agent_mod, "upload_file", _fake_upload_file)

    agent.upload_evidencias(str(tmp_path))

    assert len(chamadas_upload) == 1
    assert agent.EVIDENCIAS == {
        "norma.pdf": {"file_id": "file-1", "file_path": "healthcheck/norma.pdf"}
    }

    # Regressão: o caminho era montado com "\\" literal, que só funciona no
    # Windows — em Linux a barra invertida é caractere de nome de arquivo e o
    # os.listdir falhava com FileNotFoundError. Verificar que o caminho aponta
    # para o arquivo real cobre o bug em qualquer sistema operacional (a
    # separação em si é validada pelo os.path.isfile).
    assert os.path.isfile(chamadas_upload[0])


def test_upload_evidencias_skips_disallowed_extension(agent, monkeypatch, tmp_path):
    referencia_dir = tmp_path / "AC 1.1.1"
    referencia_dir.mkdir()
    (referencia_dir / "malicioso.exe").write_bytes(b"x")

    chamadas_upload = []
    monkeypatch.setattr(agent_mod, "upload_file", lambda **kwargs: chamadas_upload.append(1))

    agent.upload_evidencias(str(tmp_path))

    assert chamadas_upload == []
    assert agent.EVIDENCIAS == {}


@pytest.mark.parametrize("nome", ["politica.docx", "planilha.xlsx", "tela.jpg", "log.txt", "foto.JPEG"])
def test_upload_evidencias_aceita_formatos_pela_extensao(agent, monkeypatch, tmp_path, nome):
    # Regressao: o filtro usava o subtipo MIME (.docx -> "VND.OPENXMLFORMATS-...",
    # .jpg -> "JPEG", .txt -> "PLAIN") e descartava esses arquivos em silencio.
    referencia_dir = tmp_path / "AC 1.1.1"
    referencia_dir.mkdir()
    (referencia_dir / nome).write_bytes(b"conteudo")
    monkeypatch.setattr(
        agent_mod, "upload_file", lambda **kwargs: {"id": "file-1", "path": f"healthcheck/{nome}"}
    )

    agent.upload_evidencias(str(tmp_path))

    assert list(agent.EVIDENCIAS) == [nome]


def test_upload_evidencias_ignora_thumbs_db(agent, monkeypatch, tmp_path):
    referencia_dir = tmp_path / "AC 1.1.1"
    referencia_dir.mkdir()
    (referencia_dir / "Thumbs.db").write_bytes(b"x")
    chamadas_upload = []
    monkeypatch.setattr(agent_mod, "upload_file", lambda **kwargs: chamadas_upload.append(1))

    agent.upload_evidencias(str(tmp_path))

    assert chamadas_upload == []


def test_upload_evidencias_skips_file_over_19mb(agent, monkeypatch, tmp_path):
    referencia_dir = tmp_path / "AC 1.1.1"
    referencia_dir.mkdir()
    arquivo_grande = referencia_dir / "grande.pdf"
    # Escreve ~20MB para ultrapassar o limite de 19MB verificado no código.
    arquivo_grande.write_bytes(b"a" * (20 * 1024 * 1024))

    chamadas_upload = []
    monkeypatch.setattr(agent_mod, "upload_file", lambda **kwargs: chamadas_upload.append(1))

    agent.upload_evidencias(str(tmp_path))

    assert chamadas_upload == []
    assert agent.EVIDENCIAS == {}


def test_upload_evidencias_missing_reference_dir_is_swallowed(agent, monkeypatch, tmp_path, capsys):
    # Não cria a subpasta "AC 1.1.1" dentro de tmp_path -> os.listdir levanta FileNotFoundError,
    # capturado pelo try/except do método (apenas print, não propaga).
    agent.upload_evidencias(str(tmp_path))

    saida = capsys.readouterr().out
    assert "Falha no upload das evidências" in saida


# ─── transcrever_evidencias ──────────────────────────────────────────────────────

def test_transcrever_evidencias_success(agent, monkeypatch):
    agent.EVIDENCIAS = {
        "norma.pdf": {"file_id": "file-1", "file_path": "healthcheck/norma.pdf"},
    }
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output("Texto transcrito"))

    agent.transcrever_evidencias()

    assert agent.TRANSCRICAO_EVIDENCIAS == {"file-1": "Texto transcrito"}


def test_transcrever_evidencias_no_evidencias_results_in_empty_dict(agent, monkeypatch):
    agent.EVIDENCIAS = {}
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output("nao deveria ser chamado"))

    agent.transcrever_evidencias()

    assert agent.TRANSCRICAO_EVIDENCIAS == {}


def test_transcrever_evidencias_error_is_swallowed(agent, monkeypatch, capsys):
    agent.EVIDENCIAS = {"a.pdf": {"file_id": "file-a", "file_path": "healthcheck/a.pdf"}}
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: {})

    agent.transcrever_evidencias()

    assert not hasattr(agent, "TRANSCRICAO_EVIDENCIAS") or agent.TRANSCRICAO_EVIDENCIAS == {}
    saida = capsys.readouterr().out
    assert "Erro na transcrição" in saida


# ─── deletar_evidencias ──────────────────────────────────────────────────────────

def test_deletar_evidencias_calls_delete_for_each_item(agent, monkeypatch):
    agent.EVIDENCIAS = {
        "a.pdf": {"file_id": "file-a", "file_path": "healthcheck/a.pdf"},
        "b.pdf": {"file_id": "file-b", "file_path": "healthcheck/b.pdf"},
    }
    deletados = []
    monkeypatch.setattr(agent_mod, "delete_file", lambda file_id, token_apim: deletados.append(file_id))

    agent.deletar_evidencias()

    assert sorted(deletados) == ["file-a", "file-b"]


def test_deletar_evidencias_error_is_swallowed(agent, monkeypatch, capsys):
    agent.EVIDENCIAS = {"a.pdf": {"file_id": "file-a", "file_path": "x"}}
    monkeypatch.setattr(agent_mod, "delete_file", lambda file_id, token_apim: (_ for _ in ()).throw(RuntimeError("boom")))

    agent.deletar_evidencias()

    saida = capsys.readouterr().out
    assert "Erro ao deletar evidências" in saida


# ─── analisar_evidencias ─────────────────────────────────────────────────────────

def test_analisar_evidencias_sem_evidencias_gera_uma_unica_analise(agent, monkeypatch):
    agent.EVIDENCIAS = {}
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output("Justificativa da ausência"))

    agent.analisar_evidencias()

    assert agent.ANALISE_EVIDENCIAS == ["Justificativa da ausência"]


def test_analisar_evidencias_com_evidencias_gera_tres_analises(agent, monkeypatch):
    agent.EVIDENCIAS = {"a.pdf": {"file_id": "file-a", "file_path": "healthcheck/a.pdf"}}
    agent.TRANSCRICAO_EVIDENCIAS = {"file-a": "conteudo transcrito"}

    respostas = iter(["comprova X", "pontos fortes Y", "pontos fracos Z"])
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output(next(respostas)))

    agent.analisar_evidencias()

    assert agent.ANALISE_EVIDENCIAS == ["comprova X", "pontos fortes Y", "pontos fracos Z"]


# ─── analisar_resposta ───────────────────────────────────────────────────────────

def test_analisar_resposta_com_evidencias(agent, monkeypatch):
    agent.EVIDENCIAS = {"a.pdf": {}}
    agent.ANALISE_EVIDENCIAS = ["comprova X", "pontos fortes Y", "pontos fracos Z"]
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output("Resposta analisada"))

    agent.analisar_resposta()

    assert agent.ANALISE_RESPOSTA == "Resposta analisada"


def test_analisar_resposta_sem_evidencias(agent, monkeypatch):
    agent.EVIDENCIAS = {}
    agent.ANALISE_EVIDENCIAS = ["Justificativa da ausência"]
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output("Resposta analisada sem evidencia"))

    agent.analisar_resposta()

    assert agent.ANALISE_RESPOSTA == "Resposta analisada sem evidencia"


def test_analisar_resposta_error_is_swallowed(agent, monkeypatch, capsys):
    agent.EVIDENCIAS = {}
    agent.ANALISE_EVIDENCIAS = ["Justificativa da ausência"]
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: {})

    agent.analisar_resposta()

    assert not hasattr(agent, "ANALISE_RESPOSTA")
    saida = capsys.readouterr().out
    assert "Erro ao analisar a resposta" in saida


# ─── calcular_nota ───────────────────────────────────────────────────────────────

def test_calcular_nota_success(agent, monkeypatch):
    agent.EVIDENCIAS = {}
    agent.ANALISE_EVIDENCIAS = ["Justificativa da ausência"]
    agent.ANALISE_PERGUNTA = "Análise da pergunta"
    agent.ANALISE_RESPOSTA = "Análise da resposta"

    # calcular_nota faz 5 chamadas sequenciais a execute_workflow:
    # 1) cálculo bruto da nota, 2) nota, 3) justificativa, 4) observação, 5) plano de ação.
    respostas = iter([
        "analise completa da nota",
        "3",
        "justificativa da nota 3",
        "observacao da nota 3",
        "1. Elaborar evidencia complementar",
    ])
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output(next(respostas)))

    agent.calcular_nota()

    assert agent.NOTA == "3"
    assert agent.JUSTIFICATIVA_NOTA == "justificativa da nota 3"
    assert agent.OBSERVACAO_NOTA == "observacao da nota 3"
    assert agent.PLANO_DE_ACAO == "1. Elaborar evidencia complementar"


def test_calcular_nota_success_com_evidencias(agent, monkeypatch):
    # Exercita o ramo "com evidências" do contexto interno de calcular_nota
    # (uso de ANALISE_EVIDENCIAS[0], [1] e [2] em vez do ramo de ausência).
    agent.EVIDENCIAS = {"a.pdf": {"file_id": "file-a", "file_path": "healthcheck/a.pdf"}}
    agent.ANALISE_EVIDENCIAS = ["comprova X", "pontos fortes Y", "pontos fracos Z"]
    agent.ANALISE_PERGUNTA = "Análise da pergunta"
    agent.ANALISE_RESPOSTA = "Análise da resposta"

    respostas = iter([
        "analise completa da nota",
        "4",
        "justificativa da nota 4",
        "observacao da nota 4",
        "Plano de ação não identificado.",
    ])
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: _workflow_output(next(respostas)))

    agent.calcular_nota()

    assert agent.NOTA == "4"
    assert agent.JUSTIFICATIVA_NOTA == "justificativa da nota 4"
    assert agent.OBSERVACAO_NOTA == "observacao da nota 4"
    assert agent.PLANO_DE_ACAO == "Plano de ação não identificado."


def test_calcular_nota_error_is_swallowed(agent, monkeypatch, capsys):
    agent.EVIDENCIAS = {}
    agent.ANALISE_EVIDENCIAS = ["Justificativa da ausência"]
    agent.ANALISE_PERGUNTA = "Análise da pergunta"
    agent.ANALISE_RESPOSTA = "Análise da resposta"

    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: {})

    agent.calcular_nota()

    assert not hasattr(agent, "NOTA")
    saida = capsys.readouterr().out
    assert "Erro no cálculo da nota" in saida


def test_analisar_evidencias_com_evidencias_error_is_swallowed(agent, monkeypatch, capsys):
    # Exercita o except de analisar_evidencias no ramo COM evidências:
    # execute_workflow devolve estrutura incompleta (KeyError interno), que o
    # método captura e apenas reporta via print, sem propagar.
    agent.EVIDENCIAS = {"a.pdf": {"file_id": "file-a", "file_path": "healthcheck/a.pdf"}}
    agent.TRANSCRICAO_EVIDENCIAS = {"file-a": "conteudo transcrito"}
    monkeypatch.setattr(agent_mod, "execute_workflow", lambda payload, token: {})

    agent.analisar_evidencias()

    assert agent.ANALISE_EVIDENCIAS == []
    saida = capsys.readouterr().out
    assert "Erro ao analisar evidencias" in saida
