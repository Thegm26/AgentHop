from __future__ import annotations

from abc import ABC, abstractmethod

from agenthop.models import AccountModel, ProviderModel, SessionModel


class UnknownAccountError(LookupError):
    """The requested local account does not exist."""


class DuplicateAccountError(ValueError):
    """The requested account is intentionally disabled as a duplicate."""


class ProviderAdapter(ABC):
    """Contract implemented by local coding-agent account providers."""

    id: str
    name: str

    @abstractmethod
    def provider(self) -> ProviderModel: ...

    @abstractmethod
    def accounts(self, *, refresh: bool = False) -> list[AccountModel]: ...

    @abstractmethod
    def sessions(self) -> list[SessionModel]: ...

    @abstractmethod
    def activate(self, account: str) -> None: ...

    def onboard(self, account: str) -> str:
        raise NotImplementedError("account onboarding is not supported by this provider")

    def default_account_name(self) -> str:
        raise ValueError("an account name is required for this provider")

    def remove(self, account: str) -> None:
        raise NotImplementedError("account removal is not supported by this provider")

    def redeem_reset_credit(self, account: str) -> str:
        raise NotImplementedError("usage-limit reset credits are not supported by this provider")

    @abstractmethod
    def command(
        self, account: str, mode: str, session_id: str | None = None
    ) -> str: ...
