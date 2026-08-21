from typing import Literal

from pydantic import BaseModel

from app import config

BoolOrUnknown = bool | Literal["unknown"]


class IncidentFacts(BaseModel):
    is_security_incident: BoolOrUnknown
    is_complete_shipment_outage: BoolOrUnknown
    immediate_material_business_risk: BoolOrUnknown
    is_major_feature_degraded: BoolOrUnknown
    core_operations_possible: BoolOrUnknown
    workaround_exists: BoolOrUnknown


def map_severity(f: IncidentFacts) -> tuple[str | None, bool]:
    # A confirmed True on either P1 condition is P1 regardless of whether the
    # OTHER condition is "unknown" -- checking "any unknown -> needs_review"
    # BEFORE checking "any True -> P1" was a real bug: a ticket that is
    # definitely a security incident but where the model can't tell if it's
    # ALSO a complete outage would incorrectly need review instead of being
    # confidently P1. True-wins-first, then unknown-blocks, then fall through.
    if f.is_security_incident is True or f.is_complete_shipment_outage is True:
        return "P1", False
    if "unknown" in (f.is_security_incident, f.is_complete_shipment_outage):
        return None, True

    if f.immediate_material_business_risk is True and f.workaround_exists is False:
        return "P1", False
    if f.immediate_material_business_risk == "unknown":
        return None, True
    if f.immediate_material_business_risk is True and f.workaround_exists == "unknown":
        return None, True

    if f.is_major_feature_degraded is True and (f.core_operations_possible is True or f.workaround_exists is True):
        return "P2", False
    if f.is_major_feature_degraded == "unknown":
        return None, True
    if f.is_major_feature_degraded is True and "unknown" in (f.core_operations_possible, f.workaround_exists):
        return None, True

    return "P3", False


_PROMPT = """You are extracting structured incident facts from a support ticket for a
logistics company. Read the subject and description below and answer each question
with true, false, or "unknown" if the text genuinely does not say. Do not guess.

Subject: {subject}
Description: {description}

Field definitions (answer based on exactly this meaning, not a looser reading):
- is_security_incident: a confirmed security incident or suspected credential/API-key exposure.
- is_complete_shipment_outage: shipment CREATION is completely blocked for a customer
  (true even if other features, like viewing existing shipments, still work -- the
  criterion is specifically about creating new shipments, not the whole system).
- immediate_material_business_risk: some other event causing immediate material
  business risk, distinct from the two conditions above.
- is_major_feature_degraded: a major feature (not all of shipment creation) is
  unavailable or materially degraded.
- core_operations_possible: core operations remain possible despite the degradation.
- workaround_exists: a workaround exists for the degraded/unavailable feature.

Answer as JSON matching this schema:
{{
  "is_security_incident": true|false|"unknown",
  "is_complete_shipment_outage": true|false|"unknown",
  "immediate_material_business_risk": true|false|"unknown",
  "is_major_feature_degraded": true|false|"unknown",
  "core_operations_possible": true|false|"unknown",
  "workaround_exists": true|false|"unknown"
}}
"""


def extract_incident_facts(subject: str, description: str) -> IncidentFacts:
    from google import genai

    api_key = config.require_gemini_api_key()
    client = genai.Client(api_key=api_key)
    # response_schema=IncidentFacts is deliberately NOT passed here: pydantic's
    # bool | Literal["unknown"] fields translate to a JSON schema using
    # anyOf + const, and google-genai's own Schema type rejects `const`
    # ("Extra inputs are not permitted") -- a real incompatibility only
    # discoverable with a live API key, which no prior review had. The
    # prompt already spells out the exact JSON shape in text, and the
    # response is still strictly validated against IncidentFacts below, so
    # correctness doesn't depend on Gemini's schema enforcement anyway.
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=_PROMPT.format(subject=subject, description=description),
        config={"response_mime_type": "application/json"},
    )
    return IncidentFacts.model_validate_json(response.text)
