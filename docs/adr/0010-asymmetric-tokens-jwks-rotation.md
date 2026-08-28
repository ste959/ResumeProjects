# 10. Asymmetric tokens, JWKS, rotation, and a refresh/revocation lifecycle

**Status:** Accepted

## Context
The first cut of auth (ADR-era JWT/RBAC) was a symmetric **HS256** login token: one shared secret both
signs and verifies, tokens were long-lived, there was no way to revoke one before it expired, and role
enforcement covered only the order-entry path. That is fine as a demo but shallow for anything that calls
itself identity engineering — the exact gaps an identity team looks for.

## Decision
Rebuild the token layer to the pattern real identity providers use.

- **Asymmetric signing (RS256) + JWKS.** Access tokens are signed with a private RSA key that never
  leaves the process; verifiers fetch the *public* keys from `/.well-known/jwks.json` and pick the right
  one by the token's `kid`. No shared secret is distributed, so any number of resource servers can verify
  independently.
- **Key rotation.** A `KeyManager` holds a small set of keys, signs with the newest, and keeps the
  previous ones published in the JWKS until their tokens expire — so rotation never invalidates an
  in-flight token. Rotation is ADMIN-triggerable (`POST /api/v1/auth/keys/rotate`).
- **Standard claims, asserted.** Every token carries issuer, audience, a unique `jti`, and
  `iat`/`nbf`/`exp`; the parser requires the issuer and checks the audience, not just the signature.
- **Short access + rotating refresh.** Login returns a short-lived access token and a long-lived,
  opaque, **hashed-at-rest** refresh token. Refreshing rotates it (new token, old one dead); replay of an
  already-rotated token — the signature of a leaked token — is **detected and burns the whole family**.
- **Revocation.** Logout revokes the refresh family and adds the current access token's `jti` to a
  short-TTL denylist the auth filter checks, so a token can be killed before it expires. The refresh /
  denylist state uses the same in-memory-or-Redis store the idempotency keys do.
- **Complete RBAC.** `@PreAuthorize` role checks were extended to *every* write endpoint across all desks,
  so "a write needs a role" is now literally true (a `VIEWER` can't mutate anything, even via curl).

## Consequences
- **Gain:** the identity story is now production-shaped — asymmetric verification, transparent rotation,
  a real refresh lifecycle with theft detection, and immediate revocation — and the RBAC claim matches the
  code everywhere.
- **Cost:** more moving parts (a key manager, a token store, refresh/rotation flows) and a real runtime
  dependency for the multi-node case (Redis, already present). Keys are generated in-process at startup,
  so a restart invalidates outstanding tokens; a production deployment would source them from a managed
  key store (Key Vault / HSM) — a drop-in replacement for the generator.
- **Verified without infrastructure:** RS256 round-trip + rotation + eviction, JWKS content (public
  params only), refresh rotation + reuse-detection + family revocation, and the access denylist are all
  unit-tested; the full login → `/me` → refresh → reuse=401 → gated-write flow was smoke-tested live on H2.
