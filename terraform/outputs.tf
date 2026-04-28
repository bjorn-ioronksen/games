output "public_ip" {
  value = aws_eip.games_server.public_ip
}

output "ssh_command" {
  value = "ssh -i ~/.ssh/games-server.pem ec2-user@${aws_eip.games_server.public_ip}"
}

output "site_url" {
  value = "http://${aws_eip.games_server.public_ip}"
}

output "cognito_domain" {
  value = "https://${aws_cognito_user_pool_domain.games.domain}.auth.${var.region}.amazoncognito.com"
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.games.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.games.id
}

output "cognito_client_secret" {
  value     = aws_cognito_user_pool_client.games.client_secret
  sensitive = true
}

output "config_json" {
  description = "Paste this into config.json on the server (fill in your openai_key)"
  sensitive   = true
  value = jsonencode({
    openai_key            = "<your-openai-key>"
    cognito_domain        = "https://${aws_cognito_user_pool_domain.games.domain}.auth.${var.region}.amazoncognito.com"
    cognito_client_id     = aws_cognito_user_pool_client.games.id
    cognito_client_secret = aws_cognito_user_pool_client.games.client_secret
    cognito_redirect_uri  = "http://${aws_eip.games_server.public_ip}/callback"
    cognito_region        = var.region
  })
}
