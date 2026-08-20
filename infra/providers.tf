# The fpledge AWS stack, as code.
#
# WHAT TERRAFORM IS, IN ONE PARAGRAPH. You declare the infrastructure you want in these files;
# Terraform compares that declaration against what actually exists (via a STATE file mapping
# each resource block to a real AWS resource ID) and computes a diff — `terraform plan`. Nothing
# changes until `terraform apply` executes that diff. So infrastructure gets what code has had
# all along: review before change, reproducibility, and an authoritative answer to "what exactly
# is deployed?" that is not a pile of shell history.
#
# WHY THIS EXISTS HERE. Everything in this directory was first provisioned by hand with the AWS
# CLI on 2026-08-20 — three Lambdas, two roles, an API, two schedules, the bucket. It worked,
# and it was archaeology waiting to happen: the only records were OPERATIONS.md prose and shell
# history on one machine. These files ADOPT that existing infrastructure via the import blocks
# in imports.tf rather than recreating it; the definition of done was `terraform plan` printing
# "No changes" against the live account.
#
# RUNNING IT:   cd infra && AWS_PROFILE=admin terraform init && terraform plan
# The admin profile, because Terraform must read and manage IAM roles and API Gateway, which the
# scoped fpledge-ci user deliberately cannot.
#
# STATE IS LOCAL AND GITIGNORED. terraform.tfstate maps config to real resource IDs and carries
# resource attributes — treat it like a credential-adjacent file, not source code. For a solo
# project local state is a reasonable trade; the moment a second machine or CI needs to run this,
# move it to the S3 backend (the bucket already exists) with native lockfile locking.

terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  # Credentials come from AWS_PROFILE / the environment, never from these files.
}

locals {
  account_id = "546712138633"
  bucket     = "fpledge-data-546712138633"
}
