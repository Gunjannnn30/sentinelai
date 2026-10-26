"""Audit hash-chain tests: linking, tamper evidence, org scoping.

Every test gets its **own organization** — the chain is append-only and
tampering is by design unrecoverable, so tests must not share one chain.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.gateway import AuditLog
from app.services.audit import append_event, audit_summary, verify_chain


@pytest.fixture()
def chain_org(fresh: TestClient) -> str:
    """A brand-new org whose chain starts with its `auth.register` event."""
    suffix = uuid.uuid4().hex[:10]
    resp = fresh.post(
        "/api/v1/auth/register",
        json={
            "email": f"chain-{suffix}@example.com",
            "password": "Chain-Passw0rd!",
            "org_name": f"Chain {suffix}",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["org"]["id"]


def events_for(org_id, count=5):
    with SessionLocal() as db:
        for i in range(count):
            append_event(db, org_id=org_id, event_type="test.event", detail={"i": i})
        db.commit()


def rows_for(org_id, event_type=None):
    with SessionLocal() as db:
        query = db.query(AuditLog).filter(AuditLog.org_id == org_id)
        if event_type:
            query = query.filter(AuditLog.event_type == event_type)
        return query.order_by(AuditLog.seq).all()


def test_chain_links_and_verifies(chain_org):
    events_for(chain_org, count=5)
    with SessionLocal() as db:
        ok, checked, bad_seq, message = verify_chain(db, chain_org)
    assert ok is True
    # 1 register event + 5 appended
    assert checked >= 6
    assert bad_seq is None
    assert "verified" in message


def test_seq_is_contiguous(chain_org):
    events_for(chain_org, count=3)
    rows = rows_for(chain_org, event_type="test.event")
    seqs = [r.seq for r in rows]
    assert len(seqs) == 3
    assert seqs == list(range(seqs[0], seqs[0] + 3))


def test_prev_hash_links_each_event(chain_org):
    events_for(chain_org, count=3)
    rows = rows_for(chain_org)
    # The chain head is the registration event: it has no predecessor.
    assert rows[0].seq == 1
    assert rows[0].prev_hash == ""
    for prev, nxt in zip(rows, rows[1:], strict=False):
        assert nxt.prev_hash == prev.hash


def test_tampered_detail_detected(chain_org):
    events_for(chain_org, count=4)
    row = rows_for(chain_org, event_type="test.event")[1]
    bad_seq = row.seq
    row.detail = {"i": 999}
    with SessionLocal() as db:
        db.merge(row)
        db.commit()
    with SessionLocal() as db:
        ok, checked, first_bad, message = verify_chain(db, chain_org)
    assert ok is False
    assert first_bad == bad_seq
    assert "modified" in message


def test_tampered_hash_detected(chain_org):
    events_for(chain_org, count=3)
    row = rows_for(chain_org, event_type="test.event")[0]
    bad_seq = row.seq
    row.hash = "0" * 64
    with SessionLocal() as db:
        db.merge(row)
        db.commit()
    with SessionLocal() as db:
        ok, _, first_bad, message = verify_chain(db, chain_org)
    assert ok is False
    assert first_bad == bad_seq


def test_deleted_event_breaks_chain(chain_org):
    events_for(chain_org, count=4)
    victim = rows_for(chain_org, event_type="test.event")[1]
    with SessionLocal() as db:
        doomed = db.get(AuditLog, victim.id)
        db.delete(doomed)
        db.commit()
    with SessionLocal() as db:
        ok, _, first_bad, message = verify_chain(db, chain_org)
    assert ok is False
    assert "deleted" in message or "gap" in message.lower()


def test_chains_are_independent_per_org(chain_org, fresh: TestClient):
    org_a = chain_org
    events_for(org_a, count=2)

    suffix = uuid.uuid4().hex[:10]
    r = fresh.post(
        "/api/v1/auth/register",
        json={"email": f"chain2-{suffix}@example.com", "password": "Chained2!pass",
              "org_name": f"ChainOrg2 {suffix}"},
        headers={"X-CSRF-Token": fresh.cookies.get("sentinel_csrf", "")},
    )
    assert r.status_code == 201, r.text
    org_b = r.json()["org"]["id"]
    events_for(org_b, count=2)

    with SessionLocal() as db:
        ok_a, *_ = verify_chain(db, org_a)
        ok_b, *_ = verify_chain(db, org_b)
    assert ok_a is True and ok_b is True

    # Tampering org B must not affect org A's verification.
    row = rows_for(org_b, event_type="test.event")[0]
    row.detail = {"i": -1}
    with SessionLocal() as db:
        db.merge(row)
        db.commit()
    with SessionLocal() as db:
        ok_a2, *_ = verify_chain(db, org_a)
        ok_b2, *_ = verify_chain(db, org_b)
    assert ok_a2 is True
    assert ok_b2 is False


def test_detail_is_json_serializable(chain_org):
    with SessionLocal() as db:
        append_event(db, org_id=chain_org, event_type="test.json",
                     detail={"a": [1, {"b": 2}]})
        db.commit()
    row = rows_for(chain_org, event_type="test.json")[0]
    # The JSON column round-trips to a dict; the stored text stays canonical.
    assert row.detail["a"][1]["b"] == 2
    assert json.loads(json.dumps(row.detail))["a"][1]["b"] == 2


def test_audit_summary_counts(chain_org):
    events_for(chain_org, count=3)
    with SessionLocal() as db:
        summary = audit_summary(db, chain_org)
    assert summary["events"] >= 4   # register + 3


def test_fresh_org_chain_verifies(chain_org):
    """A new org's chain is small (registration only) but already valid."""
    with SessionLocal() as db:
        ok, checked, bad, message = verify_chain(db, chain_org)
    assert ok is True
    assert checked >= 1
    assert bad is None
