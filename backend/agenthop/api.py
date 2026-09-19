from __future__ import annotations

import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from agenthop import __version__
from agenthop.models import (
    ActivationResponse,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    OnboardRequest,
    OnboardResponse,
    StateModel,
)
from agenthop.providers.base import DuplicateAccountError, UnknownAccountError
from agenthop.providers.codex import CodexAdapter
from agenthop.service import AccountService

LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")


def create_app(service: AccountService | None = None) -> FastAPI:
    app = FastAPI(title="AgentHop", version=__version__)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_ORIGIN_RE.pattern,
        allow_methods=["GET", "POST"],
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
            command = adapter.onboard(request.account)
        except DuplicateAccountError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=f"onboarding failed: {exc}") from exc
        return OnboardResponse(provider=provider, account=request.account, command=command)

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

    return app


app = create_app()
