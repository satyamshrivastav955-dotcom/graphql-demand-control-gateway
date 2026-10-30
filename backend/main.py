import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import routes
from backend.api.gateway import GraphQLGateway
from backend.api.static import mount_dashboard
from backend.core.config import Settings, load_settings
from backend.core.runtime.events import EventStore


def create_app(settings: Optional[Settings] = None, gateway: Optional[GraphQLGateway] = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=logging.DEBUG if settings.app.debug else logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = gateway.store if gateway else EventStore(settings.resolved_db_path(), settings.storage.max_events)
        gw = gateway or GraphQLGateway(settings, store)
        await gw.startup()
        app.state.gateway = gw
        log = logging.getLogger("sentinel")
        if not settings.api.auth_required:
            log.warning("Management API authentication is DISABLED (api.auth_required=false); development only")
        elif not settings.api.token:
            log.warning("SENTINEL_API_TOKEN is not set: management endpoints return 503 until it is configured")
        if settings.gateway.mode == "simulation":
            log.warning("Simulation mode: allowed operations get a fake response; never use in production")
        yield
        await gw.shutdown()
        store.close()

    app = FastAPI(
        title=settings.app.name, version=settings.app.version, lifespan=lifespan,
        docs_url="/docs" if settings.app.debug else None, redoc_url=None,
        openapi_url="/openapi.json" if settings.app.debug else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
        expose_headers=["X-Sentinel-Decision", "Retry-After"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(routes.router)
    mount_dashboard(app, settings)  # last: API routes always win
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
