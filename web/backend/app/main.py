"""App factory. Wires settings, middleware and routers; nothing else.

If you're adding stuff, it almost certainly goes elsewhere:
    new endpoints  → ``routers/``
    new providers  → ``dependencies.py``
    new knobs      → ``settings.py``
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from web.backend.app.routers import health, reports
from web.backend.app.settings import (
    API_DESCRIPTION,
    API_SUMMARY,
    API_TITLE,
    API_VERSION,
    CORS_ORIGINS,
    SWAGGER_UI_PARAMETERS,
    TAGS_METADATA,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        summary=API_SUMMARY,
        description=API_DESCRIPTION,
        contact={"name": "Tomás Rodeghiero", "email": "tomyrodeghiero@gmail.com"},
        license_info={"name": "MIT"},
        openapi_tags=TAGS_METADATA,
        docs_url="/docs",
        redoc_url="/redoc",
        swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        # Any Vercel deployment (production, preview, or rename) is allowed
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    app.include_router(health.router)
    app.include_router(reports.router)

    return app


app = create_app()
