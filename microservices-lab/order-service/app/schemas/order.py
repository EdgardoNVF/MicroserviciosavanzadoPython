from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.order import OrderStatus

# Importes JSON como texto decimal exacto, máximo 999999.99.
Money = Annotated[str, Field(pattern=r"^([1-9][0-9]{0,5}\.[0-9]{2}|0\.(0[1-9]|[1-9][0-9]))$")]

class OrderItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID
    quantity: int = Field(strict=True, ge=1, le=1000)
    unit_price: Money

class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID
    items: list[OrderItemCreate] = Field(min_length=1, max_length=100)

class OrderItemResponse(OrderItemCreate):
    subtotal: str = Field(pattern=r"^[0-9]+\.[0-9]{2}$")

class OrderResponse(BaseModel):
    id: UUID
    customer_id: UUID
    status: OrderStatus
    items: list[OrderItemResponse]
    total: str = Field(pattern=r"^[0-9]+\.[0-9]{2}$")
    created_at: datetime

class BusinessError(BaseModel):
    code: str
    message: str
