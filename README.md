# ippx

Sync and async IPP/IPPS client for Python. Send print jobs and monitor network
printers, including printers exposed over the internet behind TLS with source
IP allowlisting.

Built on [httpx](https://www.python-httpx.org/) with a pure sans-IO codec for
the IPP binary protocol (RFC 8010) and the RFC 8011 required operation set.

ippx is a plain library: the only runtime dependency is httpx. No framework,
no server, no Docker required. Use it from a script, a CLI, a cron job, a
serverless function, or an async web app.

## Why

[pyipp](https://pypi.org/project/pyipp/) is monitoring only. ippx can actually
print, in both async (FastAPI-native) and sync code, with first-class support
for the realities of network printers: self-signed certificates, legacy cipher
suites, HTTP Basic auth, and flaky WAN links.

## Install

```
pip install ippx
```

Python 3.11+. Single runtime dependency: httpx. Fully typed (PEP 561).

## Quick start (async, e.g. inside FastAPI)

```python
from ippx import AsyncIppClient, BasicAuth, TlsConfig

async def print_invoice(pdf_bytes: bytes) -> None:
    async with AsyncIppClient(
        "ipps://printer.example.com:631/ipp/print",
        auth=BasicAuth("user", "password"),
        tls=TlsConfig(fingerprint="sha256:AB:CD:..."),
    ) as printer:
        job = await printer.print_job(
            pdf_bytes,
            document_format="application/pdf",
            job_name="invoice-123",
            job_attributes={"copies": 1, "sides": "two-sided-long-edge"},
        )
        result = await printer.wait_for_job(job.job_id, timeout=120)
        print(result.state, result.state_reasons)
```

## Quick start (sync)

```python
from ippx import IppClient

with IppClient("ipps://203.0.113.10:631/ipp/print") as printer:
    caps = printer.get_printer_attributes()
    print(caps.make_and_model, caps.state, caps.document_formats)
    job = printer.print_job(pdf_bytes, document_format="application/pdf")
```

## Operations

The RFC 8011 required operation set, supported by every conformant printer:

| Method | IPP operation |
|---|---|
| `print_job(document, ...)` | Print-Job |
| `validate_job(...)` | Validate-Job (pre-flight without printing) |
| `cancel_job(job_id)` | Cancel-Job |
| `get_printer_attributes(...)` | Get-Printer-Attributes |
| `get_job_attributes(job_id, ...)` | Get-Job-Attributes |
| `get_jobs(...)` | Get-Jobs |
| `wait_for_job(job_id, timeout=...)` | polling helper over Get-Job-Attributes |

`wait_for_job` polls with exponential backoff (1s doubling to a 15s cap by
default) until the job reaches a terminal state (completed, canceled,
aborted) and raises `JobTimeoutError` otherwise.

A printer's full `operations-supported` list decodes to the named `Operation`
enum (the complete IANA IPP registry, not just the implemented set), so you
can introspect capabilities like `Operation.IDENTIFY_PRINTER`.

Note that for `get_jobs` most printers only return `job-id` and `job-uri` by
default, per RFC 8011; pass
`requested_attributes=["job-id", "job-state", "job-name"]` to get more.

## Authentication

- **HTTP Basic**: `auth=ippx.BasicAuth("user", "pw")` (or a plain
  `("user", "pw")` tuple)
- **HTTP Digest**: `auth=ippx.DigestAuth("user", "pw")`
- **TLS client certificate**: `tls=TlsConfig(client_cert=("cert.pem", "key.pem"))`
- **requesting-user-name**: set via `requesting_user_name=`, sent on every
  request (identification only, not authentication)

## TLS

Printers almost universally ship self-signed certificates. `TlsConfig` gives
you four options, strongest first:

```python
TlsConfig()                                  # system CA validation (default)
TlsConfig(verify="/path/to/printer-ca.pem")  # custom CA bundle
TlsConfig(fingerprint="sha256:AB:CD:...")    # pin the exact certificate
TlsConfig(verify=False)                      # no validation (last resort)
```

Fingerprint pinning verifies the SHA-256 digest of the server certificate
during the TLS handshake itself, so there is no window between checking and
using the connection. Get a printer's fingerprint with:

```
openssl s_client -connect printer:631 < /dev/null 2>/dev/null \
  | openssl x509 -fingerprint -sha256 -noout
```

For an internet-exposed printer (port forward locked to a source WAN IP),
the recommended setup is fingerprint pinning plus HTTP Basic auth.

Two behaviours worth knowing:

- Printers very commonly offer only plain-RSA key exchange (no ECDHE), which
  stock OpenSSL policy rejects with a bare handshake-failure alert. Every
  context ippx builds therefore uses `DEFAULT:@SECLEVEL=1` ciphers so real
  hardware is reachable and genuine certificate problems surface as truthful
  certificate errors; override with `TlsConfig(ciphers=...)` to tighten or
  loosen.
- With a custom CA bundle, hostname verification is disabled (printers are
  usually addressed by IP), so any certificate issued by that CA is accepted.

## Job attributes

Pass common Job Template attributes as a plain dict; tags are inferred for
`copies`, `sides`, `media`, `print-quality`, `print-color-mode`,
`orientation-requested`, `output-bin`, `number-up`, `printer-resolution` and
others. For anything else, pass `ippx.Attribute` objects with explicit tags.

## Verified hardware

| Printer | Print-Job | Status | Notes |
|---|---|---|---|
| HP Color LaserJet Pro M283fdw | yes | verified | Full IPPS path with fingerprint pinning: Get-Printer-Attributes (128 attrs incl. nested media-col collections), Validate-Job, Print-Job to completion, job polling, Get-Jobs, sync and async. Offers RSA-key-exchange ciphers only, handled by the default `TlsConfig` cipher policy. |

Also verified end-to-end against a live CUPS 2.4 server (Get-Printer-Attributes,
Validate-Job, Print-Job, job polling to completion, Get-Jobs, sync and async
clients). Contributions to this table are welcome.

## Not in scope (yet)

- Document conversion: bring your own PDF/PCL/PWG raster bytes
- Create-Job / Send-Document multi-document jobs
- IPP event subscriptions (RFC 3995): printer firmware support is too rare
  to rely on; use `wait_for_job` polling
- Encoding IPP collections in requests (decoding is fully supported)
- mDNS/driverless discovery

## Development

```
pip install -e .[dev]
ruff check src tests
pytest
```

## License

MIT
