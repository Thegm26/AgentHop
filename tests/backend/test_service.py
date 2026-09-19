from agenthop.models import AccountModel, ProviderModel, UsageModel
from agenthop.providers.base import ProviderAdapter
from agenthop.service import AccountService


class CapacityProvider(ProviderAdapter):
    id = "capacity"
    name = "Capacity"

    def provider(self):
        return ProviderModel(id=self.id, name=self.name, available=True)

    def accounts(self, *, refresh=False):
        return [
            AccountModel(
                provider=self.id,
                id="low",
                active=True,
                authenticated=True,
                usage=UsageModel(status="close", weeklyUsed=80, fiveHourUsed=20),
            ),
            AccountModel(
                provider=self.id,
                id="high",
                active=False,
                authenticated=True,
                usage=UsageModel(status="ready", weeklyUsed=20, fiveHourUsed=50),
            ),
            AccountModel(
                provider=self.id,
                id="blocked",
                active=False,
                authenticated=True,
                usage=UsageModel(status="blocked", weeklyUsed=100, fiveHourUsed=0),
            ),
        ]

    def sessions(self):
        return []

    def activate(self, account):
        pass

    def command(self, account, mode, session_id=None):
        return "capacity"


def test_recommends_most_weekly_capacity() -> None:
    state = AccountService([CapacityProvider()]).state(refresh=True)
    assert state.recommendation is not None
    assert state.recommendation.account == "high"


class BrokenProvider(CapacityProvider):
    id = "broken"
    name = "Broken"

    def accounts(self, *, refresh=False):
        raise OSError("profiles unavailable")

    def sessions(self):
        raise RuntimeError("database busy")

    def provider(self):
        raise RuntimeError("inspection unavailable")


def test_provider_failures_are_reported_without_breaking_state() -> None:
    state = AccountService([BrokenProvider(), CapacityProvider()]).state(refresh=True)
    assert state.providers[0].error is not None
    assert state.providers[0].available is False
    assert "provider inspection failed" in state.providers[0].error
    assert "account discovery failed" in state.providers[0].error
    assert "session discovery failed" in state.providers[0].error
    assert state.recommendation is not None
    assert state.recommendation.account == "high"


class PartialUsageProvider(CapacityProvider):
    def accounts(self, *, refresh=False):
        return [
            AccountModel(
                provider=self.id,
                id="unknown-week",
                active=True,
                authenticated=True,
                usage=UsageModel(status="ready", fiveHourUsed=1),
            ),
            AccountModel(
                provider=self.id,
                id="critical-known",
                active=False,
                authenticated=True,
                usage=UsageModel(status="critical", weeklyUsed=95, fiveHourUsed=96),
            ),
        ]


def test_recommendation_does_not_treat_unknown_window_as_full_capacity() -> None:
    state = AccountService([PartialUsageProvider()]).state(refresh=True)
    assert state.recommendation is not None
    assert state.recommendation.account == "critical-known"
