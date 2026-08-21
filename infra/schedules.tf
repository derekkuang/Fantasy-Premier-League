# The schedules that make the captures nobody's job.
#
# Snapshot fires every 3 hours and SELF-GATES: the script exits in ~150ms unless a deadline is
# inside its 12-hour window, so ~7 of every 8 firings cost nothing and the one that matters
# gets four chances. That logic lives in the capture, not here, on purpose — a schedule that
# encoded deadline arithmetic would drift from FPL's actual calendar the first time a gameweek
# moved. News fires three times daily because feeds are a rolling window: items fall off
# permanently, and a missed day cannot be re-fetched.

resource "aws_cloudwatch_event_rule" "snapshot" {
  name                = "fpledge-snapshot-3h"
  schedule_expression = "rate(3 hours)"
}

resource "aws_cloudwatch_event_target" "snapshot" {
  rule = aws_cloudwatch_event_rule.snapshot.name
  arn  = aws_lambda_function.snapshot.arn
  # EventBridge sends {} as the payload; the handler treats a missing "force" as gated. So the
  # SCHEDULED path always respects the deadline window, and only a human invoking by hand with
  # {"force": true} can capture outside it.
  target_id = "snapshot"
}

resource "aws_cloudwatch_event_rule" "news" {
  name                = "fpledge-news-daily"
  schedule_expression = "cron(0 6,12,18 * * ? *)" # UTC — presser coverage lands through the UK day
}

resource "aws_cloudwatch_event_target" "news" {
  rule      = aws_cloudwatch_event_rule.news.name
  arn       = aws_lambda_function.news.arn
  target_id = "news"
}

resource "aws_lambda_permission" "events_snapshot" {
  statement_id  = "events-invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.snapshot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.snapshot.arn
}

resource "aws_lambda_permission" "events_news" {
  statement_id  = "events-invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.news.arn
}

resource "aws_cloudwatch_event_rule" "props" {
  name                = "fpledge-props-3h"
  schedule_expression = "rate(3 hours)" # self-gates to the deadline window, like snapshot —
                                        # which is also the credit budget: ~27 of 28 firings free
}

resource "aws_cloudwatch_event_target" "props" {
  rule      = aws_cloudwatch_event_rule.props.name
  arn       = aws_lambda_function.props.arn
  target_id = "props"
}

resource "aws_lambda_permission" "events_props" {
  statement_id  = "events-invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.props.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.props.arn
}

import {
  to = aws_cloudwatch_event_rule.props
  id = "fpledge-props-3h"
}
import {
  to = aws_cloudwatch_event_target.props
  id = "fpledge-props-3h/props"
}
import {
  to = aws_lambda_permission.events_props
  id = "fpledge-props/events-invoke"
}
