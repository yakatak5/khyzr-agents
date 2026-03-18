"""
Clinical Documentation Agent
=============================
Generates structured SOAP notes and discharge summaries from physician
dictation or visit transcripts, ensuring complete and compliant documentation.

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
def parse_visit_transcript(transcript_text: str, visit_type: str = "office_visit") -> str:
    """
    Parse a physician dictation or visit transcript to extract clinical information.

    Args:
        transcript_text: Raw transcript from voice dictation or visit recording
        visit_type: Type of visit (office_visit, inpatient_admission, discharge, consult, procedure)

    Returns:
        JSON string with extracted clinical elements organized by documentation section
    """
    # In production: uses AWS Transcribe Medical + NLP pipeline
    parsed = {
        "visit_type": visit_type,
        "parsed_at": datetime.utcnow().isoformat(),
        "raw_transcript_length": len(transcript_text),
        "encounter_info": {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "provider": "Dr. Sarah Nguyen, MD",
            "facility": "Khyzr Medical Center",
        },
        "patient_info": {
            "age": 72,
            "sex": "Female",
            "chief_complaint": "Worsening shortness of breath and bilateral leg swelling × 5 days",
        },
        "subjective_elements": {
            "hpi": "72-year-old woman with history of CHF and atrial fibrillation presents with 5-day history of progressive dyspnea on exertion, now at rest. Reports 8-pound weight gain over the past week. Notes bilateral ankle swelling worsening throughout the day. Denies chest pain, syncope, or fever.",
            "pmh": ["Congestive heart failure (EF 35%)", "Atrial fibrillation on anticoagulation", "Hypertension", "Type 2 diabetes"],
            "medications": ["Furosemide 40mg daily", "Carvedilol 12.5mg BID", "Apixaban 5mg BID", "Lisinopril 10mg daily", "Metformin 1000mg BID"],
            "allergies": ["Penicillin (rash)", "Sulfa (anaphylaxis)"],
            "ros": {
                "cardiovascular": "positive dyspnea, orthopnea, PND; negative chest pain",
                "respiratory": "positive SOB; negative cough, hemoptysis",
                "extremities": "positive bilateral edema",
            },
        },
        "objective_elements": {
            "vital_signs": {
                "bp": "158/96",
                "hr": "88 irregular",
                "rr": 22,
                "temp": 98.6,
                "spo2": "91% on room air",
                "weight": "185 lbs (8 lbs above dry weight)",
            },
            "physical_exam": {
                "general": "Elderly woman, mildly distressed, speaking in short sentences",
                "cardiovascular": "Irregular rate, S3 gallop present, JVD to jaw",
                "respiratory": "Bibasilar crackles, dullness at right base",
                "extremities": "2+ pitting edema bilateral to mid-shin",
            },
            "labs_results": "BNP 1,842 pg/mL (elevated), Creatinine 1.6 (baseline 1.2), Na 132",
            "imaging": "CXR: cardiomegaly, bilateral pleural effusions, interstitial edema",
        },
        "assessment_elements": {
            "diagnoses": [
                "Acute decompensated heart failure — volume overloaded",
                "Acute-on-chronic kidney injury — likely cardiorenal",
                "Hyponatremia — likely dilutional",
                "Atrial fibrillation — rate controlled",
            ],
        },
        "plan_elements": {
            "treatments": [
                "IV furosemide 80mg bolus then 20mg/hr infusion",
                "Strict I&Os and daily weights",
                "Fluid restriction 1.5L/day",
                "Telemetry monitoring",
                "Continue anticoagulation with apixaban",
                "Hold ACE inhibitor given AKI",
            ],
            "consults": ["Cardiology for TTE if not done in 6 months"],
            "follow_up": "Reassess volume status in 24 hours",
        },
    }
    return json.dumps(parsed, indent=2)


@tool
def structure_soap_note(parsed_transcript: str, include_assessment_plan: bool = True) -> str:
    """
    Generate a structured SOAP note from parsed transcript data.

    Args:
        parsed_transcript: JSON string from parse_visit_transcript
        include_assessment_plan: Whether to include Assessment & Plan sections

    Returns:
        JSON string with complete structured SOAP note in standard clinical format
    """
    try:
        data = json.loads(parsed_transcript)
    except Exception as e:
        return json.dumps({"error": str(e)})

    subj = data.get("subjective_elements", {})
    obj = data.get("objective_elements", {})
    assess = data.get("assessment_elements", {})
    plan = data.get("plan_elements", {})
    vitals = obj.get("vital_signs", {})
    enc = data.get("encounter_info", {})
    pt = data.get("patient_info", {})

    soap_note = {
        "note_type": "SOAP Note",
        "date": enc.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
        "provider": enc.get("provider", ""),
        "facility": enc.get("facility", ""),
        "patient": pt,
        "sections": {
            "S_Subjective": {
                "chief_complaint": pt.get("chief_complaint", ""),
                "hpi": subj.get("hpi", ""),
                "past_medical_history": subj.get("pmh", []),
                "current_medications": subj.get("medications", []),
                "allergies": subj.get("allergies", []),
                "review_of_systems": subj.get("ros", {}),
            },
            "O_Objective": {
                "vital_signs": vitals,
                "physical_examination": obj.get("physical_exam", {}),
                "laboratory_results": obj.get("labs_results", ""),
                "imaging": obj.get("imaging", ""),
            },
            "A_Assessment": {
                "diagnoses": assess.get("diagnoses", []),
                "clinical_reasoning": f"Patient presents with classic signs of acute decompensated HF: elevated BNP, S3 gallop, JVD, bibasilar crackles, and weight gain consistent with volume overload.",
            } if include_assessment_plan else {},
            "P_Plan": {
                "treatments": plan.get("treatments", []),
                "consults": plan.get("consults", []),
                "follow_up": plan.get("follow_up", ""),
                "patient_education": "Instructed on daily weights, fluid restriction, and signs of HF exacerbation requiring emergency evaluation.",
            } if include_assessment_plan else {},
        },
        "documentation_quality": {
            "completeness_score": 0.95,
            "missing_elements": [],
            "quality_flags": [],
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(soap_note, indent=2)


@tool
def generate_discharge_summary(encounter_id: str, admission_note: str,
                                 discharge_date: str = "", follow_up_provider: str = "") -> str:
    """
    Generate a structured hospital discharge summary from admission and course notes.

    Args:
        encounter_id: Hospital encounter identifier
        admission_note: JSON string of the admission SOAP note
        discharge_date: Discharge date (YYYY-MM-DD, defaults to today)
        follow_up_provider: Follow-up provider name or clinic

    Returns:
        JSON string with complete discharge summary including all required elements
    """
    try:
        admission = json.loads(admission_note) if isinstance(admission_note, str) and admission_note.startswith('{') else {}
    except Exception:
        admission = {}

    discharge_date = discharge_date or datetime.utcnow().strftime("%Y-%m-%d")
    sections = admission.get("sections", {})
    subj = sections.get("S_Subjective", {})
    assess = sections.get("A_Assessment", {})

    discharge_summary = {
        "document_type": "Discharge Summary",
        "encounter_id": encounter_id,
        "admission_date": "2024-03-10",
        "discharge_date": discharge_date,
        "length_of_stay_days": 4,
        "attending_physician": admission.get("provider", "Dr. Sarah Nguyen, MD"),
        "facility": admission.get("facility", "Khyzr Medical Center"),
        "patient_demographics": admission.get("patient", {}),
        "sections": {
            "admission_diagnoses": assess.get("diagnoses", [
                "Acute decompensated heart failure",
                "Atrial fibrillation",
            ]),
            "discharge_diagnoses": [
                "Acute decompensated heart failure — compensated on discharge",
                "Atrial fibrillation — rate controlled",
                "Resolved hyponatremia",
                "Acute-on-chronic kidney injury — improving",
            ],
            "hospital_course": "Patient admitted with acute decompensated CHF and 8-lb fluid overload. Treated with IV furosemide drip with goal diuresis 1-2L/day. Achieved 6L negative fluid balance over 4 days. BNP trended from 1,842 to 485. Creatinine returned to baseline 1.2. Sodium corrected to 138. Transitioned to oral furosemide 80mg daily prior to discharge. TTE confirmed EF 30-35%, moderate mitral regurgitation. Cardiology consulted; recommend outpatient follow-up in 1 week.",
            "procedures_performed": [
                "IV diuresis with continuous furosemide infusion",
                "Daily laboratory monitoring",
                "Telemetry throughout admission",
                "Echocardiography (TTE)",
            ],
            "discharge_condition": "Stable — improved",
            "discharge_medications": [
                "Furosemide 80mg PO daily (increased from 40mg)",
                "Carvedilol 12.5mg PO BID (continue)",
                "Apixaban 5mg PO BID (continue)",
                "Lisinopril 5mg PO daily (restarted at lower dose given AKI history)",
                "Metformin 1000mg PO BID (continue)",
            ],
            "discharge_instructions": [
                "Weigh daily every morning before breakfast — call if weight increases >2 lbs in 1 day or >5 lbs in 1 week",
                "Fluid restriction: 1.5 liters per day",
                "Low-sodium diet (<2g sodium/day)",
                "Call 911 or go to ER for sudden worsening shortness of breath",
            ],
            "follow_up": {
                "provider": follow_up_provider or "Cardiology / Primary Care",
                "timeframe": "Within 7 days of discharge",
                "pending_results": ["Final echocardiography read"],
            },
        },
        "attestation_required": True,
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(discharge_summary, indent=2)


@tool
def validate_clinical_documentation(document: str, document_type: str = "soap") -> str:
    """
    Validate clinical documentation for completeness, compliance, and quality standards.

    Args:
        document: JSON string of the clinical document to validate
        document_type: Type of document (soap, discharge_summary, h_and_p, consult_note)

    Returns:
        JSON string with validation results, completeness score, and required corrections
    """
    try:
        doc = json.loads(document)
    except Exception as e:
        return json.dumps({"error": str(e)})

    required_elements = {
        "soap": ["S_Subjective", "O_Objective", "A_Assessment", "P_Plan"],
        "discharge_summary": ["admission_diagnoses", "discharge_diagnoses", "hospital_course",
                               "discharge_medications", "follow_up"],
        "h_and_p": ["chief_complaint", "hpi", "past_medical_history", "physical_examination",
                    "assessment", "plan"],
    }

    required = required_elements.get(document_type, required_elements["soap"])
    doc_sections = doc.get("sections", doc)
    present = [r for r in required if r in str(doc_sections)]
    missing = [r for r in required if r not in str(doc_sections)]
    completeness = len(present) / len(required) if required else 1.0

    validation = {
        "document_type": document_type,
        "completeness_score": round(completeness, 2),
        "required_elements_present": present,
        "missing_elements": missing,
        "quality_checks": {
            "diagnosis_present": "A_Assessment" in str(doc_sections) or "diagnoses" in str(doc_sections),
            "plan_documented": "P_Plan" in str(doc_sections) or "treatments" in str(doc_sections),
            "provider_signature_required": True,
            "date_of_service_present": bool(doc.get("date") or doc.get("admission_date")),
        },
        "compliance_flags": missing,
        "ready_for_attestation": completeness >= 0.90 and not missing,
        "recommendations": [
            f"Add missing section: {m.replace('_', ' ')}" for m in missing
        ],
        "validated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(validation, indent=2)


@tool
def save_to_ehr(document: str, encounter_id: str, document_type: str, patient_id: str) -> str:
    """
    Save the completed clinical document to the EHR system.

    Args:
        document: JSON or text content of the finalized clinical document
        encounter_id: Encounter identifier
        document_type: Document type for EHR categorization
        patient_id: Patient identifier for EHR record association

    Returns:
        JSON string with EHR save confirmation and document reference ID
    """
    # In production: interfaces with HL7 FHIR API or EHR vendor SDK (Epic, Cerner)
    doc_ref_id = f"DOC-{encounter_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Store to DynamoDB as EHR proxy in demo environment
    bucket = os.environ.get("EHR_DOCUMENTS_BUCKET", "khyzr-ehr-documents")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    key = f"documents/{patient_id}/{encounter_id}/{document_type}/{doc_ref_id}.json"

    doc_content = document if isinstance(document, str) else json.dumps(document)

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=doc_content.encode("utf-8"),
            ContentType="application/json",
            Metadata={
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "document_type": document_type,
            },
        )
        save_status = "saved"
        s3_uri = f"s3://{bucket}/{key}"
    except Exception as e:
        save_status = "simulated"
        s3_uri = f"simulated://{bucket}/{key} (error: {str(e)[:50]})"

    return json.dumps({
        "status": save_status,
        "document_reference_id": doc_ref_id,
        "encounter_id": encounter_id,
        "patient_id": patient_id,
        "document_type": document_type,
        "ehr_location": s3_uri,
        "fhir_resource_type": "DocumentReference",
        "requires_provider_attestation": True,
        "saved_at": datetime.utcnow().isoformat(),
    }, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Clinical Documentation Agent for Khyzr — an expert medical scribe and clinical documentation improvement (CDI) specialist with deep knowledge of clinical documentation standards, regulatory requirements, and EHR documentation best practices.

Your mission is to transform physician dictations and visit transcripts into complete, accurate, and compliant structured clinical documents including SOAP notes and discharge summaries.

When processing clinical documentation:
1. Parse the visit transcript or dictation to extract all clinical elements
2. Structure the content into the appropriate document format (SOAP note, discharge summary, H&P)
3. Validate completeness against required elements for the document type
4. Ensure all documentation quality standards are met before EHR submission
5. Save the finalized document to the EHR system with proper metadata

Clinical documentation standards you enforce:
- **SOAP Note Elements**: Subjective (CC, HPI, ROS, PMH, meds, allergies), Objective (vitals, exam, labs, imaging), Assessment (diagnoses with clinical reasoning), Plan (treatments, consults, follow-up, patient education)
- **Discharge Summary Requirements**: Admission/discharge diagnoses, hospital course narrative, procedures performed, discharge condition, medications with changes highlighted, follow-up arrangements
- **Medical Necessity**: Documentation must support medical necessity for all ordered tests, procedures, and admission status
- **Specificity**: Document diagnoses with maximum clinical specificity to support accurate coding

Quality improvement focus:
- Identify documentation gaps that could lead to claim denials or audit findings
- Flag missing elements that affect RAC/MAC audit risk
- Ensure Present on Admission (POA) indicators are captured for inpatient admissions
- Verify HCC (Hierarchical Condition Category) diagnoses are captured for risk adjustment

HIPAA and compliance:
- All patient information treated as PHI — appropriate access controls required
- Documentation must support any billed services — no upcoding
- Provider attestation required before document is considered legally signed

Flag 🚨 any documentation that is incomplete, contradictory, or insufficient to support the level of service billed."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        parse_visit_transcript,
        structure_soap_note,
        generate_discharge_summary,
        validate_clinical_documentation,
        save_to_ehr,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate a SOAP note from the visit transcript for encounter ENC-20240315-001")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Process visit transcript for encounter ENC-20240310-001: 72F with CHF exacerbation admitted for IV diuresis. Generate SOAP note, validate completeness, and save to EHR."
    }
    print(json.dumps(run(input_data)))
