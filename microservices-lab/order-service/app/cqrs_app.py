import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI,Header
from fastapi.responses import JSONResponse
from sqlalchemy import select,text
from sqlalchemy.exc import SQLAlchemyError
from app.config import Settings
from app.eventstore.store import EventStore
from app.eventstore.models import EventRecord
from app.eventstore.projections import ProjectionEngine
from app.eventstore.outbox import OutboxRelay
from app.commands.order_commands import OrderCommands
from app.queries.order_queries import OrderQueries
from app.routers.cqrs import router
from shared.kafka import EventPublisher
from shared.health import HealthResponse,HEALTH_RESPONSES

# Factory accepts a store/publisher for isolated integration tests.
def create_cqrs_app(store=None,messaging=False,publisher=None,admin_key=None,resilience=False,inventory_client=None):
    settings=Settings()
    store=store if store is not None else EventStore(settings.database_url,settings.snapshot_threshold)
    key=admin_key if admin_key is not None else settings.admin_key
    @asynccontextmanager
    async def lifespan(application):
        relay=task=active_publisher=None
        try:
            if messaging:
                active_publisher=publisher if publisher is not None else EventPublisher(
                    os.getenv('KAFKA_BOOTSTRAP_SERVERS','localhost:29092'),'order-eventstore-producer')
                relay=OutboxRelay(store.sessions,active_publisher)
                task=asyncio.create_task(relay.run());application.state.relay_task=task
                application.state.publisher=active_publisher
            yield
        finally:
            if relay:
                relay.stop_event.set();await task
            if active_publisher:await asyncio.to_thread(active_publisher.close)
            if resilience:await application.state.inventory_client.close()
            await store.engine.dispose()
    application=FastAPI(title='OrderService Event Sourcing / CQRS',version='4.0.0',lifespan=lifespan)
    application.state.store=store;application.state.commands=OrderCommands(store)
    application.state.queries=OrderQueries(store.sessions)
    application.state.relay_task=None;application.state.publisher=None
    if resilience:
        from app.clients.inventory_client import InventoryClient
        from app.routers.resilience import router as resilience_router
        application.state.inventory_client=inventory_client if inventory_client is not None else InventoryClient.from_env()
        application.state.resilience_admin_key=key
        application.include_router(resilience_router)
    application.include_router(router)

    @application.exception_handler(SQLAlchemyError)
    async def database_failure(request,exception):
        return JSONResponse(status_code=503,content={'code':'DATABASE_UNAVAILABLE','message':'Database operation failed'})

    @application.post('/admin/rebuild-projections',tags=['Admin'],responses={403:{'description':'Clave administrativa inválida'}})
    async def rebuild(admin:str|None=Header(None,alias='X-Admin-Key')):
        if not admin or not secrets.compare_digest(admin,key):
            return JSONResponse(status_code=403,content={'detail':'Invalid admin key'})
        count=await ProjectionEngine(store.sessions).rebuild_all()
        return {'status':'completed','events_processed':count}

    @application.get('/health',response_model=HealthResponse,responses=HEALTH_RESPONSES)
    async def health():
        try:
            async with store.sessions() as session:
                await session.execute(select(EventRecord.id).limit(1))
            if messaging:
                task=application.state.relay_task
                if task is None or task.done() or not await asyncio.to_thread(application.state.publisher.ready):
                    raise RuntimeError('Outbox/Kafka no disponibles')
        except Exception:
            return JSONResponse(status_code=503,content={'status':'unhealthy','service':'order-service'})
        return {'status':'healthy','service':'order-service'}
    return application
