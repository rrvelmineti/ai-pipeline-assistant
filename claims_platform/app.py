"""Application factory.  Run:  uvicorn claims_platform.app:create_app --factory"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import router
from .config import Settings
from .db import Base, make_engine, make_session_factory
from .processing import recover_interrupted
from .security import load_cipher
from .storage import make_store

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def create_app(settings=None):
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    Session = make_session_factory(engine)
    cipher = load_cipher(settings)

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        with Session() as db:
            recovered = recover_interrupted(db)
            db.commit()
        app.state.recovered_at_startup = recovered
        from .bootstrap import bootstrap
        app.state.seed_thread = bootstrap(settings, Session, engine)
        yield
        engine.dispose()

    app = FastAPI(title="Claims Onboarding and Exception Management Platform", version=__version__,
                  lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings, app.state.engine, app.state.Session = settings, engine, Session
    app.state.cipher, app.state.store = cipher, make_store(settings, Session, cipher)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", CSP)
        return response

    app.include_router(router)

    @app.exception_handler(ValueError)
    async def value_error(_request, exc):
        return JSONResponse({"detail": str(exc)[:300]}, status_code=422)

    dist = Path(settings.web_dist)
    if (dist / "index.html").exists():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found."}, status_code=404)
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")
    return app
