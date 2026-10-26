import os
from app.cqrs_app import create_cqrs_app

from shared.observability import configure_observability, install_observability

observability_provider = configure_observability("order-service")



if os.getenv('RESILIENCE_ENABLED','false').lower()=='true' and os.getenv('EVENTSTORE_ENABLED','false').lower()!='true':
    raise RuntimeError('Lab04 requiere EVENTSTORE_ENABLED=true junto con RESILIENCE_ENABLED=true')

if os.getenv('AUTH_ENABLED','false').lower()=='true' and os.getenv('EVENTSTORE_ENABLED','false').lower()!='true':
    raise RuntimeError('Lab05 requiere EVENTSTORE_ENABLED=true')

if os.getenv('EVENTSTORE_ENABLED','false').lower()=='true':
    app=create_cqrs_app(messaging=os.getenv('MESSAGING_ENABLED','false').lower()=='true',
                        resilience=os.getenv('RESILIENCE_ENABLED','false').lower()=='true',
                        auth=os.getenv('AUTH_ENABLED','false').lower()=='true')

from shared.vault_runtime import install_vault
from shared.auth.dependencies import permission

install_vault(
    app,
    service="order-service",
    path="/api/v1/lab07/orders",
    permission_dependency=permission("order:read", "orders.read"),
)


install_observability(
    app,
    service="order-service",
    provider=observability_provider,
    permission_dependency=permission("order:read", "orders.read"),
)
