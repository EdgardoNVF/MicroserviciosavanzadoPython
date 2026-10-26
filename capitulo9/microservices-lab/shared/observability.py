import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends
from fastapi.responses import JSONResponse, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


REGISTRY = CollectorRegistry()
REQUESTS = Counter(
    'lab_http_requests_total', 'HTTP requests',
    ['service', 'method', 'route', 'status', 'traffic'], registry=REGISTRY,
)
DURATION = Histogram(
    'lab_http_duration_seconds', 'HTTP duration in seconds',
    ['service', 'method', 'route', 'traffic'],
    buckets=(.01, .025, .05, .1, .25, .5, .75, 1, 2, 5, 10),
    registry=REGISTRY,
)
ACTIVE = Gauge(
    'lab_http_in_progress', 'HTTP requests in progress',
    ['service'], registry=REGISTRY,
)


class JsonFormatter(logging.Formatter):
    def __init__(self, service):
        super().__init__()
        self.service = service

    def format(self, record):
        context = trace.get_current_span().get_span_context()
        value = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'service': self.service,
            'event': record.getMessage(),
            'trace_id': format(context.trace_id, '032x') if context.is_valid else None,
            'span_id': format(context.span_id, '016x') if context.is_valid else None,
        }
        for field in ('method', 'route', 'status', 'duration_ms'):
            if hasattr(record, field):
                value[field] = getattr(record, field)
        # No cuerpos, cabeceras, tokens ni detalles de excepciones.
        if record.exc_info:
            value['exception_type'] = record.exc_info[0].__name__
        return json.dumps(value, ensure_ascii=False)


def configure_observability(service):
    if os.getenv('OBSERVABILITY_ENABLED', 'false').lower() != 'true':
        return None

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service))
    logger = logging.getLogger('lab08.http')
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    provider = TracerProvider(resource=Resource.create({'service.name': service}))
    exporter = OTLPSpanExporter(
        endpoint=os.environ['OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'], timeout=3,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # Llamar antes de crear los clientes HTTPX de la aplicacion.
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    return provider


class HttpSignals:
    def __init__(self, app, service):
        self.app = app
        self.service = service

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] in ('/health', '/metrics'):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500
        ACTIVE.labels(self.service).inc()

        async def send_with_trace(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                context = trace.get_current_span().get_span_context()
                if context.is_valid:
                    headers = list(message.get('headers', []))
                    headers.append((b'x-trace-id', format(context.trace_id, '032x').encode()))
                    message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(scope.get('route'), 'path', 'unmatched')
            traffic = 'lab' if route.startswith('/api/v1/lab08/') else 'business'
            REQUESTS.labels(self.service, scope['method'], route, str(status), traffic).inc()
            DURATION.labels(self.service, scope['method'], route, traffic).observe(elapsed)
            ACTIVE.labels(self.service).dec()
            logging.getLogger('lab08.http').info('http_request', extra={
                'method': scope['method'], 'route': route, 'status': status,
                'duration_ms': round(elapsed * 1000, 2),
            })


def install_observability(app, service, provider, permission_dependency):
    if provider is None:
        return

    @app.get('/metrics', include_in_schema=False)
    def metrics():
        return Response(generate_latest(REGISTRY), headers={'Content-Type': CONTENT_TYPE_LATEST})

    if os.getenv('LAB08_PROBES_ENABLED', 'false').lower() == 'true':
        short = 'orders' if service == 'order-service' else 'inventory'

        @app.get('/api/v1/lab08/' + short + '/probe',
                 dependencies=[Depends(permission_dependency)], tags=['Lab08'])
        async def probe(slow: bool = False, fail: bool = False):
            if slow:
                await asyncio.sleep(.8)
            return JSONResponse(
                status_code=500 if fail else 200,
                content={'service': service, 'simulated_failure': fail, 'slow': slow},
            )

    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original(application) as state:
                yield state
        finally:
            await asyncio.to_thread(provider.shutdown)

    app.router.lifespan_context = lifespan
    app.add_middleware(HttpSignals, service=service)
    # OTel queda por fuera del middleware: el log ve el span HTTP activo.
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls='health,metrics',
    )
