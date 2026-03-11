aws_region          = "us-east-1"
environment         = "dev"
bedrock_model_id    = "anthropic.claude-sonnet-4-5"
schedule_expression = "rate(1 day)"
default_competitors = "[\"Competitor A\", \"Competitor B\", \"Competitor C\"]"
briefing_recipients = "exec@yourcompany.com,cto@yourcompany.com"  # comma-separated
ses_sender_email    = "intelligence@yourcompany.com"              # must be SES-verified
# news_api_key = "your_newsapi_key_here"  # Or set via TF_VAR_news_api_key env var
