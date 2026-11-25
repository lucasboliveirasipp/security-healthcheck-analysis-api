# tests/unit/test_main_cover.py
#
# Cobre apenas a montagem do app (wiring): metadados, OpenAPI, CORS e
# inclusao dos routers. A logica dos endpoints e testada em
# test_gateway_apim_controller.py; a orquestracao em test_analise_service_cover.py.
from fastapi.testclient import TestClient

from src.main import app


def test_app_metadata_and_openapi():
    assert app.title == "Agente Automação Análise Healthcheck - Hub BFF"
    assert app.openapi_url == "/openapi.json"

    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == app.title

    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_root_path_default():
    assert app.root_path == "/api-automacao-analise-healthchecktt"


def test_cors_middleware_registered():
    assert any(m.cls.__name__ == "CORSMiddleware" for m in app.user_middleware)


def test_routers_included():
    # Lemos as rotas pelo schema OpenAPI em vez de app.routes: no FastAPI 0.141
    # os routers incluídos aparecem como _IncludedRouter (sem atributo .path),
    # enquanto no 0.115 eram achatados em objetos Route. O OpenAPI expõe o
    # contrato público e é estável entre as duas versões.
    caminhos = TestClient(app).get("/openapi.json").json()["paths"]

    assert "/health/liveness" in caminhos
    assert "/health/readiness" in caminhos
    assert "/analisar_healthcheck" in caminhos
    assert "/analisar_healthcheck_stream" in caminhos
