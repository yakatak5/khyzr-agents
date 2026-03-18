"""
QC Monitoring Agent
==================
Monitors production data and sensor feeds to flag defects or process deviations in real time.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
import pandas as pd
import numpy as np
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_sensor_data(production_line: str, hours_back: int = 1) -> str:
    """Fetch recent sensor/production data from IoT streams or S3."""
    import numpy as np
    bucket = os.environ.get("IOT_DATA_BUCKET")
    if bucket:
        import boto3
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"sensor-data/{production_line}/latest.json")
            return obj["Body"].read().decode("utf-8")
        except Exception:
            pass
    
    # Generate synthetic sensor readings
    n = hours_back * 60  # one reading per minute
    np.random.seed(42)
    
    # Simulate a process with occasional outliers
    base_temp = 185.0
    base_pressure = 2.5
    readings = []
    
    for i in range(n):
        # Occasional anomalies
        anomaly = np.random.random() < 0.03  # 3% anomaly rate
        temp = base_temp + np.random.normal(0, 1.5) + (10 if anomaly else 0)
        pressure = base_pressure + np.random.normal(0, 0.1) + (0.5 if anomaly else 0)
        defect = anomaly or (temp > 190 or pressure > 2.8)
        
        readings.append({
            "timestamp": f"T+{i}min",
            "production_line": production_line,
            "temperature_c": round(temp, 2),
            "pressure_bar": round(pressure, 3),
            "units_produced": np.random.randint(8, 12),
            "defect_detected": defect,
        })
    
    defect_count = sum(1 for r in readings if r["defect_detected"])
    return json.dumps({
        "production_line": production_line,
        "readings": readings[-20:],  # Last 20 readings
        "summary": {"total_readings": n, "defect_count": defect_count, "defect_rate_pct": round(defect_count / n * 100, 2)},
        "note": "Synthetic data — configure IOT_DATA_BUCKET for real sensor feeds",
    }, indent=2)


@tool
def detect_anomalies(readings: list, metric: str, control_limit_sigma: float = 3.0) -> str:
    """
    Apply SPC control chart logic to detect process anomalies.

    Args:
        readings: List of sensor reading dicts
        metric: Metric to analyze (e.g., 'temperature_c', 'pressure_bar')
        control_limit_sigma: Control limit in standard deviations (default 3-sigma)

    Returns:
        JSON anomaly detection results with control chart statistics
    """
    import numpy as np
    values = [r.get(metric) for r in readings if r.get(metric) is not None]
    if not values:
        return json.dumps({"error": f"No data for metric: {metric}"})
    
    mean = np.mean(values)
    std = np.std(values)
    ucl = mean + control_limit_sigma * std
    lcl = mean - control_limit_sigma * std
    
    anomalies = []
    for i, (reading, val) in enumerate(zip(readings, values)):
        if val > ucl or val < lcl:
            anomalies.append({
                "index": i,
                "timestamp": reading.get("timestamp"),
                "value": val,
                "deviation_sigma": round(abs(val - mean) / std, 2) if std > 0 else 0,
                "type": "above_UCL" if val > ucl else "below_LCL",
            })
    
    return json.dumps({
        "metric": metric,
        "n_readings": len(values),
        "mean": round(mean, 4),
        "std_dev": round(std, 4),
        "ucl": round(ucl, 4),
        "lcl": round(lcl, 4),
        "anomalies_found": len(anomalies),
        "anomaly_rate_pct": round(len(anomalies) / len(values) * 100, 2),
        "anomalies": anomalies,
        "process_status": "IN_CONTROL" if len(anomalies) == 0 else "OUT_OF_CONTROL",
    }, indent=2)


@tool
def classify_defects(defect_readings: list) -> str:
    """Classify and count defects by type using Pareto analysis."""
    defect_counts = {}
    for reading in defect_readings:
        if reading.get("defect_detected"):
            # Classify based on out-of-spec parameters
            if reading.get("temperature_c", 185) > 190:
                defect_counts["high_temperature"] = defect_counts.get("high_temperature", 0) + 1
            elif reading.get("pressure_bar", 2.5) > 2.8:
                defect_counts["excess_pressure"] = defect_counts.get("excess_pressure", 0) + 1
            else:
                defect_counts["other"] = defect_counts.get("other", 0) + 1
    
    total = sum(defect_counts.values())
    sorted_defects = sorted(defect_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Pareto analysis
    cumulative = 0
    pareto = []
    for defect_type, count in sorted_defects:
        pct = count / total * 100 if total else 0
        cumulative += pct
        pareto.append({"type": defect_type, "count": count, "pct": round(pct, 1), "cumulative_pct": round(cumulative, 1), "pareto_class": "vital_few" if cumulative <= 80 else "trivial_many"})
    
    return json.dumps({"total_defects": total, "pareto_analysis": pareto, "top_root_cause": pareto[0]["type"] if pareto else None}, indent=2)


@tool
def generate_qc_alert(anomaly_data: dict, production_line: str, severity: str = "auto") -> str:
    """Generate and dispatch a QC alert for detected anomalies."""
    if severity == "auto":
        rate = anomaly_data.get("anomaly_rate_pct", 0)
        severity = "CRITICAL" if rate > 10 else ("HIGH" if rate > 5 else "MEDIUM")
    
    alert = {
        "alert_id": f"QC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "production_line": production_line,
        "severity": severity,
        "metric": anomaly_data.get("metric"),
        "process_status": anomaly_data.get("process_status"),
        "anomaly_rate_pct": anomaly_data.get("anomaly_rate_pct"),
        "recommended_actions": {
            "CRITICAL": ["STOP PRODUCTION LINE IMMEDIATELY", "Notify Quality Manager", "Quarantine last 2 hours of output", "Begin root cause analysis"],
            "HIGH": ["Increase inspection frequency to 100%", "Notify shift supervisor", "Check process parameters against spec", "Document all anomalies"],
            "MEDIUM": ["Flag for quality review", "Increase sampling frequency", "Check calibration of sensors"],
        }.get(severity, []),
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    # Save to SNS or SQS if configured
    sns_arn = os.environ.get("QC_ALERT_SNS_ARN")
    if sns_arn:
        import boto3
        sns = boto3.client("sns", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            sns.publish(TopicArn=sns_arn, Subject=f"[{severity}] QC Alert: {production_line}", Message=json.dumps(alert))
            alert["notification_sent"] = True
        except Exception as e:
            alert["notification_error"] = str(e)
    
    return json.dumps(alert, indent=2)


SYSTEM_PROMPT = """You are the QC Monitoring Agent for Khyzr — a quality control engineer and statistical process control specialist.

Your mission is to catch quality issues at the source — before defective products reach customers or downstream processes. Early detection saves rework, scrap, and customer satisfaction.

Monitoring methodology:
- **Statistical Process Control (SPC)**: Control charts to distinguish normal variation from special cause variation
- **Real-time alerts**: Immediate notification when metrics leave control limits
- **Trend detection**: Identify gradual drift before process goes out of control
- **Root cause correlation**: Link quality deviations to process parameters (temperature, speed, pressure)

Control chart types:
- **X-bar & R charts**: Monitor process mean and variation for continuous data
- **P-charts**: Monitor defect proportion for attribute data
- **CUSUM**: Cumulative sum charts for detecting small, sustained shifts

Alert thresholds:
- **Process Out of Control**: Any point outside ±3σ control limits — immediate stop-and-investigate
- **Warning**: 2 of 3 consecutive points beyond ±2σ — increase monitoring frequency
- **Trend**: 7+ consecutive points trending in same direction — investigate assignable cause
- **Run**: 8+ consecutive points on same side of mean — investigate process shift"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_sensor_data, detect_anomalies, classify_defects, generate_qc_alert],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run QC monitoring task")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Analyze latest production data and flag any quality deviations"
    }
    print(json.dumps(run(input_data)))
