from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, UUID4, field_validator

class DomainEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event_id: UUID4 = Field(default_factory=uuid4)
    event_version: Literal["1.0.0"] = "1.0.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: UUID4 = Field(default_factory=uuid4)

    @field_validator("timestamp")
    @classmethod
    def aware_utc(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp debe incluir zona horaria")
        return value.astimezone(timezone.utc)

    def to_kafka_value(self):
        return self.model_dump_json().encode("utf-8")

class RequestedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    product_id: UUID
    quantity: int = Field(strict=True, ge=1, le=1000)

class ReservedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    product_id: UUID
    quantity_reserved: int = Field(strict=True, ge=1, le=100000)
    remaining_stock: int = Field(strict=True, ge=0)
    reservation_id: UUID4

class OrderCreated(DomainEvent):
    event_type: Literal["OrderCreated"] = "OrderCreated"
    source_service: Literal["order-service"] = "order-service"
    order_id: UUID
    customer_id: UUID
    items: list[RequestedItem] = Field(min_length=1, max_length=100)

class StockReserved(DomainEvent):
    event_type: Literal["StockReserved"] = "StockReserved"
    source_service: Literal["inventory-service"] = "inventory-service"
    causation_id: UUID4
    order_id: UUID
    items: list[ReservedItem] = Field(min_length=1, max_length=100)

class StockReservationFailed(DomainEvent):
    event_type: Literal["StockReservationFailed"] = "StockReservationFailed"
    source_service: Literal["inventory-service"] = "inventory-service"
    causation_id: UUID4
    order_id: UUID
    product_id: UUID
    quantity_requested: int = Field(strict=True, ge=1, le=100000)
    available_stock: int = Field(strict=True, ge=0)
    reason: Literal["PRODUCT_NOT_FOUND", "INSUFFICIENT_STOCK"]
