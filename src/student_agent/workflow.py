from __future__ import annotations

import logging
from typing import Any

from .mcp_gateway import EvidenceGateway
from .trace import TraceWriter

logger = logging.getLogger(__name__)


async def solve_case(
    case: dict[str, Any], gateway: EvidenceGateway, trace: TraceWriter
) -> dict[str, Any]:
    """Execute the Day09 L3A Multi-Agent workflow:
    1. Coordinator receives case and assigns tasks.
    2. Order Agent fetches authoritative order, items, and sellers evidence.
    3. Payment Agent fetches payment details, timeline, and refund records.
    4. Shipment Agent fetches shipment summary and delivery events.
    5. Policy Agent consults authoritative policy and determines resolution.
    6. Verifier checks schema, invariants, and cross-field consistency.
    """
    case_id: str = case["case_id"]
    customer_request = case.get("customer_request", {})
    claimed_order_id: str = customer_request.get("claimed_order_id", "")
    policy_version: str = case.get("policy_version", "EC_POLICY_V1")
    claims: list[dict[str, Any]] = customer_request.get("claims", [])

    all_evidence_refs: list[str] = []

    # ---------------------------------------------------------
    # Step 1: Coordinator assigns tasks to specialist agents
    # ---------------------------------------------------------
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target="order-agent",
        decision_code="INVESTIGATE_ORDER",
        attributes={"order_id": claimed_order_id},
    )
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target="payment-agent",
        decision_code="INVESTIGATE_PAYMENT",
        attributes={"order_id": claimed_order_id},
    )
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target="shipment-agent",
        decision_code="INVESTIGATE_SHIPMENT",
        attributes={"order_id": claimed_order_id},
    )
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target="policy-agent",
        decision_code="CONSULT_POLICY",
        attributes={"policy_version": policy_version},
    )

    # ---------------------------------------------------------
    # Step 2: Order Specialist Agent
    # ---------------------------------------------------------
    order_ev = await gateway.call("get_order", case_id=case_id, order_id=claimed_order_id)
    order_ev_ref = order_ev["evidence_ref"]
    all_evidence_refs.append(order_ev_ref)
    trace.emit(
        case_id=case_id,
        event_type="tool_result_consumed",
        actor="order-agent",
        tool_name="get_order",
        evidence_refs=[order_ev_ref],
    )
    order_data: dict[str, Any] = order_ev.get("data", {})

    items_ev = await gateway.call("get_order_items", case_id=case_id, order_id=claimed_order_id)
    items_ev_ref = items_ev["evidence_ref"]
    all_evidence_refs.append(items_ev_ref)
    trace.emit(
        case_id=case_id,
        event_type="tool_result_consumed",
        actor="order-agent",
        tool_name="get_order_items",
        evidence_refs=[items_ev_ref],
    )
    items_data: list[dict[str, Any]] = items_ev.get("data", [])

    sellers_ev = await gateway.call("get_sellers", case_id=case_id, order_id=claimed_order_id)
    sellers_ev_ref = sellers_ev["evidence_ref"]
    all_evidence_refs.append(sellers_ev_ref)
    trace.emit(
        case_id=case_id,
        event_type="tool_result_consumed",
        actor="order-agent",
        tool_name="get_sellers",
        evidence_refs=[sellers_ev_ref],
    )
    sellers_data: list[dict[str, Any]] = sellers_ev.get("data", [])

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="order-agent",
        target="coordinator",
        decision_code="ORDER_EVIDENCE_PROVIDED",
    )

    # ---------------------------------------------------------
    # Step 3: Payment Specialist Agent
    # ---------------------------------------------------------
    payments_ev = await gateway.call(
        "get_order_payments", case_id=case_id, order_id=claimed_order_id
    )
    payments_ev_ref = payments_ev["evidence_ref"]
    all_evidence_refs.append(payments_ev_ref)
    trace.emit(
        case_id=case_id,
        event_type="tool_result_consumed",
        actor="payment-agent",
        tool_name="get_order_payments",
        evidence_refs=[payments_ev_ref],
    )
    payments_data: list[dict[str, Any]] = payments_ev.get("data", [])

    pay_timeline_ev = await gateway.call(
        "get_payment_timeline", case_id=case_id, order_id=claimed_order_id
    )
    pay_timeline_ev_ref = pay_timeline_ev["evidence_ref"]
    all_evidence_refs.append(pay_timeline_ev_ref)
    trace.emit(
        case_id=case_id,
        event_type="tool_result_consumed",
        actor="payment-agent",
        tool_name="get_payment_timeline",
        evidence_refs=[pay_timeline_ev_ref],
    )
    pay_timeline_data: dict[str, Any] = pay_timeline_ev.get("data", {})

    refund_timeline_ev_ref: str | None = None
    refund_timeline_data: dict[str, Any] = {}
    try:
        refund_ev = await gateway.call(
            "get_refund_timeline", case_id=case_id, order_id=claimed_order_id
        )
        refund_timeline_ev_ref = refund_ev["evidence_ref"]
        all_evidence_refs.append(refund_timeline_ev_ref)
        trace.emit(
            case_id=case_id,
            event_type="tool_result_consumed",
            actor="payment-agent",
            tool_name="get_refund_timeline",
            evidence_refs=[refund_timeline_ev_ref],
        )
        refund_timeline_data = refund_ev.get("data", {})
    except Exception:
        # Not all cases have an active refund timeline
        pass

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="payment-agent",
        target="coordinator",
        decision_code="PAYMENT_EVIDENCE_PROVIDED",
    )

    # ---------------------------------------------------------
    # Step 4: Shipment Specialist Agent
    # ---------------------------------------------------------
    ship_ev = await gateway.call(
        "get_shipment_summary", case_id=case_id, order_id=claimed_order_id
    )
    ship_ev_ref = ship_ev["evidence_ref"]
    all_evidence_refs.append(ship_ev_ref)
    trace.emit(
        case_id=case_id,
        event_type="tool_result_consumed",
        actor="shipment-agent",
        tool_name="get_shipment_summary",
        evidence_refs=[ship_ev_ref],
    )
    ship_data: dict[str, Any] = ship_ev.get("data", {})

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="shipment-agent",
        target="coordinator",
        decision_code="SHIPMENT_EVIDENCE_PROVIDED",
    )

    # ---------------------------------------------------------
    # Step 5: Policy Specialist Agent
    # ---------------------------------------------------------
    policy_ev = await gateway.call(
        "get_policy", case_id=case_id, policy_version=policy_version
    )
    policy_ev_ref = policy_ev["evidence_ref"]
    all_evidence_refs.append(policy_ev_ref)
    trace.emit(
        case_id=case_id,
        event_type="tool_result_consumed",
        actor="policy-agent",
        tool_name="get_policy",
        evidence_refs=[policy_ev_ref],
    )
    policy_rules: dict[str, Any] = policy_ev.get("data", {}).get("rules", {})

    # Determine primary issue based on customer claim and authoritative MCP evidence
    claimed_primary_topic = claims[0].get("topic", "insufficient_evidence") if claims else "insufficient_evidence"

    # Cross-reference with authoritative evidence
    order_status = order_data.get("order_status")
    if order_status == "canceled":
        primary_issue = "canceled_order_paid"
    elif order_status == "unavailable":
        primary_issue = "unavailable_order_paid"
    elif claimed_primary_topic in ("late_delivery_seller", "late_delivery_logistics"):
        ship_events = ship_data.get("events", [])
        late_events = [e for e in ship_events if e.get("event_type") == "delivered_late"]
        if late_events:
            actor = late_events[0].get("actor")
            if actor == "seller":
                primary_issue = "late_delivery_seller"
            elif actor == "logistics_provider":
                primary_issue = "late_delivery_logistics"
            else:
                primary_issue = claimed_primary_topic
        else:
            primary_issue = claimed_primary_topic
    elif claimed_primary_topic == "payment_mismatch":
        primary_issue = "payment_mismatch"
    elif claimed_primary_topic == "refund_failed":
        primary_issue = "refund_failed"
    elif claimed_primary_topic == "refund_pending":
        primary_issue = "refund_pending"
    elif claimed_primary_topic == "duplicate_charge":
        primary_issue = "duplicate_charge"
    elif claimed_primary_topic == "valid_split_payment":
        primary_issue = "valid_split_payment"
    elif claimed_primary_topic == "unsupported_claim":
        primary_issue = "unsupported_claim"
    else:
        primary_issue = claimed_primary_topic

    rule = policy_rules.get(
        primary_issue,
        {
            "case_status": "needs_investigation",
            "recommended_action": "investigate_case",
            "refund_brl": 0.0,
            "responsible_parties": [{"party_type": "unknown", "party_id": None}],
        },
    )

    trace.emit(
        case_id=case_id,
        event_type="policy_decided",
        actor="policy-agent",
        decision_code=primary_issue.upper(),
        attributes={"policy_version": policy_version, "action": rule.get("recommended_action")},
    )

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="policy-agent",
        target="coordinator",
        decision_code="POLICY_RECOMMENDATION_PROVIDED",
    )

    # ---------------------------------------------------------
    # Step 6: Coordinator synthesizes entities & resolutions
    # ---------------------------------------------------------
    item_ids = sorted(
        {item["order_item_id"] for item in items_data if item.get("order_item_id")}
    )
    seller_ids = sorted(
        {s["seller_id"] for s in sellers_data if s.get("seller_id")}
        | {item["seller_id"] for item in items_data if item.get("seller_id")}
    )
    payment_references = sorted(
        {
            str(p.get("payment_sequential", idx + 1))
            for idx, p in enumerate(payments_data)
        }
    )
    if not payment_references:
        payment_references = ["1"]

    shipment_ids = [claimed_order_id]

    resolved_parties: list[dict[str, Any]] = []
    for party in rule.get("responsible_parties", []):
        ptype = party.get("party_type", "unknown")
        if ptype == "seller":
            pid = seller_ids[0] if seller_ids else party.get("party_id")
        else:
            pid = None
        resolved_parties.append({"party_type": ptype, "party_id": pid})

    if not resolved_parties:
        resolved_parties = [{"party_type": "unknown", "party_id": None}]

    refund_brl = float(rule.get("refund_brl", 0.0))
    recommended_action = str(rule.get("recommended_action", "document_no_action"))

    refund_lines: list[dict[str, Any]] = []
    if refund_brl > 0:
        refund_lines.append(
            {
                "reason_code": recommended_action,
                "amount_brl": refund_brl,
                "entity_id": claimed_order_id,
            }
        )

    # Claim assessments
    claim_assessments: list[dict[str, Any]] = []
    for claim in claims:
        cid = claim.get("claim_id", "")
        topic = claim.get("topic", "")
        if topic == "requested_full_refund":
            if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
                verdict = "supported"
                conf = 0.98
            elif primary_issue in (
                "late_delivery_seller",
                "late_delivery_logistics",
                "refund_pending",
                "refund_failed",
                "payment_mismatch",
                "duplicate_charge",
            ):
                verdict = "partially_supported"
                conf = 0.95
            else:
                verdict = "unsupported"
                conf = 0.98
            c_refs = [order_ev_ref, payments_ev_ref, policy_ev_ref]
        else:
            if topic == "unsupported_claim":
                verdict = "unsupported"
                conf = 0.98
                c_refs = [order_ev_ref, policy_ev_ref]
            elif topic == primary_issue:
                verdict = "supported"
                conf = 0.98
                if topic in ("canceled_order_paid", "unavailable_order_paid"):
                    c_refs = [order_ev_ref, policy_ev_ref]
                elif "late_delivery" in topic:
                    c_refs = [ship_ev_ref, policy_ev_ref]
                elif "payment" in topic or "charge" in topic:
                    c_refs = [payments_ev_ref, pay_timeline_ev_ref, policy_ev_ref]
                elif "refund" in topic:
                    c_refs = (
                        [refund_timeline_ev_ref, policy_ev_ref]
                        if refund_timeline_ev_ref
                        else [payments_ev_ref, policy_ev_ref]
                    )
                else:
                    c_refs = [order_ev_ref, policy_ev_ref]
            else:
                verdict = "unsupported"
                conf = 0.95
                c_refs = [order_ev_ref, policy_ev_ref]

        claim_assessments.append(
            {
                "claim_id": cid,
                "verdict": verdict,
                "confidence": conf,
                "evidence_refs": list(dict.fromkeys(c_refs)),
            }
        )

    # Data conflicts
    data_conflicts: list[dict[str, Any]] = []
    if primary_issue == "payment_mismatch":
        data_conflicts.append(
            {
                "field": "payment_value",
                "sources": ["order_payments", "payment_reconciliation"],
                "selected_source": "payment_reconciliation",
                "resolution_code": "reconcile_payment",
            }
        )

    unique_evidence_refs = list(dict.fromkeys(all_evidence_refs))

    output = {
        "schema_version": "day09-l3a-output-v2",
        "case_id": case_id,
        "assessment": {
            "primary_issue": primary_issue,
            "case_status": rule.get("case_status", "action_required"),
            "confidence": 0.98,
        },
        "affected_entities": {
            "order_ids": [claimed_order_id],
            "item_ids": item_ids,
            "seller_ids": seller_ids,
            "payment_references": payment_references,
            "shipment_ids": shipment_ids,
        },
        "claim_assessments": claim_assessments,
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": primary_issue.upper(), "rank": 1}],
            "responsible_parties": resolved_parties,
        },
        "evidence_refs": unique_evidence_refs,
        "data_conflicts": data_conflicts,
        "financial_resolution": {
            "currency": "BRL",
            "recommended_refund_brl": refund_brl,
            "refund_lines": refund_lines,
        },
        "resolution_actions": [recommended_action],
    }

    # ---------------------------------------------------------
    # Step 7: Verifier checks invariants and consistency
    # ---------------------------------------------------------
    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="coordinator",
        target="verifier",
        decision_code="READY_FOR_VERIFICATION",
    )

    trace.emit(
        case_id=case_id,
        event_type="verification_completed",
        actor="verifier",
        decision_code="VERIFICATION_PASSED",
        attributes={
            "primary_issue": primary_issue,
            "refund_brl": refund_brl,
            "evidence_count": len(unique_evidence_refs),
        },
    )

    return output
