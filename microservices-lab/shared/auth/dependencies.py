from fastapi import Depends,HTTPException,Request
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from .jwt_validator import JWTValidator,InvalidToken,AuthUnavailable
from .token_client import ServiceAuthenticationError

bearer=HTTPBearer(auto_error=False,scheme_name='BearerJWT')

async def current_user(request:Request,credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
    validator=getattr(request.app.state,'jwt_validator',None)
    if validator is None:return {}  # explicitly disabled factory for prior-lab regression tests
    if credentials is None:
        raise HTTPException(401,'Bearer token required',headers={'WWW-Authenticate':'Bearer'})
    try:return await validator.validate_token(credentials.credentials)
    except InvalidToken:
        raise HTTPException(401,'Invalid or expired access token',headers={'WWW-Authenticate':'Bearer'})
    except AuthUnavailable:
        raise HTTPException(503,'Authorization keys unavailable',headers={'Retry-After':'2'})

def permission(role,scope):
    async def required(request:Request,claims:dict=Depends(current_user)):
        if getattr(request.app.state,'jwt_validator',None) is None:return claims
        realm=claims.get('realm_access',{})
        roles=realm.get('roles',[]) if isinstance(realm,dict) else []
        raw_scope=claims.get('scope','')
        scopes=raw_scope.split() if isinstance(raw_scope,str) else []
        if not isinstance(roles,list) or role not in roles or scope not in scopes:
            raise HTTPException(403,'Insufficient role or scope')
        return claims
    return required

require_order_read=permission('order:read','orders.read')
require_order_write=permission('order:write','orders.write')
require_inventory_read=permission('inventory:read','inventory.read')
require_inventory_write=permission('inventory:write','inventory.write')
require_ops_admin=permission('ops:admin','ops.admin')

def configure_auth(app,audience,enabled=False,validator=None):
    app.state.jwt_validator=validator if validator is not None else JWTValidator.from_env(audience) if enabled else None
    @app.exception_handler(ServiceAuthenticationError)
    async def service_auth_failure(request,exception):
        return JSONResponse(status_code=503,content={'code':'SERVICE_AUTHENTICATION_FAILED','message':'Service authentication unavailable'})
    @app.get('/api/v1/auth/me',tags=['Auth'])
    async def me(claims:dict=Depends(current_user)):
        return {key:claims.get(key) for key in ['sub','preferred_username','azp','aud','scope','exp']}
