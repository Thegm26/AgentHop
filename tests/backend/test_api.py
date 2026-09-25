from __future__ import annotations

from fastapi.testclient import TestClient

from agenthop.api import create_app
from agenthop.models import AccountModel, ProviderModel, SessionModel, UsageModel
from agenthop.providers.base import DuplicateAccountError, ProviderAdapter
from agenthop.service import AccountService


class FakeProvider(ProviderAdapter):
    id = "fake"
    name = "Fake Provider"

    def __init__(self) -> None:
        self.activated: str | None = None
        self.refresh_count = 0
        self.onboarded: str | None = None
        self.removed: str | None = None
        self.redeemed: str | None = None

    def provider(self) -> ProviderModel:
        return ProviderModel(id=self.id, name=self.name, available=True)

    def accounts(self, *, refresh: bool = False) -> list[AccountModel]:
        if refresh:
            self.refresh_count += 1
        return [
            AccountModel(
                provider=self.id,
                id="work",
                active=True,
                authenticated=True,
                email="work@example.com",
                usage=UsageModel(
                    status="ready", weeklyUsed=10, fiveHourUsed=20 + self.refresh_count
                )
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

    def onboard(self, account: str) -> str:
        if account == "existing":
            raise DuplicateAccountError("account already exists: existing")
        if account not in {"new-account", "account-01"}:
            raise ValueError("invalid account name")
        self.onboarded = account
        return "CODEX_HOME=/safe/profile codex login"

    def default_account_name(self) -> str:
        return "account-01"

    def remove(self, account: str) -> None:
        if account not in {"default", "unusable"}:
            raise ValueError("unknown account")
        self.removed = account

    def redeem_reset_credit(self, account: str) -> str:
        if account != "work":
            raise ValueError("unknown account")
        self.redeemed = account
        return "reset"

    def command(self, account: str, mode: str, session_id: str | None = None) -> str:
        if account != "work":
            raise ValueError("unknown account")
        return f"fake {mode} {session_id or ''}".strip()


def client_and_provider() -> tuple[TestClient, FakeProvider]:
    provider = FakeProvider()
    return TestClient(create_app(AccountService([provider]))), provider


def test_health_and_state_schema() -> None:
    client, _ = client_and_provider()
    assert client.get("/api/health").json() == {"status": "ok", "version": "0.4.0"}

    response = client.get("/api/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"] == [
        {"id": "fake", "name": "Fake Provider", "available": True, "error": None}
    ]
    assert payload["accounts"][0]["id"] == "work"
    assert payload["accounts"][0]["email"] == "work@example.com"
    assert payload["sessions"][0] == {
        "provider": "fake",
        "id": "session-1",
        "title": "Demo",
        "updatedAt": 123,
    }
    assert payload["recommendation"]["account"] == "work"


def test_refresh_regenerates_live_usage_on_every_request() -> None:
    client, provider = client_and_provider()
    first = client.post("/api/refresh")
    second = client.post("/api/refresh")

    assert first.status_code == second.status_code == 200
    assert provider.refresh_count == 2
    assert first.json()["accounts"][0]["usage"]["fiveHourUsed"] == 21
    assert second.json()["accounts"][0]["usage"]["fiveHourUsed"] == 22


def test_refresh_only_accepts_post() -> None:
    client, _provider = client_and_provider()
    response = client.get("/api/refresh")
    assert response.status_code == 404


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


def test_redeem_reset_credit_returns_the_codex_outcome() -> None:
    client, provider = client_and_provider()

    response = client.post("/api/providers/fake/accounts/work/reset-credit/redeem")

    assert response.status_code == 200
    assert response.json() == {"outcome": "reset"}
    assert provider.redeemed == "work"


def test_onboard_returns_a_terminal_command_without_accepting_credentials() -> None:
    client, provider = client_and_provider()

    response = client.post(
        "/api/providers/fake/accounts", json={"account": "new-account"}
    )

    assert response.status_code == 201
    assert response.json() == {
        "provider": "fake",
        "account": "new-account",
        "command": "CODEX_HOME=/safe/profile codex login",
    }
    assert provider.onboarded == "new-account"


def test_onboard_rejects_duplicates_invalid_names_and_unknown_providers() -> None:
    client, _ = client_and_provider()

    assert client.post(
        "/api/providers/fake/accounts", json={"account": "existing"}
    ).status_code == 409
    assert client.post(
        "/api/providers/fake/accounts", json={"account": "not valid"}
    ).status_code == 400
    assert client.post(
        "/api/providers/missing/accounts", json={"account": "new-account"}
    ).status_code == 404
    generated = client.post("/api/providers/fake/accounts", json={"account": ""})
    assert generated.status_code == 201
    assert generated.json()["account"] == "account-01"


def test_remove_account_accepts_default_and_reports_success() -> None:
    client, provider = client_and_provider()

    response = client.delete("/api/providers/fake/accounts/unusable")
    assert response.status_code == 200
    assert response.json() == {"provider": "fake", "account": "unusable", "removed": True}
    assert provider.removed == "unusable"
    response = client.delete("/api/providers/fake/accounts/default")
    assert response.status_code == 200
    assert response.json() == {"provider": "fake", "account": "default", "removed": True}
    assert provider.removed == "default"


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


def test_built_frontend_is_served_without_intercepting_api(tmp_path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>desktop app</html>")
    monkeypatch.setenv("AGENTHOP_FRONTEND_DIST", str(dist))
    client = TestClient(create_app(AccountService([FakeProvider()])))

    assert client.get("/").text == "<html>desktop app</html>"
    assert client.get("/nested/route").text == "<html>desktop app</html>"
    assert client.get("/api/health").json()["status"] == "ok"
