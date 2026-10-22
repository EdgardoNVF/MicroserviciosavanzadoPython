import secrets
from uuid import UUID
import redis
from fastapi import APIRouter,Request,Header
from fastapi.responses import JSONResponse
from app.clients.inventory_client import StockResponse

router=APIRouter(tags=['Resilience'])

@router.get('/api/v1/orders/check-stock/{product_id}',response_model=StockResponse)
async def check_stock(product_id:UUID,request:Request):
    # 200 describes availability observation; null explicitly means unknown.
    return await request.app.state.inventory_client.check_stock(product_id)

@router.get('/health/circuit-breakers',responses={503:{'description':'Redis unavailable'}})
async def status(request:Request):
    try:return await request.app.state.inventory_client.status()
    except redis.RedisError:
        return JSONResponse(status_code=503,content={'code':'RESILIENCE_STORAGE_UNAVAILABLE'})

@router.post('/health/circuit-breakers/{service_name}/reset',responses={403:{'description':'Invalid admin key'},404:{'description':'Unknown circuit'}})
async def reset(service_name:str,request:Request,admin:str|None=Header(None,alias='X-Admin-Key')):
    if not admin or not secrets.compare_digest(admin,request.app.state.resilience_admin_key):
        return JSONResponse(status_code=403,content={'detail':'Invalid admin key'})
    if service_name!='inventory-service':
        return JSONResponse(status_code=404,content={'code':'CIRCUIT_NOT_FOUND'})
    try:return await request.app.state.inventory_client.reset()
    except redis.RedisError:
        return JSONResponse(status_code=503,content={'code':'RESILIENCE_STORAGE_UNAVAILABLE'})
