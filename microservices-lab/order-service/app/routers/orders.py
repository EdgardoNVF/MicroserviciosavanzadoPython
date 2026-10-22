import asyncio
import logging
from uuid import UUID
from shared.events import OrderCreated, RequestedItem
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.schemas.order import OrderCreate, OrderResponse, OrderItemResponse, BusinessError
from app.services.order_service import OrderNotFound, InvalidOrderState

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

def to_response(order):
    return OrderResponse(id=order.id, customer_id=order.customer_id,
        status=order.status, created_at=order.created_at,
        total=f"{order.total:.2f}", items=[OrderItemResponse(
            product_id=i.product_id, quantity=i.quantity,
            unit_price=f"{i.unit_price:.2f}", subtotal=f"{i.subtotal:.2f}") for i in order.items])

def error(code, message, status):
    return JSONResponse(status_code=status, content={"code": code, "message": message})

@router.post("", response_model=OrderResponse, status_code=201,
             responses={503: {"model": BusinessError}})
async def create_order(payload: OrderCreate, request: Request):
    order = request.app.state.service.prepare_order(payload)
    publisher = request.app.state.publisher
    if publisher is not None:
        event = OrderCreated(order_id=order.id, customer_id=order.customer_id,
            items=[RequestedItem(product_id=i.product_id, quantity=i.quantity) for i in order.items])
        try:
            await asyncio.to_thread(publisher.publish, "orders.created", event)
        except Exception:
            logging.getLogger(__name__).exception("Publicación no confirmada")
            return error("EVENT_PUBLICATION_FAILED", "Kafka delivery not confirmed", 503)
    return to_response(request.app.state.service.save_order(order))

@router.get("", response_model=list[OrderResponse])
def list_orders(request: Request):
    return [to_response(o) for o in request.app.state.service.list_orders()]

@router.get("/{order_id}", response_model=OrderResponse, responses={404: {"model": BusinessError}})
def get_order(order_id: UUID, request: Request):
    order = request.app.state.service.get_order(order_id)
    if order is None:
        return error("ORDER_NOT_FOUND", "Order not found", 404)
    return to_response(order)

@router.patch("/{order_id}/cancel", response_model=OrderResponse,
              responses={404: {"model": BusinessError}, 409: {"model": BusinessError}})
def cancel_order(order_id: UUID, request: Request):
    try:
        return to_response(request.app.state.service.cancel_order(order_id))
    except OrderNotFound:
        return error("ORDER_NOT_FOUND", "Order not found", 404)
    except InvalidOrderState:
        return error("INVALID_ORDER_STATE", "Order cannot be cancelled", 409)
