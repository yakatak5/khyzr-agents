# =============================================================================
# Root Outputs — all 46 Khyzr agent Lambda ARNs and ECR repository URLs
# =============================================================================
# Note: Individual agent modules expose lambda_function_arn, ecr_repository_url,
# reports_bucket, and invoke_command outputs.
# =============================================================================

# ---------------------------------------------------------------------------
# Domain 1: Executive Strategy (01–11)
# ---------------------------------------------------------------------------

output "market_intelligence_lambda_arn" {
  description = "Market Intelligence Agent Lambda ARN"
  value       = try(module.market_intelligence_agent.lambda_function_arn, "")
}

output "executive_reporting_lambda_arn" {
  description = "Executive Reporting Agent Lambda ARN"
  value       = try(module.executive_reporting_agent.lambda_function_arn, "")
}

output "strategy_document_lambda_arn" {
  description = "Strategy Document Agent Lambda ARN"
  value       = try(module.strategy_document_agent.lambda_function_arn, "")
}

output "deal_sourcing_lambda_arn" {
  description = "Deal Sourcing Agent Lambda ARN"
  value       = try(module.deal_sourcing_agent.lambda_function_arn, "")
}

output "scenario_modeling_lambda_arn" {
  description = "Scenario Modeling Agent Lambda ARN"
  value       = try(module.scenario_modeling_agent.lambda_function_arn, "")
}

output "briefing_lambda_arn" {
  description = "Briefing Agent Lambda ARN"
  value       = try(module.briefing_agent.lambda_function_arn, "")
}

output "okr_tracking_lambda_arn" {
  description = "OKR Tracking Agent Lambda ARN"
  value       = try(module.okr_tracking_agent.lambda_function_arn, "")
}

output "esg_reporting_lambda_arn" {
  description = "ESG Reporting Agent Lambda ARN"
  value       = try(module.esg_reporting_agent.lambda_function_arn, "")
}

output "risk_monitoring_lambda_arn" {
  description = "Risk Monitoring Agent Lambda ARN"
  value       = try(module.risk_monitoring_agent.lambda_function_arn, "")
}

output "ir_communication_lambda_arn" {
  description = "IR Communication Agent Lambda ARN"
  value       = try(module.ir_communication_agent.lambda_function_arn, "")
}

output "audit_trail_lambda_arn" {
  description = "Audit Trail Agent Lambda ARN"
  value       = try(module.audit_trail_agent.lambda_function_arn, "")
}

# ---------------------------------------------------------------------------
# Domain 2: Sales & Marketing (12–23)
# ---------------------------------------------------------------------------

output "lead_scoring_lambda_arn" {
  description = "Lead Scoring Agent Lambda ARN"
  value       = try(module.lead_scoring_agent.lambda_function_arn, "")
}

output "seo_content_lambda_arn" {
  description = "SEO Content Agent Lambda ARN"
  value       = try(module.seo_content_agent.lambda_function_arn, "")
}

output "email_personalization_lambda_arn" {
  description = "Email Personalization Agent Lambda ARN"
  value       = try(module.email_personalization_agent.lambda_function_arn, "")
}

output "social_media_lambda_arn" {
  description = "Social Media Agent Lambda ARN"
  value       = try(module.social_media_agent.lambda_function_arn, "")
}

output "crm_enrichment_lambda_arn" {
  description = "CRM Enrichment Agent Lambda ARN"
  value       = try(module.crm_enrichment_agent.lambda_function_arn, "")
}

output "battlecard_lambda_arn" {
  description = "Battlecard Agent Lambda ARN"
  value       = try(module.battlecard_agent.lambda_function_arn, "")
}

output "sales_enablement_lambda_arn" {
  description = "Sales Enablement Agent Lambda ARN"
  value       = try(module.sales_enablement_agent.lambda_function_arn, "")
}

output "ad_optimization_lambda_arn" {
  description = "Ad Optimization Agent Lambda ARN"
  value       = try(module.ad_optimization_agent.lambda_function_arn, "")
}

output "churn_intelligence_lambda_arn" {
  description = "Churn Intelligence Agent Lambda ARN"
  value       = try(module.churn_intelligence_agent.lambda_function_arn, "")
}

output "abm_intelligence_lambda_arn" {
  description = "ABM Intelligence Agent Lambda ARN"
  value       = try(module.abm_intelligence_agent.lambda_function_arn, "")
}

output "attribution_lambda_arn" {
  description = "Attribution Agent Lambda ARN"
  value       = try(module.attribution_agent.lambda_function_arn, "")
}

output "sentiment_monitoring_lambda_arn" {
  description = "Sentiment Monitoring Agent Lambda ARN"
  value       = try(module.sentiment_monitoring_agent.lambda_function_arn, "")
}

