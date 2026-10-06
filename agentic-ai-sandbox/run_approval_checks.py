"""Verify human approval, immutable action binding, and retry-safe outbox delivery."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from approval_outbox import ApprovalError, MockPaymentProvider, RefundApprovalOutbox, proposal_digest
from durable_state import SQLiteIdempotencyStore
from support_agent import ANTHROPIC_TOOLS, RunContext, ToolRuntime


def must_reject(action, expected_text: str) -> None:
    try:
        action()
    except ApprovalError as exc:
        assert expected_text.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"Expected approval rejection containing: {expected_text}")


def prepare(store, task_id: str, reason: str = "arrived too late") -> dict:
    context = RunContext(subject_id="customer-ada", task_id=task_id)
    runtime = ToolRuntime(idempotency_store=store, clock=lambda: 1000.0)
    proposal_result = runtime.call(
        "prepare_refund_proposal",
        {"order_ref": "ORD-100", "reason": reason},
        context,
    )
    runtime.call(
        "request_human_review",
        {"proposal_id": proposal_result["proposal_id"]},
        context,
    )
    return store.get("proposals", proposal_result["proposal_id"])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentic-approval-") as temp_dir:
        app_db = Path(temp_dir) / "application.sqlite3"
        provider_db = Path(temp_dir) / "payment-provider.sqlite3"
        store = SQLiteIdempotencyStore(app_db)
        approvals = RefundApprovalOutbox(app_db, store, {"operator-1"})
        proposal = prepare(store, "approval-main")
        digest = proposal_digest(proposal)

        assert "approve_refund" not in {tool["name"] for tool in ANTHROPIC_TOOLS}
        assert approvals.outbox_count(proposal["proposal_id"]) == 0
        must_reject(
            lambda: approvals.approve(proposal["proposal_id"], digest, "attacker"),
            "not authorized",
        )
        must_reject(
            lambda: approvals.approve(proposal["proposal_id"], "0" * 64, "operator-1"),
            "proposal changed",
        )
        assert approvals.outbox_count(proposal["proposal_id"]) == 0
        print("PASS  model has no approval tool; unauthorized and altered approvals create no outbox action")

        approved = approvals.approve(proposal["proposal_id"], digest, "operator-1", now_epoch=2000)
        duplicate = approvals.approve(proposal["proposal_id"], digest, "operator-1", now_epoch=2001)
        assert approved["status"] == "approved"
        assert duplicate["approval_id"] == approved["approval_id"]
        assert duplicate["outbox_id"] == approved["outbox_id"]
        assert approvals.outbox_count(proposal["proposal_id"]) == 1
        outbox_record = approvals.outbox_status(approved["outbox_id"])
        payload = json.loads(outbox_record["payload_json"])
        assert payload["amount_cents"] == 2000
        assert payload["currency"] == "USD"
        assert payload["proposal_digest"] == digest
        print("PASS  operator approval binds to the exact proposal and creates one outbox action")

        provider_first_process = MockPaymentProvider(provider_db)
        first_claim = approvals.claim_next(now_epoch=2000, lease_seconds=30)
        assert first_claim is not None
        first_result = provider_first_process.refund(first_claim["payload"], first_claim["idempotency_key"])
        assert first_result["status"] == "succeeded"
        assert approvals.claim_next(now_epoch=2029, lease_seconds=30) is None
        assert provider_first_process.unique_refund_count() == 1
        print("PASS  only approved outbox actions are claimed; active lease prevents a second worker claim")

        # Simulate worker restart after provider success but before the outbox ack.
        provider_restarted = MockPaymentProvider(provider_db)
        retry_claim = approvals.claim_next(now_epoch=2030, lease_seconds=30)
        assert retry_claim is not None
        retry_result = provider_restarted.refund(retry_claim["payload"], retry_claim["idempotency_key"])
        assert retry_result == first_result
        must_reject(
            lambda: approvals.complete(first_claim["outbox_id"], first_claim["claim_token"], first_result),
            "claim is stale",
        )
        completed = approvals.complete(retry_claim["outbox_id"], retry_claim["claim_token"], retry_result, now_epoch=2031)
        assert completed["status"] == "completed"
        assert provider_restarted.unique_refund_count() == 1
        assert approvals.outbox_status(retry_claim["outbox_id"])["attempts"] == 2
        print("PASS  expired worker lease retries with the same provider key and records one refund")

        expired = prepare(store, "approval-expired")
        expired_digest = proposal_digest(expired)
        must_reject(
            lambda: approvals.approve(
                expired["proposal_id"],
                expired_digest,
                "operator-1",
                now_epoch=expired["expires_at_epoch"],
            ),
            "expired",
        )
        assert approvals.outbox_count(expired["proposal_id"]) == 0
        print("PASS  expired proposal cannot be approved")

        rejected = prepare(store, "approval-rejected", reason="customer changed their mind")
        rejected_digest = proposal_digest(rejected)
        rejection = approvals.reject(rejected["proposal_id"], rejected_digest, "operator-1", now_epoch=2000)
        assert rejection["status"] == "rejected"
        must_reject(
            lambda: approvals.approve(rejected["proposal_id"], rejected_digest, "operator-1", now_epoch=2001),
            "already has status rejected",
        )
        assert approvals.outbox_count(rejected["proposal_id"]) == 0
        print("PASS  rejected proposal cannot later be approved or sent to payment")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
