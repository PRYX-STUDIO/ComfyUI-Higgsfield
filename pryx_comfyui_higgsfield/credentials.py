"""Local credential resolution and atomic storage.

Credentials never enter node inputs, workflow JSON, frontend responses, or
catalog files. The frontend only sends a new value to the local settings route.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import CredentialError


STORE_FILENAME = ".pryx_comfyui_higgsfield_credentials.json"


@dataclass(frozen=True, repr=False)
class Credentials:
    key_id: str
    secret: str
    source: str

    @property
    def authorization_key(self) -> str:
        return f"{self.key_id}:{self.secret}" if self.secret else self.key_id

    def __repr__(self) -> str:
        return f"Credentials(key_id={mask_key_id(self.key_id)!r}, source={self.source!r})"


def mask_key_id(key_id: str | None) -> str | None:
    if not key_id:
        return None
    if len(key_id) <= 4:
        return "•" * len(key_id)
    return f"{key_id[:2]}…{key_id[-2:]}"


def default_user_directory() -> Path:
    configured = os.environ.get("COMFYUI_USER_DIR")
    if configured:
        return Path(configured).expanduser()
    try:
        import folder_paths

        getter = getattr(folder_paths, "get_user_directory", None)
        if callable(getter):
            return Path(getter())
        base_path = getattr(folder_paths, "base_path", None)
        if base_path:
            return Path(base_path) / "user"
    except Exception:
        pass
    return Path.cwd() / "user"


class CredentialStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else default_user_directory() / STORE_FILENAME

    def load(self) -> tuple[str, str] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            key_id = data["key_id"]
            secret = data["secret"]
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise CredentialError("The local Higgsfield credential file is invalid.") from error
        if not isinstance(key_id, str) or not isinstance(secret, str) or not key_id or not secret:
            raise CredentialError("The local Higgsfield credential file is incomplete.")
        return key_id, secret

    def save(self, key_id: str, secret: str) -> None:
        if not isinstance(key_id, str) or not key_id.strip():
            raise CredentialError("A Higgsfield key ID is required.")
        if not isinstance(secret, str) or not secret:
            raise CredentialError("A Higgsfield secret is required.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": 1, "key_id": key_id.strip(), "secret": secret},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f"{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as handle:
                temporary = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            _restrict_file(temporary)
            os.replace(temporary, self.path)
            _restrict_file(self.path)
        except OSError as error:
            if temporary:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
            raise CredentialError("Could not save the local Higgsfield credentials.") from error

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise CredentialError("Could not remove the local Higgsfield credentials.") from error

    def metadata(self, environment: Mapping[str, str] | None = None) -> dict[str, str | None]:
        credentials = resolve_credentials(self, environment=environment, allow_missing=True)
        return {
            "configured": credentials is not None,
            "source": credentials.source if credentials else "none",
            "key_id": mask_key_id(credentials.key_id) if credentials else None,
        }


def _restrict_file(path: str | os.PathLike[str]) -> None:
    if os.name != "nt":
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    else:
        try:
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        except OSError:
            pass


def _from_hf_key(value: str, source: str) -> Credentials:
    if ":" in value:
        key_id, secret = value.split(":", 1)
    else:
        key_id, secret = value, ""
    if not key_id:
        raise CredentialError("The Higgsfield API key is empty.")
    return Credentials(key_id=key_id, secret=secret, source=source)


def resolve_credentials(
    store: CredentialStore | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    allow_missing: bool = False,
) -> Credentials | None:
    env = environment if environment is not None else os.environ
    hf_key = env.get("HF_KEY")
    if hf_key:
        return _from_hf_key(hf_key, "environment:HF_KEY")

    api_key = env.get("HF_API_KEY")
    api_secret = env.get("HF_API_SECRET")
    if api_key and api_secret:
        return Credentials(api_key, api_secret, "environment:HF_API_KEY")
    if api_key or api_secret:
        raise CredentialError(
            "Both HF_API_KEY and HF_API_SECRET must be set when using split credentials."
        )

    source_store = store or CredentialStore()
    stored = source_store.load()
    if stored:
        return Credentials(stored[0], stored[1], "local")

    if allow_missing:
        return None
    raise CredentialError(
        "Higgsfield credentials are missing. Set HF_KEY, set HF_API_KEY and "
        "HF_API_SECRET, or save them in ComfyUI Settings."
    )
