from enum import Enum
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field

class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"  # Reservado para futuros capítulos; sin transición implementada.
    RELEASED = "released"

class Product(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    sku: str
    stock_quantity: int = Field(ge=0)
    reorder_threshold: int = Field(ge=0, default=10)

class StockReservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    product_id: UUID
    order_id: UUID
    quantity: int = Field(gt=0)
    status: ReservationStatus = ReservationStatus.PENDING
