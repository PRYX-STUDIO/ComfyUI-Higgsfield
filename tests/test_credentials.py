from pryx_higgsfield.credentials import CredentialStore, mask_key_id, resolve_credentials


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


def test_store_metadata_does_not_return_secret(tmp_path):
    store = CredentialStore(tmp_path / "credentials.json")
    store.save("key-id", "secret-value")
    metadata = store.metadata(environment={})
    assert metadata == {"configured": True, "source": "local", "key_id": "ke…id"}
    assert "secret-value" not in str(metadata)
