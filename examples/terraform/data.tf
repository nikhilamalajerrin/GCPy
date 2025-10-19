terraform {
  required_version = ">= 0.14.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"  # Compatible with v0.14.7
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_vpc" "default" {
  default = true
}


