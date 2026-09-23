# PRYX ComfyUI Higgsfield

[![Tests](https://github.com/PRYX-STUDIO/pryx-comfyui-higgsfield/actions/workflows/tests.yml/badge.svg)](https://github.com/PRYX-STUDIO/pryx-comfyui-higgsfield/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-%E2%89%A50.35.0-4f46e5)](https://github.com/comfyanonymous/ComfyUI)

Generate and edit images and videos with Higgsfield from ComfyUI, using
model-specific controls, connected media references, and estimate-first cost
checks.

PRYX ComfyUI Higgsfield lets you call the documented Higgsfield image and video
endpoints from normal ComfyUI workflows. Model-specific controls, choices,
limits, and tooltips come from the bundled catalog, so a node only exposes the
parameters supported by its selected model.

The ComfyUI backend sends requests directly to `api.higgsfield.ai`. PRYX does
not operate a proxy and does not receive your API credentials or generated
media.

> **Important:** This node pack accesses paid API services. New generator nodes
> start in `estimate_only` mode so you can inspect the provider's estimate
> before allowing a generation request.

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Credentials](#credentials)
- [Quick start](#quick-start)
- [Nodes](#nodes)
- [Working with references](#working-with-references)
- [Estimate Only, pricing, and generation safety](#estimate-only-pricing-and-generation-safety)
- [Model catalog](#model-catalog)
- [Outputs](#outputs)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Privacy, security, and license](#privacy-security-and-license)

## Requirements

- ComfyUI `0.35.0` or newer
- ComfyUI frontend `1.53.6` or newer
- Python `3.10` through `3.13`
- A Higgsfield API account with an API key ID and secret

The package includes the official `higgsfield-client` dependency and uses its
own `httpx` request wrapper for estimates, uploads, polling, and downloads.
ComfyUI normally already provides the media libraries needed by its
native `IMAGE`, `VIDEO`, and `AUDIO` types.

## Installation

### ComfyUI Manager

After the package is available in the ComfyUI Registry, search for
**PRYX ComfyUI Higgsfield** in ComfyUI Manager, install it, and restart ComfyUI.

### Git installation

Clone the repository into `ComfyUI/custom_nodes` and install its Python
dependencies with the same Python environment that runs ComfyUI:

```powershell
cd ComfyUI/custom_nodes
git clone https://github.com/PRYX-STUDIO/pryx-comfyui-higgsfield.git pryx-comfyui-higgsfield
python -m pip install -r .\pryx-comfyui-higgsfield\requirements.txt
```

For the Windows portable ComfyUI distribution, use its bundled interpreter
instead:

```powershell
..\python_embeded\python.exe -m pip install -r .\pryx-comfyui-higgsfield\requirements.txt
```

Restart ComfyUI after installation. When updating an existing checkout, pull
the changes and restart ComfyUI; reload the browser with `Ctrl+F5` so the
frontend extension is reloaded as well.

## Credentials

Open **ComfyUI Settings → PRYX ComfyUI Higgsfield → Credentials** and enter:

- **Higgsfield API key** — paste the complete value Higgsfield shows when you
  create the key, in `key-id:key-secret` format. ComfyUI splits it at the first
  colon before storing the two parts separately.

The key name shown in the Higgsfield console is only a label; it is not part of
the credential. If you no longer have the secret, create a new key and copy its
complete value. Never put the key in a workflow or issue report.

The **Validate estimate** button checks the credentials with an estimate
request. It does not submit a paid generation. **Save locally** stores the
credentials in the active ComfyUI user directory. The secret is cleared from
the form after saving and never becomes a workflow input or browser-storage
value.

For headless installations, use one of these supported configurations:

```text
HF_KEY=key-id:key-secret
```

or:

```text
HF_API_KEY=key-id
HF_API_SECRET=key-secret
```

Environment variables take precedence over the local ComfyUI credential file.
See [SECURITY.md](SECURITY.md) for the credential and request-safety details.

## Quick start

1. Install the node pack and configure the credentials.
2. Add a generator from **PRYX → Higgsfield**.
3. Choose a model from the model dropdown. The available controls update to
   match that model.
4. Connect a prompt. The prompt input accepts a normal text connection, so a
   Config UI Prompt node can be used for long prompts.
5. Leave **request_mode** at `estimate_only` and queue the workflow.
6. Read the `credits`, `usd`, and `status` outputs.
7. If the estimate is acceptable, switch **request_mode** to `generate`, optionally set
   a positive **max_usd** limit, and queue the workflow again.
8. Connect `video` or `images` to the corresponding native ComfyUI output/save
   node. Video results can be connected to a compatible Save Video node.

For an image-to-video workflow, connect a native `IMAGE` output such as
`Load Image` to the generator's `image` input. For a multimodal workflow, use
one Reference Collector and connect its `references` output to the generator.
Reference Preview can be placed between the inputs and generator while
building the workflow.

## Nodes

All nodes are available under **PRYX/ComfyUI/Higgsfield**. Generator nodes have a
model dropdown, a collapsed model-information panel, and dynamic controls.
Expand the information panel to see the selected model's supported media,
limits, output settings, and reference guidance.

### PRYX ComfyUI Higgsfield Model Catalog

Use this node when you want to choose a model once and reuse it in one or more
generator nodes.

**Inputs**

- `model_id` — catalog model dropdown
- `provider` — filter the catalog by provider
- `capability` — filter by task, such as `image_to_video`
- `status` — show active, deprecated, unavailable, or all entries

**Outputs**

- `model_id` — connect this `STRING` output to a generator's `model` input
- `model_info` — JSON with the selected model, supported media, limits, and
  catalog metadata

The catalog node is optional. Every generator also has its own validated model
dropdown. The catalog is useful for central selection, filtering, or sharing a
model choice between nodes.

### PRYX ComfyUI Higgsfield Reference Collector

Collect several local images, videos, or audio inputs into one ordered
`references` value. One Collector is enough; chaining multiple Collectors is
not required.

**Inputs**

- `image`, `image_2`, … — up to 30 image slots; image batches keep their order
- `video`, `video_2`, … — up to 10 video slots
- `audio`, `audio_2`, … — up to 10 audio slots
- `references` — merge an existing collection when needed
- `names` — optional labels, one per line, for example:
  `image_1=person` and `image_2=outfit`
- `external_url` — an already public HTTPS URL for a document or web page
- `external_type` — `url` or `file`

The frontend adds additional media sockets as they are connected. Sockets are
collected in numeric order, not by the order in which wires were drawn. Model
limits are checked later by the selected generator.

Connected local media does not need to be hosted manually. The backend
converts it to a supported format and uploads it through Higgsfield's
presigned upload flow. `external_url` is different: it remains an external
URL and must already be publicly reachable by the provider.

### PRYX ComfyUI Higgsfield Reference Preview

Inspect the final reference order and prompt mapping before running a
generator. This node performs no media upload and makes no Higgsfield API
request.

**Outputs**

- `prompt` — the prompt passed through the preview
- `references` — the ordered collection passed through the preview
- `model` — the selected model ID
- `reference_info` — readable mapping and resolved prompt text

Run the preview after changing media, labels, or the model. Its text output
shows which media item becomes `Image 1`, `Video 1`, and so on.

### PRYX ComfyUI Higgsfield Image Generate & Edit

Generate images or edit images with the catalog's image endpoints. The model
dropdown covers the current SOUL, Recraft, Marketing Studio, and Grok image
entries. Connect an `IMAGE` input when the selected edit model supports source
images. The visible parameter widgets change with the selected model.

**Outputs:** `images`, `image_urls`, `request_id`, `credits`, `usd`, `status`

### PRYX ComfyUI Higgsfield Text to Video

Generate a video from a text prompt. The node exposes the controls supported by
the selected text-to-video model, such as resolution, aspect ratio, duration,
audio, sound, multi-shot settings, or a seed.

**Outputs:** `video`, `local_file`, `remote_url`, `request_id`, `credits`, `usd`,
`status`

### PRYX ComfyUI Higgsfield Image to Video

Animate a starting image. Connect one native `IMAGE` to `image`; models that
support an ending frame expose the optional `end_image` input. Some models also
accept additional references through `references`. The node only lists
catalog models documented for the Higgsfield image-to-video capability.

**Outputs:** `video`, `local_file`, `remote_url`, `request_id`, `credits`, `usd`,
`status`

### PRYX ComfyUI Higgsfield Reference to Video

Generate a video from ordered multimodal references. Depending on the selected
model, references may include images, videos, audio, documents, or web links.
Connect direct media inputs for simple workflows, or use a Reference Collector
for several inputs.

**Outputs:** `video`, `local_file`, `remote_url`, `request_id`, `credits`, `usd`,
`status`

### PRYX ComfyUI Higgsfield Video Edit

Edit an existing video with a prompt and the controls supported by the active
catalog model. The model dropdown includes Genjutsu Motion Transfer and
Genjutsu Object Swap as separate modes, alongside the other documented video
edit models. Connect the source video to `video`; optional model-supported
references can be supplied through `references`.

**Outputs:** `video`, `local_file`, `remote_url`, `request_id`, `credits`, `usd`,
`status`

### PRYX ComfyUI Higgsfield Video Extend

Extend an existing video. Connect the source clip to `video` and set the
model-supported duration and output options. The selected model determines the
valid duration range.

**Outputs:** `video`, `local_file`, `remote_url`, `request_id`, `credits`, `usd`,
`status`

### PRYX ComfyUI Higgsfield Advanced Request

Send catalog-controlled JSON arguments when a specialized workflow needs more
direct control. The model is still selected from the validated catalog; this
node cannot override the API host or endpoint.

Use this node when you understand the selected model's documented request
schema. Normal generator nodes are easier to use because they create the
model-specific widgets and validate their values individually.

**Inputs**

- `model` — catalog model ID
- `arguments_json` — JSON object containing the model's request fields
- `request_mode`, `max_usd`, `auto_save`, `timeout` — common safety controls

**Outputs:** `image`, `video`, `remote_urls`, `request_id`, `credits`, `usd`,
`status`

## Working with references

### Direct inputs versus `references`

Use a direct input when the role is unambiguous:

- `image` is the source/start image for image-to-video or an image-edit node
- `end_image` is the explicit ending frame where the selected model supports it
- `video` is the source video for edit/extend nodes
- `references` is an ordered collection of additional media

The frontend hides inputs that the selected model cannot use. The backend
validates the final request again before uploading anything.

### Order and numbering

The order is deterministic:

1. Direct media inputs are mapped first.
2. Reference Collector slots follow in numeric socket order.
3. Image, video, audio, document, and web references are numbered separately
   when the provider uses numbered fields.
4. Image batches keep their internal order.

For example, two connected Collector images become `Image 1` and `Image 2`.
The socket `image_2` is always after `image`, even if its wire was added first.
Use Reference Preview to verify the actual mapping instead of guessing.

### Prompt references

Prompt syntax is endpoint-specific. The plugin does not invent `@` mentions or
angle-bracket tokens for endpoints that do not document them.

For **Wan 3.0 Reference to Video**, the documented tokens are:

```text
Image 1, Image 2, Video 1, Audio 1
```

The Collector's `names` input can assign readable aliases:

```text
image_1=person
image_2=outfit
video_1=camera
```

Then use the plugin alias syntax in the prompt:

```text
Use {{ref:person}} as the main character, {{ref:outfit}} as the clothing,
and {{ref:camera}} as the camera reference.
```

The plugin resolves those aliases to the correct documented model tokens before
upload and generation. Labels must be unique. Unknown or duplicate aliases
stop the request before media upload.

For other endpoints, numbered entries in Reference Preview describe delivery
order only. The current documentation does not confirm a prompt-token syntax
for them, so named aliases are rejected and the prompt should use the syntax
documented for that specific provider endpoint.

## Estimate Only, pricing, and generation safety

### What `estimate_only` does

When a generator runs in `estimate_only` mode, it:

1. Resolves the selected model and normalizes its parameters.
2. Checks required inputs, reference types, counts, choices, and ranges.
3. Uploads connected local references when the provider needs public media URLs.
4. Calls Higgsfield's `POST /estimate/<endpoint>` route.
5. Returns the provider's `credits` and `usd` estimate plus a `status` JSON.

It does **not** send the paid generation `POST` request. A local reference can
still be uploaded during an estimate because the provider must see the final
request shape; no generated image or video is created.

`generate` follows the same estimate-first path and submits the paid request
only after the estimate succeeds.

### Cost limits

- `max_usd = 0` disables the local cost limit.
- A positive `max_usd` is a hard upper bound.
- If the provider returns no USD estimate, a positive limit blocks generation.
- If the estimate exceeds the limit, no generation request is submitted.

The estimate is the best request-specific price supplied by the provider for
the selected model, duration, resolution, and references. `credits` and `usd`
are estimates, not a final billing receipt or account balance.

### Common safety controls

- `auto_save` stores completed media in ComfyUI's output directory when enabled
  and in its temporary directory when disabled.
- `timeout` limits how long the local node waits for a remote generation.
- Generation submissions are never automatically repeated after an ambiguous
  network timeout.
- Status polling uses bounded retries and backoff.
- ComfyUI progress events report the current phase and elapsed time. The
  provider does not currently expose a reliable percentage or ETA through this
  integration.

## Model catalog

The bundled catalog is the single source for model IDs, endpoint paths,
supported inputs, choices, ranges, defaults, conditional requirements, and
documentation links. Revision `2026-09-23.5` has 81 endpoint entries: 80
discovered from the public image/video Explore pages and their model families,
plus one separately documented SOUL Cinema endpoint. This is an inventory of
the public image/video references at the audit date, not a promise that an
account has access to every endpoint or that Higgsfield exposes no other models.

The table below is a snapshot of this bundled revision, not a provider-wide
inventory. The live dropdown in each node is authoritative for the catalog
loaded by that ComfyUI installation.

### Bundled catalog snapshot

| Capability | Bundled examples |
| --- | --- |
| Image generation (10) | SOUL, Recraft, Ideogram, Z-Image |
| Image editing (5) | Marketing Studio, Grok Image |
| Text to video (19) | MiniMax H3, Seedance, Kling, Wan, PixVerse |
| Image to video (22) | MiniMax H3, Seedance, Kling, Wan, PixVerse |
| Reference to video (15) | MiniMax H3, Seedance, Kling Omni, Wan |
| Video edit (5) | Genjutsu Motion Transfer, Genjutsu Object Swap, Seedance, Kling |
| Motion/control (4) | Kling motion-control models, also in Video Edit |
| Video extend (1) | Seedance |

Each public platform entry includes the API reference's JSON input schema.
The backend checks required fields, choices, nested JSON, conditions, and
per-input limits before uploading local media. The collapsed model-information
panel lists the selected endpoint's media counts and options; the widgets show
its choices and tooltips. For Kling variants, provider `mode` (such as `std`
or `pro`) is distinct from the node's `request_mode` (estimate or generate).

A manual catalog refresh downloads the published PRYX catalog, not live model
pages. Restart ComfyUI afterward so the Python nodes and browser UI use the
same revision. The scheduled drift check audits the public Higgsfield platform
references; a partial inventory fails instead of replacing the bundled catalog.
Remote data is accepted only after schema, ID, endpoint, and documentation
validation. Account access and media acceptance are ultimately decided by
Higgsfield.

Model availability is capability-specific. A model can be available for one
Higgsfield task and still be absent from another node when the provider does
not document a compatible endpoint for that capability. The dropdowns therefore
filter by capability: an item missing from **Reference to Video** is not a
statement that the model is unavailable from Higgsfield in general.

To refresh manually, open **ComfyUI Settings → PRYX ComfyUI Higgsfield → Model
catalog**, click **Refresh catalog**, restart ComfyUI, and reload the browser.

## Outputs

### Generator outputs

| Output | Meaning |
| --- | --- |
| `images` | Native ComfyUI `IMAGE` result. Empty in estimate-only mode. |
| `video` | Native ComfyUI `VIDEO` result, or a local-file fallback when the installed ComfyUI version has no native video wrapper. Empty in estimate-only mode. |
| `image_urls` / `remote_url` / `remote_urls` | JSON text containing provider result URLs. These are not native media inputs. |
| `local_file` | Local path of a downloaded video result. It is empty until generation completes. |
| `request_id` | Provider request ID. Empty for estimate-only runs. |
| `credits` | Provider credit estimate for the normalized request. |
| `usd` | Provider USD estimate for the normalized request. |
| `status` | JSON diagnostics containing status, request ID, elapsed time, URLs, reference mapping, and provider status when available. |

Connect `images` or `video` to downstream ComfyUI nodes. Use URL outputs for
logging, diagnostics, or workflows that explicitly need the provider URL.

## Troubleshooting

### A model is missing from a dropdown

The dropdown is filtered by node capability and active catalog status. Refresh
the catalog, restart ComfyUI, and hard-reload the browser. If the model is not
in the official Higgsfield endpoint documentation, it will not appear in this
node pack.

### The model-information panel is too large

Panels start collapsed. Click the panel heading to expand it. The expanded state
is remembered per node; use `Ctrl+F5` after updating the package if the old
frontend script is still cached.

### The video output is empty

This is expected in `estimate_only` mode. Switch to `generate` only after
checking the estimate and setting an appropriate `max_usd` limit.

### Connected media is rejected

Check the selected model's information panel and Reference Preview. The model
may accept a different media type, a smaller number of items, or a specific
source/end-frame field. Validation happens before generation and prevents an
invalid request from being sent.

### A long prompt is difficult to edit

Connect a Config UI Prompt node to the generator's `prompt` input. The prompt
field is designed to accept a connected `STRING` input.

### Credentials validate but generation fails

Run `estimate_only` with the exact model and inputs first. Then inspect the
`status` output and ComfyUI console. Provider-side model availability, account
credits, content policy, media duration, and retention rules can still affect a
real generation.

## Development

Run the local unit and mock integration tests:

```powershell
python -m pytest -q
node --test
```

Validate the Python import path:

```powershell
python -m compileall -q pryx_comfyui_higgsfield tools __init__.py
```

Validate the catalog against the official documentation pages:

```powershell
python tools/sync_platform_catalog.py --catalog pryx_comfyui_higgsfield/catalog/models.json --check --summary
```

The test suite uses mocks and does not send paid generation requests. A live
credential smoke test should use an estimate only. A real generation requires
separate cost approval and an explicit positive `max_usd` value.

## Privacy, security, and license

- API credentials stay in the local ComfyUI installation or supported
  environment variables.
- PRYX does not proxy requests or collect credentials, prompts, references, or
  generated media.
- API authorization headers are not sent to the presigned storage upload host.
- See [SECURITY.md](SECURITY.md) for security reporting and request-safety
  details.
- The project is released under the [MIT License](LICENSE).
- See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dependency notices.

## Links

- [Higgsfield API documentation](https://docs.higgsfield.ai/docs/models)
- [Higgsfield video model documentation](https://docs.higgsfield.ai/docs/models/video-generation)
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [Issue tracker](https://github.com/PRYX-STUDIO/pryx-comfyui-higgsfield/issues)
