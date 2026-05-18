# KBaaS — Project Guide

## Architecture

- **Frontend**: Next.js 16 (App Router, TypeScript) — standalone output on ECS Fargate
- **Backend**: Python FastAPI — async, on ECS Fargate
- **Database**: PostgreSQL 16 + pgvector on RDS
- **Storage**: S3 for raw documents
- **CDN**: CloudFront → ALB → ECS (frontend on port 3000, backend on port 8000)
- **Infra**: Terraform in `infra/`

## AWS Resources (us-east-1, account 020529562369)

| Resource | Name/ID |
|----------|---------|
| ECS Cluster | kbaas-cluster |
| Frontend Service | kbaas-frontend |
| Backend Service | kbaas-backend |
| Frontend ECR | 020529562369.dkr.ecr.us-east-1.amazonaws.com/kbaas-backend |
| Backend ECR | 020529562369.dkr.ecr.us-east-1.amazonaws.com/kbaas-frontend |
| CloudFront | E1HPA3NXLSFBKO (dkpc4gx6pbmnd.cloudfront.net) |
| ALB | kbaas-alb-577364062.us-east-1.elb.amazonaws.com |
| RDS | kbaas-db (private subnet, not publicly accessible) |
| S3 | kbaas-docs-020529562369 |

## Routing

- `/*` → frontend (port 3000) — default ALB action
- `/api/*` → backend (port 8000) — ALB listener rule priority 100
- CloudFront → ALB origin, no caching (all forwarded)

## Deployment Playbook

### Standard deploy (code changes only)

```bash
# 1. Auth to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 020529562369.dkr.ecr.us-east-1.amazonaws.com

# 2. Build & push (from repo root) — MUST specify platform on Apple Silicon
docker build --platform linux/amd64 -t 020529562369.dkr.ecr.us-east-1.amazonaws.com/kbaas-backend:latest ./backend
docker build --platform linux/amd64 -t 020529562369.dkr.ecr.us-east-1.amazonaws.com/kbaas-frontend:latest ./frontend
docker push 020529562369.dkr.ecr.us-east-1.amazonaws.com/kbaas-backend:latest
docker push 020529562369.dkr.ecr.us-east-1.amazonaws.com/kbaas-frontend:latest

# 3. Force new deployment (pulls latest image)
aws ecs update-service --cluster kbaas-cluster --service kbaas-backend --force-new-deployment
aws ecs update-service --cluster kbaas-cluster --service kbaas-frontend --force-new-deployment

# 4. Invalidate CloudFront cache
aws cloudfront create-invalidation --distribution-id E1HPA3NXLSFBKO --paths "/*"
```

### Infrastructure changes (task def, env vars, etc.)

```bash
cd infra
terraform apply -var-file=dev.tfvars
```

### Verify deployment

```bash
# Check service status
aws ecs describe-services --cluster kbaas-cluster --services kbaas-frontend kbaas-backend \
  --query 'services[*].{name:serviceName,running:runningCount,desired:desiredCount}' --output table

# Check which task definition is running
aws ecs list-tasks --cluster kbaas-cluster --service-name kbaas-frontend --query 'taskArns[0]' --output text | \
  xargs -I{} aws ecs describe-tasks --cluster kbaas-cluster --tasks {} \
  --query 'tasks[0].{taskDef:taskDefinitionArn,health:healthStatus,imageDigest:containers[0].imageDigest}' --output json

# Check CloudFront
curl -s -o /dev/null -w "%{http_code}" https://dkpc4gx6pbmnd.cloudfront.net/login
curl -s -o /dev/null -w "%{http_code}" https://dkpc4gx6pbmnd.cloudfront.net/api/health
```

## Debugging ECS Issues

### CRITICAL LESSONS LEARNED

#### 1. Stacked deployments cause exponential backoff
Each `force-new-deployment` while a previous deployment is failing creates a NEW deployment.
Failed tasks accumulate across deployments. After ~100+ failures, ECS delays new task launches
by several minutes. The service looks stuck but is just waiting.

**Fix**: Don't keep issuing force-new-deployment. Instead:
```bash
# Delete and recreate the service
aws ecs delete-service --cluster kbaas-cluster --service kbaas-frontend --force
# Wait for INACTIVE
aws ecs wait services-inactive --cluster kbaas-cluster --services kbaas-frontend
# Then remove from Terraform state and re-apply
terraform state rm aws_ecs_service.frontend
terraform apply -var-file=dev.tfvars -target=aws_ecs_service.frontend
```

