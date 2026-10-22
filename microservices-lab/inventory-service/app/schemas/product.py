from typing import Annotated, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field
from app.models.product import ReservationStatus

Quantity = Annotated[int, Field(strict=True, ge=1, le=1000000)]

class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9-]+$")
    stock_quantity: int = Field(strict=True, ge=0, le=1000000, default=0)
    reorder_threshold: int = Field(strict=True, ge=0, le=1000000, default=10)

class ProductResponse(ProductCreate):
    id: UUID = Field(default_factory=uuid4)

class StockReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID
    order_id: UUID
    quantity: Quantity

class StockReservationResponse(StockReservationCreate):
    id: UUID = Field(default_factory=uuid4)
    status: ReservationStatus

class BusinessError(BaseModel):
    code: str
    message: str
