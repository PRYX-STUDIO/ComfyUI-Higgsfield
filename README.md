# PRYX Higgsfield for ComfyUI

PRYX Higgsfield provides catalog-driven ComfyUI nodes for the Higgsfield API.
Requests go directly from the local ComfyUI backend to api.higgsfield.ai.
PRYX does not operate a proxy and does not receive API credentials or media
files.

The package targets ComfyUI 0.35.0 or newer, the 1.53.6 frontend, and Python
3.10 through 3.13. The bundled catalog is checked against the official
Higgsfield documentation and includes the documented image and video
endpoints.

## Installation

Install through ComfyUI Manager after the package is published to the ComfyUI
Registry. For development or a direct Git installation, clone this repository
into the ComfyUI custom_nodes directory:

    git clone https://github.com/PRYX-STUDIO/ComfyUI-Higgsfield.git custom_nodes/PRYX-Higgsfield
    python -m pip install -r custom_nodes/PRYX-Higgsfield/requirements.txt

Restart ComfyUI after installation.

## Credentials

Open ComfyUI Settings and choose PRYX Higgsfield: Credentials. The secret is
stored atomically in the active ComfyUI user directory and is not returned to
the browser after saving. It never becomes a node input or workflow value.

For headless installations, the supported environment variables are:

    HF_KEY=key-id:key-secret

or:

    HF_API_KEY=key-id
    HF_API_SECRET=key-secret

Environment variables take precedence over the local settings file. The
settings validation route performs an estimate request only; it does not
submit a generation.

## Nodes

All nodes appear under PRYX/Higgsfield:

- PRYX Higgsfield Model Catalog
- PRYX Higgsfield Reference Collector
- PRYX Higgsfield Image Generate & Edit
- PRYX Higgsfield Text to Video
- PRYX Higgsfield Image to Video
- PRYX Higgsfield Reference to Video
- PRYX Higgsfield Video Edit
- PRYX Higgsfield Video Extend
- PRYX Higgsfield Advanced Request

Reference Collector values retain their order and can contain local images,
videos, and audio. Local media is uploaded through a Higgsfield presigned
upload URL. API credentials are not sent to the storage host.

## Estimates and generation safety

Generator nodes default to estimate_only. In that mode the node returns the
credits, USD estimate, and status JSON without sending a generation request.
generate mode always estimates with the normalized request arguments first.
max_usd is a hard upper bound; if the estimate is missing or exceeds the
limit, the generation POST is not sent.

Generation submissions are never automatically repeated after an ambiguous
network timeout. Status GET requests use bounded retries and polling backs off
from two seconds to ten seconds. Higgsfield does not currently provide a
reliable percentage or ETA, so the progress event reports phase and elapsed
time instead.

Completed media is downloaded to ComfyUI output when auto_save is enabled and
to ComfyUI temp otherwise. Higgsfield keeps generated files for a limited
period, so workflows that need durable results should keep the local copy.

## Catalog

The bundled catalog is always available offline. A background-safe catalog
check may run at most once per 24 hours against the fixed repository raw URL.
Remote data is accepted only after schema validation, unique-ID validation,
official API-host validation, and documentation-source validation. A failed
refresh leaves the last valid cache or bundled catalog active.

The catalog checked on 2026-09-21 contains six documented image entries and
nineteen documented video entries across SOUL, Marketing Studio, Recraft,
Grok, Seedance, Kling, and Wan. The number is descriptive of this catalog
revision and is not a promise about the provider's future model inventory.

## Development

Run the local unit and mock integration tests with:

    python -m pytest -q

Validate the Python import path with:

    python -m compileall -q pryx_higgsfield tools __init__.py

The catalog generator reads only the official documentation index and linked
model pages:

    python tools/sync_catalog.py --check

Tests never send a paid generation request. A live smoke test may perform an
estimate only; a real generation requires a separate cost approval and an
explicit max_usd value.

## Privacy, security, and license

See SECURITY.md for reporting guidance and credential handling. The project is
released under the MIT license. Higgsfield's Python SDK is used under its own
MIT license; the attribution is recorded in THIRD_PARTY_NOTICES.md.
