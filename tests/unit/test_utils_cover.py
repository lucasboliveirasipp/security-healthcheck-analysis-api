# tests/unit/test_utils_cover.py
import os
import zipfile
import pytest

import src.services.utils as utils_mod


class DummyResponse:
    """
    Simula uma resposta do módulo `requests`.
    - payload: dict retornado por .json(), ou uma Exception para simular
      erro de parsing (JSONDecodeError).
    - text: texto retornado quando .json() falha (usado pelo fallback de
      upload_file/delete_file).
    - status: código HTTP simulado; usado por raise_for_status().
    """

    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = {} if payload is None else payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        import requests
        if self.status_code and int(self.status_code) >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def mock_requests_post(monkeypatch, checker):
    import requests
    monkeypatch.setattr(requests, "post", lambda url, **kwargs: checker(url, **kwargs))


def mock_requests_get(monkeypatch, checker):
    import requests
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: checker(url, **kwargs))


def mock_requests_delete(monkeypatch, checker):
    import requests
    monkeypatch.setattr(requests, "delete", lambda url, **kwargs: checker(url, **kwargs))


# ─── authenticate_apim ─────────────────────────────────────────────────────────

def test_authenticate_apim_success(monkeypatch):
    def _checker(url, **kwargs):
        assert "login.microsoftonline.com" in url
        assert kwargs["data"]["grant_type"] == "client_credentials"
        return DummyResponse(payload={"access_token": "tok-abc"})
    mock_requests_post(monkeypatch, _checker)

    token = utils_mod.authenticate_apim()
    assert token == "tok-abc"


def test_authenticate_apim_missing_token_returns_none(monkeypatch):
    # Quando a resposta não contém "access_token", .get() retorna None
    mock_requests_post(monkeypatch, lambda url, **kwargs: DummyResponse(payload={}))

    token = utils_mod.authenticate_apim()
    assert token is None


# ─── startworkflow ──────────────────────────────────────────────────────────────

def test_startworkflow_success(monkeypatch):
    def _checker(url, **kwargs):
        assert url == os.getenv("WORKFLOW_URL")
        assert kwargs["headers"]["Authorization"] == "Bearer tok-123"
        assert kwargs["json"] == {"foo": "bar"}
        return DummyResponse(payload={"workflow_execution_id": "we-1"})
    mock_requests_post(monkeypatch, _checker)

    result = utils_mod.startworkflow({"foo": "bar"}, "tok-123")
    assert result == {"workflow_execution_id": "we-1"}


def test_startworkflow_http_error_raises(monkeypatch):
    import requests
    mock_requests_post(monkeypatch, lambda url, **kwargs: DummyResponse(status=500))

    with pytest.raises(requests.exceptions.HTTPError):
        utils_mod.startworkflow({"foo": "bar"}, "tok-123")


# ─── get_workflow_status ────────────────────────────────────────────────────────

def test_get_workflow_status_success(monkeypatch):
    def _checker(url, **kwargs):
        assert url == f"{os.getenv('WORKFLOW_STATUS_URL')}/we-1"
        assert kwargs["headers"]["Authorization"] == "Bearer tok-123"
        return DummyResponse(payload={"status": "WF_COMPLETED_SUCCESS"})
    mock_requests_get(monkeypatch, _checker)

    result = utils_mod.get_workflow_status("we-1", "tok-123")
    assert result == {"status": "WF_COMPLETED_SUCCESS"}


def test_get_workflow_status_http_error_raises(monkeypatch):
    import requests
    mock_requests_get(monkeypatch, lambda url, **kwargs: DummyResponse(status=404))

    with pytest.raises(requests.exceptions.HTTPError):
        utils_mod.get_workflow_status("we-x", "tok-123")


# ─── execute_workflow ───────────────────────────────────────────────────────────

def test_execute_workflow_polls_until_success(monkeypatch):
    # startworkflow sempre retorna o mesmo workflow_execution_id
    mock_requests_post(monkeypatch, lambda url, **kwargs: DummyResponse(payload={"workflow_execution_id": "we-42"}))

    # get_workflow_status simula 2 chamadas "em andamento" antes do sucesso,
    # validando o comportamento de polling do laço `while not WF_COMPLETED_SUCCESS`.
    status_sequence = iter([
        {"status": "WF_IN_PROGRESS"},
        {"status": "WF_IN_PROGRESS"},
        {"status": "WF_COMPLETED_SUCCESS", "output_collection": {"ok": True}},
    ])
    mock_requests_get(monkeypatch, lambda url, **kwargs: DummyResponse(payload=next(status_sequence)))

    esperas = []
    monkeypatch.setattr(utils_mod.time, "sleep", esperas.append)

    result = utils_mod.execute_workflow({"payload": True}, "tok-123")
    assert result == {"status": "WF_COMPLETED_SUCCESS", "output_collection": {"ok": True}}
    # Espera entre as consultas em andamento, em vez de martelar a APIM.
    assert len(esperas) == 2


