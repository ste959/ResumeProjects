# 6. Hash-chained, optionally-signed result seals

**Status:** Accepted

## Context
When a partner runs the validation suite on their hardware and submits results, those results must be
trustworthy — a partner shouldn't be able to quietly flip a FAIL to a PASS.

## Decision
Seal a run (`harness/integrity.py`): hash each result's material verdict, hash-chain the hashes, and
record the chain head. Verification recomputes the chain and **pinpoints the first altered result**.
Keep two levels honestly distinct: a plain `sha256-chain` gives **integrity** (detectable *if the seal
is anchored where the tamperer can't also rewrite it*), and an optional HMAC signature gives
**authenticity** (unforgeable without the secret `LAB_SEAL_KEY`, which lives in the environment only).

## Consequences
- **Gain:** tamper-evident, shareable result records; CI proves the control fires by tampering a field
  and asserting verification fails.
- **Cost:** signed seals require key management (documented as env-only, never committed).
- **Honesty:** the integrity-vs-authenticity distinction is stated plainly — a bare hash chain is not
  proof against a party who can edit both the results and the seal.
