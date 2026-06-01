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

# ── SSM Parameter Store ────────────────────────────────────────────────────────

resource "aws_ssm_parameter" "openai_key" {
  name        = "/games/openai-key"
  type        = "SecureString"
  value       = "REPLACE_ME"
  description = "OpenAI API key for image generation"

  lifecycle {
    ignore_changes = [value]
  }
}

# ── IAM role for EC2 ───────────────────────────────────────────────────────────

resource "aws_iam_role" "games_server" {
  name = "games-server-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "games_server_secrets" {
  name = "games-server-secrets"
  role = aws_iam_role.games_server.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = [aws_ssm_parameter.openai_key.arn]
    }]
  })
}

resource "aws_iam_instance_profile" "games_server" {
  name = "games-server-profile"
  role = aws_iam_role.games_server.name
}

# ── EC2 ───────────────────────────────────────────────────────────────────────

resource "aws_security_group" "games_server" {
  name        = "games-server"
  description = "Games server"

  ingress {
    from_port   = 40285
    to_port     = 40285
    protocol    = "tcp"
    cidr_blocks = [
      "213.152.255.113/32", # work
      "0.0.0.0/0",          # remove once home IP added
    ]
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
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = "t3.nano"
  key_name                    = aws_key_pair.games_server.key_name
  vpc_security_group_ids      = [aws_security_group.games_server.id]
  iam_instance_profile        = aws_iam_instance_profile.games_server.name

  tags = {
    Name = "games-server"
  }

  user_data = <<-EOF
    #!/bin/bash
    yum update -y
    yum install -y python3 git python3-pip
    pip3 install boto3
    mkdir -p /opt/games
  EOF

  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_eip" "games_server" {
  instance = aws_instance.games_server.id
  domain   = "vpc"
}
