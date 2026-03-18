"""
Patient Intake Agent
====================
Collects patient demographics, verifies insurance eligibility, checks prior
authorization requirements, and pre-populates EHR fields to streamline check-in.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def collect_patient_demographics(patient_data: str) -> str:
    """
    Collect and validate patient demographic information for registration.

    Args:
        patient_data: JSON string with patient-provided demographic information

    Returns:
        JSON string with validated and standardized patient demographic record
    """
    try:
        raw = json.loads(patient_data)
    except Exception:
        raw = {}

    # Standardize and validate
    first_name = raw.get("first_name", "John").strip().title()
    last_name = raw.get("last_name", "Smith").strip().title()
    dob = raw.get("date_of_birth", "1985-06-15")
    phone = "".join(c for c in raw.get("phone", "555-234-5678") if c.isdigit())
    phone_formatted = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}" if len(phone) == 10 else phone
    email = raw.get("email", "").lower().strip()
    address = raw.get("address", {})

    # Calculate age
    try:
        birth_date = datetime.strptime(dob, "%Y-%m-%d")
        age = (datetime.utcnow() - birth_date).days // 365
    except Exception:
        age = None

    demographic_record = {
        "patient_id": f"PAT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "first_name": first_name,
        "last_name": last_name,
        "full_name": f"{first_name} {last_name}",
        "date_of_birth": dob,
        "age": age,
        "sex": raw.get("sex", "").upper(),
        "gender_identity": raw.get("gender_identity", ""),
        "ssn_last4": raw.get("ssn_last4", ""),
        "contact": {
            "phone_primary": phone_formatted,
            "phone_type": raw.get("phone_type", "mobile"),
            "email": email,
            "preferred_contact": raw.get("preferred_contact", "phone"),
        },
        "address": {
            "street": address.get("street", "123 Main St"),
            "city": address.get("city", "Springfield"),
            "state": address.get("state", "IL").upper(),
            "zip": address.get("zip", "62701"),
            "country": "US",
        },
        "emergency_contact": raw.get("emergency_contact", {
            "name": "Jane Smith",
            "relationship": "Spouse",
            "phone": "(555) 234-9999",
        }),
        "preferred_language": raw.get("preferred_language", "English"),
        "race_ethnicity": raw.get("race_ethnicity", ""),
        "validation": {
            "dob_valid": age is not None,
            "phone_valid": len(phone) == 10,
            "email_valid": "@" in email if email else False,
            "address_complete": bool(address.get("street") and address.get("city") and address.get("zip")),
        },
        "collected_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(demographic_record, indent=2)


@tool
def verify_insurance_eligibility(patient_id: str, insurance_member_id: str,
                                   payer_id: str, service_date: str = "") -> str:
    """
    Verify patient insurance eligibility and benefits in real-time.

    Args:
        patient_id: Patient identifier
        insurance_member_id: Insurance member/subscriber ID
        payer_id: Payer/insurance company identifier (e.g., '00001' for Aetna)
        service_date: Date of service (YYYY-MM-DD, defaults to today)

    Returns:
        JSON string with eligibility status, coverage details, copay, deductible, and network status
    """
    service_date = service_date or datetime.utcnow().strftime("%Y-%m-%d")

    # In production: calls 270/271 EDI eligibility transaction or real-time payer API
    payer_names = {
        "00001": "Aetna",
        "00002": "UnitedHealthcare",
        "00003": "Cigna",
        "00004": "Humana",
        "00005": "BCBS",
        "00006": "Medicare",
        "00007": "Medicaid",
    }

    eligibility = {
        "patient_id": patient_id,
        "insurance_member_id": insurance_member_id,
        "payer_id": payer_id,
        "payer_name": payer_names.get(payer_id, f"Payer {payer_id}"),
        "service_date": service_date,
        "eligibility_status": "active",
        "coverage": {
            "plan_name": "Gold PPO 500",
            "plan_type": "PPO",
            "effective_date": "2024-01-01",
            "termination_date": "2024-12-31",
            "group_number": "GRP-78432",
            "subscriber_name": "John Smith",
            "patient_relationship_to_subscriber": "self",
        },
        "benefits": {
            "in_network": {
                "deductible_annual": 500.00,
                "deductible_met": 225.00,
                "deductible_remaining": 275.00,
                "out_of_pocket_max": 4000.00,
                "out_of_pocket_met": 225.00,
                "copay_primary_care": 25.00,
                "copay_specialist": 50.00,
                "coinsurance_after_deductible": 0.20,
            },
            "out_of_network": {
                "deductible_annual": 2000.00,
                "covered": True,
                "coinsurance": 0.40,
            },
        },
        "provider_network_status": "in_network",
        "requires_referral": False,
        "requires_pcp": False,
        "verified_at": datetime.utcnow().isoformat(),
        "verification_transaction_id": f"EVR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
    }
    return json.dumps(eligibility, indent=2)


@tool
def check_prior_auth_requirements(cpt_codes: str, diagnosis_codes: str,
                                    payer_id: str, provider_npi: str = "") -> str:
    """
    Check whether prior authorization is required for planned services.

    Args:
        cpt_codes: JSON array string of CPT codes for planned procedures
        diagnosis_codes: JSON array string of ICD-10 diagnosis codes
        payer_id: Payer identifier
        provider_npi: Provider NPI for specialist services

    Returns:
        JSON string with prior auth requirements, status, and submission instructions
    """
    try:
        cpts = json.loads(cpt_codes) if isinstance(cpt_codes, str) else cpt_codes
        dx_codes = json.loads(diagnosis_codes) if isinstance(diagnosis_codes, str) else diagnosis_codes
    except Exception:
        cpts = []
        dx_codes = []

    # Rules-based prior auth check (in production: payer API or clearinghouse)
    requires_auth = {
        "99213": False,  # Office visit — no PA
        "99214": False,
        "99215": False,
        "71046": False,  # Chest X-ray — no PA
        "70553": True,   # MRI brain with contrast — requires PA
        "27447": True,   # Total knee arthroplasty — requires PA
        "43239": True,   # EGD with biopsy — requires PA
        "93306": True,   # Echocardiogram — may require PA
        "94010": False,  # Spirometry — no PA
    }

    auth_results = []
    for code in (cpts if isinstance(cpts, list) else []):
        code_str = code if isinstance(code, str) else code.get("code", "")
        pa_required = requires_auth.get(code_str, False)
        auth_results.append({
            "cpt_code": code_str,
            "prior_auth_required": pa_required,
            "status": "required" if pa_required else "not_required",
            "submission_method": "online_portal" if pa_required else None,
            "typical_turnaround_hours": 72 if pa_required else None,
            "criteria": f"Clinical criteria review required for {code_str}" if pa_required else None,
        })

    pa_required_codes = [r["cpt_code"] for r in auth_results if r["prior_auth_required"]]

    return json.dumps({
        "payer_id": payer_id,
        "prior_auth_summary": {
            "any_required": len(pa_required_codes) > 0,
            "codes_requiring_auth": pa_required_codes,
            "codes_not_requiring_auth": [r["cpt_code"] for r in auth_results if not r["prior_auth_required"]],
        },
        "code_details": auth_results,
        "submission_portal": f"https://payer-portal.{payer_id}.com/prior-auth" if pa_required_codes else None,
        "checked_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def pre_populate_ehr(patient_id: str, demographic_data: str, eligibility_data: str,
                      prior_auth_data: str, appointment_info: str = "") -> str:
    """
    Pre-populate EHR fields with intake information to streamline check-in and clinical workflows.

    Args:
        patient_id: Patient identifier
        demographic_data: JSON string from collect_patient_demographics
        eligibility_data: JSON string from verify_insurance_eligibility
        prior_auth_data: JSON string from check_prior_auth_requirements
        appointment_info: Optional JSON string with appointment details

    Returns:
        JSON string with EHR pre-population confirmation and field mapping
    """
    try:
        demo = json.loads(demographic_data)
        elig = json.loads(eligibility_data)
        pa = json.loads(prior_auth_data)
        appt = json.loads(appointment_info) if appointment_info else {}
    except Exception as e:
        return json.dumps({"error": str(e)})

    # Map intake data to EHR fields (Epic/Cerner/Athenahealth field schema)
    ehr_fields = {
        "demographics": {
            "legal_name": demo.get("full_name"),
            "dob": demo.get("date_of_birth"),
            "sex": demo.get("sex"),
            "gender_identity": demo.get("gender_identity"),
            "phone": demo.get("contact", {}).get("phone_primary"),
            "email": demo.get("contact", {}).get("email"),
            "address": demo.get("address"),
            "language": demo.get("preferred_language"),
            "emergency_contact": demo.get("emergency_contact"),
        },
        "insurance": {
            "primary_payer": elig.get("payer_name"),
            "member_id": elig.get("insurance_member_id"),
            "group_number": elig.get("coverage", {}).get("group_number"),
            "plan_name": elig.get("coverage", {}).get("plan_name"),
            "eligibility_verified": elig.get("eligibility_status") == "active",
            "copay_due": elig.get("benefits", {}).get("in_network", {}).get("copay_primary_care"),
            "deductible_remaining": elig.get("benefits", {}).get("in_network", {}).get("deductible_remaining"),
        },
        "prior_auth": {
            "pa_required": pa.get("prior_auth_summary", {}).get("any_required"),
            "pa_pending_codes": pa.get("prior_auth_summary", {}).get("codes_requiring_auth", []),
        },
        "appointment": {
            "scheduled": bool(appt),
            "appointment_id": appt.get("appointment_id"),
            "provider": appt.get("provider_name"),
            "time": appt.get("appointment_time"),
        },
    }

    # In production: calls EHR API to write fields
    bucket = os.environ.get("EHR_INTAKE_BUCKET", "khyzr-patient-intake")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    key = f"intake/{patient_id}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"

    try:
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(ehr_fields).encode(), ContentType="application/json")
        save_status = "saved"
    except Exception:
        save_status = "simulated"

    return json.dumps({
        "status": save_status,
        "patient_id": patient_id,
        "ehr_fields_populated": ehr_fields,
        "fields_count": sum(len(v) if isinstance(v, dict) else 1 for v in ehr_fields.values()),
        "ready_for_check_in": (
            ehr_fields["insurance"]["eligibility_verified"] and
            not ehr_fields["prior_auth"]["pa_required"]
        ),
        "check_in_alerts": [
            f"Prior auth required for: {ehr_fields['prior_auth']['pa_pending_codes']}" if ehr_fields["prior_auth"]["pa_required"] else None,
            f"Copay due at check-in: ${ehr_fields['insurance'].get('copay_due', 0):.0f}" if ehr_fields["insurance"].get("copay_due") else None,
        ],
        "populated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_intake_summary(patient_id: str, demographic_data: str,
                              eligibility_data: str, prior_auth_data: str) -> str:
    """
    Generate a concise intake summary for front desk and clinical staff.

    Args:
        patient_id: Patient identifier
        demographic_data: JSON string from collect_patient_demographics
        eligibility_data: JSON string from verify_insurance_eligibility
        prior_auth_data: JSON string from check_prior_auth_requirements

    Returns:
        JSON string with intake summary dashboard for staff review
    """
    try:
        demo = json.loads(demographic_data)
        elig = json.loads(eligibility_data)
        pa = json.loads(prior_auth_data)
    except Exception as e:
        return json.dumps({"error": str(e)})

    benefits = elig.get("benefits", {}).get("in_network", {})
    pa_summary = pa.get("prior_auth_summary", {})

    summary = {
        "intake_summary": {
            "patient_id": patient_id,
            "patient_name": demo.get("full_name"),
            "date_of_birth": demo.get("date_of_birth"),
            "age": demo.get("age"),
            "ready_for_visit": True,
            "insurance_status": {
                "payer": elig.get("payer_name"),
                "status": elig.get("eligibility_status"),
                "plan": elig.get("coverage", {}).get("plan_name"),
                "network": elig.get("provider_network_status"),
                "copay": f"${benefits.get('copay_primary_care', 0):.0f}",
                "deductible_remaining": f"${benefits.get('deductible_remaining', 0):.0f}",
            },
            "prior_auth_status": {
                "required": pa_summary.get("any_required"),
                "pending_codes": pa_summary.get("codes_requiring_auth", []),
            },
            "action_items": [
                item for item in [
                    "Collect copay at check-in" if benefits.get("copay_primary_care") else None,
                    f"Prior auth needed for: {pa_summary.get('codes_requiring_auth')}" if pa_summary.get("any_required") else None,
                    "Verify ID and insurance card" ,
                ] if item
            ],
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(summary, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Patient Intake Agent for Khyzr — an expert healthcare patient access specialist with deep knowledge of insurance verification, prior authorization workflows, and EHR patient registration.

Your mission is to create a frictionless patient intake experience: collect demographics, verify insurance eligibility in real-time, check prior auth requirements, pre-populate EHR fields, and prepare a comprehensive intake summary for front desk and clinical staff.

When processing patient intake:
1. Collect and validate complete patient demographics (name, DOB, contact, insurance info)
2. Run real-time insurance eligibility verification (270/271 EDI or payer API)
3. Check prior authorization requirements for all planned CPT codes
4. Pre-populate EHR registration fields with validated intake data
5. Generate an intake summary dashboard with action items for staff

Insurance verification priorities:
- **Active Coverage**: Confirm policy is active for the date of service
- **Network Status**: Verify the provider is in-network to avoid surprise billing
- **Benefit Details**: Copay, deductible remaining, coinsurance — communicate to patient upfront
- **Coordination of Benefits**: Identify when patient has multiple payers

Prior authorization workflow:
- Check payer-specific PA requirements for all ordered procedures
- For required PAs: initiate submission process and document tracking number
- Flag urgent services that need expedited review (same-day PA)
- Alert clinical team if PA may delay care

Patient experience standards:
- Minimize time in waiting room — digital pre-registration when possible
- Communicate financial responsibility clearly at scheduling and check-in
- Identify language barriers and arrange interpreter services proactively
- HIPAA-compliant handling of all PHI throughout the intake process

Revenue cycle impact: Complete, accurate intake directly prevents claim denials from eligibility and authorization issues — two of the top denial categories. Flag 🚨 any insurance coverage gaps, expired coverage, or required authorizations that could result in payment denial."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        collect_patient_demographics,
        verify_insurance_eligibility,
        check_prior_auth_requirements,
        pre_populate_ehr,
        generate_intake_summary,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Process intake for new patient John Smith, DOB 1985-06-15, Aetna insurance member ID AET-123456")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Complete intake for new patient: John Smith, DOB 1985-06-15, Aetna PPO (member ID AET-123456). Scheduled for office visit and spirometry (CPT 99214, 94010). Verify eligibility, check prior auth, and pre-populate EHR."
    }
    print(json.dumps(run(input_data)))
