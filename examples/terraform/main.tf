# Your existing data sources (KEEP THESE - from previous message)
data "aws_subnets" "all" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Your instances (GOOD - no changes)
resource "aws_instance" "web_app" {
  ami           = "kk"
  instance_type = "t3.micro"

  root_block_device {
    volume_size = 15
  }
}

# EBS Volumes (GOOD - no changes)
resource "aws_ebs_volume" "storage_option_1" {
  availability_zone = data.aws_availability_zones.available.names[0]
  type              = "io1"
  size              = 15
  iops              = 100
}

resource "aws_ebs_volume" "storage_option_2" {
  availability_zone = data.aws_availability_zones.available.names[0]
  type              = "standard"
  size              = 15
}

# EIP (GOOD - uncommented)
resource "aws_eip" "nat_eip" {
  //vpc = true
}

# NAT Gateway - FIXED!
resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat_eip.id
  subnet_id     = tolist(data.aws_subnets.all.ids)[0]  
}