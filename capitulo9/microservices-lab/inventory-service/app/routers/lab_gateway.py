from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from shared.auth.dependencies import permission


router = APIRouter(
    prefix="/api/v1/lab",
    tags=["Laboratorio API Gateway"],
)

require_inventory_read = permission(
    "inventory:read",
    "inventory.read",
)


@router.get(
    "/inventory/failure",
    dependencies=[Depends(require_inventory_read)],
)
def simulate_inventory_failure(fail: bool = True):
    """
    Endpoint exclusivo de la práctica.

    fail=true: devuelve un fallo controlado.
    fail=false: devuelve una respuesta correcta.

    No modifica productos, reservas ni stock.
    """
    return JSONResponse(
        status_code=500 if fail else 200,
        content={
            "service": "inventory-service",
            "simulated_failure": fail,
        },
        headers={
            "X-Lab-Backend": "inventory-service",
        },
    )
