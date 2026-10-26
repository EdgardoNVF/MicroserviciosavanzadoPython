from shared.auth.token_client import ServiceTokenClient,ServiceAuthenticationError
import asyncio
import os
from uuid import UUID
import httpx
import pybreaker
import redis
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from shared.resilience import BulkheadSemaphore,BulkheadFullError,CircuitBreakerRegistry
from shared.resilience.retry_policies import retry_policy,RETRYABLE_STATUS,TRANSIENT,TransientInventoryError,InventoryProtocolError

class ProductStock(BaseModel):
    model_config=ConfigDict(extra='ignore')
    id:UUID
    stock_quantity:int=Field(strict=True,ge=0)

class StockResponse(BaseModel):
    product_id:UUID
    available:bool|None
    quantity:int|None
    source:str
    reason:str|None=None
    attempts:int=0

class InventoryClient:
    """Async-facing adapter around pybreaker's public synchronous call API.

    The entire GET/retry operation executes in a worker thread. Pybreaker's
    per-breaker RLock serializes actual HTTP calls; slots bound queued + active
    jobs. Cancellation keeps the slot until the worker really finishes.
    """
    def __init__(self,base_url='http://localhost:8002',redis_url='redis://localhost:6379/1',
                 namespace='lab04:orders:local:inventory',fail_max=5,reset_timeout=30,
                 max_concurrent=10,acquire_timeout=.1,http_timeout=1,attempts=3,
                 retry_multiplier=.1,retry_max_wait=.5,transport=None,token_client=None):
        self.token_client=token_client
        self.registry=CircuitBreakerRegistry(redis_url,namespace,fail_max,reset_timeout,
                                            excluded=(ServiceAuthenticationError,))
        self.bulkhead=BulkheadSemaphore('inventory-service',max_concurrent,acquire_timeout)
        self.http=httpx.Client(base_url=base_url,timeout=http_timeout,transport=transport,trust_env=False)
        self.retry_options=dict(attempts=attempts,multiplier=retry_multiplier,max_wait=retry_max_wait)
        self.pending=set()
        self.closed=False

    @classmethod
    def from_env(cls):
        return cls(base_url=os.getenv('INVENTORY_BASE_URL','http://localhost:8002'),
            redis_url=os.getenv('RESILIENCE_REDIS_URL','redis://localhost:6379/1'),
            namespace=os.getenv('RESILIENCE_NAMESPACE','lab04:orders:local:inventory'),
            fail_max=int(os.getenv('RESILIENCE_FAIL_MAX','5')),
            reset_timeout=int(os.getenv('RESILIENCE_RESET_TIMEOUT','30')),
            max_concurrent=int(os.getenv('RESILIENCE_MAX_CONCURRENT','10')),
            acquire_timeout=float(os.getenv('RESILIENCE_ACQUIRE_TIMEOUT','.1')),
            http_timeout=float(os.getenv('RESILIENCE_HTTP_TIMEOUT','1')),
            token_client=ServiceTokenClient.from_env() if os.getenv('AUTH_ENABLED','false').lower()=='true' else None)

    def _request(self,product_id,counter):
        counter['attempts']+=1
        token=self.token_client.get_token() if self.token_client else None
        response=self.http.get(f'/api/v1/products/{product_id}',headers={'Authorization':f'Bearer {token}'} if token else {})
        if token and response.status_code==401 and counter.get('auth_refreshes',0)==0:
            counter['auth_refreshes']=1
            self.token_client.invalidate(token)
            token=self.token_client.get_token()
            counter['attempts']+=1
            response=self.http.get(f'/api/v1/products/{product_id}',headers={'Authorization':f'Bearer {token}'})
        if token and response.status_code in {401,403}:
            raise ServiceAuthenticationError('Inventory rejected service identity')
        if response.status_code in RETRYABLE_STATUS:
            raise TransientInventoryError(f'Inventory HTTP {response.status_code}')
        if response.status_code==404:
            return StockResponse(product_id=product_id,available=False,quantity=0,
                                 source='inventory-service',reason='product_not_found',attempts=counter['attempts'])
        if response.status_code!=200:
            raise InventoryProtocolError(f'Inventory HTTP {response.status_code}')
        try:
            product=ProductStock.model_validate(response.json())
        except (ValueError,ValidationError) as exc:
            raise InventoryProtocolError('Invalid inventory body') from exc
        if product.id!=product_id:raise InventoryProtocolError('Wrong product ID')
        return StockResponse(product_id=product_id,available=product.stock_quantity>0,
              quantity=product.stock_quantity,source='inventory-service',attempts=counter['attempts'])

    def _worker(self,product_id,counter):
        if self.token_client:self.token_client.get_token()
        breaker=self.registry.get_breaker()
        policy=retry_policy(**self.retry_options)
        return breaker.call(policy,self._request,product_id,counter)

    @staticmethod
    def fallback(product_id,reason,attempts=0):
        return StockResponse(product_id=product_id,available=None,quantity=None,
                             source='fallback',reason=reason,attempts=attempts)

    async def check_stock(self,product_id):
        if self.closed:raise RuntimeError('Client is closed')
        try:await self.bulkhead.acquire()
        except BulkheadFullError:return self.fallback(product_id,'bulkhead_full')
        counter={'attempts':0}
        task=asyncio.create_task(asyncio.to_thread(self._worker,product_id,counter))
        self.pending.add(task)
        # Callback owns release, even when the awaiting HTTP request is cancelled.
        def finished(job):
            self.pending.discard(job)
            self.bulkhead.release()
            if not job.cancelled():job.exception()  # retrieve detached worker failure
        task.add_done_callback(finished)
        try:
            return await asyncio.shield(task)
        except pybreaker.CircuitBreakerError:
            return self.fallback(product_id,'circuit_open',counter['attempts'])
        except redis.RedisError:
            return self.fallback(product_id,'resilience_storage_unavailable',counter['attempts'])
        except TRANSIENT:
            return self.fallback(product_id,'upstream_unavailable',counter['attempts'])
        except InventoryProtocolError:
            return self.fallback(product_id,'invalid_upstream_response',counter['attempts'])
        # Programming errors intentionally propagate; they are not disguised as stock.

    async def status(self):
        status=await asyncio.to_thread(self.registry.status)
        return {'circuit_breakers':{'inventory-service':status},
                'bulkheads':{'inventory-service':self.bulkhead.stats}}

    async def reset(self):
        return await asyncio.to_thread(self.registry.reset)

    async def close(self):
        self.closed=True
        if self.pending:await asyncio.gather(*list(self.pending),return_exceptions=True)
        await asyncio.to_thread(self.http.close)
        await asyncio.to_thread(self.registry.close)
        if self.token_client:await asyncio.to_thread(self.token_client.close)
