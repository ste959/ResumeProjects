# Security Policy

This is a portfolio project, not a production service, but it is engineered to a professional security
posture and the practices below are enforced.

## Secret handling

- Credentials (API keys, tokens, DB passwords) live only in **git-ignored** files (`.env`,
  `alpaca-local.yml`) or environment variables. They are **never committed** — verifiable with
  `git log --all -- .env`.
- Only placeholder `*.example` files are checked in.
- **No secrets or confidential data are sent to AI tools** or any external service.

## Automated scanning

- **CodeQL** SAST (Java + TypeScript) on every push/PR (`.github/workflows/codeql.yml`).
- **Trivy** image scanning on built containers (report-only SARIF upload).
- **Dependabot** weekly dependency updates across Maven, npm, pip, and GitHub Actions
  (`.github/dependabot.yml`).

## Application security practices

- Persistence is parameterized (Spring Data JPA) — no string-built SQL.
- Kafka deserialization pins trusted packages; no polymorphic default typing.
- The Java API supports config-gated authentication (`oms.security.enabled` → `X-API-Key`,
  constant-time compared); the Python research service gates mutating routes behind a token.
- WebSocket origins are bound to the CORS allow-list, not `*`.
- Container images run as a non-root user.
- Captured logs/telemetry are **redacted** (secrets, emails, IPs, home paths) before storage
  (`harness/telemetry.py`).
- **Diagnostic reproduction bundles** (`harness/repro.py`) are a deliberate data-egress surface — they
  are meant to be attached to a ticket or shared — so they contain only already-redacted output and an
  environment fingerprint whose hostname is opt-in, never raw secrets.
- **Tamper-evident result seals** (`harness/integrity.py`) hash-chain a run's results.
  - The plain `sha256-chain` gives **integrity**: any altered/added/removed/reordered result is
    detected and pinpointed — *provided the seal is anchored where a tamperer can't also edit it.*
  - HMAC signing gives **authenticity** (a party without the key can't forge a valid seal). The signing
    key is supplied via `LAB_SEAL_KEY` in the **environment only** — it is a secret, never committed,
    and never written into a seal (a seal stores only the HMAC of the chain head, not the key).

## Reporting a vulnerability

This is a personal project without a formal disclosure process. If you find a security issue, please
open a GitHub issue describing it (omit any exploit details that would aid misuse) or contact the
maintainer directly.
