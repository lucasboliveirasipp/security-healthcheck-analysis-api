# tests/unit/test_prompts_cover.py
import pytest
from src.services.prompts import prompts

# Atributos de instância que devem existir e ser strings não vazias.
# Não validamos o conteúdo literal (texto de negócio/prompt de LLM), pois isso
# tornaria o teste frágil a qualquer ajuste editorial dos prompts. Validamos
# apenas o contrato: atributo existe, é string e não é vazio.
ATRIBUTOS_ESPERADOS = [
    "sistema",
    "analisar_pergunta",
    "analisar_ausencia_evidencias",
    "analisar_resposta",
    "calcular_nota",
    "obter_nota",
    "obter_justificativa",
    "obter_observacao",
    "obter_plano_de_acao",
]


@pytest.mark.parametrize("atributo", ATRIBUTOS_ESPERADOS)
def test_prompt_attribute_is_non_empty_string(atributo):
    p = prompts()
    valor = getattr(p, atributo)
    assert isinstance(valor, str)
    assert valor.strip() != ""


def test_sistema_prompt_menciona_shcv():
    # O prompt de sistema é a base de contexto para todos os workflows; garantimos
    # que ele referencia o framework SHCv, requisito central do agente.
    p = prompts()
    assert "SHCv" in p.sistema


def test_obter_nota_prompt_define_as_cinco_alternativas_de_nota():
    # payloads.py e agent.py dependem de que este prompt restrinja a saída a uma
    # das 5 faixas de nota SHCv (0 a 4). Validamos que as 5 alternativas estão
    # presentes no texto, sem fixar o texto completo.
    p = prompts()
    for alternativa in ["- 4", "- 3", "- 2", "- 1", "- 0"]:
        assert alternativa in p.obter_nota


def test_analisar_evidencias_prompt_incorpora_a_tarefa_recebida():
    p = prompts()
    tarefa = "avalie os pontos fortes das evidências"
    resultado = p.analisar_evidencias(tarefa)

    assert isinstance(resultado, str)
    # O método deve injetar literalmente a tarefa recebida no texto do prompt.
    assert tarefa in resultado


def test_analisar_evidencias_prompt_varia_conforme_a_tarefa():
    p = prompts()
    resultado_1 = p.analisar_evidencias("tarefa A")
    resultado_2 = p.analisar_evidencias("tarefa B")

    # Prompts gerados para tarefas diferentes devem ser textos diferentes,
    # confirmando que o parâmetro realmente influencia a saída.
    assert resultado_1 != resultado_2
