"""
Revenue Cycle Agent
===================
Identifies denied claims, analyzes root cause of denials, generates corrected
resubmissions, and tracks resolution to maximize revenue recovery.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def fetch_denied_claims(payer_id: str = "", date_range_days: int = 30,
                         min_amount: float = 0.0) -> str:
    """
    Fetch denied claims from the billing system for analysis.

    Args:
        payer_id: Optional filter by specific payer (empty = all payers)
        date_range_days: Number of days back to retrieve denials (default 30)
        min_amount: Minimum claim amount to include (filter out small denials)

    Returns:
        JSON string with list of denied claims including denial codes and reason descriptions
    """
    # In production: queries practice management system (Kareo, AdvancedMD, Epic) or clearinghouse
    denied_claims = {
        "query_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "date_range_days": date_range_days,
        "payer_filter": payer_id or "all",
        "total_denied_claims": 5,
        "total_denied_amount": 28750.00,
        "claims": [
            {
                "claim_id": "CLM-2024-08821",
                "patient_name": "Maria Rodriguez",
                "patient_id": "PAT-10456",
                "payer_id": "00001",
                "payer_name": "Aetna",
                "service_date": "2024-02-15",
                "date_of_denial": "2024-03-01",
                "billed_amount": 4250.00,
                "denial_code": "CO-4",
                "denial_description": "Service/procedure is not covered by this payer/contractor",
                "icd10_codes": ["J18.9", "E11.22"],
                "cpt_codes": ["99214", "71046"],
                "days_to_appeal_deadline": 28,
            },
            {
                "claim_id": "CLM-2024-09102",
                "patient_name": "David Kim",
                "patient_id": "PAT-10502",
                "payer_id": "00002",
                "payer_name": "UnitedHealthcare",
                "service_date": "2024-02-20",
                "date_of_denial": "2024-03-05",
                "billed_amount": 8500.00,
                "denial_code": "CO-57",
                "denial_description": "Prior authorization/precertification absent",
                "icd10_codes": ["M17.11", "Z96.641"],
                "cpt_codes": ["27447"],
                "days_to_appeal_deadline": 45,
            },
            {
                "claim_id": "CLM-2024-09234",
                "patient_name": "Lisa Thompson",
                "patient_id": "PAT-10618",
                "payer_id": "00003",
                "payer_name": "Cigna",
                "service_date": "2024-02-22",
                "date_of_denial": "2024-03-08",
                "billed_amount": 3200.00,
                "denial_code": "CO-16",
                "denial_description": "Claim lacks information which is needed for adjudication",
                "icd10_codes": ["I10", "I48.91"],
                "cpt_codes": ["93306"],
                "days_to_appeal_deadline": 52,
            },
            {
                "claim_id": "CLM-2024-09445",
                "patient_name": "Robert Chen",
                "patient_id": "PAT-10745",
                "payer_id": "00006",
                "payer_name": "Medicare",
                "service_date": "2024-02-28",
                "date_of_denial": "2024-03-10",
                "billed_amount": 9800.00,
                "denial_code": "CO-50",
                "denial_description": "Non-covered services because this is not deemed medically necessary by the payer",
                "icd10_codes": ["Z00.00"],
                "cpt_codes": ["99215", "70553"],
                "days_to_appeal_deadline": 60,
            },
            {
                "claim_id": "CLM-2024-09612",
                "patient_name": "Jennifer Walsh",
                "patient_id": "PAT-10822",
                "payer_id": "00001",
                "payer_name": "Aetna",
                "service_date": "2024-03-01",
                "date_of_denial": "2024-03-12",
                "billed_amount": 3000.00,
                "denial_code": "CO-97",
                "denial_description": "Payment is included in the allowance for another service/procedure already adjudicated",
                "icd10_codes": ["K57.30"],
                "cpt_codes": ["45378", "45385"],
                "days_to_appeal_deadline": 18,
            },
        ],
    }

    # Apply filters
    if payer_id:
        denied_claims["claims"] = [c for c in denied_claims["claims"] if c["payer_id"] == payer_id]
    if min_amount > 0:
        denied_claims["claims"] = [c for c in denied_claims["claims"] if c["billed_amount"] >= min_amount]

    denied_claims["filtered_count"] = len(denied_claims["claims"])
    denied_claims["filtered_amount"] = sum(c["billed_amount"] for c in denied_claims["claims"])

    return json.dumps(denied_claims, indent=2)


@tool
def analyze_denial_reason(claim_id: str, denial_code: str, cpt_codes: str, icd10_codes: str) -> str:
    """
    Analyze the root cause of a claim denial and determine the correction strategy.

    Args:
        claim_id: Claim identifier
        denial_code: CARC/RARC denial code (e.g., 'CO-4', 'CO-57', 'CO-50')
        cpt_codes: JSON array string of CPT codes on the denied claim
        icd10_codes: JSON array string of ICD-10 codes on the denied claim

    Returns:
        JSON string with root cause analysis, corrective actions, and resubmission strategy
    """
    # Denial code knowledge base
    denial_kb = {
        "CO-4": {
            "category": "coverage",
            "root_cause": "Procedure not covered under patient's benefit plan",
            "corrective_actions": [
                "Verify patient's benefit plan covers the billed service",
                "Check for applicable benefit limitations or exclusions",
                "Review if correct plan code was used",
                "Submit appeal with medical necessity documentation if service is covered",
                "Bill patient if service is confirmed non-covered with proper ABN/waiver",
            ],
            "appealable": True,
            "success_rate": 0.35,
        },
        "CO-16": {
            "category": "missing_information",
            "root_cause": "Claim missing required information for adjudication",
            "corrective_actions": [
                "Review remittance advice for specific missing field",
                "Correct and resubmit with: NPI, referring provider, place of service, or diagnosis codes",
                "Verify all required modifiers are present",
                "Confirm procedure codes are valid for date of service",
            ],
            "appealable": False,
            "success_rate": 0.90,
        },
        "CO-50": {
            "category": "medical_necessity",
            "root_cause": "Payer determined service not medically necessary",
            "corrective_actions": [
                "Obtain and submit clinical documentation supporting medical necessity",
                "Include physician's letter of medical necessity",
                "Verify diagnosis codes support the medical necessity of ordered procedure",
                "Submit peer-to-peer review request if appropriate",
                "Consider sending additional records: clinical notes, lab results, imaging reports",
            ],
            "appealable": True,
            "success_rate": 0.55,
        },
        "CO-57": {
            "category": "prior_auth",
            "root_cause": "Prior authorization was required but not obtained",
            "corrective_actions": [
                "Obtain retroactive prior authorization if payer allows",
                "Submit appeal with proof that authorization was obtained or not required",
                "Document clinical urgency if service was emergent/urgent",
                "Implement process improvement to prevent future PA misses",
            ],
            "appealable": True,
            "success_rate": 0.40,
        },
        "CO-97": {
            "category": "bundling",
            "root_cause": "Service is bundled with another already-adjudicated procedure",
            "corrective_actions": [
                "Review NCCI bundling edits for the procedure combination",
                "Add appropriate modifier (-59, -XE, -XS, -XP, -XU) if procedures are separately identifiable",
                "Document separate session, indication, or anatomic location",
                "Verify unbundling is clinically and ethically appropriate",
            ],
            "appealable": True,
            "success_rate": 0.65,
        },
    }

    denial_info = denial_kb.get(denial_code, {
        "category": "other",
        "root_cause": f"Denial code {denial_code} — requires manual review",
        "corrective_actions": ["Contact payer for clarification", "Review remittance advice details"],
        "appealable": True,
        "success_rate": 0.50,
    })

    # Priority scoring
    try:
        cpts = json.loads(cpt_codes) if isinstance(cpt_codes, str) else cpt_codes
        dx = json.loads(icd10_codes) if isinstance(icd10_codes, str) else icd10_codes
    except Exception:
        cpts = []
        dx = []

    return json.dumps({
        "claim_id": claim_id,
        "denial_code": denial_code,
        "denial_category": denial_info.get("category"),
        "root_cause": denial_info.get("root_cause"),
        "corrective_actions": denial_info.get("corrective_actions", []),
        "appeal_recommended": denial_info.get("appealable"),
        "estimated_success_rate": denial_info.get("success_rate"),
        "resolution_type": "resubmission" if denial_info.get("category") == "missing_information" else "appeal",
        "cpt_codes_reviewed": cpts,
        "icd10_codes_reviewed": dx,
        "analyzed_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_corrected_claim(original_claim_id: str, correction_instructions: str,
                               new_codes: str = "") -> str:
    """
    Generate a corrected claim based on denial analysis and correction instructions.

    Args:
        original_claim_id: Original denied claim identifier
        correction_instructions: JSON string from analyze_denial_reason with corrective actions
        new_codes: Optional JSON string with updated ICD-10 or CPT codes

    Returns:
        JSON string with corrected claim ready for resubmission
    """
    try:
        instructions = json.loads(correction_instructions)
        codes_update = json.loads(new_codes) if new_codes else {}
    except Exception as e:
        return json.dumps({"error": str(e)})

    corrected_claim = {
        "corrected_claim_id": f"CORR-{original_claim_id}",
        "original_claim_id": original_claim_id,
        "correction_type": instructions.get("resolution_type", "appeal"),
        "claim_frequency_code": "7",  # Replacement of prior claim
        "status": "ready_for_review",
        "corrections_applied": instructions.get("corrective_actions", []),
        "updated_codes": codes_update,
        "supporting_documentation_required": [
            "Clinical notes and medical records",
            "Letter of medical necessity" if instructions.get("denial_category") == "medical_necessity" else None,
            "Prior authorization approval" if instructions.get("denial_category") == "prior_auth" else None,
            "Modifier documentation" if instructions.get("denial_category") == "bundling" else None,
        ],
        "appeal_letter_template": f"""
