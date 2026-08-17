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

## Authentication & authorization

The Java API enforces authentication and role-based authorization on every request (Spring Security,
stateless — no server session):

- **Users** authenticate at `POST /api/v1/auth/login` and receive a signed **JWT** (HMAC-SHA256, jjwt).
  The token carries the subject and roles; it is verified on each request by a stateless filter — a
  tampered, wrong-key, or expired token is rejected. Passwords are stored **BCrypt-hashed**, never in
  plaintext, and login returns an identical error for unknown-user / wrong-password / disabled so it
  can't be used to enumerate accounts.
- **Machines** authenticate with an `X-API-Key` (constant-time compared) and get `ROLE_SERVICE`.
- **Authorization** is role-based (`VIEWER` / `TRADER` / `ADMIN` for humans, `SERVICE` for machines).
  Reads are public; **writes require a role**, enforced at the controller with method security
  (`@EnableMethodSecurity` + `@PreAuthorize`). A denied write is a clean `403` (not a masked `500`); an
  unauthenticated write is `401`. Enforcement is **always on** — there is no config flag to disable it.
- The signing secret comes from `OMS_JWT_SECRET` (**environment only**, never committed; a dev default
  is used only when unset). Demo users (`admin`/`trader`/`viewer`) are seeded for local use behind
  `OMS_SEED_DEMO_USERS` and **must be disabled in any real deployment** — the app logs a warning when
  it seeds them.
- The Python research service gates mutating routes behind a separate token.

## Application security practices

- Persistence is parameterized (Spring Data JPA) — no string-built SQL.
- Kafka deserialization pins trusted packages; no polymorphic default typing.
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
