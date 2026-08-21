import sqlite3

# Hand-extracted, section-level chunks from the six supplied PDFs (spec §6, §9).
# Committed as reviewed data rather than parsed at runtime — see spec §9 rationale.
_CHUNKS = [
    dict(chunk_id="policy_v3_precedence", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§1 Scope and source precedence",
         scenario_tags="sla,cancellation,service_credit",
         text="This policy defines default support severity and response targets. A signed "
              "customer agreement may override these defaults. When sources conflict, use the "
              "signed customer agreement first, then the current support policy, then current "
              "product documentation. Historical tickets and internal notes are context only "
              "and may contain incorrect past guidance."),
    dict(chunk_id="policy_v3_severity", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§2 Severity definitions", scenario_tags="sla",
         text="P1 - Critical: Complete production outage preventing all shipment creation for a "
              "customer, confirmed security incident or suspected credential exposure, or "
              "another event causing immediate material business risk with no workaround. "
              "P2 - High: Major feature unavailable or materially degraded for a customer, but "
              "core operations remain possible or a workaround exists. P3 - Normal: Minor "
              "defect, how-to question, configuration request, or issue with limited "
              "operational impact."),
    dict(chunk_id="policy_v3_targets", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§3 Default first-response targets", scenario_tags="sla",
         text="Enterprise: P1 30 minutes 24x7, P2 2 hours, P3 1 business day. Growth: P1 2 "
              "business hours, P2 4 business hours, P3 2 business days. Standard: P1 4 business "
              "hours, P2 1 business day, P3 2 business days."),
    dict(chunk_id="policy_v3_escalation", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§4 Escalation", scenario_tags="sla",
         text="P1 incidents should be escalated immediately. If a response target is already "
              "breached, the agent should clearly state the breach and recommend escalation "
              "rather than hiding uncertainty."),
    dict(chunk_id="policy_v2_targets", document_id="02", document_name="Support Policy v2",
         document_type="policy_deprecated", customer_id=None, status="DEPRECATED",
         effective_date="2025-01-01", section="Severity and response targets", scenario_tags="sla",
         text="DEPRECATED - DO NOT USE FOR CURRENT REQUESTS, superseded by Support Policy v3 "
              "effective 1 May 2026. Enterprise: P1 1 hour, P2 4 hours, P3 2 business days. "
              "Growth: P1 4 business hours, P2 1 business day, P3 3 business days. Standard: "
              "P1 8 business hours, P2 2 business days, P3 3 business days."),
    dict(chunk_id="sop_v4_cancellation", document_id="03", document_name="Cancellation & Service Credit SOP v4",
         document_type="sop", customer_id=None, status="CURRENT", effective_date="2026-06-15",
         section="§1 Order cancellation", scenario_tags="cancellation",
         text="DRAFT: may be cancelled with no fee. BOOKED, not yet PICKED_UP: may be "
              "cancelled; no fee within 30 minutes of booking, after 30 minutes charge INR 250 "
              "unless a customer agreement explicitly waives the cancellation fee. PICKED_UP: "
              "do not cancel, use the return-to-origin workflow. DELIVERED: cannot be cancelled."),
    dict(chunk_id="sop_v4_credit", document_id="03", document_name="Cancellation & Service Credit SOP v4",
         document_type="sop", customer_id=None, status="CURRENT", effective_date="2026-06-15",
         section="§2 Failed-pickup service credits", scenario_tags="service_credit",
         text="A customer is eligible for a service credit when pickup is more than 2 hours "
              "past the end of the scheduled pickup window, the carrier is at fault, and there "
              "is no customer-caused issue. The default credit is the lower of INR 500 or 10% "
              "of the shipment fee. A signed customer agreement may replace the default delay "
              "threshold, credit amount, or cap."),
    dict(chunk_id="sop_v4_guardrails", document_id="03", document_name="Cancellation & Service Credit SOP v4",
         document_type="sop", customer_id=None, status="CURRENT", effective_date="2026-06-15",
         section="§3 Approval and uncertainty", scenario_tags="service_credit,cancellation",
         text="Any individual credit above INR 1,000 requires manager approval. Do not promise "
              "a credit when carrier fault, pickup timing, or customer fault is unknown. When "
              "data conflicts, identify the conflict and request verification before a "
              "state-changing action."),
    dict(chunk_id="product_guide_capabilities", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§1 Plan capabilities", scenario_tags="product_capability",
         text="Bulk Upload: available on Growth and Enterprise, supported file size up to 5,000 "
              "rows per CSV. Standard: Bulk Upload not included. BOOKED means the shipment is "
              "created but pickup confirmation not yet received. PICKED_UP means carrier pickup "
              "has been confirmed."),
    dict(chunk_id="product_guide_ki208", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§2 Known issues - KI-208", scenario_tags="known_issue,product_capability",
         text="KI-208 Bulk Upload failures on large CSVs. Opened 10 August 2026, Investigating. "
              "Some Growth and Enterprise customers experience intermittent failures on CSV "
              "uploads above approximately 3,000 rows, even though the supported product limit "
              "remains 5,000 rows. Workaround: split the upload into files below 3,000 rows. "
              "Individual shipment creation is unaffected."),
    dict(chunk_id="product_guide_ki211", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§2 Known issues - KI-211", scenario_tags="known_issue",
         text="KI-211 SwiftShip pickup webhook delay. Opened 12 August 2026, Monitoring. "
              "SwiftShip pickup confirmation webhooks can arrive up to 20 minutes late. A "
              "parcel may physically be collected while ParcelPilot still shows BOOKED. Before "
              "telling a customer that a pickup did not occur, verify the carrier status or "
              "wait through the known delay window."),
    dict(chunk_id="product_guide_ki176", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§3 Resolved issue - KI-176", scenario_tags="known_issue",
         text="KI-176 Address validation: Resolved 18 July 2026. Do not use this resolved issue "
              "to explain new incidents unless evidence specifically matches it."),
    dict(chunk_id="northstar_support_terms", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§1 Support terms", scenario_tags="sla",
         text="For Northstar Logistics, the following first-response targets replace "
              "ParcelPilot's standard support-policy targets: P1 15 minutes 24x7, P2 1 hour, "
              "P3 8 business hours."),
    dict(chunk_id="northstar_cancellation", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§2 Shipment cancellation", scenario_tags="cancellation",
         text="Northstar may cancel any BOOKED shipment before pickup with no cancellation fee, "
              "regardless of how long ago the shipment was booked. Once a shipment is "
              "PICKED_UP, the standard return-to-origin process applies."),
    dict(chunk_id="northstar_credits", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§3 Service credits", scenario_tags="service_credit",
         text="Monthly aggregate service credits are capped at INR 5,000. Unless this agreement "
              "states otherwise, the current ParcelPilot service-credit SOP applies."),
    dict(chunk_id="northstar_contact", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§4 Account contact", scenario_tags="",
         text="Dedicated CSM: Priya Mehta."),
    dict(chunk_id="lumenworks_support_terms", document_id="06", document_name="LumenWorks Service Agreement",
         document_type="customer_agreement", customer_id="ACCT-002", status="ACTIVE",
         effective_date="2026-03-01", section="§1 Support terms", scenario_tags="sla",
         text="P1 2 business hours, P2 4 business hours, P3 2 business days. No weekend or "
              "after-hours support coverage."),
    dict(chunk_id="lumenworks_cancellation", document_id="06", document_name="LumenWorks Service Agreement",
         document_type="customer_agreement", customer_id="ACCT-002", status="ACTIVE",
         effective_date="2026-03-01", section="§2 Cancellation terms", scenario_tags="cancellation",
         text="No special cancellation-fee waiver applies. Use the current ParcelPilot "
              "Cancellation & Service Credit SOP."),
    dict(chunk_id="lumenworks_credits", document_id="06", document_name="LumenWorks Service Agreement",
         document_type="customer_agreement", customer_id="ACCT-002", status="ACTIVE",
         effective_date="2026-03-01", section="§3 Failed-pickup credits", scenario_tags="service_credit",
         text="If a pickup is more than 4 hours past the end of the scheduled pickup window, "
              "the carrier is at fault, and the customer is not at fault, LumenWorks receives a "
              "fixed INR 300 service credit. This clause replaces the default failed-pickup "
              "credit amount and timing threshold in the SOP."),
]


def load(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO document_chunks (chunk_id, document_id, document_name, document_type, "
        "customer_id, status, effective_date, section, scenario_tags, text) "
        "VALUES (:chunk_id, :document_id, :document_name, :document_type, :customer_id, "
        ":status, :effective_date, :section, :scenario_tags, :text)",
        _CHUNKS,
    )
    conn.commit()
