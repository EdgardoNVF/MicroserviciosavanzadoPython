import asyncio
import os
import time
import math
import httpx
import jwt

class InvalidToken(Exception):pass
class AuthUnavailable(Exception):pass

class JWTValidator:
    """Resource-server validator: fixed RS256/issuer/audience and trusted JWKS URL."""
    def __init__(self,issuer,audience,jwks_url,ttl=60,refresh_interval=2,transport=None,clock=time.monotonic):
        if not issuer or not audience or not jwks_url:raise ValueError('Issuer, audience and JWKS are required')
        self.issuer=issuer
        self.audience=audience
        self.jwks_url=jwks_url
        self.ttl=ttl
        self.refresh_interval=refresh_interval
        self.clock=clock
        self.keys={}
        self.fetched_at=float('-inf')
        self.lock=asyncio.Lock()
        self.http=httpx.AsyncClient(timeout=2,transport=transport,trust_env=False,follow_redirects=False)

    @classmethod
    def from_env(cls,audience):
        return cls(issuer=os.environ['AUTH_ISSUER'],audience=audience,
                   jwks_url=os.environ['AUTH_JWKS_URL'],ttl=int(os.getenv('AUTH_JWKS_TTL','60')))

    async def _refresh(self):
        try:
            response=await self.http.get(self.jwks_url)
            response.raise_for_status()
            if len(response.content)>65536:raise ValueError('JWKS too large')
            raw=response.json()['keys']
            if not isinstance(raw,list) or len(raw)>50:raise ValueError('Invalid JWKS')
            keys={}
            for entry in raw:
                if not isinstance(entry,dict):raise ValueError('Invalid JWK entry')
                kid=entry.get('kid')
                if entry.get('kty')!='RSA' or entry.get('use','sig')!='sig' or entry.get('alg','RS256')!='RS256':continue
                if not isinstance(kid,str) or not kid or kid in keys:raise ValueError('Invalid/ambiguous kid')
                key=jwt.PyJWK.from_dict(entry,algorithm='RS256').key
                if key.key_size<2048:raise ValueError('Weak RSA key')
                keys[kid]=key
            if not keys:raise ValueError('No usable signing keys')
        except (httpx.HTTPError,ValueError,KeyError,TypeError,jwt.PyJWTError) as exc:
            raise AuthUnavailable('JWKS unavailable') from exc
        self.keys=keys
        self.fetched_at=self.clock()

    async def _key(self,kid):
        # Double-checked lock prevents concurrent cold-cache downloads.
        async with self.lock:
            if self.clock()-self.fetched_at>=self.ttl:await self._refresh()
            if kid not in self.keys and self.clock()-self.fetched_at>=self.refresh_interval:
                await self._refresh()
            key=self.keys.get(kid)
        if key is None:raise InvalidToken('Unknown signing key')
        return key

    async def validate_token(self,token):
        try:
            if not isinstance(token,str) or len(token)>16384:raise InvalidToken('Invalid token size')
            header=jwt.get_unverified_header(token)
            kid=header.get('kid')
            if header.get('alg')!='RS256' or header.get('crit') or header.get('b64') is False:
                raise InvalidToken('Unsupported JWT header')
            if not isinstance(kid,str) or not kid or len(kid)>200:raise InvalidToken('Missing kid')
            key=await self._key(kid)
            claims=jwt.decode(token,key,algorithms=['RS256'],issuer=self.issuer,audience=self.audience,
                leeway=0,options={'require':['exp','iat','iss','aud','sub'],
                                  'verify_signature':True,'verify_exp':True,'verify_iss':True,'verify_aud':True})
            if claims.get('typ')!='Bearer':raise InvalidToken('Not an access token')
            for name in ['exp','iat']:
                value=claims[name]
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise InvalidToken('Invalid numeric date')
            if not isinstance(claims['sub'],str) or not claims['sub']:raise InvalidToken('Invalid subject')
            return claims
        except jwt.PyJWTError as exc:raise InvalidToken('Invalid or expired token') from exc

    async def close(self):await self.http.aclose()
