# Alerting: the difference between a quiet day and a dead pipeline.
#
# This exists because of a specific near-miss. On what looked like deadline day, the snapshot
# index showed no capture inside the window and NOTHING in the system could say whether the
# schedule had fired — the panic turned out to be a timezone misread, but the gap it exposed
# was real: a broken EventBridge permission produces no errors, no logs, no signal at all.
# A dead schedule is indistinguishable from a quiet one unless something alarms on absence.
#
# Two alarm shapes per capture, because they catch different failures:
#   *-errors       the capture RAN and failed. One error alerts — captures are unrepeatable,
#                  so "wait for a pattern" means "lose data while waiting".
#   *-not-running  the capture NEVER RAN. Lambda emits no Invocations datapoint at all when a
#                  function is not invoked, so `treat_missing_data = "breaching"` is not a
#                  conservative default here — the missing metric IS the failure signal.

resource "aws_sns_topic" "alerts" {
  name = "fpledge-alerts"
}

# The email subscription is NOT managed here: SNS email subscriptions require a human clicking
# a confirmation link, which Terraform cannot do, and an unconfirmed subscription resource
# would sit permanently dirty in every plan. Subscribe by hand (once):
#   aws sns subscribe --topic-arn <arn> --protocol email --notification-endpoint <you>

locals {
  capture_functions = {
    snapshot = aws_lambda_function.snapshot.function_name
    news     = aws_lambda_function.news.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "capture_errors" {
  for_each = local.capture_functions

  alarm_name          = "${each.value}-errors"
  alarm_description   = "A ${each.value} run failed. Captures are unrepeatable — check CloudWatch logs now."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "capture_not_running" {
  for_each = local.capture_functions

  alarm_name          = "${each.value}-not-running"
  alarm_description   = "${each.value} had ZERO invocations in 24h — the schedule itself is broken. This alarm exists because a dead schedule looks identical to a quiet one."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching" # zero invocations = no datapoint at all; missing IS the signal
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# --- adopt the live resources (created by CLI 2026-08-20; see imports.tf for the pattern) ----
import {
  to = aws_sns_topic.alerts
  id = "arn:aws:sns:us-east-1:546712138633:fpledge-alerts"
}
import {
  to = aws_cloudwatch_metric_alarm.capture_errors["snapshot"]
  id = "fpledge-snapshot-errors"
}
import {
  to = aws_cloudwatch_metric_alarm.capture_errors["news"]
  id = "fpledge-news-errors"
}
import {
  to = aws_cloudwatch_metric_alarm.capture_not_running["snapshot"]
  id = "fpledge-snapshot-not-running"
}
import {
  to = aws_cloudwatch_metric_alarm.capture_not_running["news"]
  id = "fpledge-news-not-running"
}