def test_execute_workflow_erro_na_gateway_levanta_workflow_error(monkeypatch):
    # Regressao: WF_COMPLETED_ERROR deixava o laco consultando para sempre.
    mock_requests_post(monkeypatch, lambda url, **kwargs: DummyResponse(payload={"workflow_execution_id": "we-err"}))
    mock_requests_get(
        monkeypatch,
        lambda url, **kwargs: DummyResponse(payload={"status": "WF_COMPLETED_ERROR", "error": {"message": "OCR falhou"}}),
    )

    with pytest.raises(utils_mod.WorkflowError, match="WF_COMPLETED_ERROR.*OCR falhou"):
        utils_mod.execute_workflow({"payload": True}, "tok-123")


def test_execute_workflow_excede_tempo_limite(monkeypatch):
    monkeypatch.setenv("WORKFLOW_TIMEOUT", "0")
    monkeypatch.setattr(utils_mod.time, "sleep", lambda s: None)
    mock_requests_post(monkeypatch, lambda url, **kwargs: DummyResponse(payload={"workflow_execution_id": "we-lento"}))
    mock_requests_get(monkeypatch, lambda url, **kwargs: DummyResponse(payload={"status": "WF_RUNNING"}))

    with pytest.raises(utils_mod.WorkflowError, match="tempo limite"):
        utils_mod.execute_workflow({"payload": True}, "tok-123")


# ─── upload_file ────────────────────────────────────────────────────────────────

def test_upload_file_success(monkeypatch, tmp_path):
    arquivo = tmp_path / "evidencia.pdf"
    arquivo.write_bytes(b"PDFDATA")

    # Sem container_name explícito, cai no default vindo do ambiente
    # (CONTAINER_NAME=test-container, definido em tests/conftest.py).
    def _checker(url, **kwargs):
        assert url == os.getenv("UPLOAD_FILE_URL")
        assert kwargs["headers"]["Authorization"] == "Bearer tok-123"
        assert kwargs["data"]["container_name"] == os.getenv("CONTAINER_NAME")
        assert kwargs["data"]["connection_mode"] == "APIM"
        return DummyResponse(payload={"file_id": {"id": "file-1", "path": "test-container/evidencia.pdf"}})
    mock_requests_post(monkeypatch, _checker)

    result = utils_mod.upload_file(str(arquivo), "tok-123")
    assert result == {"file_id": {"id": "file-1", "path": "test-container/evidencia.pdf"}}


def test_upload_file_argumentos_do_chamador_tem_precedencia(monkeypatch, tmp_path):
    # Regressão: os argumentos container_name/create_container/overwrite eram
    # descartados e sobrescritos pelas variáveis de ambiente. Agora o valor
    # informado pelo chamador (ex.: agent.py passa "healthcheck") prevalece.
    arquivo = tmp_path / "evidencia.pdf"
    arquivo.write_bytes(b"PDFDATA")

    def _checker(url, **kwargs):
        assert kwargs["data"]["container_name"] == "container-x"
        assert kwargs["data"]["create_container"] == "false"
        assert kwargs["data"]["overwrite"] == "false"
        return DummyResponse(payload={"ok": True})
    mock_requests_post(monkeypatch, _checker)

    utils_mod.upload_file(
        str(arquivo),
        "tok-123",
        container_name="container-x",
        create_container=False,
        overwrite=False,
    )


def test_upload_file_flags_booleanas_viram_string_minuscula(monkeypatch, tmp_path):
    # A API espera "true"/"false" em minúsculo; str(True) produziria "True".
    arquivo = tmp_path / "evidencia.pdf"
    arquivo.write_bytes(b"PDFDATA")

    def _checker(url, **kwargs):
        assert kwargs["data"]["create_container"] == "true"
        assert kwargs["data"]["overwrite"] == "true"
        return DummyResponse(payload={"ok": True})
    mock_requests_post(monkeypatch, _checker)

    utils_mod.upload_file(str(arquivo), "tok-123", create_container=True, overwrite=True)


