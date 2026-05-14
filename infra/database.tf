# ===== RDS Postgres with pgvector =====

resource "random_password" "db_password" {
  length  = 32
  special = false # Keep it simple for connection strings
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.project}-db-subnet" }
}

resource "aws_db_parameter_group" "postgres16" {
  name_prefix = "${var.project}-pg16-"
  family      = "postgres16"

  # pgvector is loaded via CREATE EXTENSION, no parameter needed
  # Tune for small instance
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  parameter {
    name         = "max_connections"
    value        = "50"
    apply_method = "pending-reboot"
  }

  lifecycle { create_before_destroy = true }
}

resource "aws_db_instance" "main" {
  identifier     = "${var.project}-db"
  engine         = "postgres"
  engine_version = "16.4"

  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 100 # Autoscale up to 100GB
  storage_type          = "gp3"

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  storage_encrypted      = true

  # Cost optimization: single-AZ, no read replicas
  multi_az               = false
  publicly_accessible    = false
  skip_final_snapshot    = true # Dev — change for prod
  deletion_protection    = false
  backup_retention_period = 7

  tags = { Name = "${var.project}-db" }
}

# Store DB credentials in Secrets Manager
resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project}/db-credentials"
  recovery_window_in_days = 0 # Allow immediate delete in dev

  tags = { Name = "${var.project}-db-creds" }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = var.db_name
    username = var.db_username
    password = random_password.db_password.result
    url      = "postgresql+asyncpg://${var.db_username}:${random_password.db_password.result}@${aws_db_instance.main.address}:${aws_db_instance.main.port}/${var.db_name}"
  })
}
