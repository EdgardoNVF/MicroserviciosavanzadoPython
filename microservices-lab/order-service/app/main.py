import os
from app.cqrs_app import create_cqrs_app

if os.getenv('EVENTSTORE_ENABLED','false').lower()=='true':
    app=create_cqrs_app(messaging=os.getenv('MESSAGING_ENABLED','false').lower()=='true',
                        resilience=os.getenv('RESILIENCE_ENABLED','false').lower()=='true')
