from shared.auth import configure_auth
import asyncio
import logging
import os
from contextlib import asynccontextmanager
import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.routers.product import router
from app.services.inventory_service import InventoryService
from app.services.redis_inventory import RedisInventoryService
from app.messaging import InventoryWorker
from shared.kafka import EventPublisher
from shared.health import HealthResponse, HEALTH_RESPONSES

logging.basicConfig(level=logging.INFO)

def create_app(messaging=False, service=None,auth=False,jwt_validator=None):
    @asynccontextmanager
    async def lifespan(application):
        client = publisher = worker = None
        try:
            if messaging:
                client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                    decode_responses=True, socket_timeout=3, socket_connect_timeout=3)
                await asyncio.to_thread(client.ping)
                application.state.service = RedisInventoryService(client)
                bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
                publisher = EventPublisher(bootstrap, "inventory-service-producer")
                worker = InventoryWorker(application.state.service, publisher, bootstrap)
                application.state.worker = worker
                worker.start()
            yield
        finally:
            if worker:
                await asyncio.to_thread(worker.stop)
            if publisher:
                await asyncio.to_thread(publisher.close)
            if client:
                client.close()
            if application.state.jwt_validator:await application.state.jwt_validator.close()
    application = FastAPI(title="InventoryService", version="2.0.0", lifespan=lifespan)
    configure_auth(application,'inventory-api',auth,jwt_validator)
    application.state.service = service if service is not None else InventoryService()
    application.state.worker = None
    application.include_router(router)
    @application.get("/health", response_model=HealthResponse, responses=HEALTH_RESPONSES)
    def health():
        if messaging:
            try:
                worker = application.state.worker
                if worker is None or not worker.ready.is_set() or not worker.thread.is_alive():
                    raise RuntimeError("Consumidor no preparado")
                application.state.service.client.ping()
                if not worker.publisher.ready():
                    raise RuntimeError("Kafka no disponible")
            except Exception:
                return JSONResponse(status_code=503, content={"status":"unhealthy", "service":"inventory-service"})
        return {"status": "healthy", "service": "inventory-service"}
    return application

app = create_app(messaging=os.getenv("MESSAGING_ENABLED", "false").lower() == "true",
                 auth=os.getenv("AUTH_ENABLED","false").lower()=="true")
