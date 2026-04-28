output "public_ip" {
  value = aws_eip.games_server.public_ip
}

output "ssh_command" {
  value = "ssh -i ~/.ssh/games-server.pem ec2-user@${aws_eip.games_server.public_ip}"
}

output "site_url" {
  value = "http://${aws_eip.games_server.public_ip}"
}