# ---------------------------------------------------------------------------
# Domain 3: Operations (24–35)
# ---------------------------------------------------------------------------

output "demand_forecasting_lambda_arn" {
  description = "Demand Forecasting Agent Lambda ARN"
  value       = try(module.demand_forecasting_agent.lambda_function_arn, "")
}

output "inventory_optimization_lambda_arn" {
  description = "Inventory Optimization Agent Lambda ARN"
  value       = try(module.inventory_optimization_agent.lambda_function_arn, "")
}

output "vendor_compliance_lambda_arn" {
  description = "Vendor Compliance Agent Lambda ARN"
  value       = try(module.vendor_compliance_agent.lambda_function_arn, "")
}

output "project_management_lambda_arn" {
  description = "Project Management Agent Lambda ARN"
  value       = try(module.project_management_agent.lambda_function_arn, "")
}

output "sop_drafting_lambda_arn" {
  description = "SOP Drafting Agent Lambda ARN"
  value       = try(module.sop_drafting_agent.lambda_function_arn, "")
}

output "procurement_lambda_arn" {
  description = "Procurement Agent Lambda ARN"
  value       = try(module.procurement_agent.lambda_function_arn, "")
}

output "scheduling_optimization_lambda_arn" {
  description = "Scheduling Optimization Agent Lambda ARN"
  value       = try(module.scheduling_optimization_agent.lambda_function_arn, "")
}

output "qc_monitoring_lambda_arn" {
  description = "QC Monitoring Agent Lambda ARN"
  value       = try(module.qc_monitoring_agent.lambda_function_arn, "")
}

output "logistics_coordination_lambda_arn" {
  description = "Logistics Coordination Agent Lambda ARN"
  value       = try(module.logistics_coordination_agent.lambda_function_arn, "")
}

output "contract_management_lambda_arn" {
  description = "Contract Management Agent Lambda ARN"
  value       = try(module.contract_management_agent.lambda_function_arn, "")
}

output "support_automation_lambda_arn" {
  description = "Support Automation Agent Lambda ARN"
  value       = try(module.support_automation_agent.lambda_function_arn, "")
}

output "process_intelligence_lambda_arn" {
  description = "Process Intelligence Agent Lambda ARN"
  value       = try(module.process_intelligence_agent.lambda_function_arn, "")
}

# ---------------------------------------------------------------------------
# Domain 4: Finance & Accounting (36–41)
# ---------------------------------------------------------------------------

output "ap_automation_lambda_arn" {
  description = "AP Automation Agent Lambda ARN"
  value       = try(module.ap_automation_agent.lambda_function_arn, "")
}

output "financial_reporting_lambda_arn" {
  description = "Financial Reporting Agent Lambda ARN"
  value       = try(module.financial_reporting_agent.lambda_function_arn, "")
}

output "investment_analysis_lambda_arn" {
  description = "Investment Analysis Agent Lambda ARN"
  value       = try(module.investment_analysis_agent.lambda_function_arn, "")
}

output "expense_audit_lambda_arn" {
  description = "Expense Audit Agent Lambda ARN"
  value       = try(module.expense_audit_agent.lambda_function_arn, "")
}

output "ar_collections_lambda_arn" {
  description = "AR Collections Agent Lambda ARN"
  value       = try(module.ar_collections_agent.lambda_function_arn, "")
}

output "cash_flow_lambda_arn" {
  description = "Cash Flow Agent Lambda ARN"
  value       = try(module.cash_flow_agent.lambda_function_arn, "")
}

# ---------------------------------------------------------------------------
# Domain 5: Healthcare (42–46)
# ---------------------------------------------------------------------------

output "scheduling_automation_lambda_arn" {
  description = "Healthcare Scheduling Automation Agent Lambda ARN"
  value       = try(module.scheduling_automation_agent.lambda_function_arn, "")
}

output "medical_coding_lambda_arn" {
  description = "Medical Coding Agent Lambda ARN"
  value       = try(module.medical_coding_agent.lambda_function_arn, "")
}

output "clinical_documentation_lambda_arn" {
  description = "Clinical Documentation Agent Lambda ARN"
  value       = try(module.clinical_documentation_agent.lambda_function_arn, "")
}

output "patient_intake_lambda_arn" {
  description = "Patient Intake Agent Lambda ARN"
  value       = try(module.patient_intake_agent.lambda_function_arn, "")
}

output "revenue_cycle_lambda_arn" {
  description = "Revenue Cycle Agent Lambda ARN"
  value       = try(module.revenue_cycle_agent.lambda_function_arn, "")
}
