terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment and configure for remote state:
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "khyzr-agents/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
}

# ===========================================================================
# DOMAIN 1: Executive Strategy (Agents 01–11)
# ===========================================================================

module "market_intelligence_agent" {
  source      = "../agents/01-market-intelligence-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "executive_reporting_agent" {
  source      = "../agents/02-executive-reporting-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "strategy_document_agent" {
  source      = "../agents/03-strategy-document-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "deal_sourcing_agent" {
  source      = "../agents/04-deal-sourcing-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "scenario_modeling_agent" {
  source      = "../agents/05-scenario-modeling-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "briefing_agent" {
  source      = "../agents/06-briefing-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "okr_tracking_agent" {
  source      = "../agents/07-okr-tracking-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "esg_reporting_agent" {
  source      = "../agents/08-esg-reporting-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "risk_monitoring_agent" {
  source      = "../agents/09-risk-monitoring-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "ir_communication_agent" {
  source      = "../agents/10-ir-communication-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "audit_trail_agent" {
  source      = "../agents/11-audit-trail-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

# ===========================================================================
# DOMAIN 2: Sales & Marketing (Agents 12–23)
# ===========================================================================

module "lead_scoring_agent" {
  source      = "../agents/12-lead-scoring-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "seo_content_agent" {
  source      = "../agents/13-seo-content-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "email_personalization_agent" {
  source      = "../agents/14-email-personalization-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "social_media_agent" {
  source      = "../agents/15-social-media-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "crm_enrichment_agent" {
  source      = "../agents/16-crm-enrichment-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "battlecard_agent" {
  source      = "../agents/17-battlecard-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "sales_enablement_agent" {
  source      = "../agents/18-sales-enablement-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "ad_optimization_agent" {
  source      = "../agents/19-ad-optimization-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "churn_intelligence_agent" {
  source      = "../agents/20-churn-intelligence-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "abm_intelligence_agent" {
  source      = "../agents/21-abm-intelligence-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "attribution_agent" {
  source      = "../agents/22-attribution-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "sentiment_monitoring_agent" {
  source      = "../agents/23-sentiment-monitoring-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

# ===========================================================================
# DOMAIN 3: Operations (Agents 24–35)
# ===========================================================================

module "demand_forecasting_agent" {
  source      = "../agents/24-demand-forecasting-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "inventory_optimization_agent" {
  source      = "../agents/25-inventory-optimization-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "vendor_compliance_agent" {
  source      = "../agents/26-vendor-compliance-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "project_management_agent" {
  source      = "../agents/27-project-management-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "sop_drafting_agent" {
  source      = "../agents/28-sop-drafting-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "procurement_agent" {
  source      = "../agents/29-procurement-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "scheduling_optimization_agent" {
  source      = "../agents/30-scheduling-optimization-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "qc_monitoring_agent" {
  source      = "../agents/31-qc-monitoring-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "logistics_coordination_agent" {
  source      = "../agents/32-logistics-coordination-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "contract_management_agent" {
  source      = "../agents/33-contract-management-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "support_automation_agent" {
  source      = "../agents/34-support-automation-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "process_intelligence_agent" {
  source      = "../agents/35-process-intelligence-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

# ===========================================================================
# DOMAIN 4: Finance & Accounting (Agents 36–41)
# ===========================================================================

module "ap_automation_agent" {
  source      = "../agents/36-ap-automation-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "financial_reporting_agent" {
  source      = "../agents/37-financial-reporting-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "investment_analysis_agent" {
  source      = "../agents/38-investment-analysis-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "expense_audit_agent" {
  source      = "../agents/39-expense-audit-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "ar_collections_agent" {
  source      = "../agents/40-ar-collections-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "cash_flow_agent" {
  source      = "../agents/41-cash-flow-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

# ===========================================================================
# DOMAIN 5: Healthcare (Agents 42–46)
# ===========================================================================

module "scheduling_automation_agent" {
  source      = "../agents/42-scheduling-automation-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "medical_coding_agent" {
  source      = "../agents/43-medical-coding-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "clinical_documentation_agent" {
  source      = "../agents/44-clinical-documentation-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "patient_intake_agent" {
  source      = "../agents/45-patient-intake-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}

module "revenue_cycle_agent" {
  source      = "../agents/46-revenue-cycle-agent/infra"
  aws_region  = var.aws_region
  environment = var.environment
}
