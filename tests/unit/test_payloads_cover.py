# tests/unit/test_payloads_cover.py
from src.services.payloads import payloads
from src.services.prompts import prompts


def _props_as_dict(payload):
    """
    Helper que converte a lista de workflow_step_properties em um dict
    {full_path: actual_value}, facilitando as asserções sem depender da
    ordem dos campos no payload.
    """
    props = payload["input_collection"]["input_properties"][0]["workflow_step_properties"]
    return {p["full_path"]: p["actual_value"] for p in props}


# ─── analise_pergunta ───────────────────────────────────────────────────────────

def test_analise_pergunta_payload_structure():
    payload = payloads().analise_pergunta("contexto da pergunta")
    assert payload["workflow_configuration_code"] == "WF_HEALTHCHECK_ANALISE_PERGUNTA"

    props = _props_as_dict(payload)
    assert props["input_text"] == "contexto da pergunta"
    assert props["prompt"] == prompts().analisar_pergunta
    assert props["system_prompt"] == prompts().sistema
    assert props["open_ai_chat_completion_body.model"] == "deployment-gpt-4o"
    assert props["open_ai_chat_completion_body.max_tokens"] == "1000"


# ─── transcrever_evidencias ─────────────────────────────────────────────────────

def test_transcrever_evidencias_payload_structure():
    payload = payloads().transcrever_evidencias("file-1", "container/arquivo.pdf", "healthcheck")
    assert payload["workflow_configuration_code"] == "WF_HEALTHCHECK_TRANSCREVER_EVIDENCIAS"

    props = _props_as_dict(payload)
    # files_id e files_path são sempre listas com um único elemento nesta implementação
    assert props["files_id"] == ["file-1"]
    assert props["files_path"] == ["container/arquivo.pdf"]
    assert props["container"] == "healthcheck"
    assert props["input_text"] == ""


# ─── analisar_evidencias ────────────────────────────────────────────────────────

def test_analisar_evidencias_payload_com_evidencias_usa_prompt_por_tarefa():
    tarefa = "avalie os pontos fortes"
    payload = payloads().analisar_evidencias("contexto", True, tarefa)
    assert payload["workflow_configuration_code"] == "WF_HEALTHCHECK_ANALISE_EVIDENCIAS"

    props = _props_as_dict(payload)
    assert props["input_text"] == "contexto"
    # Quando existem_evidencias=True, o prompt deve ser o template parametrizado por tarefa
    assert props["prompt"] == prompts().analisar_evidencias(tarefa)


def test_analisar_evidencias_payload_sem_evidencias_usa_prompt_de_ausencia():
    payload = payloads().analisar_evidencias("contexto", False, "")
    props = _props_as_dict(payload)
    # Quando existem_evidencias=False, o prompt deve ser o de justificativa de ausência
    assert props["prompt"] == prompts().analisar_ausencia_evidencias


# ─── analisar_resposta ──────────────────────────────────────────────────────────

def test_analisar_resposta_payload_structure():
    payload = payloads().analisar_resposta("contexto da resposta")
    assert payload["workflow_configuration_code"] == "WF_HEALTHCHECK_ANALISE_RESPOSTA"

    props = _props_as_dict(payload)
    assert props["input_text"] == "contexto da resposta"
    assert props["prompt"] == prompts().analisar_resposta
    assert props["open_ai_chat_completion_body.max_tokens"] == "800"


# ─── calcular_nota ──────────────────────────────────────────────────────────────

def test_calcular_nota_payload_structure():
    p = prompts()
    payload = payloads().calcular_nota("contexto completo", p.obter_nota)
    assert payload["workflow_configuration_code"] == "WF_HEALTHCHECK_CALCULAR_NOTA"

    props = _props_as_dict(payload)
    assert props["input_text"] == "contexto completo"
    # calcular_nota recebe o prompt como parâmetro explícito (diferente dos demais métodos)
    assert props["prompt"] == p.obter_nota
    assert props["open_ai_chat_completion_body.max_tokens"] == "2000"
