"""
Financial Reporting Agent
=========================
Pulls general ledger data and auto-generates GAAP-compliant financial statements:
income statements, balance sheets, and cash flow statements.

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
def fetch_gl_data(period: str, account_type: str = "all") -> str:
    """
    Fetch general ledger data for a specified accounting period.

    Args:
        period: Accounting period in YYYY-MM or YYYY-QN format (e.g., '2024-Q1', '2024-03')
        account_type: Filter by account type (all, revenue, expense, asset, liability, equity)

    Returns:
        JSON string with GL entries organized by account category and code
    """
    # In production: queries ERP (QuickBooks, NetSuite, SAP) via API or data warehouse
    gl_data = {
        "period": period,
        "account_type_filter": account_type,
        "currency": "USD",
        "accounts": {
            "revenue": [
                {"code": "4000", "name": "Product Revenue", "balance": 2450000.00},
                {"code": "4100", "name": "Service Revenue", "balance": 680000.00},
                {"code": "4200", "name": "Subscription Revenue", "balance": 320000.00},
            ],
            "cogs": [
                {"code": "5000", "name": "Cost of Goods Sold", "balance": 1102500.00},
                {"code": "5100", "name": "Direct Labor", "balance": 245000.00},
                {"code": "5200", "name": "Manufacturing Overhead", "balance": 89000.00},
            ],
            "operating_expenses": [
                {"code": "6000", "name": "Salaries & Benefits", "balance": 620000.00},
                {"code": "6100", "name": "Marketing & Advertising", "balance": 185000.00},
                {"code": "6200", "name": "General & Administrative", "balance": 142000.00},
                {"code": "6300", "name": "Research & Development", "balance": 95000.00},
                {"code": "6400", "name": "Depreciation & Amortization", "balance": 48000.00},
            ],
            "assets": [
                {"code": "1000", "name": "Cash & Equivalents", "balance": 1850000.00},
                {"code": "1100", "name": "Accounts Receivable", "balance": 920000.00},
                {"code": "1200", "name": "Inventory", "balance": 445000.00},
                {"code": "1500", "name": "Property, Plant & Equipment (net)", "balance": 2100000.00},
                {"code": "1600", "name": "Intangible Assets", "balance": 380000.00},
            ],
            "liabilities": [
                {"code": "2000", "name": "Accounts Payable", "balance": 485000.00},
                {"code": "2100", "name": "Accrued Liabilities", "balance": 220000.00},
                {"code": "2200", "name": "Deferred Revenue", "balance": 148000.00},
                {"code": "2500", "name": "Long-term Debt", "balance": 1200000.00},
            ],
            "equity": [
                {"code": "3000", "name": "Common Stock", "balance": 500000.00},
                {"code": "3100", "name": "Additional Paid-in Capital", "balance": 2800000.00},
                {"code": "3200", "name": "Retained Earnings", "balance": 342000.00},
            ],
        },
        "fetched_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(gl_data, indent=2)


@tool
def generate_income_statement(gl_data: str, period_label: str = "") -> str:
    """
    Generate a GAAP income statement from GL data.

    Args:
        gl_data: JSON string from fetch_gl_data
        period_label: Human-readable period label for the statement header

    Returns:
        JSON string with structured income statement (revenue, gross profit, EBITDA, net income)
    """
    try:
        data = json.loads(gl_data)
        accounts = data.get("accounts", {})
    except Exception:
        return json.dumps({"error": "Invalid GL data"})

    revenue = sum(a["balance"] for a in accounts.get("revenue", []))
    cogs = sum(a["balance"] for a in accounts.get("cogs", []))
    opex = sum(a["balance"] for a in accounts.get("operating_expenses", []))
    da = next((a["balance"] for a in accounts.get("operating_expenses", []) if "Depreciation" in a["name"]), 0)

    gross_profit = revenue - cogs
    gross_margin = gross_profit / revenue if revenue else 0
    ebitda = gross_profit - opex + da
    ebit = gross_profit - opex
    interest_expense = 42000.00  # from notes payable/debt
    ebt = ebit - interest_expense
    tax_rate = 0.21
    income_tax = max(0, ebt * tax_rate)
    net_income = ebt - income_tax

    statement = {
        "statement": "Income Statement",
        "period": period_label or data.get("period", ""),
        "currency": "USD",
        "revenue": {
            "breakdown": accounts.get("revenue", []),
            "total": revenue,
        },
        "cost_of_goods_sold": {
            "breakdown": accounts.get("cogs", []),
            "total": cogs,
        },
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_margin * 100, 1),
        "operating_expenses": {
            "breakdown": accounts.get("operating_expenses", []),
            "total": opex,
        },
        "ebitda": ebitda,
        "ebitda_margin_pct": round(ebitda / revenue * 100, 1) if revenue else 0,
        "depreciation_amortization": da,
        "ebit": ebit,
        "interest_expense": interest_expense,
        "earnings_before_tax": ebt,
        "income_tax": round(income_tax, 2),
        "net_income": round(net_income, 2),
        "net_margin_pct": round(net_income / revenue * 100, 1) if revenue else 0,
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(statement, indent=2)


@tool
def generate_balance_sheet(gl_data: str, period_label: str = "") -> str:
    """
    Generate a GAAP balance sheet from GL data.

    Args:
        gl_data: JSON string from fetch_gl_data
        period_label: Human-readable period label for the statement header

    Returns:
        JSON string with structured balance sheet (assets, liabilities, equity)
    """
    try:
        data = json.loads(gl_data)
        accounts = data.get("accounts", {})
    except Exception:
        return json.dumps({"error": "Invalid GL data"})

    total_assets = sum(a["balance"] for a in accounts.get("assets", []))
    total_liabilities = sum(a["balance"] for a in accounts.get("liabilities", []))
    total_equity = sum(a["balance"] for a in accounts.get("equity", []))

    balance_sheet = {
        "statement": "Balance Sheet",
        "period": period_label or data.get("period", ""),
        "currency": "USD",
        "assets": {
            "current_assets": [a for a in accounts.get("assets", []) if a["code"] < "1400"],
            "non_current_assets": [a for a in accounts.get("assets", []) if a["code"] >= "1400"],
            "total_assets": total_assets,
        },
        "liabilities": {
            "current_liabilities": [a for a in accounts.get("liabilities", []) if a["code"] < "2400"],
            "long_term_liabilities": [a for a in accounts.get("liabilities", []) if a["code"] >= "2400"],
            "total_liabilities": total_liabilities,
        },
        "equity": {
            "breakdown": accounts.get("equity", []),
            "total_equity": total_equity,
        },
        "balance_check": {
            "assets": total_assets,
            "liabilities_plus_equity": total_liabilities + total_equity,
            "balanced": abs(total_assets - (total_liabilities + total_equity)) < 0.01,
        },
        "key_ratios": {
            "current_ratio": round(
                sum(a["balance"] for a in accounts.get("assets", []) if a["code"] < "1400") /
                sum(a["balance"] for a in accounts.get("liabilities", []) if a["code"] < "2400"), 2
            ),
            "debt_to_equity": round(total_liabilities / total_equity, 2) if total_equity else None,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(balance_sheet, indent=2)


@tool
def generate_cash_flow_statement(gl_data: str, net_income: float, period_label: str = "") -> str:
    """
    Generate a cash flow statement using the indirect method.

    Args:
        gl_data: JSON string from fetch_gl_data
        net_income: Net income figure from the income statement
        period_label: Human-readable period label

    Returns:
        JSON string with operating, investing, and financing cash flows
    """
    try:
        data = json.loads(gl_data)
        accounts = data.get("accounts", {})
    except Exception:
        return json.dumps({"error": "Invalid GL data"})

    da = next((a["balance"] for a in accounts.get("operating_expenses", []) if "Depreciation" in a["name"]), 48000.0)
    ar_change = -85000.00   # increase in AR (use of cash)
    inv_change = 32000.00   # decrease in inventory (source of cash)
    ap_change = 45000.00    # increase in AP (source of cash)
    accrued_change = 18000.00

    operating_cf = net_income + da + ar_change + inv_change + ap_change + accrued_change
    investing_cf = -320000.00   # capex net of disposals
    financing_cf = -95000.00    # debt repayment net of new borrowings

    cash_flow = {
        "statement": "Cash Flow Statement",
        "method": "Indirect",
        "period": period_label or data.get("period", ""),
        "currency": "USD",
        "operating_activities": {
            "net_income": net_income,
            "adjustments": {
                "depreciation_amortization": da,
                "change_in_accounts_receivable": ar_change,
                "change_in_inventory": inv_change,
                "change_in_accounts_payable": ap_change,
                "change_in_accrued_liabilities": accrued_change,
            },
            "net_cash_from_operations": operating_cf,
        },
        "investing_activities": {
            "capital_expenditures": -350000.00,
            "proceeds_from_asset_sales": 30000.00,
            "net_cash_from_investing": investing_cf,
        },
        "financing_activities": {
            "debt_repayments": -150000.00,
            "proceeds_from_borrowings": 55000.00,
            "net_cash_from_financing": financing_cf,
        },
        "net_change_in_cash": operating_cf + investing_cf + financing_cf,
        "beginning_cash": 1800000.00,
        "ending_cash": 1800000.00 + operating_cf + investing_cf + financing_cf,
        "free_cash_flow": operating_cf - 350000.00,
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(cash_flow, indent=2)


@tool
def save_financial_report(report_content: str, report_type: str, period: str) -> str:
    """
    Save a financial statement or report to S3.

    Args:
        report_content: The complete report in markdown or JSON format
        report_type: Type of report (income_statement, balance_sheet, cash_flow, full_package)
        period: Accounting period for file organization (e.g., '2024-Q1')

    Returns:
        JSON string with S3 URI and confirmation
    """
    bucket = os.environ.get("REPORTS_BUCKET", "khyzr-financial-reports")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"financial-statements/{period}/{report_type}/{timestamp}.md"

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=report_content.encode("utf-8"),
            ContentType="text/markdown",
            Metadata={"period": period, "report_type": report_type},
        )
        return json.dumps({"status": "saved", "s3_uri": f"s3://{bucket}/{key}"})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "note": "Report generated but not persisted."})


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Financial Reporting Agent for Khyzr — a seasoned financial analyst and CPA-level expert in GAAP financial reporting, general ledger analysis, and management accounting.

Your mission is to pull general ledger data and automatically generate accurate, GAAP-compliant financial statements: income statements, balance sheets, and cash flow statements.

When generating financial reports for a period:
1. Fetch the complete GL data for the specified accounting period
2. Generate the Income Statement: revenue → gross profit → EBITDA → EBIT → net income with all margins
3. Generate the Balance Sheet: verify assets = liabilities + equity; compute key ratios
4. Generate the Cash Flow Statement using the indirect method: operating → investing → financing
5. Save the complete financial reporting package to S3

Financial reporting standards you enforce:
- **Revenue Recognition**: Ensure revenue is recognized per ASC 606 principles
- **Matching Principle**: Expenses matched to the period they are incurred
- **Balance Sheet Equation**: Always verify Assets = Liabilities + Equity
- **Free Cash Flow**: Highlight FCF as it's the truest measure of financial health
- **Key Ratios**: Always compute current ratio, debt-to-equity, gross margin, EBITDA margin, net margin

Presentation standards:
- Format all currency values with two decimal places and thousands separators
- Clearly label whether numbers represent period totals or point-in-time balances
- Include variance vs. prior period when comparative data is available
- Flag 🚨 any items that deviate >20% from plan or prior period
- Summarize key insights in an executive narrative at the top of each statement

You maintain rigorous accuracy — every number must reconcile. When generating markdown reports, use clean tables and clearly delineated sections for CFO-level review."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        fetch_gl_data,
        generate_income_statement,
        generate_balance_sheet,
        generate_cash_flow_statement,
        save_financial_report,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate the full financial reporting package for 2024-Q1")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate the complete financial reporting package for Q1 2024 — income statement, balance sheet, and cash flow statement."
    }
    print(json.dumps(run(input_data)))
