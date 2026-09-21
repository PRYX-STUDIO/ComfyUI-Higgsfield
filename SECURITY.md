# Security

## Credential handling

The node pack resolves credentials in this order:

1. HF_KEY
2. HF_API_KEY together with HF_API_SECRET
3. The local ComfyUI user credential file

The secret is not a workflow widget, is not returned by the settings API, and
is not stored in browser storage. The local file is written atomically. POSIX
systems receive owner-only permissions; Windows keeps the file in the active
user directory and applies restrictive file attributes where the platform
permits it.

## Request safety

Catalog endpoints are relative paths and are validated against
https://api.higgsfield.ai. Advanced Request accepts a catalog model ID and
JSON arguments but cannot override the API host. Storage uploads use only
headers returned by Higgsfield and never receive the API Authorization header.

Generation POST requests are not retried after a timeout. Status GET requests
may be retried with a bounded policy. Test suites do not send generation
requests.

## Reporting

Please report a security issue privately to the project maintainer before
opening a public issue. Do not include API keys, secrets, cookies, signed
upload URLs, private media, or complete request payloads in a report.
