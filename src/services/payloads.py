import os
from src.services.prompts import prompts


class payloads():

    def __init__(self):
        pass

    def analise_pergunta(self, text_input):
        payload = {
            "workflow_configuration_code": "WF_HEALTHCHECK_ANALISE_PERGUNTA",
            "input_collection": {
                "input_properties": [
                    {
                        "workflow_step_order": 0,
                        "workflow_step_properties": [
                            {"full_path": "open_ai_api_base", "actual_value": "https://seu-recurso.openai.azure.com/"},
                            {"full_path": "open_ai_api_version", "actual_value": "2024-02-01"},
                            {"full_path": "input_text", "actual_value": text_input},
                            {"full_path": "prompt", "actual_value": prompts().analisar_pergunta},
                            {"full_path": "system_prompt", "actual_value": prompts().sistema},
                            {"full_path": "open_ai_chat_completion_body.model", "actual_value": "deployment-gpt-4o"},
                            {"full_path": "open_ai_chat_completion_body.temperature", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.max_tokens", "actual_value": "1000"},
                            {"full_path": "open_ai_chat_completion_body.top_p", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.frequency_penalty", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.presence_penalty", "actual_value": 0},
                            {"full_path": "base_filter_fields", "actual_value": {}},
                            {"full_path": "categorization_filter_fields", "actual_value": {}},
                        ]
                    }
                ]
            }
        }
        return payload

    def transcrever_evidencias(self, file_id, file_path, container):
        payload = {
            "workflow_configuration_code": "WF_HEALTHCHECK_TRANSCREVER_EVIDENCIAS",
            "input_collection": {
                "input_properties": [
                    {
                        "workflow_step_order": 0,
                        "workflow_step_properties": [
                            {"full_path": "files_id", "actual_value": [file_id]},
                            {"full_path": "files_path", "actual_value": [file_path]},
                            {"full_path": "container", "actual_value": container},
                            {"full_path": "input_text", "actual_value": ""},
                        ]
                    }
                ]
            }
        }
        return payload

    def analisar_evidencias(self, text_input, existem_evidencias, tarefa):
        payload = {
            "workflow_configuration_code": "WF_HEALTHCHECK_ANALISE_EVIDENCIAS",
            "input_collection": {
                "input_properties": [
                    {
                        "workflow_step_order": 0,
                        "workflow_step_properties": [
                            {"full_path": "open_ai_api_base", "actual_value": "https://seu-recurso.openai.azure.com/"},
                            {"full_path": "open_ai_api_version", "actual_value": "2024-02-01"},
                            {"full_path": "input_text", "actual_value": text_input},
                            {"full_path": "prompt", "actual_value": prompts().analisar_evidencias(tarefa) if existem_evidencias else prompts().analisar_ausencia_evidencias},
                            {"full_path": "system_prompt", "actual_value": prompts().sistema},
                            {"full_path": "open_ai_chat_completion_body.model", "actual_value": "deployment-gpt-4o"},
                            {"full_path": "open_ai_chat_completion_body.temperature", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.max_tokens", "actual_value": "1000"},
                            {"full_path": "open_ai_chat_completion_body.top_p", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.frequency_penalty", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.presence_penalty", "actual_value": 0},
                            {"full_path": "base_filter_fields", "actual_value": {}},
                            {"full_path": "categorization_filter_fields", "actual_value": {}},
                        ]
                    }
                ]
            }
        }
        return payload

    def analisar_resposta(self, text_input):
        payload = {
            "workflow_configuration_code": "WF_HEALTHCHECK_ANALISE_RESPOSTA",
            "input_collection": {
                "input_properties": [
                    {
                        "workflow_step_order": 0,
                        "workflow_step_properties": [
                            {"full_path": "open_ai_api_base", "actual_value": "https://seu-recurso.openai.azure.com/"},
                            {"full_path": "open_ai_api_version", "actual_value": "2024-02-01"},
                            {"full_path": "input_text", "actual_value": text_input},
                            {"full_path": "prompt", "actual_value": prompts().analisar_resposta},
                            {"full_path": "system_prompt", "actual_value": prompts().sistema},
                            {"full_path": "open_ai_chat_completion_body.model", "actual_value": "deployment-gpt-4o"},
                            {"full_path": "open_ai_chat_completion_body.temperature", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.max_tokens", "actual_value": "800"},
                            {"full_path": "open_ai_chat_completion_body.top_p", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.frequency_penalty", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.presence_penalty", "actual_value": 0},
                            {"full_path": "base_filter_fields", "actual_value": {}},
                            {"full_path": "categorization_filter_fields", "actual_value": {}},
                        ]
                    }
                ]
            }
        }
        return payload

    def calcular_nota(self, text_input, prompt):
        payload = {
            "workflow_configuration_code": "WF_HEALTHCHECK_CALCULAR_NOTA",
            "input_collection": {
                "input_properties": [
                    {
                        "workflow_step_order": 0,
                        "workflow_step_properties": [
                            {"full_path": "open_ai_api_base", "actual_value": "https://seu-recurso.openai.azure.com/"},
                            {"full_path": "open_ai_api_version", "actual_value": "2024-02-01"},
                            {"full_path": "input_text", "actual_value": text_input},
                            {"full_path": "prompt", "actual_value": prompt},
                            {"full_path": "system_prompt", "actual_value": prompts().sistema},
                            {"full_path": "open_ai_chat_completion_body.model", "actual_value": "deployment-gpt-4o"},
                            {"full_path": "open_ai_chat_completion_body.temperature", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.max_tokens", "actual_value": "2000"},
                            {"full_path": "open_ai_chat_completion_body.top_p", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.frequency_penalty", "actual_value": 0},
                            {"full_path": "open_ai_chat_completion_body.presence_penalty", "actual_value": 0},
                            {"full_path": "base_filter_fields", "actual_value": {}},
                            {"full_path": "categorization_filter_fields", "actual_value": {}},
                        ]
                    }
                ]
            }
        }
        return payload
