import pytest

from pryx_comfyui_higgsfield.credentials import CredentialStore, mask_key_id, resolve_credentials
from pryx_comfyui_higgsfield.errors import CredentialError


def test_environment_priority_and_masking(tmp_path):
    store = CredentialStore(tmp_path / "credentials.json")
    store.save("stored-id", "stored-secret")

    credentials = resolve_credentials(
        store,
        environment={"HF_API_KEY": "env-id", "HF_API_SECRET": "env-secret"},
    )
    assert credentials.authorization_key == "env-id:env-secret"
    assert credentials.source == "environment:HF_API_KEY"
    assert credentials.secret not in repr(credentials)
    assert mask_key_id("abcdef") == "ab…ef"

    single = resolve_credentials(store, environment={"HF_KEY": "single-id:single-secret"})
    assert single.authorization_key == "single-id:single-secret"
    with pytest.raises(CredentialError, match="both the Higgsfield key ID and secret"):
        resolve_credentials(store, environment={"HF_KEY": "id-only"})


def test_store_metadata_does_not_return_secret(tmp_path):
    store = CredentialStore(tmp_path / "credentials.json")
    store.save("key-id", "secret-value")
    metadata = store.metadata(environment={})
    assert metadata == {"configured": True, "source": "local", "key_id": "ke…id"}
    assert "secret-value" not in str(metadata)
