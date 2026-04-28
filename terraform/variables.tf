variable "region" {
  default = "eu-west-1"
}

variable "public_key_path" {
  description = "Path to SSH public key to install on the instance"
  default     = "~/.ssh/games-server.pub"
}
