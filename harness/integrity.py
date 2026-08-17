"""Tamper-evident run records — a hash-chained seal over results.

When a partner runs the suite on their hardware and submits results, those results must be trustworthy.
This module seals a run: it hashes each result's *material verdict* (id, status, seed, exit code,
metrics, checks — not timing or logs), chains the hashes so order and membership are fixed, and records
the chain head as the run's **seal**. Re-verifying recomputes the chain from the report and, on a
mismatch, pinpoints the first altered result.

Two levels, kept honestly distinct:

* **Integrity** (plain ``sha256-chain``): any change to a sealed result is *detectable* — provided the
  seal itself is anchored somewhere the tamperer can't also edit (published, or held by the verifier).
  A tamperer who can rewrite both the results *and* the seal could recompute a consistent chain.
* **Authenticity** (``hmac-sha256-chain``, opt-in): the seal is HMAC-signed with a secret key, so a
  party without the key cannot forge a valid seal over altered results. This is what makes the record
  tamper-*evident* against a motivated party. The key is a **secret** — supplied via environment, never
  committed (see SECURITY.md).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from pathlib import Path

from .telemetry import now_iso

_GENESIS = hashlib.sha256(b"lab-seal-v1").hexdigest()


def _canonical(result: dict) -> str:
    """Deterministic serialization of the fields that define a result's verdict (order-independent)."""
    material = {
        "id": result.get("id"),
        "status": result.get("status"),
        "seed": result.get("seed"),
        "exit_code": result.get("exit_code"),
        "error": result.get("error"),
        "metrics": result.get("metrics", {}),
        "checks": [{"name": c.get("name"), "ok": c.get("ok"), "detail": c.get("detail")}
                   for c in result.get("checks", [])],
    }
    return json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)


def result_hash(result: dict) -> str:
    return hashlib.sha256(_canonical(result).encode()).hexdigest()


def _chain_head(leaf_hashes: list[str]) -> str:
    prev = _GENESIS
    for leaf in leaf_hashes:
        prev = hashlib.sha256((prev + leaf).encode()).hexdigest()
    return prev


@dataclass
class Seal:
    algo: str
    leaves: list[dict]                                # ordered [{"id":..., "hash":...}]
    chain_head: str
    count: int
    sealed_at: str
    signature: str | None = None                     # HMAC(key, chain_head) when signed

    @property
    def signed(self) -> bool:
        return self.signature is not None

    def to_json(self) -> str:
        return json.dumps({
            "algo": self.algo, "chain_head": self.chain_head, "signature": self.signature,
            "count": self.count, "sealed_at": self.sealed_at, "leaves": self.leaves,
        }, indent=2)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Seal":
        d = json.loads(Path(path).read_text())
        return cls(d["algo"], d["leaves"], d["chain_head"], d["count"], d["sealed_at"],
                   d.get("signature"))


def seal_report(report: dict, *, key: str | None = None) -> Seal:
    """Seal a run report (its ``to_dict()``). With ``key``, the seal is HMAC-signed (authenticity)."""
    results = report.get("results", [])
    leaves = [{"id": r.get("id"), "hash": result_hash(r)} for r in results]
    head = _chain_head([leaf["hash"] for leaf in leaves])
    signature = hmac.new(key.encode(), head.encode(), hashlib.sha256).hexdigest() if key else None
    return Seal("hmac-sha256-chain" if key else "sha256-chain", leaves, head,
                len(leaves), now_iso(), signature)


@dataclass
class VerifyResult:
    ok: bool
    integrity_ok: bool
    authenticity_ok: bool | None                     # None when the seal is unsigned or no key supplied
    tampered_at: str | None
    detail: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "integrity_ok": self.integrity_ok,
                "authenticity_ok": self.authenticity_ok, "tampered_at": self.tampered_at,
                "detail": self.detail}


def verify_report(report: dict, seal: Seal, *, key: str | None = None) -> VerifyResult:
    """Recompute the chain from ``report`` and check it against ``seal``; pinpoint the first change."""
    results = report.get("results", [])
    recomputed = [{"id": r.get("id"), "hash": result_hash(r)} for r in results]

    # Locate the first divergence (altered / reordered / removed / added result).
    tampered_at, detail = None, "results intact"
    for i in range(max(len(recomputed), len(seal.leaves))):
        sealed = seal.leaves[i] if i < len(seal.leaves) else None
        now = recomputed[i] if i < len(recomputed) else None
        if sealed is None:
            tampered_at, detail = now["id"], f"result added: {now['id']}"
            break
        if now is None:
            tampered_at, detail = sealed["id"], f"result removed: {sealed['id']}"
            break
        if sealed["id"] != now["id"]:
            tampered_at, detail = now["id"], f"result reordered/replaced at position {i}"
            break
        if sealed["hash"] != now["hash"]:
            tampered_at, detail = now["id"], f"result altered: {now['id']}"
            break

    head = _chain_head([leaf["hash"] for leaf in recomputed])
    integrity_ok = (tampered_at is None) and (head == seal.chain_head)

    authenticity_ok: bool | None = None
    if seal.signed:
        if key is None:
            detail += " | signed seal — supply the key to verify authenticity"
        else:
            expected = hmac.new(key.encode(), seal.chain_head.encode(), hashlib.sha256).hexdigest()
            authenticity_ok = hmac.compare_digest(expected, seal.signature or "")
            if not authenticity_ok:
                detail += " | signature invalid (wrong key or forged seal)"

    ok = integrity_ok and (authenticity_ok is not False)
    return VerifyResult(ok, integrity_ok, authenticity_ok, tampered_at, detail)
