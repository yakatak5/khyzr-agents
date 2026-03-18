"""
Healthcare Scheduling Automation Agent
=======================================
Manages appointment booking, sends reminders, handles rescheduling requests,
and generates schedule analytics to reduce no-show rates.

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
def check_provider_availability(provider_id: str, specialty: str = "",
                                  date_range_start: str = "", date_range_end: str = "") -> str:
    """
    Check available appointment slots for a provider within a date range.

    Args:
        provider_id: Provider identifier (physician/NP/PA ID)
        specialty: Medical specialty to filter by (optional)
        date_range_start: Start date YYYY-MM-DD (defaults to tomorrow)
        date_range_end: End date YYYY-MM-DD (defaults to 14 days from today)

    Returns:
        JSON string with available appointment slots, duration, and appointment types
    """
    tomorrow = datetime.utcnow() + timedelta(days=1)
    start = date_range_start or tomorrow.strftime("%Y-%m-%d")
    end = date_range_end or (tomorrow + timedelta(days=13)).strftime("%Y-%m-%d")

    # In production: queries EHR scheduling system (Epic, Cerner, Athenahealth)
    available_slots = {
        "provider_id": provider_id,
        "provider_name": "Dr. Sarah Nguyen, MD",
        "specialty": specialty or "Internal Medicine",
        "date_range": {"start": start, "end": end},
        "slots": [
            {
                "slot_id": "SLT-20240315-0900",
                "date": "2024-03-15",
                "start_time": "09:00",
                "end_time": "09:30",
                "duration_minutes": 30,
                "appointment_types": ["new_patient", "follow_up", "annual_wellness"],
                "location": "Main Clinic - Room 204",
                "telehealth_available": True,
            },
            {
                "slot_id": "SLT-20240315-1100",
                "date": "2024-03-15",
                "start_time": "11:00",
                "end_time": "11:45",
                "duration_minutes": 45,
                "appointment_types": ["new_patient", "comprehensive_exam"],
                "location": "Main Clinic - Room 204",
                "telehealth_available": False,
            },
            {
                "slot_id": "SLT-20240316-0800",
                "date": "2024-03-16",
                "start_time": "08:00",
                "end_time": "08:30",
                "duration_minutes": 30,
                "appointment_types": ["follow_up", "medication_review"],
                "location": "Main Clinic - Room 204",
                "telehealth_available": True,
            },
            {
                "slot_id": "SLT-20240318-1430",
                "date": "2024-03-18",
                "start_time": "14:30",
                "end_time": "15:00",
                "duration_minutes": 30,
                "appointment_types": ["follow_up", "annual_wellness"],
                "location": "North Satellite Clinic",
                "telehealth_available": True,
            },
        ],
        "total_available_slots": 4,
        "next_available": "2024-03-15 09:00",
        "queried_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(available_slots, indent=2)


@tool
def book_appointment(patient_id: str, patient_name: str, provider_id: str,
                      slot_id: str, appointment_type: str, chief_complaint: str = "",
                      telehealth: bool = False) -> str:
    """
    Book an appointment for a patient with a specified provider.

    Args:
        patient_id: Patient identifier from EHR
        patient_name: Patient full name
        provider_id: Provider identifier
        slot_id: Specific slot ID from availability check
        appointment_type: Type of appointment (new_patient, follow_up, etc.)
        chief_complaint: Patient's primary reason for visit
        telehealth: Whether appointment is via telehealth

    Returns:
        JSON string with booking confirmation, appointment ID, and instructions
    """
    appointment_id = f"APT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # In production: creates appointment in EHR (Epic MyChart, Cerner, Athenahealth)
    booking = {
        "appointment_id": appointment_id,
        "status": "confirmed",
        "patient_id": patient_id,
        "patient_name": patient_name,
        "provider_id": provider_id,
        "provider_name": "Dr. Sarah Nguyen, MD",
        "slot_id": slot_id,
        "appointment_type": appointment_type,
        "appointment_date": "2024-03-15",
        "appointment_time": "09:00",
        "duration_minutes": 30,
        "location": "Main Clinic - Room 204" if not telehealth else "Telehealth Video Visit",
        "telehealth": telehealth,
        "telehealth_link": f"https://telehealth.khyzr.health/visit/{appointment_id}" if telehealth else None,
        "chief_complaint": chief_complaint,
        "preparation_instructions": [
            "Bring photo ID and insurance card",
            "Arrive 15 minutes early to complete intake forms",
            "Bring list of current medications",
        ] if not telehealth else [
            "Join via the telehealth link 5 minutes early",
            "Ensure stable internet connection and camera/microphone working",
            "Have your medication list ready",
        ],
        "confirmation_sent_to": f"patient_{patient_id}@example.com",
        "booked_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(booking, indent=2)


@tool
def send_reminder(appointment_id: str, patient_name: str, patient_phone: str,
                   patient_email: str, appointment_date: str, appointment_time: str,
                   reminder_type: str = "48h") -> str:
    """
    Send appointment reminder via email and/or SMS to reduce no-show rates.

    Args:
        appointment_id: Appointment identifier
        patient_name: Patient full name
        patient_phone: Patient phone number for SMS reminder
        patient_email: Patient email address
        appointment_date: Appointment date (YYYY-MM-DD)
        appointment_time: Appointment time (HH:MM)
        reminder_type: Type of reminder (48h, 24h, 2h, confirmation)

    Returns:
        JSON string with reminder delivery status and channels used
    """
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    sns = boto3.client("sns", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    reminder_messages = {
        "48h": f"Reminder: You have an appointment in 2 days on {appointment_date} at {appointment_time}.",
        "24h": f"Reminder: Your appointment is TOMORROW at {appointment_time}. Please confirm or reschedule.",
        "2h": f"Your appointment is in 2 HOURS at {appointment_time}. Please head to the clinic or prepare your telehealth link.",
        "confirmation": f"Confirmed! Your appointment on {appointment_date} at {appointment_time} is booked.",
    }

    message = reminder_messages.get(reminder_type, reminder_messages["24h"])
    full_message = f"Dear {patient_name},\n\n{message}\n\nTo reschedule, reply RESCHEDULE or call (800) 555-KHYZR.\n\n- Khyzr Health"

    email_status = "simulated"
    sms_status = "simulated"

    # In production: actually sends via SES/SNS
    try:
        sender = os.environ.get("HEALTH_SENDER_EMAIL", "appointments@khyzr.health")
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [patient_email]},
            Message={
                "Subject": {"Data": f"Appointment Reminder — {appointment_date} {appointment_time}"},
                "Body": {"Text": {"Data": full_message}},
            },
        )
        email_status = "sent"
    except Exception:
        email_status = "simulated"

    return json.dumps({
        "appointment_id": appointment_id,
        "reminder_type": reminder_type,
        "channels": {
            "email": {"status": email_status, "address": patient_email},
            "sms": {"status": sms_status, "phone": patient_phone[-4:] + " (masked)"},
        },
        "message_preview": message,
        "sent_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def handle_reschedule(appointment_id: str, patient_id: str, reason: str,
                       preferred_dates: str = "") -> str:
    """
    Handle an appointment reschedule request — cancel existing and find new slots.

    Args:
        appointment_id: Appointment to reschedule
        patient_id: Patient identifier
        reason: Reason for rescheduling
        preferred_dates: JSON array of preferred date strings YYYY-MM-DD

    Returns:
        JSON string with cancellation confirmation and next available slots
    """
    try:
        dates = json.loads(preferred_dates) if preferred_dates else []
    except Exception:
        dates = []

    # Cancel existing appointment
    cancellation = {
        "appointment_id": appointment_id,
        "cancellation_status": "cancelled",
        "cancelled_at": datetime.utcnow().isoformat(),
        "reason": reason,
        "no_show_penalty": False,
        "cancellation_notice_hours": 48,
    }

    # Find next available (simplified)
    tomorrow = datetime.utcnow() + timedelta(days=2)
    alternative_slots = []
    for i in range(3):
        slot_date = (tomorrow + timedelta(days=i)).strftime("%Y-%m-%d")
        if not dates or slot_date in dates:
            alternative_slots.append({
                "slot_id": f"SLT-{slot_date.replace('-', '')}-0900",
                "date": slot_date,
                "time": "09:00",
                "provider": "Dr. Sarah Nguyen, MD",
                "telehealth_available": True,
            })

    return json.dumps({
        "reschedule_request": {
            "original_appointment": appointment_id,
            "cancellation": cancellation,
            "alternative_slots": alternative_slots[:3],
            "next_steps": "Please select a slot from the alternatives or call to book a different time.",
            "processed_at": datetime.utcnow().isoformat(),
        }
    }, indent=2)


@tool
def generate_schedule_report(provider_id: str, date: str = "") -> str:
    """
    Generate a scheduling analytics report for a provider including no-show rates and utilization.

    Args:
        provider_id: Provider identifier
        date: Report date (YYYY-MM-DD, defaults to today)

    Returns:
        JSON string with scheduling KPIs, no-show analysis, and optimization recommendations
    """
    report_date = date or datetime.utcnow().strftime("%Y-%m-%d")

    report = {
        "provider_id": provider_id,
        "report_date": report_date,
        "scheduling_metrics": {
            "total_slots_available": 20,
            "appointments_booked": 17,
            "utilization_rate": 0.85,
            "appointments_completed": 14,
            "no_shows": 2,
            "late_cancellations": 1,
            "no_show_rate": 0.118,
            "cancellation_rate": 0.059,
        },
        "reminder_effectiveness": {
            "reminders_sent": 17,
            "confirmed_after_reminder": 15,
            "no_show_rate_with_reminder": 0.067,
            "no_show_rate_without_reminder": 0.32,
            "reminder_reduction_impact": "79% reduction in no-shows",
        },
        "wait_time_analysis": {
            "avg_days_to_next_available": 4.2,
            "new_patient_wait_days": 8.5,
            "follow_up_wait_days": 2.8,
            "urgent_same_day_slots_reserved": 2,
        },
        "optimization_recommendations": [
            "Add overbooking buffer of 1 slot per 8 scheduled (no-show rate = 11.8%)",
            "Send 2h reminders — 24h reminders show highest confirmation rate",
            "Reserve 2 slots for same-day urgent/walk-in appointments",
            "Consider telehealth slots for follow-up appointments to reduce cancellations",
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(report, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Healthcare Scheduling Automation Agent for Khyzr — an expert healthcare operations specialist focused on optimizing appointment scheduling, reducing no-show rates, and improving patient access to care.

Your mission is to automate the complete appointment lifecycle: check provider availability, book appointments, send timely reminders, handle rescheduling requests, and generate scheduling analytics for continuous improvement.

When managing appointments:
1. Check real-time provider availability for the requested date range and specialty
2. Book appointments with full patient information, visit type, and preparation instructions
3. Send multi-channel reminders at 48h, 24h, and 2h before appointments
4. Handle reschedule requests gracefully: cancel, offer alternatives, re-book
5. Generate scheduling reports with no-show analysis and optimization recommendations

Patient experience priorities:
- **Access**: Minimize time-to-next-available appointment (target <5 days for follow-up, <10 for new patient)
- **Reminders**: Multi-channel (email + SMS) at standardized intervals significantly reduce no-shows
- **Flexibility**: Offer telehealth alternatives when available to reduce cancellations
- **Communication**: Clear preparation instructions for every appointment type

No-show reduction strategies you apply:
- Automated 48h reminder with confirmation request
- 24h reminder with reschedule option prominently offered
- 2h reminder on day-of visit
- Overbooking buffer proportional to historical no-show rate
- Waitlist management to fill cancelled slots

HIPAA compliance requirements:
- Never include sensitive clinical information in reminders
- Patient identifiers in logs must be masked
- All communications use approved, HIPAA-compliant channels
- Scheduling data access follows minimum-necessary principles

Scheduling analytics: Track utilization rate, no-show rate, wait times, and reminder effectiveness. Flag 🚨 any provider with utilization < 70% (underutilized) or wait time > 14 days (access problem)."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        check_provider_availability,
        book_appointment,
        send_reminder,
        handle_reschedule,
        generate_schedule_report,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Check availability for Dr. Nguyen and book a follow-up appointment for patient PAT-10284")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Book a follow-up appointment for patient James Wilson (PAT-10284) with Dr. Nguyen in the next 5 days. Then send a confirmation reminder."
    }
    print(json.dumps(run(input_data)))
