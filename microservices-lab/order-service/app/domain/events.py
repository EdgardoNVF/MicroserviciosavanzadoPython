"""Eventos internos: no sustituir shared.events.OrderCreated del Lab 02."""
from typing import Literal
from uuid import UUID
from pydantic import Field, UUID4
from shared.events import DomainEvent
from app.schemas.order import OrderItemCreate
from app.models.order import OrderStatus

class OrderEvent(DomainEvent):
    aggregate_id: UUID
    aggregate_type: Literal["Order"] = "Order"
    source_service: Literal["order-service"] = "order-service"
    causation_id: UUID4 | None = None
    @property
    def order_id(self):return self.aggregate_id

class OrderCreated(OrderEvent):
    event_type: Literal["OrderCreated"] = "OrderCreated"
    customer_id: UUID
    items: list[OrderItemCreate] = Field(min_length=1,max_length=100)

class OrderStatusChanged(OrderEvent):
    event_type: Literal["OrderStatusChanged"] = "OrderStatusChanged"
    previous_status: OrderStatus
    new_status: OrderStatus

class OrderCancelled(OrderEvent):
    event_type: Literal["OrderCancelled"] = "OrderCancelled"
    reason: str = Field(default="",max_length=500)

class OrderItemAdded(OrderEvent):
    event_type: Literal["OrderItemAdded"] = "OrderItemAdded"
    item: OrderItemCreate

EVENT_TYPES={cls.model_fields['event_type'].default:cls for cls in
    (OrderCreated,OrderStatusChanged,OrderCancelled,OrderItemAdded)}

def decode_event(event_type,payload):
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Tipo de evento desconocido: {event_type}")
    return EVENT_TYPES[event_type].model_validate(payload)
