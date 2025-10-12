variable "subnet_id" {
  type = string
}

module "subnetwork" {
  source   = "./subnetwork"
  for_each = {
    subnet1 = "subnet-module-1"
    subnet2 = "subnet-module-2"
  }

  subnet_id = each.value
}


resource "aws_network_interface" "module_eip_network_interface" {
  subnet_id   = var.subnet_id
  private_ips = ["10.0.0.1"]
}

resource "aws_eip" "module_nat_eip" {
  network_interface = aws_network_interface.module_eip_network_interface.id
 
}

resource "aws_nat_gateway" "module_nat" {
  subnet_id     = var.subnet_id
  allocation_id = aws_eip.module_nat_eip.id
}