def test_upload_file_missing_file_raises(monkeypatch, tmp_path):
    caminho_inexistente = tmp_path / "nao_existe.pdf"

    with pytest.raises(FileNotFoundError):
        utils_mod.upload_file(str(caminho_inexistente), "tok-123")


def test_upload_file_missing_token_raises(tmp_path):
    arquivo = tmp_path / "evidencia.pdf"
    arquivo.write_bytes(b"PDFDATA")

    with pytest.raises(ValueError):
        utils_mod.upload_file(str(arquivo), "")


def test_upload_file_non_json_response_returns_text(monkeypatch, tmp_path):
    import requests
    arquivo = tmp_path / "evidencia.pdf"
    arquivo.write_bytes(b"PDFDATA")

    def _checker(url, **kwargs):
        return DummyResponse(payload=requests.exceptions.JSONDecodeError("msg", "doc", 0), text="not-json-body")
    mock_requests_post(monkeypatch, _checker)

    result = utils_mod.upload_file(str(arquivo), "tok-123")
    assert result == "not-json-body"


# ─── delete_file ────────────────────────────────────────────────────────────────

def test_delete_file_success(monkeypatch):
    def _checker(url, **kwargs):
        # O file_id vai como query param na rota base (/files/delete/{id} da 404).
        assert url == os.getenv("DELETE_FILE_URL")
        assert kwargs["params"]["file_id"] == "file-1"
        assert kwargs["headers"]["Authorization"] == "Bearer tok-123"
        return DummyResponse(payload={"deleted": True})
    mock_requests_delete(monkeypatch, _checker)

    result = utils_mod.delete_file("file-1", "tok-123")
    assert result == {"deleted": True}


def test_delete_file_missing_id_raises():
    with pytest.raises(ValueError):
        utils_mod.delete_file("", "tok-123")


def test_delete_file_non_json_response_returns_text(monkeypatch):
    import requests

    def _checker(url, **kwargs):
        return DummyResponse(payload=requests.exceptions.JSONDecodeError("msg", "doc", 0), text="deleted-ok")
    mock_requests_delete(monkeypatch, _checker)

    result = utils_mod.delete_file("file-1", "tok-123")
    assert result == "deleted-ok"


# ─── extrair_evidencias ─────────────────────────────────────────────────────────

def test_extrair_evidencias_extracts_zip_contents(tmp_path):
    # Monta um .zip real com uma pasta "AC 1.1.1" e um arquivo dentro,
    # simulando a estrutura esperada pelo agent.py (dir_evidencias/Ref/arquivo).
    zip_path = tmp_path / "evidencias.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("AC 1.1.1/norma.txt", "conteudo da evidencia")

    destino = utils_mod.extrair_evidencias(str(zip_path))

    arquivo_extraido = os.path.join(destino, "AC 1.1.1", "norma.txt")
    assert os.path.isfile(arquivo_extraido)
    with open(arquivo_extraido, "r", encoding="utf-8") as f:
        assert f.read() == "conteudo da evidencia"


# ─── ssl_verify ─────────────────────────────────────────────────────────────────

def test_ssl_verify_default_is_true(monkeypatch):
    # Sem nenhuma variável definida, a validação de certificado fica ativa.
    for var in ("PATH_ROOT_CA", "REQUESTS_CA_BUNDLE", "SSL_VERIFY"):
        monkeypatch.delenv(var, raising=False)

    assert utils_mod.ssl_verify() is True


def test_ssl_verify_usa_ca_bundle_quando_arquivo_existe(monkeypatch, tmp_path):
    ca = tmp_path / "corp-ca.crt"
    ca.write_text("-----BEGIN CERTIFICATE-----")
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("PATH_ROOT_CA", str(ca))

    assert utils_mod.ssl_verify() == str(ca)


def test_ssl_verify_aceita_requests_ca_bundle(monkeypatch, tmp_path):
    ca = tmp_path / "outra-ca.crt"
    ca.write_text("-----BEGIN CERTIFICATE-----")
    monkeypatch.delenv("PATH_ROOT_CA", raising=False)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(ca))

    assert utils_mod.ssl_verify() == str(ca)


