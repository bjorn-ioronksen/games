output "public_ip" {
  value = aws_eip.games_server.public_ip
}

output "ssh_command" {
  value = "ssh -i ~/.ssh/games-server.pem -p 40285 ec2-user@${aws_eip.games_server.public_ip}"
}

output "site_url" {
  value = "https://${aws_eip.games_server.public_ip}.nip.io"
}

output "openai_secret_update_command" {
  description = "Run this to set your OpenAI key in SSM"
  value       = "aws ssm put-parameter --name /games/openai-key --value 'sk-...' --type SecureString --overwrite"
}
