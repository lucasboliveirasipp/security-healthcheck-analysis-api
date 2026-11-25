# tests/conftest.py
from __future__ import annotations
import os
import sys
from pathlib import Path
import pytest

# ==============================================================================
# 1) Descobrir a raiz do repositório e injetar caminhos no sys.path
#    - Permite que os testes importem usando "from src..." e "from src.services..."
#    - Espelha a estratégia usada no repositório api-reembolso-demo
# ==============================================================================
THIS_FILE = Path(__file__).resolve()        # .../tests/conftest.py
TESTS_DIR = THIS_FILE.parent                 # .../tests
ROOT = TESTS_DIR.parent                      # raiz do repositório
SRC = ROOT / "src"                           # .../src

# Só adicionamos caminhos que existem, sempre no início do sys.path
paths_to_add = []
if SRC.exists():
    paths_to_add.append(str(SRC))
paths_to_add.append(str(ROOT))

for p in paths_to_add:
    if p not in sys.path:
        sys.path.insert(0, p)

# ==============================================================================
# 2) Variáveis de ambiente padrão para modo de teste
#    - São exatamente as env vars lidas por src/services/utils.py.
#    - Definimos valores falsos e determinísticos para evitar qualquer
#      dependência de configuração real ou chamada externa acidental.
#    - Usamos os.environ diretamente (não monkeypatch) porque precisam existir
#      já no momento do import dos módulos de src.
# ==============================================================================
DEFAULT_ENV = {
    "ENV": os.getenv("ENV", "test"),
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
    # Autenticação APIM (authenticate_apim).
    # Nomes padronizados com os secrets compartilhados dos BFFs do Hub.
    # GATEWAYAPPIDURI guarda apenas o prefixo api://... — o sufixo
    # /.default é acrescentado por authenticate_apim.
    "TENANTID": "test-tenant",
    "GATEWAYAPPID": "test-client-id",
    "GATEWAYAPPIDURI": "api://test-app",
    "GATEWAYCLIENTSECRET": "test-secret",
    # URLs de workflow (startworkflow / get_workflow_status)
    "WORKFLOW_URL": "https://wf.test.example.com/start",
    "WORKFLOW_STATUS_URL": "https://wf.test.example.com/status",
    # URLs de arquivos (upload_file / delete_file)
    "UPLOAD_FILE_URL": "https://fm.test.example.com/files/upload",
    "DELETE_FILE_URL": "https://fm.test.example.com/files",
    # Config de container/arquivo (upload_file)
    "CONTAINER_NAME": "test-container",
    "CREATE_CONTAINER": "true",
    "OVERWRITE_FILE": "true",
    # Validação de certificado (ssl_verify). Mantemos o padrão seguro nos
    # testes; os cenários de CA bundle e de opt-in são exercitados
    # isoladamente via monkeypatch em test_utils_cover.py.
    "SSL_VERIFY": "true",
}

# Só definimos quando ainda não houver valor no ambiente, preservando overrides
# feitos por quem executa os testes.
for k, v in DEFAULT_ENV.items():
    if os.getenv(k) is None:
        os.environ[k] = v


# ==============================================================================
# 3) Fixture autouse
#    - Aplica variáveis extras por teste via monkeypatch (isolamento por função).
#    - monkeypatch reverte automaticamente ao fim de cada teste.
# ==============================================================================
@pytest.fixture(autouse=True)
def _setup_test_env(monkeypatch):
    test_envs = {
        "APIM_MOCK": "1",
        "TEST_FAKE_BEARER": "fake-token-for-tests",
    }
    for k, v in test_envs.items():
        monkeypatch.setenv(k, v)
    yield


# ==============================================================================
# 4) Fixtures básicas
# ==============================================================================
@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # Backend usado por testes assíncronos (endpoints async do FastAPI).
    return "asyncio"


@pytest.fixture(scope="function")
def client():
    # TestClient do FastAPI (requer httpx instalado).
    # Import tardio: garante que o sys.path e as env vars já foram configurados.
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)


# Força UTF-8 para evitar problemas de encoding no Windows ao capturar stdout.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
