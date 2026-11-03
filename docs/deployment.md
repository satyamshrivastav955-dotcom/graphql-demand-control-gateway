# Deployment Guide: GraphQL Demand Control Gateway

**Status: Reference implementation tested in CI; ready for controlled self-hosted deployment.**
This document outlines the deployment architecture, verification evidence, local verification steps, security controls, and a complete handoff guide for hosting the **GraphQL Demand Control Gateway**.

---

## 1. Security Architecture & Threat Boundary

The deployment follows a layered defence-in-depth model:

```
Internet (Clients / Operators)
               │
               ▼  (Ports 80 / 443 - Public)
┌─────────────────────────────────────────────────────────────┐
│  Caddy Reverse Proxy (deploy/Caddyfile)                     │
│  - Automatic TLS (Let's Encrypt / ZeroSSL)                  │
│  - HSTS, X-Content-Type-Options, Strict Referrer Policy     │
│  - Re-writes X-Forwarded-For with true client remote IP     │
└──────────────────────────────┬──────────────────────────────┘
                               │  (Internal Docker Network)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Nginx Web Server & Static Host (docker/nginx.conf)         │
│  - Serves compiled React dashboard (non-root UID 101)       │
│  - Enforces Content Security Policy (CSP: script-src 'self')│
│  - Rate-limits /api/* and /graphql-proxy per client IP      │
│  - Replaces X-Forwarded-For before forwarding to backend    │
└──────────────────────────────┬──────────────────────────────┘
                               │  (Internal Docker Network: port 8000)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Security Gateway (docker/backend.Dockerfile)       │
│  - AST parsing, token budget, saturating fragment expansion │
│  - Hybrid rule + calibrated ML risk scoring                 │
│  - Policy decision: ALLOW / THROTTLE / BLOCK                │
│  - Audit events written to persistent SQLite volume         │
│  - Runs as non-root user (UID 10001)                        │
└──────────────────────────────┬──────────────────────────────┘
                               │  (Internal Docker Network: port 8001)
                               ▼  [BLOCK: never forwarded]
┌─────────────────────────────────────────────────────────────┐
│  Protected Upstream GraphQL API (demo/upstream)             │
│  - Completely isolated from host and public internet        │
│  - Only receives verified, policy-allowed operations        │
└─────────────────────────────────────────────────────────────┘
```

### Endpoint Exposure Matrix

| Endpoint | Access Level | Protection & Verification Controls |
|---|---|---|
| `POST /graphql-proxy` | Public / Clients | Requires `X-API-Key` if `SENTINEL_GATEWAY_KEYS` is set; hard limits, per-IP rate limit, per-client THROTTLE quota, body size limit; `BLOCK` never forwards. |
| `GET /api/events`, `/api/events/{id}` | **Sensitive (Operator only)** | Constant-time Bearer token authentication (`SENTINEL_API_TOKEN`); 10 failed attempts trigger a 5-minute IP lockout. |
| `GET /api/metrics`, `/api/live` | **Sensitive (Operator only)** | Bearer token; SSE stream connections strictly capped (max 5 concurrent). |
| `GET /api/config` | **Sensitive (Operator only)** | Bearer token; prevents attackers from probing exact rule limits and upstream host. |
| `POST /api/analyze` | **Sensitive (Operator only)** | Bearer token; rate-limited dry-run analysis oracle. |
| `GET /api/ready` | Public / Health check | Returns `{"status":"ready"}` only without token; upstream reachability probe requires token. |
| `GET /api/health`, `/api/evaluation` | Public | Liveness check and static benchmark report; harmless. |

---

## 2. Verification Status & CI Evidence

To ensure complete transparency, repository components are verified across three distinct operational tiers:

| Component / Layer | Status | Verification Evidence |
|---|---|---|
| **Backend Test Suite** | **Verified (100% Pass)** | 126 unit, integration, and security tests passing locally and in CI (`pytest -q`). |
| **Backend Code Quality** | **Verified (Clean)** | Ruff linter and code formatting passing with zero warnings (`ruff check .`). |
| **Dashboard Test Suite** | **Verified (100% Pass)** | 62 Vitest tests passing (`npm test` in `dashboard/`), covering a11y, auth, event tables, and shadow mode. |
| **Dashboard Typecheck & Build** | **Verified (Clean)** | TypeScript strict check (`npx tsc --noEmit`) and Vite production bundle build succeed with 0 errors. |
| **Dependency Audits** | **Verified (0 CVEs)** | `npm audit` in `dashboard/` reports 0 vulnerabilities; `backend/requirements.txt` dependencies audited. |
| **Linux Docker Stack (CI)** | **Verified in CI** | **GitHub Actions Run 41049613905 (Run #25, Commit `c8affa5b`)**: `docker compose build`, container startup with health checks (`docker compose up -d --wait`), and automated smoke tests passed completely. |
| **Compose Configuration Syntax** | **Verified** | `docker compose config -q` and production overlay syntax verified locally on Windows. |
| **Local Windows Docker Daemon** | **Outstanding** | Docker Desktop client v29.8.2 is installed; local execution is pending starting the Windows Docker Desktop daemon service (`npipe:////./pipe/dockerDesktopLinuxEngine`). |
| **Caddy TLS Overlay with Live DNS** | **Pending Host** | Production Caddyfile reviewed and syntactically valid; live automated TLS issuance requires deployment to a VPS with an active DNS `A` record. |
| **Public Production Deployment** | **Not Deployed** | No public VPS has been provisioned; no live public URL exists. |

---

## 3. Local Verification Guide

### Prerequisites
- Python 3.12+ with `pip`
- Node.js 20+ with `npm`
- (Optional for container testing) Docker Compose v2 with daemon running

### A. Non-Container Local Verification (PowerShell or Bash)

This workflow runs the entire gateway stack, dashboard, and demo upstream natively:

```powershell
# 1. Clone the repository
git clone https://github.com/satyamshrivastav955-dotcom/graphql-demand-control-gateway.git
cd graphql-demand-control-gateway

# 2. Install backend dependencies
pip install -r backend/requirements.txt

# 3. Start development stack
# Builds the dashboard, starts demo upstream (:8001) and gateway (:8000), and prints a session token
python scripts/dev.py
```

Open `http://127.0.0.1:8000` in your browser. The landing page is at `/`, and the operator console is at `/app`.

In a separate terminal, run the automated end-to-end check:
```powershell
# In PowerShell:
$env:SENTINEL_API_TOKEN = "<token-printed-by-dev.py>"
python scripts/e2e_check.py
```

### B. Local Docker Compose Verification (Windows PowerShell)

When Docker Desktop is running:

```powershell
# 1. Create environment file if missing
if (-not (Test-Path .env)) {
    $token = python -c "import secrets; print(secrets.token_urlsafe(32))"
    (Get-Content .env.example) -replace 'SENTINEL_API_TOKEN=', "SENTINEL_API_TOKEN=$token" | Set-Content .env
}

# 2. Validate configuration syntax
docker compose config -q

# 3. Build and launch services with health checks
docker compose build
docker compose up -d --wait
docker compose ps

# 4. Verify public health
Invoke-RestMethod -Uri "http://localhost:8080/api/health"

# 5. Verify protected management endpoint returns 401 without token
try {
    Invoke-RestMethod -Uri "http://localhost:8080/api/events"
} catch {
    Write-Host "Correctly rejected unauthenticated request: $($_.Exception.Response.StatusCode)"
}

# 6. Verify legitimate GraphQL query is forwarded (ALLOW)
$body = @{ query = "{ users(first: 2) { name } }" } | ConvertTo-Json
$response = Invoke-RestMethod -Uri "http://localhost:8080/graphql-proxy" -Method Post -Body $body -ContentType "application/json"
$response.extensions.security

# 7. Check container identity (must be non-root UID 10001)
docker compose exec backend id

# 8. Clean shutdown (preserving named persistent volume)
docker compose down
```

> [!CAUTION]
> Never execute `docker compose down -v` in production or during normal maintenance. The `-v` flag deletes the named persistent volume (`sentinel-data`), destroying the SQLite security audit log.

---

## 4. Production Deployment on Linux VPS

### Recommended Architecture: Single Linux VPS
The single-node Compose stack (`deploy/docker-compose.prod.yml`) is the most robust and cost-effective deployment target because:
1. It avoids multi-node distributed state synchronization (rate limiters and behavioral counters currently run in-memory per gateway process).
2. It persists the SQLite audit database safely in a Docker named volume (`sentinel-data`).
3. Caddy automatically handles Let's Encrypt TLS certificate provisioning and renewals.

### Step 1: VPS Host Prerequisites
- OS: Ubuntu 24.04 LTS or Debian 12
- Hardware: Minimum 2 vCPU, 2 GB RAM (accommodates FastAPI + scikit-learn model in memory + Nginx + Caddy).
- Open ports in firewall: `22` (SSH), `80` (HTTP), `443` (HTTPS). Ensure internal ports (`8000`, `8001`, `8080`) are **never** opened to the public.
- DNS: A DNS `A` record pointing your domain (e.g., `gateway.example.com`) to the VPS IPv4 address.

### Step 2: Clone and Configure Environment
On your VPS terminal:
```bash
# Clone the repository
git clone https://github.com/satyamshrivastav955-dotcom/graphql-demand-control-gateway.git
cd graphql-demand-control-gateway

# Generate secure tokens
ADMIN_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
GATEWAY_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Create .env from template
cp .env.example .env
```

Edit `.env` to configure production parameters:
```dotenv
SENTINEL_DOMAIN=gateway.example.com
SENTINEL_API_TOKEN=<paste-ADMIN_TOKEN>
SENTINEL_GATEWAY_KEYS=<paste-GATEWAY_KEY>
SENTINEL_CORS_ORIGINS=https://gateway.example.com
SENTINEL_TRUST_PROXY_HEADERS=true
SENTINEL_ENFORCEMENT=enforce
```

### Step 3: Launch Production Stack
```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build --wait
```

### Step 4: Validate Production Deployment
```bash
# 1. Health check over HTTPS
curl -i https://gateway.example.com/api/health

# 2. Confirm management API rejects unauthenticated requests (HTTP 401)
curl -i https://gateway.example.com/api/events

# 3. Confirm management API accepts valid Bearer token
curl -i -H "Authorization: Bearer <ADMIN_TOKEN>" https://gateway.example.com/api/config

# 4. Confirm gateway proxy requires client key
curl -i -X POST https://gateway.example.com/graphql-proxy \
  -H "Content-Type: application/json" \
  -d '{"query":"{ users { id } }"}'  # Expected 401 Unauthorized

# 5. Confirm gateway proxy processes legitimate request with client key
curl -i -X POST https://gateway.example.com/graphql-proxy \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <GATEWAY_KEY>" \
  -d '{"query":"{ users(first: 2) { name } }"}'  # Expected 200 ALLOW
```

---

## 5. Maintenance, Backup & Operations

### SQLite Audit Log Backup
The security events database is stored inside the named Docker volume `sentinel-data` at `/app/backend/storage/sentinel.db`.

To create an online backup without stopping containers:
```bash
# Snapshot the SQLite volume into a compressed tar archive
docker run --rm \
  -v sentinel-data:/data:ro \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/sentinel-backup-$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
```

To restore from a backup:
```bash
docker compose down
docker run --rm \
  -v sentinel-data:/data \
  -v $(pwd)/backups:/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/<backup-filename>.tar.gz -C /data"
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
```

### Management Token Rotation
To rotate the operator management token:
1. Generate a new secret: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Update `SENTINEL_API_TOKEN` in `.env`.
3. Apply changes with zero downtime to other services:
   ```bash
   docker compose up -d backend
   ```

### Application Upgrades
```bash
git pull origin main
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build --wait
```

---

## 6. Hosting Evaluation & Recommendations

| Option | Architecture Fit | Estimated Cost (2026) | Trade-offs & Limitations |
|---|---|---|---|
| **Hetzner Cloud CX22 / CX32** *(Recommended)* | **Native** (Full Compose + Caddy + Named Volume) | **€3.79 – €7.00 / month** | Full root control, persistent NVMe storage, unmetered 20TB traffic, handles scikit-learn memory footprint with headroom. |
| **DigitalOcean Basic Droplet (2GB)** | **Native** (Full Compose + Caddy + Named Volume) | **$12.00 / month** | Standard worldwide cloud availability, one-click Docker droplet, predictable billing. |
| **Render / Fly.io Container Apps** | Partial (Requires converting Compose to separate services) | Free tier sleeps on idle; **~$7–$15 / mo** for persistent disks | Free tiers wipe local SQLite storage on container restart/sleep; multi-container networking requires complex per-service configuration. |
| **Static Portfolio Preview (Vercel / GitHub Pages)** | Frontend Only | **$0.00 (Free)** | Excellent for portfolio demonstration of the React UI using recorded offline sample replays; **cannot** run the live FastAPI gateway or execute real GraphQL proxying. |

### Privacy & Data Retention Notice for Public Demos
When hosting a public demonstration:
1. Any query submitted through `/graphql-proxy` records the operation text, execution metadata, and client IP in SQLite.
2. Ensure `storage.max_events` is bounded (default: 5,000 events) so historical data automatically rolls off.
3. Provide a clear notice on the landing page stating that submitted operations are logged for security evaluation purposes.