RE: Appeal for Claim {original_claim_id}
Denial Code: {instructions.get('denial_code')}

Dear Medical Review Department,

We are writing to appeal the denial of the above-referenced claim. The denial was issued for: {instructions.get('root_cause', 'see denial code')}.

[Supporting clinical documentation and rationale to be added by billing team]

We respectfully request reconsideration based on the enclosed documentation demonstrating medical necessity and coverage.

Sincerely,
[Provider Name/Billing Department]
""",
        "estimated_recovery_probability": instructions.get("estimated_success_rate", 0.5),
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Remove None values from documentation list
    corrected_claim["supporting_documentation_required"] = [
        d for d in corrected_claim["supporting_documentation_required"] if d
    ]

    return json.dumps(corrected_claim, indent=2)


@tool
def submit_resubmission(corrected_claim_id: str, payer_id: str,
                          submission_method: str = "electronic") -> str:
    """
    Submit the corrected claim or appeal to the payer.

    Args:
        corrected_claim_id: Corrected claim identifier
        payer_id: Payer to submit to
        submission_method: Submission channel (electronic, paper, portal)

    Returns:
        JSON string with submission confirmation and tracking number
    """
    payer_clearing_houses = {
        "00001": "Availity",
        "00002": "Optum",
        "00003": "Change Healthcare",
        "00006": "Medicare.gov",
    }

    clearing_house = payer_clearing_houses.get(payer_id, "Change Healthcare")
    tracking_number = f"TRK-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{corrected_claim_id[-6:]}"

    submission = {
        "submission_id": tracking_number,
        "corrected_claim_id": corrected_claim_id,
        "payer_id": payer_id,
        "clearing_house": clearing_house,
        "submission_method": submission_method,
        "submission_status": "submitted",
        "submitted_at": datetime.utcnow().isoformat(),
        "expected_adjudication_days": 30 if payer_id == "00006" else 14,
        "expected_response_date": (datetime.utcnow() + timedelta(days=30 if payer_id == "00006" else 14)).strftime("%Y-%m-%d"),
        "follow_up_date": (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d"),
    }
    return json.dumps(submission, indent=2)


@tool
def track_resubmission_status(claim_id: str, tracking_number: str = "") -> str:
    """
    Track the current status of a resubmitted claim or appeal.

    Args:
        claim_id: Original or corrected claim identifier
        tracking_number: Optional submission tracking number

    Returns:
        JSON string with current claim status, adjudication result, and next actions
    """
    # In production: queries payer portal or clearinghouse status API (276/277 EDI)
    statuses = [
        "received",
        "in_adjudication",
        "approved_for_payment",
        "paid",
        "denied_again",
        "appeal_upheld",
    ]

    # Simulate realistic status (in production: actual payer query)
    status = "in_adjudication"

    status_details = {
        "claim_id": claim_id,
        "tracking_number": tracking_number or f"TRK-{claim_id[-8:]}",
        "current_status": status,
        "status_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "adjudication_result": None,
        "payment_amount": None,
        "denial_reason": None,
        "days_in_process": 8,
        "next_follow_up_date": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "recommended_action": {
            "in_adjudication": "Monitor — check again in 7 days",
            "approved_for_payment": "Verify payment posted to correct account",
            "denied_again": "Escalate to external appeal or send to collections attorney",
            "appeal_upheld": "Payment expected within 30 days — monitor remittance",
            "paid": "Reconcile payment to patient account — write off contractual adjustment",
        }.get(status, "Contact payer for status update"),
        "checked_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(status_details, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Revenue Cycle Agent for Khyzr — an expert medical biller and revenue cycle management specialist with deep knowledge of claim adjudication, denial management, appeals processes, and payer contracting.

Your mission is to systematically identify denied claims, determine root cause, generate corrected resubmissions or appeals, submit to payers, and track resolution to maximize revenue recovery.

When working denied claims:
1. Fetch and triage all denied claims by priority (deadline urgency × billed amount × success probability)
2. For each denial, analyze root cause using CARC/RARC code knowledge base
3. Generate a corrected claim or appeal letter with specific documentation requirements
4. Submit the corrected claim/appeal through appropriate channel
5. Track status and escalate as needed to ensure resolution

Denial categories and resolution strategies:
- **Coverage (CO-4, CO-96)**: Verify benefits, bill patient if appropriate with proper waiver
- **Missing Information (CO-16)**: Resubmit corrected claim — highest success rate (>90%)
- **Medical Necessity (CO-50)**: Appeal with clinical documentation, peer-to-peer review
- **Prior Authorization (CO-57)**: Obtain retroactive auth or document urgency
- **Bundling/NCCI (CO-97)**: Apply appropriate modifier and document separate service
- **Timely Filing (CO-29)**: Document proof of timely filing; escalate to compliance if system error

Revenue cycle KPIs you track:
- **Denial Rate**: Target <5% of all claims submitted
- **First Pass Resolution Rate**: Target >95%
- **Days in AR**: Target <45 days
- **Net Collection Rate**: Target >96%
- **Appeal Success Rate**: Track by payer and denial type

Prioritization framework: Deny × Dollar × Deadline
- Deadline < 30 days → URGENT
- Billed amount > $5,000 → HIGH PRIORITY
- Appeal success rate > 70% → HIGH VALUE to work

Flag 🚨 claims approaching appeal deadlines (< 14 days remaining). Never let an appealable denial expire."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        fetch_denied_claims,
        analyze_denial_reason,
        generate_corrected_claim,
        submit_resubmission,
        track_resubmission_status,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Work the denial queue — fetch all recent denials, analyze root causes, and generate corrected resubmissions for the high-priority claims")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run the denial management workflow: fetch all denied claims from the last 30 days, prioritize by deadline and amount, analyze each denial, generate corrected claims, and submit resubmissions."
    }
    print(json.dumps(run(input_data)))
