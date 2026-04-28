terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
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

# Random suffix to make Cognito domain globally unique
resource "random_id" "suffix" {
  byte_length = 4
}

# ── Cognito ────────────────────────────────────────────────────────────────────

resource "aws_cognito_user_pool" "games" {
  name = "games-users"

  password_policy {
    minimum_length    = 8
    require_uppercase = false
    require_symbols   = false
    require_numbers   = false
  }

  auto_verified_attributes = ["email"]

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_user_pool_domain" "games" {
  domain       = "games-${random_id.suffix.hex}"
  user_pool_id = aws_cognito_user_pool.games.id
}

resource "aws_cognito_user_pool_client" "games" {
  name         = "games-client"
  user_pool_id = aws_cognito_user_pool.games.id

  generate_secret = true

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true
  supported_identity_providers         = ["COGNITO"]

  callback_urls = ["http://${aws_eip.games_server.public_ip}/callback"]
  logout_urls   = ["http://${aws_eip.games_server.public_ip}/"]

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  access_token_validity  = 8
  id_token_validity      = 8
  refresh_token_validity = 30
}

# ── EC2 ───────────────────────────────────────────────────────────────────────

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
    yum install -y python3 git
    mkdir -p /opt/games
  EOF
}

resource "aws_eip" "games_server" {
  instance = aws_instance.games_server.id
  domain   = "vpc"
}
