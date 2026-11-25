from pathlib import Path
import mimetypes
import requests
import os
import tempfile
import time
import zipfile


def ssl_verify():
    """
    Resolve o parametro `verify` das chamadas HTTP.

    Ordem de precedencia:
      1. Caminho de CA bundle informado em PATH_ROOT_CA ou REQUESTS_CA_BUNDLE,
         quando o arquivo existir (cenario de container com CA corporativa).
      2. SSL_VERIFY=false para desabilitar a validacao — uso restrito a
         desenvolvimento local, onde a CA corporativa nao esta instalada.
      3. True (padrao): validacao de certificado habilitada.

    O padrao seguro evita expor as chamadas a ataques man-in-the-middle;
    a desativacao exige opt-in explicito por variavel de ambiente.
    """
    for var in ("PATH_ROOT_CA", "REQUESTS_CA_BUNDLE"):
        ca_bundle = os.getenv(var)
        if ca_bundle and os.path.isfile(ca_bundle):
            return ca_bundle

    return os.getenv("SSL_VERIFY", "true").strip().lower() not in ("false", "0", "no")


def authenticate_apim():
    TENANT_ID = os.getenv("TENANTID")
    CLIENT_ID = os.getenv("GATEWAYAPPID")
    SCOPE = os.getenv("GATEWAYAPPIDURI")
    SECRET = os.getenv("GATEWAYCLIENTSECRET")

    # O scope precisa terminar em /.default. O valor injetado pelo Key Vault
    # costuma trazer apenas o prefixo (api://...), mas a checagem evita
    # duplicar o sufixo caso ele ja venha embutido.
    if SCOPE and not SCOPE.endswith("/.default"):
        SCOPE = f"{SCOPE}/.default"

    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": SECRET,
        "scope": SCOPE,
    }

    auth = requests.post(token_url, data=token_data, timeout=120, verify=ssl_verify())
    return auth.json().get("access_token")


def startworkflow(payload, token_apim):
    url = os.getenv("WORKFLOW_URL")
    headers = {
        "Authorization": f"Bearer {token_apim}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=120, verify=ssl_verify())
    response.raise_for_status()
    return response.json()


def get_workflow_status(workflow_execution_id, token_apim):
    headers = {"Authorization": f"Bearer {token_apim}"}
    base_url = os.getenv("WORKFLOW_STATUS_URL")
    url = f"{base_url}/{workflow_execution_id}"
    response = requests.get(url, headers=headers, timeout=120, verify=ssl_verify())
    response.raise_for_status()
    return response.json()


class WorkflowError(Exception):
    """Workflow da Gateway terminou em erro ou nao terminou dentro do prazo."""


# Status em que a Gateway ainda esta processando. Qualquer outro status que nao
# seja WF_COMPLETED_SUCCESS e tratado como terminal com erro, para o laco nunca
# ficar preso num status desconhecido.
STATUS_EM_ANDAMENTO = {"WF_INITIATED", "WF_PENDING", "WF_RUNNING", "WF_IN_PROGRESS"}


def execute_workflow(payload, token_apim):
    workflow_execution_id = startworkflow(payload, token_apim)["workflow_execution_id"]
    intervalo = float(os.getenv("WORKFLOW_POLL_INTERVAL", "2"))
    prazo = time.monotonic() + float(os.getenv("WORKFLOW_TIMEOUT", "300"))

    while True:
        workflow_status = get_workflow_status(workflow_execution_id, token_apim)
        status = workflow_status.get("status")
        if status == "WF_COMPLETED_SUCCESS":
            return workflow_status
        if status not in STATUS_EM_ANDAMENTO:
            raise WorkflowError(
                f"Workflow {workflow_execution_id} terminou com {status}: "
                f"{workflow_status.get('error') or workflow_status.get('message')}"
            )
        if time.monotonic() >= prazo:
            raise WorkflowError(f"Workflow {workflow_execution_id} excedeu o tempo limite em {status}.")
        time.sleep(intervalo)


def _flag(valor, env_var, default="true"):
    """
    Normaliza uma flag booleana para a string "true"/"false" esperada pela API.

    Aceita bool ou str vindos do chamador; quando `valor` e None, cai na
    variavel de ambiente correspondente.
    """
    if valor is None:
        valor = os.getenv(env_var, default)
    if isinstance(valor, str):
        valor = valor.strip().lower() not in ("false", "0", "no")
    return str(bool(valor)).lower()


def upload_file(file_path, token_apim, container_name=None, create_container=None, overwrite=None):
    try:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        if not token_apim:
            raise ValueError("Token APIM não informado.")

        # Os argumentos do chamador tem precedencia; as variaveis de ambiente
        # sao apenas o default quando nada e informado.
        container = container_name or os.getenv("CONTAINER_NAME")

        url = os.getenv("UPLOAD_FILE_URL")
        data = {
            "container_name": container,
            "create_container": _flag(create_container, "CREATE_CONTAINER"),
            "overwrite": _flag(overwrite, "OVERWRITE_FILE"),
            "connection_mode": "APIM",
        }
        headers = {"Authorization": f"Bearer {token_apim}", "Accept": "application/json"}
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        with path.open("rb") as file_stream:
            files = {"file": (path.name, file_stream, content_type)}
            response = requests.post(url, headers=headers, data=data, files=files, timeout=120, verify=ssl_verify())

        response.raise_for_status()
        return response.json()

    except requests.exceptions.JSONDecodeError:
        return response.text


def delete_file(file_id, token_apim):
    try:
        if not file_id:
            raise ValueError("O file_id não foi informado.")

        # A API espera o file_id como query param na rota base, e não como
        # segmento de path (ex: /files/delete/{id} nao existe -> 404).
        url = os.getenv("DELETE_FILE_URL")
        headers = {"Authorization": f"Bearer {token_apim}", "Accept": "application/json"}
        params = {"connection_mode": "APIM", "file_id": file_id}

        response = requests.delete(url, headers=headers, params=params, timeout=120, verify=ssl_verify())
        response.raise_for_status()
        return response.json()

    except requests.exceptions.JSONDecodeError:
        return response.text


def extrair_evidencias(caminho_zip):
    temp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(caminho_zip, "r") as zip_ref:
        zip_ref.extractall(temp_dir)
    print(f"Evidências extraídas para: {temp_dir}")
    return temp_dir
