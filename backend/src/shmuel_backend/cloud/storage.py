from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CloudFolder:
    id: str
    name: str
    web_view_url: str | None = None


@dataclass(frozen=True)
class CloudFile:
    id: str
    name: str
    mime_type: str
    size_bytes: int
    web_view_url: str | None = None
    thumbnail_url: str | None = None


class CloudStorageError(RuntimeError):
    pass


class CloudUnauthorizedError(CloudStorageError):
    """Raised when the connection's credentials no longer work — re-auth needed."""


class CloudStorage(Protocol):
    """Provider-agnostic storage interface.

    Implementations are passed a per-call refresh token rather than holding
    state, so the same instance is safe to reuse across requests.
    """

    provider_name: str

    async def ensure_root_folder(
        self, refresh_token: str, name: str
    ) -> CloudFolder: ...

    async def ensure_subfolder(
        self, refresh_token: str, parent_id: str, name: str
    ) -> CloudFolder: ...

    async def upload_file(
        self,
        refresh_token: str,
        folder_id: str,
        file_name: str,
        content: bytes,
        mime_type: str,
    ) -> CloudFile: ...

    async def trash_file(self, refresh_token: str, file_id: str) -> None: ...

    async def get_account_email(self, refresh_token: str) -> str | None: ...

    async def get_thumbnail_url(
        self, refresh_token: str, file_id: str
    ) -> str | None:
        """Fetch a fresh, signed thumbnail URL for a file (None if not yet ready)."""
        ...
