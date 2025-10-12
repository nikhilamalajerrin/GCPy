provider "aws" {
  region                      = "us-east-1"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  access_key                  = "mock_access_key"
  secret_key                  = "mock_secret_key"
}

data "aws_region" "current" {}

module "network" {
  source   = "./network"
  for_each = {
    subnet1 = "subnet-module-1"
    subnet2 = "subnet-module-2"
  }

  subnet_id = each.value
}



resource "aws_network_interface" "root_eip_network_interface" {
  subnet_id   = "subnet-root"
  private_ips = ["10.0.0.1"]
}

resource "aws_eip" "root_nat_eip" {
  network_interface = aws_network_interface.root_eip_network_interface.id
}

resource "aws_nat_gateway" "root_nat" {
  subnet_id     = "subnet-root"
  allocation_id = aws_eip.root_nat_eip.id
}