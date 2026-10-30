# InvoiceFlow: Deployment Architecture & Cloud Runbook

This document details the deployment procedures, continuous delivery pipeline, database migration policies, rollback runbooks, and cloud-agnostic deployment mappings (AWS and Google Cloud Platform).

---

## 1. AWS Production Deployment Architecture

InvoiceFlow is architected for zero-downtime rolling deployments on AWS in the **ap-south-1** (Mumbai) region:

```mermaid
flowchart TD
    CF[AWS CloudFront<br/>OAC + Security Headers Policy] --> S3_WEB[(Private S3<br/>React Static Assets)]
    CF -- API Requests /api/* --> ALB[Application Load Balancer<br/>HTTPS TLS 1.3 ACM]
    ALB --> TG[Target Group<br/>Health: /api/health]
    
    subgraph ECS Fargate Cluster
        TG --> API[Service: api<br/>Autoscaling 4-16 tasks]
        W1[Service: worker-extract<br/>Queue: extract]
        W2[Service: worker-general<br/>Queue: ingest, push, notify, maintenance]
        BEAT[Service: beat<br/>Desired: 1 single-instance]
    end
    
    subgraph Data Tier (Private Subnets)
        API & W1 & W2 --> RDS[(Amazon RDS PostgreSQL 16<br/>Multi-AZ + KMS)]
        API & W1 & W2 --> REDIS[(Amazon ElastiCache Redis 7<br/>Multi-Node Replication)]
        API & W1 & W2 --> S3[(Amazon S3 Invoices<br/>SSE-KMS + Glacier Lifecycle)]
    end
```

---

## 2. Zero-Downtime Deployment & CI/CD Pipeline

The continuous deployment pipeline (`.github/workflows/ci.yml`) executes:
1. **Quality Gates:** Linting (`ruff`), strict typecheck (`mypy`), unit and security test suites (`pytest`), and the evaluation harness.
2. **Security Scans:** `pip-audit`, `npm audit`, `bandit` SAST, and `gitleaks`.
3. **Container Build & Push:** Builds multi-stage Docker images running as non-root user `appuser` (UID 10001) and pushes to Amazon ECR tagged with the Git commit SHA.
4. **Staging Continuous Deployment:** GitHub Actions assumes an AWS IAM role via OIDC (zero long-lived credentials), triggers an ECS one-off task for `alembic upgrade head`, and performs rolling updates of ECS services.
5. **Manual Production Promotion Gate:** Following staging verification, a designated DevOps lead approves the GitHub Actions production environment deployment.

---

## 3. Database Migration Policy: Expand-and-Contract

To guarantee zero downtime and enable safe rollbacks without database lockouts or broken running tasks, all schema modifications must strictly adhere to the **Expand-and-Contract** pattern:

### 3.1 Phase 1: Expand (Release N)
- Add new columns as **nullable** or with server defaults.
- Create new tables with foreign keys that do not block writes.
- Write application code that writes to both old and new columns, but reads from old columns.
- *Rule:* Never drop, rename, or add non-null columns without defaults in the same release.

### 3.2 Phase 2: Backfill (Background Maintenance)
- Run backfill Celery tasks or batched SQL updates to populate new columns for historical rows.

### 3.3 Phase 3: Switch Reads (Release N+1)
- Deploy application release that reads from new columns.

### 3.4 Phase 4: Contract (Release N+2)
- Safely drop deprecated columns or tables in a separate migration after verifying all services have migrated.

### 3.5 Rollback Procedure
If a deployment fails health checks during an ECS rolling update:
1. ECS deployment circuit breaker automatically triggers and cancels the deployment.
2. Traffic remains routed to healthy tasks running the previous container version.
3. Because the migration was strictly additive (Expand phase), the previous code version continues operating safely without syntax errors or missing column exceptions.
4. If a manual rollback is needed:
   ```bash
   aws ecs update-service \
       --cluster invoiceflow-prod-cluster \
       --service api \
       --task-definition invoiceflow-prod-api:<PREVIOUS_REVISION>
   ```

---

## 4. Multi-Cloud Portability: Deploying to Google Cloud Platform (GCP)

InvoiceFlow is strictly cloud-agnostic. All application components communicate via standard protocols (HTTP, PostgreSQL, Redis, and S3-compatible APIs) reading configuration from standard environment variables injected by the container runtime.

### Component Mapping: AWS to GCP

| Capability | AWS Implementation | GCP Equivalent Mapping | Container Environment Configuration |
| :--- | :--- | :--- | :--- |
| **API Web Service** | ECS Fargate + ALB | **Google Cloud Run** (Fully Managed) | Set `PORT=8000`, minimum 2 instances, max 20 |
| **Extraction Worker** | ECS Fargate (`worker-extract`) | **Google Kubernetes Engine (GKE)** or Compute Engine VM | Run `celery worker -Q extract` |
| **General Worker** | ECS Fargate (`worker-general`) | **GKE** or Compute Engine VM | Run `celery worker -Q ingest,push,notify,maintenance` |
| **Scheduler** | ECS Fargate (`beat`) | **Cloud Run Job** (Cron) or single GKE pod | Run `celery beat` |
| **Relational Database**| RDS PostgreSQL 16 Multi-AZ | **Cloud SQL for PostgreSQL 16** (High Availability) | `DATABASE_URL=postgresql+asyncpg://...` |
| **Task Broker & Cache**| ElastiCache Redis 7 | **Memorystore for Redis** (Standard Tier HA) | `REDIS_URL=rediss://...` |
| **Object Storage** | Amazon S3 | **Google Cloud Storage (GCS)** | Use GCS S3-compatible XML API (`S3_ENDPOINT=https://storage.googleapis.com`) |
| **Web Application** | CloudFront + S3 | **Cloud Storage** bucket + **Cloud CDN** | Configure default index routing and Cloud Armor |
| **WAF & DDoS** | AWS WAFv2 | **Google Cloud Armor** | Pre-configured OWASP Top 10 CRS rules |
| **Secrets Management** | AWS Secrets Manager | **Google Secret Manager** | Mount secrets as environment variables in Cloud Run |

