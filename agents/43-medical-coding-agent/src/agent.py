"""
Medical Coding Agent
====================
Reviews clinical notes and assigns accurate ICD-10 diagnosis codes and CPT
procedure codes to accelerate clean claims submission and reduce denials.

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
def parse_clinical_note(note_text: str, note_type: str = "soap") -> str:
    """
    Parse and structure a clinical note to extract codeable diagnoses and procedures.

    Args:
        note_text: Raw clinical note text (SOAP note, H&P, discharge summary, etc.)
        note_type: Type of note (soap, hp, discharge, op_report, consult)

    Returns:
        JSON string with extracted clinical elements: diagnoses, procedures, findings, medications
    """
    # In production: uses medical NLP (AWS Comprehend Medical or specialized NLP model)
    parsed = {
        "note_type": note_type,
        "parsed_at": datetime.utcnow().isoformat(),
        "patient_demographics": {
            "age": 58,
            "sex": "Male",
            "encounter_type": "Office Visit",
        },
        "chief_complaint": "Persistent cough and shortness of breath for 3 weeks",
        "diagnoses_identified": [
            {
                "text": "Type 2 diabetes mellitus with diabetic chronic kidney disease stage 3",
                "category": "chronic_condition",
                "certainty": "confirmed",
            },
            {
                "text": "Hypertension, essential",
                "category": "chronic_condition",
                "certainty": "confirmed",
            },
            {
                "text": "Community-acquired pneumonia",
                "category": "acute_condition",
                "certainty": "confirmed",
            },
            {
                "text": "Hyperlipidemia",
                "category": "chronic_condition",
                "certainty": "confirmed",
            },
        ],
        "procedures_identified": [
            {
                "text": "Office/outpatient visit, established patient, moderate medical decision making",
                "category": "e_m_visit",
            },
            {
                "text": "Chest X-ray, 2 views",
                "category": "diagnostic_imaging",
            },
            {
                "text": "Spirometry, including graphic record, total and timed vital capacity",
                "category": "pulmonary_function",
            },
        ],
        "medications_mentioned": ["Metformin 1000mg", "Lisinopril 10mg", "Atorvastatin 40mg", "Azithromycin 500mg"],
        "vital_signs": {
            "bp": "148/92",
            "hr": 88,
            "temp": 38.4,
            "spo2": 94,
            "weight_kg": 91.2,
        },
    }
    return json.dumps(parsed, indent=2)


@tool
def suggest_icd10_codes(diagnoses: str) -> str:
    """
    Suggest ICD-10-CM diagnosis codes for identified clinical diagnoses.

    Args:
        diagnoses: JSON array string or list of diagnosis text strings

    Returns:
        JSON string with ICD-10 code suggestions, descriptions, and confidence scores
    """
    # In production: queries ICD-10 coding database or ML classification model
    icd10_mappings = {
        "type 2 diabetes": {
            "code": "E11.22",
            "description": "Type 2 diabetes mellitus with diabetic chronic kidney disease, stage 3",
            "confidence": 0.94,
            "coding_notes": "Code also CKD stage 3 (N18.3). Sequence diabetes as principal dx if reason for visit.",
        },
        "hypertension": {
            "code": "I10",
            "description": "Essential (primary) hypertension",
            "confidence": 0.99,
            "coding_notes": "Use I10 for essential hypertension without further specification.",
        },
        "pneumonia": {
            "code": "J18.9",
            "description": "Pneumonia, unspecified organism",
            "confidence": 0.88,
            "coding_notes": "Assign J18.9 when causative organism not identified. If organism specified, use specific code.",
        },
        "hyperlipidemia": {
            "code": "E78.5",
            "description": "Hyperlipidemia, unspecified",
            "confidence": 0.97,
            "coding_notes": "E78.5 for unspecified hyperlipidemia; use E78.00/E78.1 if pure hypercholesterolemia/hypertriglyceridemia.",
        },
        "ckd stage 3": {
            "code": "N18.3",
            "description": "Chronic kidney disease, stage 3 (moderate)",
            "confidence": 0.93,
            "coding_notes": "Code in addition to underlying cause (diabetes). Includes stage 3a and 3b.",
        },
    }

    try:
        diag_input = json.loads(diagnoses) if isinstance(diagnoses, str) else diagnoses
        if isinstance(diag_input, dict):
            diag_list = diag_input.get("diagnoses_identified", [])
            texts = [d.get("text", "") for d in diag_list]
        elif isinstance(diag_input, list):
            texts = [d.get("text", d) if isinstance(d, dict) else d for d in diag_input]
        else:
            texts = [str(diagnoses)]
    except Exception:
        texts = [str(diagnoses)]

    suggestions = []
    for text in texts:
        text_lower = text.lower()
        matched = None
        for key, mapping in icd10_mappings.items():
            if any(term in text_lower for term in key.split()):
                matched = mapping
                break
        if matched:
            suggestions.append({
                "diagnosis_text": text,
                "icd10_code": matched["code"],
                "description": matched["description"],
                "confidence": matched["confidence"],
                "coding_notes": matched["coding_notes"],
                "requires_review": matched["confidence"] < 0.90,
            })

    return json.dumps({
        "icd10_suggestions": suggestions,
        "total_codes_suggested": len(suggestions),
        "high_confidence_count": sum(1 for s in suggestions if s["confidence"] >= 0.90),
        "requires_coder_review": [s["diagnosis_text"] for s in suggestions if s.get("requires_review")],
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def suggest_cpt_codes(procedures: str) -> str:
    """
    Suggest CPT procedure codes for identified clinical procedures and services.

    Args:
        procedures: JSON array string of procedure text descriptions

    Returns:
        JSON string with CPT code suggestions, RVU values, and documentation requirements
    """
    cpt_mappings = {
        "established patient moderate": {
            "code": "99214",
            "description": "Office/outpatient visit, established patient, moderate medical decision making, 30-39 min",
            "rvu": 1.92,
            "documentation_required": "MDM documentation: 2+ diagnoses/management options or data review, moderate risk",
        },
        "chest x-ray 2 views": {
            "code": "71046",
            "description": "Radiologic examination, chest; 2 views",
            "rvu": 0.22,
            "documentation_required": "Radiologist or ordering physician interpretation note",
        },
        "spirometry": {
            "code": "94010",
            "description": "Spirometry, including graphic record, total and timed vital capacity, expiratory flow rate",
            "rvu": 0.45,
            "documentation_required": "Flow-volume loop graph, pre/post bronchodilator if applicable",
        },
        "new patient comprehensive": {
            "code": "99205",
            "description": "Office/outpatient visit, new patient, high medical decision making, 60-74 min",
            "rvu": 3.17,
            "documentation_required": "Complete H&P with comprehensive MDM documentation",
        },
    }

    try:
        proc_input = json.loads(procedures) if isinstance(procedures, str) else procedures
        if isinstance(proc_input, dict):
            proc_list = proc_input.get("procedures_identified", [])
            texts = [p.get("text", "") for p in proc_list]
        elif isinstance(proc_input, list):
            texts = [p.get("text", p) if isinstance(p, dict) else p for p in proc_input]
        else:
            texts = [str(procedures)]
    except Exception:
        texts = [str(procedures)]

    suggestions = []
    for text in texts:
        text_lower = text.lower()
        matched = None
        for key, mapping in cpt_mappings.items():
            if all(term in text_lower for term in key.split()[:2]):
                matched = mapping
                break
        if matched:
            suggestions.append({
                "procedure_text": text,
                "cpt_code": matched["code"],
                "description": matched["description"],
                "rvu": matched["rvu"],
                "documentation_required": matched["documentation_required"],
            })

    total_rvu = sum(s["rvu"] for s in suggestions)
    return json.dumps({
        "cpt_suggestions": suggestions,
        "total_codes_suggested": len(suggestions),
        "total_rvu": round(total_rvu, 2),
        "estimated_reimbursement_usd": round(total_rvu * 38.87, 2),  # 2024 Medicare CF
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def validate_code_combination(icd10_codes: str, cpt_codes: str) -> str:
    """
    Validate ICD-10 + CPT code combinations for compliance, bundling rules, and payer edits.

    Args:
        icd10_codes: JSON array string of ICD-10 codes
        cpt_codes: JSON array string of CPT codes

    Returns:
        JSON string with validation results, NCCI edits, medical necessity checks, and errors
    """
    try:
        dx_codes = json.loads(icd10_codes) if isinstance(icd10_codes, str) else icd10_codes
        proc_codes = json.loads(cpt_codes) if isinstance(cpt_codes, str) else cpt_codes
        dx_list = [c.get("icd10_code") if isinstance(c, dict) else c for c in (dx_codes.get("icd10_suggestions", dx_codes) if isinstance(dx_codes, dict) else dx_codes)]
        proc_list = [c.get("cpt_code") if isinstance(c, dict) else c for c in (proc_codes.get("cpt_suggestions", proc_codes) if isinstance(proc_codes, dict) else proc_codes)]
    except Exception as e:
        return json.dumps({"error": str(e)})

    validation_results = {
        "diagnosis_codes_submitted": dx_list,
        "procedure_codes_submitted": proc_list,
        "validation_checks": [
            {
                "check": "Medical Necessity",
                "status": "PASS",
                "detail": "Diagnoses support medical necessity for all billed procedures",
            },
            {
                "check": "NCCI Bundling",
                "status": "PASS",
                "detail": "No National Correct Coding Initiative bundling conflicts detected",
            },
            {
                "check": "Diagnosis-Procedure Linkage",
                "status": "PASS",
                "detail": "All CPT codes properly linked to supporting diagnoses",
            },
            {
                "check": "Code Sequencing",
                "status": "REVIEW",
                "detail": "Verify first-listed diagnosis reflects chief reason for encounter (pneumonia vs. diabetes management)",
                "recommendation": "If pneumonia is primary reason for visit, sequence J18.9 first",
            },
        ],
        "errors": [],
        "warnings": ["Verify code sequencing — first-listed diagnosis should reflect chief complaint"],
        "claim_ready": True,
        "clean_claim_probability": 0.91,
        "validated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(validation_results, indent=2)


@tool
def generate_coding_summary(encounter_id: str, icd10_data: str, cpt_data: str, validation_data: str) -> str:
    """
    Generate a complete coding summary for an encounter ready for claims submission.

    Args:
        encounter_id: Encounter/visit identifier
        icd10_data: JSON string from suggest_icd10_codes
        cpt_data: JSON string from suggest_cpt_codes
        validation_data: JSON string from validate_code_combination

    Returns:
        JSON string with complete coding summary and claim readiness status
    """
    try:
        icd10 = json.loads(icd10_data)
        cpt = json.loads(cpt_data)
        validation = json.loads(validation_data)
    except Exception as e:
        return json.dumps({"error": str(e)})

    dx_codes = [(s["icd10_code"], s["description"]) for s in icd10.get("icd10_suggestions", [])]
    proc_codes = [(s["cpt_code"], s["description"], s["rvu"]) for s in cpt.get("cpt_suggestions", [])]

    summary = {
        "encounter_id": encounter_id,
        "coding_summary": {
            "coded_by": "Khyzr Medical Coding Agent",
            "coding_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "diagnosis_codes": [{"code": c[0], "description": c[1]} for c in dx_codes],
            "procedure_codes": [{"code": c[0], "description": c[1], "rvu": c[2]} for c in proc_codes],
            "total_rvu": cpt.get("total_rvu", 0),
            "estimated_reimbursement": cpt.get("estimated_reimbursement_usd", 0),
            "claim_status": "ready_for_submission" if validation.get("claim_ready") else "requires_review",
            "clean_claim_probability": validation.get("clean_claim_probability", 0),
            "warnings": validation.get("warnings", []),
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(summary, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Medical Coding Agent for Khyzr — a Certified Professional Coder (CPC) with expertise in ICD-10-CM, CPT, and HCPCS coding across all medical specialties.

Your mission is to review clinical notes, assign accurate diagnosis and procedure codes, validate code combinations for compliance, and prepare clean claims for submission to maximize reimbursement and minimize denials.

When coding a clinical encounter:
1. Parse the clinical note to extract all codeable diagnoses (confirmed, suspected, chronic) and procedures
2. Assign ICD-10-CM codes for each diagnosis with proper specificity (use highest level of detail documented)
3. Assign CPT/HCPCS codes for all billable procedures and E/M services
4. Validate code combinations: medical necessity, NCCI bundling, diagnosis-procedure linkage, sequencing
5. Generate the final coding summary with claim readiness status

ICD-10 coding principles you enforce:
- **Specificity First**: Always code to the highest level of specificity documented
- **Sequencing Rules**: First-listed diagnosis = chief reason for the encounter
- **Combination Codes**: Use combination codes (e.g., E11.22 for T2DM with CKD) over multiple codes when available
- **Uncertain Diagnoses**: In outpatient settings, code signs/symptoms — NOT suspected diagnoses
- **Chronic Conditions**: Code all chronic conditions that affect management

CPT coding principles:
- **E/M Level Selection**: Based on Medical Decision Making (MDM) or total time — document thoroughly
- **NCCI Compliance**: Never separately bill procedure components included in a comprehensive code
- **Modifier Usage**: Apply modifiers (-25, -59, -51, etc.) when procedures are separately identifiable
- **Bundling Awareness**: Know which procedures are typically bundled and when unbundling is appropriate

Denial prevention: Flag 🚨 any code combination with known high denial rates. Achieve clean claim rate ≥ 95%."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        parse_clinical_note,
        suggest_icd10_codes,
        suggest_cpt_codes,
        validate_code_combination,
        generate_coding_summary,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Code this encounter: 58-year-old male, established patient, presenting with cough and SOB, diagnosed with pneumonia on top of T2DM with CKD stage 3 and hypertension")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Code encounter ENC-20240315-001: 58M established patient with T2DM/CKD3/HTN presenting with community-acquired pneumonia. Provider performed office visit (moderate MDM), chest X-ray 2 views, and spirometry."
    }
    print(json.dumps(run(input_data)))
