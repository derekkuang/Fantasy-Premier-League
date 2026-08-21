# Cost guardrails. None of these save much money today — the point is that all three growth
# curves (spend, object versions, logs) are UNBOUNDED by default, and unbounded curves get
# noticed on the bill that finally hurts, months after the fix was a one-liner.

# A $10/month ceiling with two triggers: actual spend at 80% (something IS wrong), forecast at
# 100% (something WILL BE wrong — this one fires days earlier). Budgets over a CloudWatch
# billing alarm because it emails directly: no SNS topic, no confirmation-click dependency.
resource "aws_budgets_budget" "monthly" {
  name         = "fpledge-monthly"
  budget_type  = "COST"
  limit_amount = "10"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    notification_type          = "ACTUAL"
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = ["derekkuang0213@gmail.com"]
  }
  notification {
    notification_type          = "FORECASTED"
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = ["derekkuang0213@gmail.com"]
  }
}

# Versioning on the data bucket exists to survive a bad sync — a recovery measured in days.
# Without expiry, every overwrite of news.json (3x daily) and gw{N}.json (daily) keeps its old
# body forever: insurance that outlived its purpose, billed monthly.
resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
  rule {
    id     = "abort-stale-multiparts"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Lambda auto-creates its log groups with retention "never expire". Thirty days covers every
# debugging session this project has ever needed; the capture INDEX in S3 — not CloudWatch —
# is the permanent record of what ran.
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = toset(["fpledge-api", "fpledge-snapshot", "fpledge-news", "fpledge-props"])

  name              = "/aws/lambda/${each.value}"
  retention_in_days = 30
}

# --- adopt the live resources (created by CLI 2026-08-20) ------------------------------------
import {
  to = aws_budgets_budget.monthly
  id = "546712138633:fpledge-monthly"
}
import {
  to = aws_s3_bucket_lifecycle_configuration.data
  id = "fpledge-data-546712138633"
}
import {
  to = aws_cloudwatch_log_group.lambda["fpledge-api"]
  id = "/aws/lambda/fpledge-api"
}
import {
  to = aws_cloudwatch_log_group.lambda["fpledge-snapshot"]
  id = "/aws/lambda/fpledge-snapshot"
}
import {
  to = aws_cloudwatch_log_group.lambda["fpledge-news"]
  id = "/aws/lambda/fpledge-news"
}

import {
  to = aws_cloudwatch_log_group.lambda["fpledge-props"]
  id = "/aws/lambda/fpledge-props"
}
