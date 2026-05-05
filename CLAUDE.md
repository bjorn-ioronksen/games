# Games Site — Claude Instructions

## Overview

A password-protected games site running on AWS EC2. Static files + a Python HTTP server with cookie-based session auth and an OpenAI image generation endpoint.

- **Live site**: http://34.242.181.49
- **Server**: EC2 t3.micro, eu-west-1, IP 34.242.181.49
- **SSH**: `ssh -i ~/.ssh/games-server.pem ec2-user@34.242.181.49`
- **GitHub repo**: `bjorn-ioronksen/games` (personal account)

## Deploying

Deployments are triggered by pushing a version tag — they do NOT deploy on every push to main.

```bash
git tag v1.2 && git push origin v1.2
```

GitHub Actions (`.github/workflows/deploy.yml`) will:
1. rsync files to `/opt/games/` on EC2 (excluding `.git`, `.github`, `terraform`, `__pycache__`, `config.json`)
2. Run `sudo systemctl restart games`

Use `gh run list --repo bjorn-ioronksen/games` to check deploy status, or watch it at github.com/bjorn-ioronksen/games/actions.

## Config on the Server

`config.json` is gitignored and must exist on the server at `/opt/games/config.json`. It is never deployed by CI. To update it:

```bash
ssh -i ~/.ssh/games-server.pem ec2-user@34.242.181.49
sudo nano /opt/games/config.json
sudo systemctl restart games
```

Format:
```json
{
  "site_password": "...",
  "openai_key": "sk-..."
}
```

The OpenAI key is optional — if omitted, images fall back to Pollinations.ai then Loremflickr.

## Server Process

Managed by systemd as the `games` service running as root on port 80.

```bash
sudo systemctl status games
sudo systemctl restart games
sudo journalctl -u games -f   # live logs
```

## Terraform

Infrastructure is in `terraform/`. State is local (not in S3). The Terraform config manages EC2, EIP, security groups, IAM role, SSM parameters, and a Cognito user pool (unused — kept for potential future use).

```bash
cd terraform
terraform plan
terraform apply
```

AWS profile: uses default credentials. Region: `eu-west-1`.

To update the OpenAI key in SSM:
```bash
aws ssm put-parameter --name /games/openai-key --value 'sk-...' --type SecureString --overwrite --region eu-west-1
```

## GitHub Accounts

- **Personal** (for this repo): `bjorn-ioronksen` — switch with `gh auth switch --user bjorn-ioronksen`
- **Work**: `robdickinson` — switch with `gh auth switch --user robdickinson`

Always confirm you're on the right account before pushing or managing secrets:
```bash
gh auth status
```

## Secrets in GitHub Actions

Set on the `bjorn-ioronksen/games` repo:
- `EC2_HOST` — the server's public IP (34.242.181.49)
- `EC2_SSH_KEY` — contents of `~/.ssh/games-server.pem`

To update: `gh secret set <NAME> --repo bjorn-ioronksen/games`
