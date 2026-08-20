# Two execution roles, split on the only axis that matters: WHO MAY WRITE THE DATA.
#
#   fpledge-api-lambda       read-only.  The API serves artifacts; an endpoint that could write
#                            the bucket would mean a request-path bug could corrupt a season of
#                            captures.
#   fpledge-captures-lambda  read/write. The captures exist to write; they also read (the news
#                            digest rebuilds the corpus from every prior capture).
#
# Neither can touch anything outside the one data bucket, and neither can be assumed by
# anything but Lambda.

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- the API's role: read-only ---------------------------------------------------------------
resource "aws_iam_role" "api" {
  name               = "fpledge-api-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api_serving_read" {
  name = "fpledge-serving-read"
  role = aws_iam_role.api.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.data.arn, "${aws_s3_bucket.data.arn}/*"]
    }]
  })
}

# --- the captures' role: read/write ----------------------------------------------------------
resource "aws_iam_role" "captures" {
  name               = "fpledge-captures-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "captures_logs" {
  role       = aws_iam_role.captures.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "captures_data_readwrite" {
  name = "fpledge-data-readwrite"
  role = aws_iam_role.captures.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.data.arn, "${aws_s3_bucket.data.arn}/*"]
    }]
  })
}
