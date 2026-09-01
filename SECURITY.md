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

- **Users** authenticate at `POST /api/v1/auth/login` and receive a short-lived **access token** plus a
  long-lived **refresh token**. The access token is an **asymmetrically-signed (RS256) JWT**: the private
  key stays in-process and verifiers fetch the public keys from the **JWKS endpoint**
  (`/.well-known/jwks.json`), selecting the right one by the token's `kid` — no shared secret is
  distributed. Signing keys **rotate** (a retired key stays in the JWKS until its tokens expire, so
  rotation never breaks an in-flight token; rotation is ADMIN-triggerable). Every access token carries
  the standard claims — issuer, audience, a unique `jti`, and `iat`/`nbf`/`exp` — all asserted on
  verification. Passwords are **BCrypt-hashed**, and login returns an identical error for
  unknown-user / wrong-password / disabled so it can't enumerate accounts.
- **Token lifecycle & revocation.** Refresh tokens are opaque, stored **hashed**, single-use, and
  **rotating** — each refresh mints a new one and invalidates the old; presenting an already-rotated
  token (the signature of a stolen, replayed token) is detected and **revokes the whole token family**.
  Logout revokes the refresh family and **denylists the current access token's `jti`** for its remaining
  lifetime (the auth filter checks the denylist). Refresh/revocation state lives in the same in-memory /
  Redis-selectable store as the idempotency keys.
- **Machines** authenticate with an `X-API-Key` (constant-time compared) and get `ROLE_SERVICE`.
- **Authorization** is role-based (`VIEWER` / `TRADER` / `ADMIN` for humans, `SERVICE` for machines).
  Every write on the **regulated OMS desk** — order entry and lifecycle, strategies, RFQ, rates, tax,
  rebalance, backtest — **requires a role**, enforced with method security (`@EnableMethodSecurity` +
  `@PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")`), so a `VIEWER` cannot mutate desk state even
  by calling the API directly. A denied write is a clean `403` (not a masked `500`); an unauthenticated
  write is `401`. Enforcement is **always on** — no config flag disables it.
- **Public sandboxes (a deliberate demo choice).** The standalone **matching-engine terminal**
  (`/api/exchange/**`) and **crypto-market** (`/api/market/**`) are login-less, interactive "play with the
  engine" demos over simulated/paper state — so their *writes* are public, matching their no-login UIs.
  This is scoped authz (gate the regulated desk, not the toy sandboxes), not an oversight. Likewise every
  `GET` is public — including the blotter, positions, and the paper account view — intentional for a
  read-only public demo over seeded/paper data (no real customer information). A real deployment would put
  the account/blotter reads and the sandbox writes behind `authenticated()`.
- Signing keys are generated at startup (a production deployment would source them from a managed key
  store / HSM); the `X-API-Key` and any JWT config come from the **environment only**, never committed.
  Demo users (`admin`/`trader`/`viewer`) are seeded for local use behind `OMS_SEED_DEMO_USERS` and
  **must be disabled in any real deployment** — the app logs a warning when it seeds them.
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
