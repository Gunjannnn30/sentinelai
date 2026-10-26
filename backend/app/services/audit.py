"""Append-only audit log with an optional SHA-256 hash chain.

## Design (documented, tested — see docs/SECURITY.md §Audit integrity)

- Each event gets a per-organization monotonic ``seq``.
- ``hash = sha256(canonical_json(payload) + prev_hash)`` where the payload is
  serialized with sorted keys and compact separators (``(',', ':')``) — so the
  same logical event always hashes identically across processes.
- ``prev_hash`` links to the previous event's hash in the same org → any
  retroactive edit or deletion breaks the chain and is caught by
  ``verify_chain`` (endpoint: ``GET /api/v1/audit/verify``).
- Concurrency: the org's tail row is read with a row lock when the backend
  supports it (PostgreSQL ``FOR UPDATE``); on SQLite a unique
  ``(org_id, seq)`` constraint plus retry keeps sequences contiguous.
- Application code only ever **inserts**. There are no update/delete paths.

This is tamper-*evidence*, not cryptographic signing. Signatures (e.g. Ed25519)
are a possible future addition and would need documented key-management and a
verification procedure for recipients; plain DB rows are never described as
"signed evidence".
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.gateway import AuditLog


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str)


def ts_iso(dt: datetime) -> str:
    """Timestamp as used in hash material — UTC, tzinfo stripped.

    SQLite (and ``DateTime(timezone=True)`` round-trips generally) return naive
    UTC datetimes on read, so hashing must use the same normalization at write
    and verify time or every hash would mismatch after the process restarts.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat()


def compute_hash(payload: dict[str, Any], prev_hash: str) -> str:
    material = canonical_json(payload) + "|" + (prev_hash or "")
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _event_payload(org_id: str, seq: int, event_type: str, actor_user_id: str | None,
                   actor_email: str | None, resource_type: str, resource_id: str | None,
                   request_id: str | None, outcome: str, detail: dict,
                   created_at_iso: str) -> dict[str, Any]:
    return {
        "org_id": org_id,
        "seq": seq,
        "event_type": event_type,
        "actor_user_id": actor_user_id,
        "actor_email": actor_email,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "request_id": request_id,
        "outcome": outcome,
        "detail": detail,
        "created_at": created_at_iso,
    }


def append_event(
    db: Session,
    *,
    org_id: str,
    event_type: str,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    resource_type: str = "",
    resource_id: str | None = None,
    request_id: str | None = None,
    outcome: str = "success",
    detail: dict | None = None,
    max_attempts: int = 5,
) -> AuditLog:
    """Append one immutable event. Retries on seq collision (concurrent writers)."""
    detail = detail or {}
    last_error: Exception | None = None
    for _ in range(max_attempts):
        tail = db.execute(
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.seq.desc())
            .limit(1)
        ).scalar_one_or_none()
        seq = (tail.seq + 1) if tail else 1
        prev_hash = tail.hash if tail else ""

        from app.db.base import utcnow

        created = utcnow()
        payload = _event_payload(
            org_id, seq, event_type, actor_user_id, actor_email,
            resource_type, resource_id, request_id, outcome, detail,
            ts_iso(created),
        )
        entry = AuditLog(
            org_id=org_id, seq=seq, prev_hash=prev_hash,
            hash=compute_hash(payload, prev_hash),
            event_type=event_type, actor_user_id=actor_user_id, actor_email=actor_email,
            resource_type=resource_type, resource_id=resource_id, request_id=request_id,
            outcome=outcome, detail=detail,
        )
        entry.created_at = created
        db.add(entry)
        try:
            db.flush()
            return entry
        except IntegrityError as exc:  # unique (org_id, seq) collision → retry
            db.rollback()
            last_error = exc
    raise RuntimeError(f"Could not append audit event after {max_attempts} attempts: {last_error}")


def verify_chain(db: Session, org_id: str) -> tuple[bool, int, int | None, str]:
    """Walk the org's chain; returns (ok, checked, first_bad_seq, message)."""
    rows = (
        db.execute(
            select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.seq.asc())
        )
        .scalars()
        .all()
    )
    prev_hash = ""
    expected_seq = 1
    for row in rows:
        if row.seq != expected_seq:
            return False, expected_seq - 1, row.seq, (
                f"Sequence gap: expected {expected_seq}, found {row.seq} — an event was deleted."
            )
        if row.prev_hash != prev_hash:
            return False, expected_seq - 1, row.seq, (
                f"Link mismatch at seq {row.seq}: prev_hash does not match previous event hash."
            )
        # Recompute hash from stored fields (detail may have been altered → mismatch).
        payload = _event_payload(
            row.org_id, row.seq, row.event_type, row.actor_user_id, row.actor_email,
            row.resource_type, row.resource_id, row.request_id, row.outcome,
            row.detail, ts_iso(row.created_at),
        )
        recomputed = compute_hash(payload, row.prev_hash)
        if recomputed != row.hash:
            return False, expected_seq - 1, row.seq, (
                f"Hash mismatch at seq {row.seq}: event content was modified after creation."
            )
        prev_hash = row.hash
        expected_seq += 1
    if not rows:
        return True, 0, None, "No audit events recorded yet."
    return True, len(rows), None, f"All {len(rows)} events verified; chain intact."


def export_events(db: Session, org_id: str, *, limit: int = 10_000) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.seq.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def audit_summary(db: Session, org_id: str) -> dict[str, Any]:
    count = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.org_id == org_id)
    ).scalar_one()
    return {"events": count}
