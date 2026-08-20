# ADOPTING THE HAND-BUILT STACK — the heart of this exercise.
#
# Everything here already exists in AWS, created by CLI on 2026-08-20. Without these blocks,
# `terraform apply` would try to CREATE each resource and collide with the live one (or worse,
# make a second API with a second URL). An `import` block instead tells Terraform "this config
# block IS that existing resource — record the mapping in state, change nothing."
#
# The workflow this enables, and the definition of done:
#   1. terraform plan   -> "N to import" and, critically, ZERO to change: proof the HCL matches
#                          reality attribute-for-attribute. Any diff shown here is a place where
#                          the code and the account disagree — reconcile it BEFORE apply.
#   2. terraform apply  -> executes the imports (writes state; touches no infrastructure).
#   3. terraform plan   -> "No changes." From this moment the account is described by code.
#
# These blocks are inert after step 2 and could be deleted; they stay as the record of where
# this state came from — the same reason the capture index keeps its legacy entries.

# --- S3 --------------------------------------------------------------------------------------
import {
  to = aws_s3_bucket.data
  id = "fpledge-data-546712138633"
}
import {
  to = aws_s3_bucket_versioning.data
  id = "fpledge-data-546712138633"
}
import {
  to = aws_s3_bucket_public_access_block.data
  id = "fpledge-data-546712138633"
}

# --- IAM -------------------------------------------------------------------------------------
import {
  to = aws_iam_role.api
  id = "fpledge-api-lambda"
}
import {
  to = aws_iam_role_policy_attachment.api_logs
  id = "fpledge-api-lambda/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
import {
  to = aws_iam_role_policy.api_serving_read
  id = "fpledge-api-lambda:fpledge-serving-read"
}
import {
  to = aws_iam_role.captures
  id = "fpledge-captures-lambda"
}
import {
  to = aws_iam_role_policy_attachment.captures_logs
  id = "fpledge-captures-lambda/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
import {
  to = aws_iam_role_policy.captures_data_readwrite
  id = "fpledge-captures-lambda:fpledge-data-readwrite"
}

# --- Lambda ----------------------------------------------------------------------------------
import {
  to = aws_lambda_function.api
  id = "fpledge-api"
}
import {
  to = aws_lambda_function.snapshot
  id = "fpledge-snapshot"
}
import {
  to = aws_lambda_function.news
  id = "fpledge-news"
}

# --- API Gateway (quick-create made the stage/route/integration implicitly; IDs from the
# --- live account: integration 0gms6ed, route cd6cxeu) ---------------------------------------
import {
  to = aws_apigatewayv2_api.api
  id = "wdvmpi4xw6"
}
import {
  to = aws_apigatewayv2_integration.api
  id = "wdvmpi4xw6/0gms6ed"
}
import {
  to = aws_apigatewayv2_route.default
  id = "wdvmpi4xw6/cd6cxeu"
}
import {
  to = aws_apigatewayv2_stage.default
  id = "wdvmpi4xw6/$default"
}
import {
  to = aws_lambda_permission.apigw
  id = "fpledge-api/apigw-invoke"
}

# --- EventBridge -----------------------------------------------------------------------------
import {
  to = aws_cloudwatch_event_rule.snapshot
  id = "fpledge-snapshot-3h"
}
import {
  to = aws_cloudwatch_event_target.snapshot
  id = "fpledge-snapshot-3h/snapshot"
}
import {
  to = aws_cloudwatch_event_rule.news
  id = "fpledge-news-daily"
}
import {
  to = aws_cloudwatch_event_target.news
  id = "fpledge-news-daily/news"
}
import {
  to = aws_lambda_permission.events_snapshot
  id = "fpledge-snapshot/events-invoke"
}
import {
  to = aws_lambda_permission.events_news
  id = "fpledge-news/events-invoke"
}
