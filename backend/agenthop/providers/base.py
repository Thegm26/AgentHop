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

    @abstractmethod
    def command(
        self, account: str, mode: str, session_id: str | None = None
    ) -> str: ...
