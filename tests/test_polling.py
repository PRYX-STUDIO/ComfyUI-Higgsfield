from pryx_higgsfield.polling import PollingConfig, RequestPoller
from pryx_higgsfield.types import AcceptedRequest, RequestStatus, StatusSnapshot


def test_poller_uses_provider_safe_backoff():
    accepted = AcceptedRequest(
        request_id="request-1",
        status_url="https://api.higgsfield.ai/requests/request-1/status",
        cancel_url="https://api.higgsfield.ai/requests/request-1/cancel",
        status=RequestStatus.QUEUED,
    )
    statuses = iter([
        StatusSnapshot(RequestStatus.QUEUED, payload={"status": "queued"}),
        StatusSnapshot(RequestStatus.IN_PROGRESS, payload={"status": "in_progress"}),
        StatusSnapshot(
            RequestStatus.COMPLETED,
            payload={"status": "completed", "images": [{"url": "https://cdn.example/image.png"}]},
        ),
    ])
    waits = []
    result = RequestPoller(
        PollingConfig(timeout=60, jitter_fraction=0),
        sleep=waits.append,
        jitter=lambda: 0,
    ).poll(accepted, status_getter=lambda url: next(statuses))
    assert result.status is RequestStatus.COMPLETED
    assert waits == [2.0, 3.0, 4.5]
