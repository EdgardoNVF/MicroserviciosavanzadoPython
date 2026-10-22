from shared.auth import require_order_read,require_order_write
from uuid import UUID
from fastapi import Depends,APIRouter,Request,Response,Header,Query,Body
from fastapi.responses import JSONResponse
from app.schemas.order import OrderCreate,OrderResponse,OrderItemCreate,BusinessError
from app.schemas.commands import ChangeStatusRequest,CancelRequest
from app.services.order_service import OrderNotFound,InvalidOrderState
from app.eventstore.store import VersionConflict
from app.queries.order_queries import response_from_order

router=APIRouter(prefix='/api/v1/orders',tags=['Orders CQRS'])
ERRORS={404:{'model':BusinessError},409:{'model':BusinessError}}

def error(code,message,status):return JSONResponse(status_code=status,content={'code':code,'message':message})

def command_response(aggregate,response):
    response.headers['X-Aggregate-Version']=str(aggregate.version)
    return response_from_order(aggregate.order)

@router.post('',response_model=OrderResponse,status_code=201,responses={409:{'model':BusinessError}},dependencies=[Depends(require_order_write)])
async def create(payload:OrderCreate,request:Request,response:Response):
    client=getattr(request.app.state,'inventory_client',None)
    if client is not None:
        quantities={}
        for item in payload.items:
            quantities[item.product_id]=quantities.get(item.product_id,0)+item.quantity
        deferred=False
        for product_id,quantity in quantities.items():
            observed=await client.check_stock(product_id)
            if observed.available is None:
                deferred=True
            elif observed.quantity < quantity:
                code='PRODUCT_NOT_AVAILABLE' if observed.reason=='product_not_found' else 'INSUFFICIENT_STOCK'
                return error(code,'Inventory precheck rejected the order',409)
        response.headers['X-Stock-Precheck']='deferred' if deferred else 'verified'
    return command_response(await request.app.state.commands.create(payload),response)

@router.get('',response_model=list[OrderResponse],dependencies=[Depends(require_order_read)])
async def list_orders(request:Request,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    return await request.app.state.queries.list(limit,offset)

@router.get('/{order_id}',response_model=OrderResponse,responses={404:{'model':BusinessError}},dependencies=[Depends(require_order_read)])
async def get(order_id:UUID,request:Request,response:Response):
    found=await request.app.state.queries.get(order_id)
    if found is None:return error('ORDER_NOT_FOUND','Order not found',404)
    order,version=found;response.headers['X-Aggregate-Version']=str(version);return order

async def change(request,response,order_id,kind,payload,expected):
    try:
        aggregate=await request.app.state.commands.change(order_id,kind,payload,expected)
        return command_response(aggregate,response)
    except OrderNotFound:return error('ORDER_NOT_FOUND','Order not found',404)
    except InvalidOrderState:return error('INVALID_ORDER_STATE','Invalid order transition',409)
    except VersionConflict:return error('VERSION_CONFLICT','Aggregate version changed',409)

@router.patch('/{order_id}/status',response_model=OrderResponse,responses=ERRORS,dependencies=[Depends(require_order_write)])
async def status(order_id:UUID,payload:ChangeStatusRequest,request:Request,response:Response,
                 expected:int|None=Header(None,alias='X-Expected-Version',ge=1)):
    return await change(request,response,order_id,'status',payload,expected)

@router.patch('/{order_id}/cancel',response_model=OrderResponse,responses=ERRORS,dependencies=[Depends(require_order_write)])
async def cancel(order_id:UUID,request:Request,response:Response,payload:CancelRequest|None=Body(None),
                 expected:int|None=Header(None,alias='X-Expected-Version',ge=1)):
    return await change(request,response,order_id,'cancel',payload,expected)

@router.post('/{order_id}/items',response_model=OrderResponse,responses=ERRORS,dependencies=[Depends(require_order_write)])
async def item(order_id:UUID,payload:OrderItemCreate,request:Request,response:Response,
               expected:int|None=Header(None,alias='X-Expected-Version',ge=1)):
    return await change(request,response,order_id,'item',payload,expected)
