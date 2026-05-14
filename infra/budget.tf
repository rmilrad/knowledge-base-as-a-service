# ===== AWS Budget Alert =====

resource "aws_budgets_budget" "monthly" {
  count = var.budget_alert_email != "" ? 1 : 0

  name         = "${var.project}-monthly-budget"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_limit
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80 # Alert at 80% of limit
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100 # Alert when exceeded
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
