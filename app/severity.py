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
    if "unknown" in (f.is_security_incident, f.is_complete_shipment_outage):
        return None, True
    if f.is_security_incident or f.is_complete_shipment_outage:
        return "P1", False

    if "unknown" in (f.immediate_material_business_risk, f.workaround_exists):
        return None, True
    if f.immediate_material_business_risk and not f.workaround_exists:
        return "P1", False

    if "unknown" in (f.is_major_feature_degraded, f.core_operations_possible, f.workaround_exists):
        return None, True
    if f.is_major_feature_degraded and (f.core_operations_possible or f.workaround_exists):
        return "P2", False

    return "P3", False


_PROMPT = """You are extracting structured incident facts from a support ticket for a
logistics company. Read the subject and description below and answer each question
with true, false, or "unknown" if the text genuinely does not say. Do not guess.

Subject: {subject}
Description: {description}

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
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_PROMPT.format(subject=subject, description=description),
        config={"response_mime_type": "application/json", "response_schema": IncidentFacts},
    )
    return IncidentFacts.model_validate_json(response.text)
