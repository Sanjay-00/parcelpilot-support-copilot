from app.severity import IncidentFacts, map_severity


def test_security_incident_is_p1():
    facts = IncidentFacts(
        is_security_incident=True, is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=True, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P1"
    assert needs_review is False


def test_complete_outage_is_p1():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=True,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=False, workaround_exists=False,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P1"


def test_business_risk_catch_all_without_workaround_is_p1():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=False,
        immediate_material_business_risk=True, is_major_feature_degraded=False,
        core_operations_possible=False, workaround_exists=False,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P1"


def test_major_feature_degraded_with_workaround_is_p2():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=True,
        core_operations_possible=False, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P2"


def test_minor_issue_is_p3():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=True, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P3"


def test_unknown_security_field_forces_needs_review():
    facts = IncidentFacts(
        is_security_incident="unknown", is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=True, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity is None
    assert needs_review is True


import os

import pytest

from app.severity import extract_incident_facts, map_severity


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_tkt505_api_key_exposure_extracts_as_p1():
    facts = extract_incident_facts(
        "Possible API key exposure",
        "An employee accidentally posted a screenshot containing a production API "
        "key in a public channel. They are asking what to do.",
    )
    severity, _ = map_severity(facts)
    assert severity == "P1"


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_tkt501_complete_outage_extracts_as_p1():
    facts = extract_incident_facts(
        "All shipment creation is failing",
        "Every user at Northstar gets HTTP 500 when creating any shipment. "
        "Existing shipments can still be viewed.",
    )
    severity, _ = map_severity(facts)
    assert severity == "P1"
