from __future__ import annotations

import os
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agenthop import __version__
from agenthop.models import (
    ActivationResponse,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    OnboardRequest,
    OnboardResponse,
    RemovalResponse,
    StateModel,
)
from agenthop.providers.base import DuplicateAccountError, UnknownAccountError
from agenthop.providers.codex import CodexAdapter
from agenthop.service import AccountService

LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")


def frontend_dist() -> Path | None:
    """Return a built frontend without relying on the current working directory."""
    configured = os.environ.get("AGENTHOP_FRONTEND_DIST")
    candidates = ([Path(configured)] if configured else []) + [
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def create_app(service: AccountService | None = None) -> FastAPI:
    app = FastAPI(title="AgentHop", version=__version__)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_ORIGIN_RE.pattern,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.state.account_service = service or AccountService([CodexAdapter()])

    @app.middleware("http")
    async def reject_remote_browser_origins(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and not LOCAL_ORIGIN_RE.fullmatch(origin):
            return JSONResponse(
                status_code=403, content={"detail": "remote origins are not allowed"}
            )
        return await call_next(request)

    def current_service() -> AccountService:
        return app.state.account_service

    dist = frontend_dist()
    if dist and (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @app.get("/api/state", response_model=StateModel, response_model_by_alias=True)
    def state() -> StateModel:
        return current_service().state(refresh=False)

    @app.post("/api/refresh", response_model=StateModel, response_model_by_alias=True)
    def refresh() -> StateModel:
        return current_service().state(refresh=True)

    @app.post(
        "/api/providers/{provider}/accounts",
        response_model=OnboardResponse,
        status_code=201,
    )
    def onboard(provider: str, request: OnboardRequest) -> OnboardResponse:
        try:
            adapter = current_service().provider(provider)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            account = request.account if request.account.strip() else adapter.default_account_name()
            command = adapter.onboard(account)
        except DuplicateAccountError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=f"onboarding failed: {exc}") from exc
        return OnboardResponse(provider=provider, account=account, command=command)

    @app.delete(
        "/api/providers/{provider}/accounts/{account}",
        response_model=RemovalResponse,
    )
    def remove(provider: str, account: str) -> RemovalResponse:
        try:
            adapter = current_service().provider(provider)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            adapter.remove(account)
        except UnknownAccountError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"profile removal failed: {exc}") from exc
        return RemovalResponse(provider=provider, account=account, removed=True)

    @app.post(
        "/api/providers/{provider}/accounts/{account}/activate",
        response_model=ActivationResponse,
    )
    def activate(provider: str, account: str) -> ActivationResponse:
        try:
            adapter = current_service().provider(provider)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            adapter.activate(account)
        except UnknownAccountError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DuplicateAccountError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"activation failed: {exc}"
            ) from exc
        return ActivationResponse(provider=provider, account=account, active=True)

    @app.post(
        "/api/providers/{provider}/accounts/{account}/command",
        response_model=CommandResponse,
    )
    def command(
        provider: str, account: str, request: CommandRequest
    ) -> CommandResponse:
        try:
            adapter = current_service().provider(provider)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            value = adapter.command(account, request.mode, request.session_id)
        except UnknownAccountError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DuplicateAccountError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(
                status_code=500, detail=f"command preparation failed: {exc}"
            ) from exc
        return CommandResponse(command=value)

    if dist:

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            # API routes are defined above; this is deliberately only the SPA fallback.
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            requested = (dist / path).resolve()
            if path and requested.is_file() and requested.is_relative_to(dist):
                return FileResponse(requested)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
