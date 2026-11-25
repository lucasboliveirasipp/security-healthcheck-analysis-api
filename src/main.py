# Carrega variáveis do arquivo .env mais próximo (pasta do projeto)
def _carregar_env():
    from pathlib import Path
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for pasta in Path(__file__).resolve().parents:
        if (pasta / ".env").exists():
            load_dotenv(pasta / ".env")
            break


_carregar_env()

import os
import warnings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.controllers.gateway_apim_controller import gateway_apim_route
from src.controllers.health_check_controller import health_check_route

warnings.filterwarnings("ignore")


app = FastAPI(
    title="Agente Automação Análise Healthcheck - Hub BFF",
    version=os.getenv("APP_VERSION", "1.0.0"),
    root_path=os.getenv("APP_ROOT_PATH", "/api-automacao-analise-healthchecktt"),
    docs_url=os.getenv("DOCS_URL", "/docs"),
    redoc_url=os.getenv("REDOC_URL", "/redoc"),
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://seu-storage.z15.web.core.windows.net", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_check_route)
app.include_router(gateway_apim_route)