#### 2. Verify the RUNNING task matches the intended deployment
After force-new-deployment, check that the running task is actually on the new task definition:
```bash
aws ecs list-tasks --cluster kbaas-cluster --service-name kbaas-frontend --query 'taskArns[0]' --output text | \
  xargs -I{} aws ecs describe-tasks --cluster kbaas-cluster --tasks {} \
  --query 'tasks[0].taskDefinitionArn' --output text
```
Old stacked deployments can launch tasks on old task definitions before the new PRIMARY
deployment gets a chance. Always verify after deployment.

#### 3. Next.js in Fargate: HOSTNAME=0.0.0.0 is required
In ECS Fargate with `awsvpc` networking, the container gets an ENI with a specific IP.
Next.js standalone mode may bind to that IP only, making `localhost` unreachable for
container health checks. Set `HOSTNAME=0.0.0.0` in the task definition environment.

#### 4. Use node for health checks, not wget
Alpine-based Node images have busybox wget which can be unreliable. Use node directly:
```
node -e "const http = require('http'); http.get('http://localhost:3000/login', (r) => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"
```

#### 5. Health check timing for cold-start containers
- `startPeriod`: 90s (Next.js SSR compilation on first request takes time on 0.25 vCPU)
- `retries`: 5
- `timeout`: 10s
- `interval`: 30s

#### 6. Docker Desktop proxy broken pipe errors
Docker Desktop's proxy occasionally drops connections during large layer pushes.
Just retry — layers already pushed show "Layer already exists" and eventually all
remaining layers will succeed.

#### 7. RDS parameter groups: static params need pending-reboot
`shared_preload_libraries` and `max_connections` are static parameters.
They require `apply_method = "pending-reboot"` in Terraform. Using "immediate"
causes Terraform apply to fail.

#### 8. Next.js standalone dotfile issue
Shell glob `*` does NOT match dotfiles like `.next`. In Dockerfile, use:
```dockerfile
COPY --from=builder /app/.next/standalone/. ./
```
NOT: `cp -r /app-standalone/* /app/` (skips .next directory)

#### 9. ALWAYS build with --platform linux/amd64
On Apple Silicon Macs, `docker build` defaults to `linux/arm64`. ECS Fargate runs
`linux/amd64`. If you forget `--platform`, the image pushes fine but ECS fails with:
`CannotPullContainerError: image Manifest does not contain descriptor matching platform 'linux/amd64'`

**ALWAYS use:**
```bash
docker build --platform linux/amd64 -t <ecr-url>:latest ./backend
docker build --platform linux/amd64 -t <ecr-url>:latest ./frontend
```

### Quick diagnostic commands

```bash
# Service overview
aws ecs describe-services --cluster kbaas-cluster --services kbaas-frontend kbaas-backend \
  --query 'services[*].{name:serviceName,running:runningCount,desired:desiredCount,deployments:deployments[*].{status:status,failed:failedTasks,taskDef:taskDefinition}}' --output json

# Recent events (what went wrong)
aws ecs describe-services --cluster kbaas-cluster --services kbaas-frontend \
  --query 'services[0].events[0:5]' --output json

# Task health details
aws ecs list-tasks --cluster kbaas-cluster --service-name kbaas-frontend --query 'taskArns[0]' --output text | \
  xargs -I{} aws ecs describe-tasks --cluster kbaas-cluster --tasks {} \
  --query 'tasks[0].{health:healthStatus,status:lastStatus,stop:stoppedReason,containers:containers[0].{health:healthStatus,exit:exitCode,reason:reason}}' --output json

# Container logs (last crashed task)
STREAM=$(aws logs describe-log-streams --log-group-name /ecs/kbaas-frontend \
  --order-by LastEventTime --descending --limit 1 \
  --query 'logStreams[0].logStreamName' --output text)
aws logs get-log-events --log-group-name /ecs/kbaas-frontend \
  --log-stream-name "$STREAM" --limit 50 \
  --query 'events[*].message' --output text

# ALB target health
aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups --names kbaas-frontend-tg --query 'TargetGroups[0].TargetGroupArn' --output text) \
  --output json
```

### AWS Console links for visual monitoring
- ECS Services: https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/kbaas-cluster/services?region=us-east-1
- CloudWatch Logs: https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups
- Target Groups: https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#TargetGroups

## Local Development

```bash
docker compose up -d          # Postgres + MinIO
cd backend && pip install -e . && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Code Patterns

- **API client**: `frontend/src/lib/api-client.ts` — `apiFetch()` and `apiUpload()`
- **Auth**: JWT in localStorage, `Authorization: Bearer <token>` header
- **CORS**: Backend allows origins from `CORS_ORIGINS` env var (comma-separated)
- **API prefix**: All backend routes under `/api/`, health check at `/api/health`
- **Secrets**: Managed via AWS Secrets Manager, injected as ECS task secrets
- **Embeddings**: Local fastembed (BAAI/bge-small-en-v1.5, 384 dims), NOT OpenAI
