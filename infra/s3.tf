# The data bucket: the single most irreplaceable thing in this stack.
#
# raw/      immutable captures — the FPL API, odds API and news feeds serve only the present,
#           so anything lost here cannot be bought back at any price
# serving/  the artifacts the API reads — regenerable by re-running a capture or precompute

resource "aws_s3_bucket" "data" {
  bucket = local.bucket

  # Terraform's default on destroy is to DELETE the bucket. `prevent_destroy` makes any plan
  # that would remove it fail loudly instead — for a bucket holding a season of unrepeatable
  # captures, "you must edit the code twice to lose this" is the right amount of friction.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled" # a bad sync must be recoverable; without this it is terminal
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
