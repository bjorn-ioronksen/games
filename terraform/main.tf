terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_security_group" "games_server" {
  name        = "games-server"
  description = "Games server"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_key_pair" "games_server" {
  key_name   = "games-server-tf"
  public_key = file(var.public_key_path)
}

resource "aws_instance" "games_server" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t3.micro"
  key_name               = aws_key_pair.games_server.key_name
  vpc_security_group_ids = [aws_security_group.games_server.id]

  tags = {
    Name = "games-server"
  }

  user_data = <<-EOF
    #!/bin/bash
    yum update -y
    yum install -y python3
    mkdir -p /opt/games
  EOF
}

resource "aws_eip" "games_server" {
  instance = aws_instance.games_server.id
  domain   = "vpc"
}
