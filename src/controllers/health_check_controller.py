from fastapi import APIRouter

health_check_route = APIRouter()

@health_check_route.get(
    "/health/liveness",
    name="Estado da aplicação",
    description="Utilizado pela esteira para validar o estado da aplicação",
    summary="Endpoint responsável por retornar o estado da aplicação para controle da esteira",
    tags=["Health"]
)
async def liveness():
    return {
        "title": "Estado da aplicação",
        "description": "Utilizado pela esteira para validar o estado da aplicação",
        "version": "v1.0",
        "status": "OK",
    }

@health_check_route.get(
    "/health/readiness",
    name="Status da prontidão",
    description="Utilizado pela esteira para validar a prontidão da aplicação",
    summary="Endpoint responsável por retornar a prontidão da aplicação para controle da esteira",
    tags=["Health"]
)
async def readiness():
    return {
        "title": "Status da prontidão",
        "description": "Utilizado pela esteira para validar a prontidão da aplicação",
        "version": "v1.0",
        "status": "OK",
    }
