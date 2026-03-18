"""
Demand Forecasting Agent
=========================
Analyzes historical sales data, seasonality patterns, and market signals 
to generate demand forecasts and inventory recommendations.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import StringIO
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_historical_sales(product_id: str = None, months_back: int = 24) -> str:
    """
    Fetch historical sales data for demand forecasting.

    Args:
        product_id: Specific product/SKU (None = all products)
        months_back: Historical data window in months

    Returns:
        JSON historical sales data with monthly volumes and revenue
    """
    bucket = os.environ.get("SALES_DATA_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            key = f"historical-sales/{product_id or 'all'}.csv"
            obj = s3.get_object(Bucket=bucket, Key=key)
            df = pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")))
            return df.to_json(orient="records", indent=2)
        except Exception:
            pass
    
    # Generate synthetic historical data for demonstration
    dates = pd.date_range(end=datetime.utcnow(), periods=months_back, freq="ME")
    base_demand = 1000
    trend = np.linspace(0, 300, months_back)
    seasonal = 150 * np.sin(2 * np.pi * np.arange(months_back) / 12)
    noise = np.random.normal(0, 50, months_back)
    demand = base_demand + trend + seasonal + noise
    
    data = [{"date": str(d.date()), "product_id": product_id or "ALL", "units_sold": max(0, round(v)), "revenue": max(0, round(v * 45.5, 2))} for d, v in zip(dates, demand)]
    
    return json.dumps({"product_id": product_id or "ALL", "months_back": months_back, "data": data, "note": "Synthetic data — configure SALES_DATA_BUCKET for real historical data"}, indent=2)


@tool
def generate_forecast(historical_data: list, forecast_periods: int = 3, method: str = "moving_average") -> str:
    """
    Generate demand forecast from historical data.

    Args:
        historical_data: List of historical sales records
        forecast_periods: Number of periods to forecast ahead
        method: Forecasting method - 'moving_average', 'exponential_smoothing', 'seasonal_decomposition'

    Returns:
        JSON forecast with point estimates and confidence intervals
    """
    if not historical_data:
        return json.dumps({"error": "No historical data provided"})
    
    values = [d.get("units_sold", 0) for d in historical_data]
    
    if method == "moving_average":
        window = min(12, len(values))
        ma = np.mean(values[-window:])
        std = np.std(values[-window:])
        forecasts = []
        for i in range(forecast_periods):
            forecasts.append({
                "period": i + 1,
                "point_estimate": round(ma),
                "lower_80": round(max(0, ma - 1.28 * std)),
                "upper_80": round(ma + 1.28 * std),
                "lower_95": round(max(0, ma - 1.96 * std)),
                "upper_95": round(ma + 1.96 * std),
            })
    elif method == "exponential_smoothing":
        alpha = 0.3
        smoothed = values[0]
        for v in values[1:]:
            smoothed = alpha * v + (1 - alpha) * smoothed
        std = np.std(values[-12:]) if len(values) >= 12 else np.std(values)
        forecasts = [{"period": i+1, "point_estimate": round(smoothed), "lower_80": round(max(0, smoothed - 1.28*std)), "upper_80": round(smoothed + 1.28*std)} for i in range(forecast_periods)]
    else:
        avg = np.mean(values[-3:]) if len(values) >= 3 else np.mean(values)
        forecasts = [{"period": i+1, "point_estimate": round(avg)} for i in range(forecast_periods)]
    
    return json.dumps({
        "method": method,
        "forecast_periods": forecast_periods,
        "historical_avg": round(np.mean(values), 1),
        "historical_std": round(np.std(values), 1),
        "forecasts": forecasts,
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_inventory_recommendations(forecast: dict, current_inventory: dict, lead_time_days: int = 14) -> str:
    """
    Generate inventory recommendations based on demand forecast.

    Args:
        forecast: Demand forecast output
        current_inventory: Dict with current stock levels per SKU
        lead_time_days: Supplier lead time in days

    Returns:
        JSON inventory recommendations with reorder points and quantities
    """
    forecasts = forecast.get("forecasts", [])
    if not forecasts:
        return json.dumps({"error": "No forecast data available"})
    
    next_period_demand = forecasts[0].get("point_estimate", 0)
    upper_95 = forecasts[0].get("upper_95", next_period_demand * 1.3)
    
    # Safety stock = (max daily demand - avg daily demand) * lead time
    daily_avg = next_period_demand / 30
    daily_max = upper_95 / 30
    safety_stock = round((daily_max - daily_avg) * lead_time_days)
    reorder_point = round(daily_avg * lead_time_days + safety_stock)
    
    recommendations = []
    for sku, stock in current_inventory.items():
        status = "OK" if stock > reorder_point else ("REORDER_NOW" if stock < safety_stock else "APPROACHING_REORDER")
        recommendations.append({
            "sku": sku,
            "current_stock": stock,
            "reorder_point": reorder_point,
            "safety_stock": safety_stock,
            "recommended_order_qty": round(next_period_demand * 1.5 - stock) if stock < reorder_point else 0,
            "status": status,
            "days_of_stock_remaining": round(stock / daily_avg) if daily_avg > 0 else 999,
        })
    
    return json.dumps({"lead_time_days": lead_time_days, "recommendations": recommendations, "forecast_period_demand": next_period_demand}, indent=2)


SYSTEM_PROMPT = """You are the Demand Forecasting Agent for Khyzr — a supply chain analyst and demand planner.

Your mission is to generate accurate demand forecasts that minimize stockouts while avoiding excess inventory. Good forecasting directly impacts cash flow, customer satisfaction, and operational efficiency.

Forecasting methodologies:
- **Moving Average**: Simple, robust for stable demand patterns
- **Exponential Smoothing**: Weights recent data more — better for trending products
- **Seasonal Decomposition**: Explicitly models seasonal patterns — essential for cyclical businesses
- **Regression-Based**: Incorporates external signals (promotions, market events)

Demand signals you incorporate:
- Historical sales data (24+ months recommended)
- Seasonality patterns (month-of-year, day-of-week effects)
- Promotions and marketing calendar
- External signals: economic indicators, competitor pricing, weather for seasonal goods
- Sales pipeline (forward-looking demand from committed deals)

Inventory optimization principles:
- **Safety Stock**: Buffer against demand uncertainty and supply variability
- **Reorder Point**: Stock level that triggers a new purchase order
- **Economic Order Quantity (EOQ)**: Optimal order size balancing holding and ordering costs
- **ABC Analysis**: Prioritize forecasting accuracy for high-value (A) items

When forecasting demand:
1. Fetch historical sales data for requested product/category
2. Run demand forecast using appropriate method(s)
3. Generate inventory recommendations based on forecast and current stock
4. Highlight high-risk items (stockout risk or excess inventory)
5. Produce executive summary with key actions"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_historical_sales, generate_forecast, generate_inventory_recommendations],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate demand forecast for next quarter and inventory recommendations")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Forecast demand for the next 3 months using exponential smoothing. Current inventory: SKU-001: 450 units, SKU-002: 120 units. Lead time is 21 days."
    }
    print(json.dumps(run(input_data)))
