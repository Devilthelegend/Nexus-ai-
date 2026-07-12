terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Configure a remote backend for shared state in real environments.
  # backend "s3" {
  #   bucket         = "nexusai-tfstate"
  #   key            = "nexusai/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "nexusai-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "nexusai"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
