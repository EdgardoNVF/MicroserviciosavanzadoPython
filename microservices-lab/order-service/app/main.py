import os
from app.cqrs_app import create_cqrs_app

if os.getenv('RESILIENCE_ENABLED','false').lower()=='true' and os.getenv('EVENTSTORE_ENABLED','false').lower()!='true':
    raise RuntimeError('Lab04 requiere EVENTSTORE_ENABLED=true junto con RESILIENCE_ENABLED=true')

if os.getenv('AUTH_ENABLED','false').lower()=='true' and os.getenv('EVENTSTORE_ENABLED','false').lower()!='true':
    raise RuntimeError('Lab05 requiere EVENTSTORE_ENABLED=true')

if os.getenv('EVENTSTORE_ENABLED','false').lower()=='true':
    app=create_cqrs_app(messaging=os.getenv('MESSAGING_ENABLED','false').lower()=='true',
                        resilience=os.getenv('RESILIENCE_ENABLED','false').lower()=='true',
                        auth=os.getenv('AUTH_ENABLED','false').lower()=='true')
