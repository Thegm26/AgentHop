from __future__ import annotations

from fastapi.testclient import TestClient

from agenthop.api import create_app
from agenthop.models import AccountModel, ProviderModel, SessionModel, UsageModel
from agenthop.providers.base import ProviderAdapter
from agenthop.service import AccountService


class FakeProvider(ProviderAdapter):
    id = "fake"
    name = "Fake Provider"

    def __init__(self) -> None:
        self.activated: str | None = None
        self.refreshed = False

    def provider(self) -> ProviderModel:
        return ProviderModel(id=self.id, name=self.name, available=True)

    def accounts(self, *, refresh: bool = False) -> list[AccountModel]:
        self.refreshed = refresh
        return [
            AccountModel(
                provider=self.id,
                id="work",
                active=True,
                authenticated=True,
                usage=UsageModel(status="ready", weeklyUsed=10, fiveHourUsed=25)
                if refresh
                else None,
            )
        ]

    def sessions(self) -> list[SessionModel]:
        return [
            SessionModel(provider=self.id, id="session-1", title="Demo", updatedAt=123)
        ]

    def activate(self, account: str) -> None:
        if account != "work":
            raise ValueError("unknown account")
        self.activated = account

    def command(self, account: str, mode: str, session_id: str | None = None) -> str:
        if account != "work":
            raise ValueError("unknown account")
        return f"fake {mode} {session_id or ''}".strip()


def client_and_provider() -> tuple[TestClient, FakeProvider]:
    provider = FakeProvider()
    return TestClient(create_app(AccountService([provider]))), provider


def test_health_and_state_schema() -> None:
    client, _ = client_and_provider()
    assert client.get("/api/health").json() == {"status": "ok", "version": "0.1.0"}

    response = client.get("/api/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"] == [
        {"id": "fake", "name": "Fake Provider", "available": True, "error": None}
    ]
    assert payload["accounts"][0]["id"] == "work"
    assert payload["sessions"][0] == {
        "provider": "fake",
        "id": "session-1",
        "title": "Demo",
        "updatedAt": 123,
    }
    assert payload["recommendation"]["account"] == "work"


def test_refresh_collects_live_usage() -> None:
    client, provider = client_and_provider()
    response = client.post("/api/refresh")
    assert response.status_code == 200
    assert provider.refreshed is True
    assert response.json()["accounts"][0]["usage"]["fiveHourUsed"] == 25


def test_activate_and_command() -> None:
    client, provider = client_and_provider()
    response = client.post("/api/providers/fake/accounts/work/activate")
    assert response.json() == {"provider": "fake", "account": "work", "active": True}
    assert provider.activated == "work"

    response = client.post(
        "/api/providers/fake/accounts/work/command",
        json={"mode": "resume", "sessionId": "session-1"},
    )
    assert response.json() == {"command": "fake resume session-1"}


def test_api_rejects_invalid_mode_and_unknown_provider() -> None:
    client, _ = client_and_provider()
    assert (
        client.post(
            "/api/providers/fake/accounts/work/command", json={"mode": "delete"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/providers/missing/accounts/work/command", json={"mode": "new"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/providers/fake/accounts/work/command",
            json={"mode": "new", "auth": "must-not-be-accepted"},
        ).status_code
        == 422
    )


def test_remote_browser_origin_is_rejected() -> None:
    client, provider = client_and_provider()
    response = client.post(
        "/api/providers/fake/accounts/work/activate",
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert provider.activated is None


def test_untrusted_host_is_rejected() -> None:
    client, _ = client_and_provider()
    assert (
        client.get("/api/health", headers={"Host": "attacker.example"}).status_code
        == 400
    )
