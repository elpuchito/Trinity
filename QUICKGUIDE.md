# Quick Start — 60 Seconds

## Prerequisites

- **Docker Desktop** (or Docker + Docker Compose v2)
- **Google Gemini API Key** — [Get one here](https://aistudio.google.com/apikey)

## Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd triageforge

# 2. Configure environment
cp .env.example .env
```

Open `.env` and paste your **Google API Key**:
```
GOOGLE_API_KEY=your-actual-gemini-api-key
```

```bash
# 3. Launch everything
docker compose up --build -d
```

> ⏱️ **First run takes ~3-4 minutes** (Docker image build + pip install + RAG indexing).
> Subsequent starts take ~15 seconds.

## Access

| Service | URL | Description |
|---|---|---|
| 🖥️ **Frontend** | [localhost:3000](http://localhost:3000) | Dashboard + incident management |
| 🔌 **Backend API** | [localhost:8000](http://localhost:8000) | REST API |
| 📋 **Swagger Docs** | [localhost:8000/docs](http://localhost:8000/docs) | Interactive API documentation |
| 📊 **Grafana** | [localhost:3001](http://localhost:3001) | Observability dashboards |
| 📈 **Prometheus** | [localhost:9090](http://localhost:9090) | Metrics explorer |

## Try It

1. Open **http://localhost:3000**
2. Click **"Report Incident"** in the sidebar
3. Fill in:
   - **Title**: `Payment gateway timeout during checkout`
   - **Description**: `Customers are seeing 504 errors when trying to complete purchases. Stripe webhook logs show timeout after 30s. Multiple reports in the last 15 minutes. Affecting all payment methods.`
   - **Your Name**: anything
   - **Your Email**: anything
4. Click **Submit**
5. **Watch the magic** — the pipeline animation shows each agent processing in real-time
6. After ~15 seconds, the full triage report appears with:
   - Root cause hypothesis (based on Saleor codebase search)
   - Runbook steps (from documentation RAG)
   - Severity assignment (P1–P4)
   - Team routing
   - Auto-generated ticket + notifications

## Verify Observability

1. Open **http://localhost:3001** (Grafana)
2. Navigate to **Dashboards → TriageForge**
3. See real-time metrics: pipeline latency, severity distribution, guardrails

## Stopping

```bash
docker compose down          # Stop services
docker compose down -v       # Stop + delete data volumes
```

## Troubleshooting

| Issue | Fix |
|---|---|
| `GOOGLE_API_KEY` error | Verify your key is in `.env` and has Gemini API access |
| Slow first start | Normal — building Docker images + installing ~40 Python packages |
| ChromaDB connection error | Wait 30s after `docker compose up`, then refresh |
| Port conflict | Check nothing else is using ports 3000, 3001, 8000, 9090 |
