from typing import Literal
from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    service: Literal["order-service", "inventory-service"]

HEALTH_RESPONSES = {503: {"model": HealthResponse, "description": "Dependencias no disponibles"}}
