terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # After first apply, uncomment and set your bucket/region to persist state:
  # backend "s3" {
  #   bucket = "kbaas-terraform-state"
  #   key    = "kbaas/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "kbaas"
      ManagedBy = "terraform"
    }
  }
}
