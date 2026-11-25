from src.services.payloads import payloads
from src.services.utils import (
    authenticate_apim, execute_workflow, upload_file, delete_file
)
import os
from pathlib import Path


class ANALISE_HEALTHCHECK():

    def __init__(self, token_apim, input_data):
        print("# ======================================== #")
        print(f"# INICIANDO A ANÁLISE DA PERGUNTA {input_data['Ref']} #")
        print("# ======================================== #")

        self.TOKEN_APIM = token_apim
        self.CONTAINER = "healthcheck"
        self.EVIDENCIAS = {}
        self.INPUT = input_data
        self.OUTPUT = self.INPUT.copy()

    def analise_pergunta(self):
        print(" - Iniciando a análise da pergunta")
        try:
            contexto = f"""
# Pergunta
{self.INPUT["Ref"]} - {self.INPUT["Pergunta"]}

# Informações de contexto
{self.INPUT["Informações da Pergunta e Orientações"]}
"""
            workflow_status = execute_workflow(
                payloads().analise_pergunta(contexto),
                self.TOKEN_APIM,
            )
            self.ANALISE_PERGUNTA = workflow_status["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]
            print("    - Pergunta analisada com sucesso.")
        except Exception as error:
            print("    - Falha ao analisar a pergunta:", error)

    def upload_evidencias(self, dir_evidencias):
        print(" - Fazendo upload de evidências no file manager")
        try:
            referencia = self.INPUT["Ref"]
            formatos_permitidos = ["PDF", "TXT", "CSV", "XLS", "XLSX", "DOC", "DOCX", "MD", "PPT", "PPTX", "JSON", "HTML", "XML", "YAML", "YML", "JPG", "JPEG", "PNG", "TIF", "TIFF", "BMP", "MP3", "WAV", "MP4", "FLAC", "OGG"]

            self.EVIDENCIAS = dict()
            # Path/os.path.join resolvem o separador conforme o sistema. Montar
            # o caminho com "\\" literal quebra em Linux, onde a barra invertida
            # e um caractere valido de nome de arquivo e nao um separador.
            dir_referencia = Path(dir_evidencias) / referencia
            lista_evidencias = os.listdir(dir_referencia)
            print(f"    - Foram identificadas {len(lista_evidencias)} evidencias.")

            for evidencia in lista_evidencias:
                print("       - Analisando o arquivo", evidencia)
                caminho_evidencia = str(dir_referencia / evidencia)
                condicao_tamanho = (Path(caminho_evidencia).stat().st_size / (1024 ** 2)) <= 19
                # O formato e decidido pela extensao do arquivo. O subtipo MIME
                # nao serve: .docx vira "VND.OPENXMLFORMATS-...", .jpg vira
                # "JPEG", .txt vira "PLAIN", e esses arquivos eram descartados.
                extensao = Path(evidencia).suffix.lstrip(".").upper()
                condicao_formato = extensao in formatos_permitidos

                if condicao_formato and condicao_tamanho:
                    UPLOAD_RESULT = upload_file(
                        file_path=caminho_evidencia,
                        token_apim=self.TOKEN_APIM,
                        container_name=self.CONTAINER,
                        create_container=True,
                        overwrite=True,
                    )
                    self.EVIDENCIAS[evidencia] = {
                        "file_id": UPLOAD_RESULT["id"],
                        "file_path": UPLOAD_RESULT["path"],
                    }
                    print("       - Upload concluído.")
                else:
                    print("       - O arquivo possui mais de 20Mb ou não pertence aos formatos aceitos.")
        except Exception as error:
            print(" - Falha no upload das evidências:", error)

    def transcrever_evidencias(self):
        print(" - Iniciando transcrição das evidências.")
        try:
            files_id = [self.EVIDENCIAS[e]["file_id"] for e in self.EVIDENCIAS]
            files_path = [self.EVIDENCIAS[e]["file_path"] for e in self.EVIDENCIAS]

            self.TRANSCRICAO_EVIDENCIAS = dict()
            for n in range(len(files_id)):
                print("    - Transcrevendo", files_path[n].split("/")[-1])
                workflow_status = execute_workflow(
                    payloads().transcrever_evidencias(files_id[n], files_path[n], self.CONTAINER),
                    self.TOKEN_APIM,
                )
                self.TRANSCRICAO_EVIDENCIAS[files_id[n]] = workflow_status["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]
                print("       - Transcrição concluída.")
        except Exception as erro:
            print("       - Erro na transcrição:", erro)

    def deletar_evidencias(self):
        try:
            print(" - Deletando evidências.")
            for evidencia in self.EVIDENCIAS.keys():
                delete_file(file_id=self.EVIDENCIAS[evidencia]["file_id"], token_apim=self.TOKEN_APIM)
            print("    - Evidências deletadas com sucesso.")
        except Exception as erro:
            print("    - Erro ao deletar evidências:", erro)

    def analisar_evidencias(self):
        self.ANALISE_EVIDENCIAS = list()
        tarefas = [
            "faça uma análise das evidências e explique o que cada arquivo realmente comprova (item por item)",
            "avalie os pontos fortes das evidências e aponte onde os arquivos são sólidos e como se conectam com a pergunta e a resposta fornecida (atenção: neste momento **não avalie os pontos fracos das evidências**)",
            "avalie os pontos fracos das evidências e aponte lacunas identificadas ou arquivos que não fazem sentido com a pergunta e a resposta fornecida (atenção: neste momento **não avalie os pontos fortes das evidências**)",
        ]
        try:
            contexto = f"""
# Pergunta
{self.INPUT["Ref"]} - {self.INPUT["Pergunta"]}

# Informações de contexto
{self.INPUT["Informações da Pergunta e Orientações"]}

# Resposta do responsável
{self.INPUT["Resposta"]}
"""
            if self.EVIDENCIAS == {}:
                print(" - Analisando justificativa para ausência de evidências.")
                workflow_status = execute_workflow(
                    payloads().analisar_evidencias(contexto, False, ""),
                    self.TOKEN_APIM,
                )
                self.ANALISE_EVIDENCIAS.append(workflow_status["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"])
            else:
                print(" - Iniciando análise das evidências.")
                contexto += "\n# Evidências em anexo\n"
                for n, evidencia in enumerate(self.TRANSCRICAO_EVIDENCIAS.keys()):
                    contexto += f"\n## Evidência {n+1}\n{self.TRANSCRICAO_EVIDENCIAS[evidencia]}\n"

                for tarefa in tarefas:
                    workflow_status = execute_workflow(
                        payloads().analisar_evidencias(contexto, True, tarefa),
                        self.TOKEN_APIM,
                    )
                    self.ANALISE_EVIDENCIAS.append(workflow_status["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"])

            print("    - Análise concluída.")
        except Exception as erro:
            print("    - Erro ao analisar evidencias:", erro)

    def analisar_resposta(self):
        try:
            print(" - Iniciando análise da resposta.")
            contexto = f"""
# Pergunta
{self.INPUT["Ref"]} - {self.INPUT["Pergunta"]}

# Informações de contexto
{self.INPUT["Informações da Pergunta e Orientações"]}

# Resposta do responsável
{self.INPUT["Resposta"]}

# Análise das evidências em anexo
"""
            if self.EVIDENCIAS == {}:
                contexto += f"\n## Análise da ausência de evidências\n{self.ANALISE_EVIDENCIAS[0]}\n"
            else:
                contexto += f"\n## O que as evidências realmente comprovam?\n{self.ANALISE_EVIDENCIAS[0]}\n\n## Pontos fortes\n{self.ANALISE_EVIDENCIAS[1]}\n\n## Pontos fracos\n{self.ANALISE_EVIDENCIAS[2]}\n"

            workflow_status = execute_workflow(
                payloads().analisar_resposta(contexto),
                self.TOKEN_APIM,
            )
            self.ANALISE_RESPOSTA = workflow_status["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]
            print("    - Análise concluída.")
        except Exception as erro:
            print("    - Erro ao analisar a resposta:", erro)

    def calcular_nota(self):
        from src.services.prompts import prompts as _prompts
        try:
            contexto = f"""
# Pergunta
{self.INPUT["Ref"]} - {self.INPUT["Pergunta"]}

# Informações de contexto
{self.INPUT["Informações da Pergunta e Orientações"]}

# Análise da pergunta
{self.ANALISE_PERGUNTA}

# Resposta do responsável
{self.INPUT["Resposta"]}

# Análise da resposta
{self.ANALISE_RESPOSTA}

# Análise das evidências em anexo
"""
            if self.EVIDENCIAS == {}:
                contexto += f"\n## Análise da ausência de evidências\n{self.ANALISE_EVIDENCIAS[0]}\n"
            else:
                contexto += f"\n## O que as evidências realmente comprovam?\n{self.ANALISE_EVIDENCIAS[0]}\n\n## Pontos fortes\n{self.ANALISE_EVIDENCIAS[1]}\n\n## Pontos fracos\n{self.ANALISE_EVIDENCIAS[2]}\n"

            p = _prompts()

            print(" - Iniciando cálculo da nota.")
            wf = execute_workflow(payloads().calcular_nota(contexto, p.calcular_nota), self.TOKEN_APIM)
            CALCULAR_NOTA = wf["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]

            print("    - Obtendo nota.")
            wf = execute_workflow(payloads().calcular_nota(CALCULAR_NOTA, p.obter_nota), self.TOKEN_APIM)
            self.NOTA = wf["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]

            print("    - Obtendo justificativa da nota.")
            wf = execute_workflow(payloads().calcular_nota(CALCULAR_NOTA, p.obter_justificativa), self.TOKEN_APIM)
            self.JUSTIFICATIVA_NOTA = wf["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]

            print("    - Obtendo observação da nota.")
            wf = execute_workflow(payloads().calcular_nota(CALCULAR_NOTA, p.obter_observacao), self.TOKEN_APIM)
            self.OBSERVACAO_NOTA = wf["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]

            print("    - Obtendo planos de melhoria.")
            wf = execute_workflow(payloads().calcular_nota(CALCULAR_NOTA, p.obter_plano_de_acao), self.TOKEN_APIM)
            self.PLANO_DE_ACAO = wf["output_collection"]["output_datas"][0]["workflow_step_output_collection"]["output"]["json_data"]["output_text"]

        except Exception as erro:
            print(" - Erro no cálculo da nota:", erro)
