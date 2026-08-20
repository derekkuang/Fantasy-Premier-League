# The public front door: API Gateway HTTP API -> the fpledge-api Lambda.
#
# WHY A GATEWAY AND NOT A FUNCTION URL. A Function URL with auth NONE and a provably correct
# public-invoke policy 403'd persistently on this account (likely an account-level public-access
# block). API Gateway is the standard front door anyway, and it is what the Vercel frontend's
# NEXT_PUBLIC_API_URL points at — which is why this API's ID appearing in a destroy plan should
# terrify you slightly: replacing it CHANGES THE PUBLIC URL and breaks the deployed site until
# the env var is updated.
#
# The API was created with the CLI's quick-create, which implicitly made the stage, route and
# integration below. Terraform manages them explicitly — implicit resources are exactly the kind
# of thing that gets missed when someone asks "what is deployed?"

resource "aws_apigatewayv2_api" "api" {
  name          = "fpledge-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"] # the API is public and read-only apart from /advise, which is rate-limited in-app
    allow_methods = ["*"] # "OPTIONS" is 7 chars and the field caps members at 6 — hence "*", found the hard way
    allow_headers = ["content-type"]
    max_age       = 86400
  }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "default" {
  api_id = aws_apigatewayv2_api.api.id
  # $default catches every path — FastAPI does the routing, the gateway just forwards. One
  # route means adding an endpoint is a code deploy, never an infrastructure change.
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "apigw-invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*"
}

output "api_url" {
  value       = aws_apigatewayv2_api.api.api_endpoint
  description = "Set this as NEXT_PUBLIC_API_URL on Vercel (and redeploy — the var is baked at build time)."
}
