from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"  # Comando habilitado en el modo CQRS del laboratorio 3.
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class OrderItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    product_id: UUID
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(gt=0)

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity

class Order(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    customer_id: UUID
    items: tuple[OrderItem, ...] = Field(min_length=1)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.items), Decimal("0.00"))
