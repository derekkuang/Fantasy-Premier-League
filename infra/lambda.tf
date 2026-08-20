# Three functions, one pattern: arm64 (Graviton — ~20% cheaper per ms, and it matches the
# Apple Silicon dev machine so locally-tested wheels are the deployed wheels), python3.13,
# 512MB. Timeouts differ because the jobs differ: the API answers in ~300ms and 30s is already
# generous; the news capture politely throttles ~90 feed fetches and needs minutes.
#
# CODE DEPLOYS ARE NOT TERRAFORM'S JOB HERE — that is what `ignore_changes` on the code
# attributes declares. Terraform owns that each function EXISTS with this runtime, role, memory
# and environment; shipping new code stays `build_lambda.sh` + `aws lambda update-function-code`
# (see docs/OPERATIONS.md). Without the ignore, every plan after every deploy would show a
# spurious diff and eventually someone would "fix" it by applying an old zip over new code.

locals {
  common_env = {
    FPLEDGE_RAW_URI     = "s3://${local.bucket}/raw"
    FPLEDGE_SERVING_URI = "s3://${local.bucket}/serving"
  }
}

resource "aws_lambda_function" "api" {
  function_name = "fpledge-api"
  role          = aws_iam_role.api.arn
  runtime       = "python3.13"
  architectures = ["arm64"]
  handler       = "fpledge.api.lambda_handler.handler"
  memory_size   = 512
  timeout       = 30
  filename      = "${path.module}/../build/fpledge-api.zip"

  environment {
    # The API gets ONLY the serving URI. It has no business knowing where the raw zone is —
    # its role cannot read it anyway, and the asymmetry is the design, not an omission.
    variables = { FPLEDGE_SERVING_URI = local.common_env.FPLEDGE_SERVING_URI }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash, last_modified]
  }
}

resource "aws_lambda_function" "snapshot" {
  function_name = "fpledge-snapshot"
  role          = aws_iam_role.captures.arn
  runtime       = "python3.13"
  architectures = ["arm64"]
  handler       = "scripts.lambda_captures.snapshot_handler"
  memory_size   = 512
  timeout       = 120
  filename      = "${path.module}/../build/fpledge-captures.zip"

  environment {
    variables = local.common_env
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash, last_modified]
  }
}

resource "aws_lambda_function" "news" {
  function_name = "fpledge-news"
  role          = aws_iam_role.captures.arn
  runtime       = "python3.13"
  architectures = ["arm64"]
  handler       = "scripts.lambda_captures.news_handler"
  memory_size   = 512
  timeout       = 600 # ~90 throttled feed fetches + an S3 corpus rebuild; measured 76s, 8x headroom
  filename      = "${path.module}/../build/fpledge-captures.zip"

  environment {
    variables = local.common_env
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash, last_modified]
  }
}