def test_ssl_verify_ignora_ca_bundle_inexistente(monkeypatch, tmp_path):
    # Caminho apontando para arquivo ausente (caso do container em dev local)
    # não deve ser repassado ao requests, senão a chamada quebra com
    # "Could not find a suitable TLS CA certificate bundle".
    monkeypatch.setenv("PATH_ROOT_CA", str(tmp_path / "nao-existe.crt"))
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_VERIFY", raising=False)

    assert utils_mod.ssl_verify() is True


@pytest.mark.parametrize("valor", ["false", "FALSE", "0", "no", " False "])
def test_ssl_verify_desabilita_com_opt_in_explicito(monkeypatch, valor):
    for var in ("PATH_ROOT_CA", "REQUESTS_CA_BUNDLE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SSL_VERIFY", valor)

    assert utils_mod.ssl_verify() is False


@pytest.mark.parametrize("valor", ["true", "1", "yes", "qualquer-outra-coisa"])
def test_ssl_verify_mantem_true_para_valores_nao_negativos(monkeypatch, valor):
    for var in ("PATH_ROOT_CA", "REQUESTS_CA_BUNDLE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SSL_VERIFY", valor)

    assert utils_mod.ssl_verify() is True


def test_chamadas_http_repassam_verify_resolvido(monkeypatch):
    # Garante que o valor devolvido por ssl_verify() chega de fato ao requests,
    # em vez de um literal False fixo no código.
    monkeypatch.setattr(utils_mod, "ssl_verify", lambda: "/etc/ssl/corp-ca.crt")

    def _checker(url, **kwargs):
        assert kwargs["verify"] == "/etc/ssl/corp-ca.crt"
        return DummyResponse(payload={"workflow_execution_id": "we-1"})
    mock_requests_post(monkeypatch, _checker)

    utils_mod.startworkflow({"foo": "bar"}, "tok-123")


# ─── _flag ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "valor,esperado",
    [
        (True, "true"),
        (False, "false"),
        ("true", "true"),
        ("TRUE", "true"),
        ("1", "true"),
        ("yes", "true"),
        ("false", "false"),
        ("FALSE", "false"),
        ("0", "false"),
        ("no", "false"),
        (" False ", "false"),
    ],
)
def test_flag_normaliza_valores_do_chamador(valor, esperado):
    assert utils_mod._flag(valor, "QUALQUER_ENV") == esperado


def test_flag_usa_env_var_quando_valor_e_none(monkeypatch):
    monkeypatch.setenv("MINHA_FLAG", "false")
    assert utils_mod._flag(None, "MINHA_FLAG") == "false"


def test_flag_usa_default_quando_env_ausente(monkeypatch):
    monkeypatch.delenv("MINHA_FLAG", raising=False)
    assert utils_mod._flag(None, "MINHA_FLAG") == "true"
    assert utils_mod._flag(None, "MINHA_FLAG", default="false") == "false"


def test_flag_false_explicito_nao_cai_no_default(monkeypatch):
    # False é falsy: um `valor or os.getenv(...)` cairia no default "true".
    # A checagem por `is None` preserva a intenção do chamador.
    monkeypatch.setenv("MINHA_FLAG", "true")
    assert utils_mod._flag(False, "MINHA_FLAG") == "false"


def test_authenticate_apim_scope_ausente_nao_concatena_sufixo(monkeypatch):
    # Quando GATEWAYAPPIDURI não está definido, o scope deve seguir como
    # None em vez de virar a string "None/.default" — que mascararia variável
    # ausente como erro de scope inválido no Azure AD.
    monkeypatch.delenv("GATEWAYAPPIDURI", raising=False)

    def _checker(url, **kwargs):
        assert kwargs["data"]["scope"] is None
        return DummyResponse(payload={"access_token": "tok-sem-scope"})
    mock_requests_post(monkeypatch, _checker)

    assert utils_mod.authenticate_apim() == "tok-sem-scope"


def test_authenticate_apim_scope_ja_com_sufixo_nao_duplica(monkeypatch):
    # Se o valor injetado pelo Key Vault já vier com /.default, o sufixo não
    # deve ser concatenado novamente (geraria AADSTS70011).
    monkeypatch.setenv("GATEWAYAPPIDURI", "api://app-x/.default")

    def _checker(url, **kwargs):
        assert kwargs["data"]["scope"] == "api://app-x/.default"
        return DummyResponse(payload={"access_token": "tok-ok"})
    mock_requests_post(monkeypatch, _checker)

    assert utils_mod.authenticate_apim() == "tok-ok"
