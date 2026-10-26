import asyncio
import hashlib
import hmac
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import hvac
from fastapi import Depends, HTTPException


log = logging.getLogger("lab07.vault")


class VaultRuntime:
    def __init__(self, service):
        self.service = service
        self.role = os.environ["VAULT_ROLE"]
        self.path = os.environ["VAULT_SECRET_PATH"]
        self.mount = os.getenv("VAULT_KV_MOUNT", "lab07")
        self.jwt_file = os.getenv("VAULT_JWT_FILE", "/var/run/vault/token")
        self.client = hvac.Client(url=os.environ["VAULT_ADDR"], timeout=3)
        self.lock = threading.RLock()
        self.secret = None
        self.version = None
        self.last_read = 0.0
        self.next_renew = 0.0
        self.renewals = 0
        self.logins = 0
        self.degraded = False
        self.instance = str(uuid4())

    def login(self):
        # Leer el archivo nuevamente: Kubernetes renueva el JWT proyectado.
        jwt = Path(self.jwt_file).read_text().strip()
        self.client.auth.kubernetes.login(role=self.role, jwt=jwt)
        self.logins += 1
        self.next_renew = time.monotonic() + 30
        log.info("Vault login correcto: service=%s", self.service)

    def refresh(self):
        with self.lock:
            if not self.client.token:
                self.login()
            elif time.monotonic() >= self.next_renew:
                try:
                    self.client.auth.token.renew_self()
                    self.renewals += 1
                    self.next_renew = time.monotonic() + 30
                    log.info("Vault token renovado: service=%s", self.service)
                except hvac.exceptions.Forbidden:
                    # Token expirado o revocado: autenticar de nuevo.
                    self.client.token = None
                    self.login()

            try:
                result = self.client.secrets.kv.v2.read_secret_version(
                    path=self.path,
                    mount_point=self.mount,
                    raise_on_deleted_version=True,
                )
            except hvac.exceptions.Forbidden:
                # No utilizar la cache para ocultar una denegacion explicita.
                self.secret = None
                self.client.token = None
                raise

            value = result["data"]["data"]["signing_key"]
            if not isinstance(value, str) or len(value) < 32:
                self.secret = None
                raise ValueError("Clave de demostracion invalida")

            self.secret = value
            self.version = result["data"]["metadata"]["version"]
            self.last_read = time.monotonic()
            self.degraded = False

    def start(self):
        # Sin token root, sin secreto por defecto y sin cache inicial en disco.
        self.client.token = None
        self.refresh()

    def refresh_safely(self):
        try:
            self.refresh()
        except Exception as exc:
            with self.lock:
                self.degraded = True
            # No registrar mensajes que pudieran incluir datos o credenciales.
            log.warning("Vault refresh fallo: service=%s type=%s",
                        self.service, type(exc).__name__)

    def view(self):
        with self.lock:
            age = time.monotonic() - self.last_read
            if self.secret is None or age > 120:
                raise HTTPException(503, "Secreto no disponible o cache vencida")
            proof = hmac.new(
                self.secret.encode(), b"lab07-proof", hashlib.sha256
            ).hexdigest()
            return {
                "service": self.service,
                "instance_id": self.instance,
                "secret_version": self.version,
                "proof": proof,
                "source": "cache" if self.degraded else "vault",
                "cache_age_seconds": round(age, 1),
                "token_renewals": self.renewals,
                "logins": self.logins,
            }

    def close(self):
        try:
            if self.client.token:
                self.client.auth.token.revoke_self()
        except Exception:
            pass
        finally:
            self.client.adapter.close()


def install_vault(app, service, path, permission_dependency):
    if os.getenv("VAULT_ENABLED", "false").lower() != "true":
        return

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        runtime = VaultRuntime(service)
        application.state.lab07_vault = runtime
        stop = asyncio.Event()
        task = None

        async def refresh_loop():
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    await asyncio.to_thread(runtime.refresh_safely)

        try:
            await asyncio.to_thread(runtime.start)
            task = asyncio.create_task(refresh_loop())
            # Conservar el lifespan original: BD, Kafka, Redis y autenticacion.
            async with original_lifespan(application) as state:
                yield state
        finally:
            stop.set()
            if task is not None:
                await task
            await asyncio.to_thread(runtime.close)

    app.router.lifespan_context = lifespan

    async def state_endpoint():
        return await asyncio.to_thread(application_runtime_view)

    def application_runtime_view():
        return app.state.lab07_vault.view()

    app.add_api_route(
        path,
        state_endpoint,
        methods=["GET"],
        tags=["Lab07 Vault"],
        dependencies=[Depends(permission_dependency)],
    )
