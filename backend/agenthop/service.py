from __future__ import annotations

from agenthop.models import ProviderModel, RecommendationModel, StateModel
from agenthop.providers.base import ProviderAdapter


class AccountService:
    def __init__(self, providers: list[ProviderAdapter]) -> None:
        self.providers = {provider.id: provider for provider in providers}

    def provider(self, provider_id: str) -> ProviderAdapter:
        try:
            return self.providers[provider_id]
        except KeyError as exc:
            raise ValueError(f"unknown provider: {provider_id}") from exc

    def state(self, *, refresh: bool = False) -> StateModel:
        provider_models = []
        accounts = []
        sessions = []
        for adapter in self.providers.values():
            errors: list[str] = []
            try:
                provider = adapter.provider()
            # Provider plugins are an isolation boundary; one must not break state.
            except Exception as exc:  # noqa: BLE001
                provider = ProviderModel(
                    id=adapter.id,
                    name=adapter.name,
                    available=False,
                    error=f"provider inspection failed: {exc}",
                )
            try:
                accounts.extend(adapter.accounts(refresh=refresh))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"account discovery failed: {exc}")
            try:
                sessions.extend(adapter.sessions())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"session discovery failed: {exc}")
            if errors:
                detail = "; ".join(filter(None, [provider.error, *errors]))
                provider = provider.model_copy(update={"error": detail})
            provider_models.append(provider)
        candidates = [
            account
            for account in accounts
            if account.authenticated
            and not account.duplicate
            and (
                account.usage is None
                or account.usage.status in {"ready", "close", "critical"}
            )
        ]
        recommendation = None
        if candidates:

            def capacity(account):
                usage = account.usage
                if usage is None:
                    return (-1, -1)
                return (
                    -1 if usage.weekly_used is None else 100 - usage.weekly_used,
                    -1 if usage.five_hour_used is None else 100 - usage.five_hour_used,
                )

            chosen = max(candidates, key=capacity)
            recommendation = RecommendationModel(
                provider=chosen.provider,
                account=chosen.id,
                reason="most available known capacity"
                if chosen.usage
                else "authenticated account",
            )
        return StateModel(
            providers=provider_models,
            accounts=accounts,
            sessions=sessions,
            recommendation=recommendation,
        )
