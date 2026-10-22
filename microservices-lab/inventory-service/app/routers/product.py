from shared.auth import require_inventory_read,require_inventory_write
from uuid import UUID
from fastapi import Depends,APIRouter, Request
from fastapi.responses import JSONResponse
from app.schemas.product import ProductResponse, ProductCreate, StockReservationCreate, StockReservationResponse, BusinessError
from app.services.inventory_service import ProductNotFound, InsufficientStock

router = APIRouter(prefix="/api/v1", tags=["inventory"])

def error(code: str, message: str, status: int):
    return JSONResponse(status_code=status, content={"code": code, "message": message})

@router.post("/products", dependencies=[Depends(require_inventory_write)], response_model=ProductResponse, status_code=201)
def create_product(payload: ProductCreate, request: Request):
    return ProductResponse.model_validate(request.app.state.service.add_product(payload).model_dump())

@router.get("/products", dependencies=[Depends(require_inventory_read)], response_model=list[ProductResponse])
def list_products(request: Request):
    return [ProductResponse.model_validate(p.model_dump()) for p in request.app.state.service.list_products()]

@router.get("/products/{product_id}", dependencies=[Depends(require_inventory_read)], response_model=ProductResponse,
            responses={404: {"model": BusinessError}})
def get_product(product_id: UUID, request: Request):
    product = request.app.state.service.get_product(product_id)
    if product is None:
        return error("PRODUCT_NOT_FOUND", "Product not found", 404)
    return ProductResponse.model_validate(product.model_dump())

@router.post("/reservations", dependencies=[Depends(require_inventory_write)], response_model=StockReservationResponse,
             status_code=201,
             responses={404: {"model": BusinessError}, 409: {"model": BusinessError}})
def create_reservation(payload: StockReservationCreate, request: Request):
    try:
        return StockReservationResponse.model_validate(request.app.state.service.create_reservation(payload).model_dump())
    except ProductNotFound:
        return error("PRODUCT_NOT_FOUND", "Product not found", 404)
    except InsufficientStock:
        return error("INSUFFICIENT_STOCK", "Insufficient stock", 409)
