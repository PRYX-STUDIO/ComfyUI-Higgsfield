import json

import httpx

from pryx_comfyui_higgsfield.catalog import load_bundled_catalog
from pryx_comfyui_higgsfield.client import HiggsfieldClient
from pryx_comfyui_higgsfield.credentials import Credentials


def test_estimate_submit_status_and_upload_do_not_send_credentials_to_storage():
    model = load_bundled_catalog().get("soul-2")
    api_requests = []
    upload_requests = []

    def api_handler(request):
        api_requests.append(request)
        if request.url.path.startswith("/estimate/"):
            return httpx.Response(200, json={"credits": "1.5", "usd": "0.09"})
        if request.url.path == "/files/generate-upload-url":
            return httpx.Response(
                200,
                json={
                    "public_url": "https://cdn.example/input.png",
                    "upload_url": "https://storage.example/upload",
                    "upload_headers": {"Content-Type": "image/png", "x-amz-tagging": "safe"},
                },
            )
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "completed", "request_id": "request-1"})
        return httpx.Response(
            200,
            json={
                "status": "queued",
                "request_id": "request-1",
                "status_url": "https://api.higgsfield.ai/requests/request-1/status",
                "cancel_url": "https://api.higgsfield.ai/requests/request-1/cancel",
            },
        )

    def upload_handler(request):
        upload_requests.append(request)
        return httpx.Response(200)

    client = HiggsfieldClient(
        Credentials("key-id", "secret-value", "test"),
        http_client=httpx.Client(transport=httpx.MockTransport(api_handler)),
        upload_client=httpx.Client(transport=httpx.MockTransport(upload_handler)),
    )
    estimate = client.estimate(model, {"prompt": "test"})
    accepted = client.submit(model, {"prompt": "test"})
    status = client.status(accepted.status_url)
    public_url = client.upload_bytes(b"image", "image/png")

    assert estimate.usd == 0.09
    assert accepted.request_id == "request-1"
    assert status.status.value == "completed"
    assert public_url == "https://cdn.example/input.png"
    assert "Key key-id:secret-value" in api_requests[0].headers["Authorization"]
    assert "Authorization" not in upload_requests[0].headers


def test_request_payload_is_json():
    seen = {}

    def handler(request):
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "queued",
                "request_id": "request-2",
                "status_url": "https://api.higgsfield.ai/status",
                "cancel_url": "https://api.higgsfield.ai/cancel",
            },
        )

    model = load_bundled_catalog().get("soul-2")
    client = HiggsfieldClient(
        Credentials("id", "secret", "test"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        upload_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
    )
    client.submit(model, {"prompt": "no secret here"})
    assert seen["payload"] == {"prompt": "no secret here"}
