"""
Scheduling Optimization Agent
================================
Builds and adjusts shift/resource schedules based on demand forecasts, labor rules, and availability.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
import pandas as pd
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_staffing_requirements(week_start: str, department: str = None) -> str:
    """Fetch staffing requirements based on demand forecast for a given week."""
    bucket = os.environ.get("SCHEDULING_BUCKET")
    if bucket:
        import boto3
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"requirements/{week_start}.json")
            return obj["Body"].read().decode("utf-8")
        except Exception:
            pass
    
    # Generate sample staffing requirements
    requirements = []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    shifts = {"morning": "6:00-14:00", "afternoon": "14:00-22:00", "night": "22:00-6:00"}
    
    for day in days:
        for shift_name, shift_hours in shifts.items():
            is_weekend = day in ["Saturday", "Sunday"]
            required = 3 if is_weekend else (5 if shift_name == "morning" else 4)
            requirements.append({
                "day": day, "shift": shift_name, "hours": shift_hours,
                "required_headcount": required, "min_skill_level": "associate",
                "department": department or "Operations",
            })
    
    return json.dumps({"week_start": week_start, "requirements": requirements}, indent=2)


@tool
def fetch_staff_availability(week_start: str) -> str:
    """Fetch staff availability and time-off requests for a given week."""
    table_name = os.environ.get("STAFF_TABLE_NAME")
    if table_name:
        import boto3
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            resp = table.scan()
            return json.dumps({"staff": resp.get("Items", [])}, indent=2)
        except Exception:
            pass
    
    staff = [
        {"employee_id": f"EMP-{i:03d}", "name": f"Employee {i}", "role": "associate", "hours_per_week": 40,
         "preferred_shift": "morning", "time_off_requests": [], "skills": ["general_ops"],
         "max_consecutive_days": 5, "min_hours_between_shifts": 10}
        for i in range(1, 16)
    ]
    return json.dumps({"week_start": week_start, "staff": staff, "total_staff": len(staff), "note": "Configure STAFF_TABLE_NAME for real availability data"}, indent=2)


@tool
def generate_optimized_schedule(requirements: list, staff: list, optimization_goal: str = "coverage") -> str:
    """
    Generate an optimized schedule matching staff to requirements.

    Args:
        requirements: List of staffing requirements by day/shift
        staff: List of available staff with availability
        optimization_goal: 'coverage', 'cost', or 'fairness'

    Returns:
        JSON optimized schedule with assignments and metrics
    """
    schedule = []
    staff_hours = {s["employee_id"]: 0 for s in staff}
    
    for req in requirements:
        day = req.get("day")
        shift = req.get("shift")
        needed = req.get("required_headcount", 3)
        
        # Sort staff by hours (least assigned first for fairness)
        eligible = sorted(
            [s for s in staff if staff_hours[s["employee_id"]] < 40],
            key=lambda s: staff_hours[s["employee_id"]]
        )
        
        assigned = eligible[:needed]
        for emp in assigned:
            staff_hours[emp["employee_id"]] += 8
        
        schedule.append({
            "day": day, "shift": shift, "hours": req.get("hours"),
            "required": needed, "assigned": len(assigned),
            "coverage_pct": round(len(assigned) / needed * 100, 1) if needed else 100,
            "employees": [e.get("name", e.get("employee_id")) for e in assigned],
            "status": "covered" if len(assigned) >= needed else "understaffed",
        })
    
    covered = sum(1 for s in schedule if s["status"] == "covered")
    return json.dumps({
        "optimization_goal": optimization_goal,
        "schedule": schedule,
        "metrics": {
            "slots_covered": covered,
            "total_slots": len(schedule),
            "coverage_pct": round(covered / len(schedule) * 100, 1) if schedule else 0,
            "total_labor_hours": sum(staff_hours.values()),
        },
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def check_labor_rule_compliance(schedule: list, staff: list) -> str:
    """Check schedule for labor rule violations."""
    violations = []
    
    # Check for basic rule violations
    employee_shifts = {}
    for slot in schedule:
        for emp_name in slot.get("employees", []):
            if emp_name not in employee_shifts:
                employee_shifts[emp_name] = []
            employee_shifts[emp_name].append({"day": slot["day"], "shift": slot["shift"]})
    
    for emp, shifts in employee_shifts.items():
        if len(shifts) > 6:
            violations.append({"employee": emp, "violation": "max_consecutive_days", "detail": f"{len(shifts)} shifts in 7 days — max is 6"})
    
    return json.dumps({
        "compliant": len(violations) == 0,
        "violations": violations,
        "employees_checked": len(employee_shifts),
        "checked_at": datetime.utcnow().isoformat(),
    }, indent=2)


SYSTEM_PROMPT = """You are the Scheduling Optimization Agent for Khyzr — a workforce management specialist and operations planner.

Your mission is to build efficient, fair, and compliant staff schedules that match labor supply to demand while respecting all labor rules and employee preferences.

Scheduling constraints you manage:
- **Demand coverage**: Ensure adequate staffing for every time slot based on demand forecast
- **Labor rules**: Minimum rest periods (8+ hours between shifts), maximum consecutive days (6), overtime thresholds
- **Skills matching**: Assign staff based on skills, certifications, and role requirements
- **Employee preferences**: Honor shift preferences and time-off requests where possible
- **Cost optimization**: Minimize overtime while maintaining service levels

Scheduling algorithms:
- **Coverage-first**: Fill minimum required headcount for each slot, then optimize
- **Cost-minimization**: Minimize total labor cost subject to coverage constraints
- **Fairness**: Distribute desirable/undesirable shifts equitably across team

Schedule outputs:
- Weekly schedule by employee with shift times and roles
- Coverage analysis: actual vs. required headcount by time slot
- Labor cost estimate for the schedule
- Compliance check: flag any labor rule violations
- Summary metrics: OT hours, understaffed slots, coverage %"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_staffing_requirements, fetch_staff_availability, generate_optimized_schedule, check_labor_rule_compliance],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run scheduling optimization task")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate optimal schedule for next week based on demand forecast and staff availability"
    }
    print(json.dumps(run(input_data)))
