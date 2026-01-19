# Referral Agent 🚀

An AI-powered job monitoring agent that tracks company career pages and notifies you of new opportunities matching your interests.

## Features

- 🤖 **AI-Powered Extraction** - Uses Gemini 1.5 Flash to intelligently parse career pages
- 🔄 **Automatic Deduplication** - Never get notified about the same job twice
- 📧 **Multi-Channel Notifications** - Email, Slack, and Discord support
- ☁️ **Serverless Architecture** - Runs on Google Cloud Run ($0 cost in free tier)
- 🎯 **Dynamic Configuration** - Add/remove companies via Firestore without code changes

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Cloud Scheduler │────▶│  Cloud Run API   │────▶│   Firestore     │
│   (9 AM Daily)  │     │  (FastAPI)       │     │   (Config/DB)   │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │  Email  │  │  Slack  │  │ Discord │
              └─────────┘  └─────────┘  └─────────┘
```

## Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd referral-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Setup Firestore

Create a `targets` collection with documents like:

```json
{
  "company_name": "Tesla",
  "careers_url": "https://www.tesla.com/careers/search/?query=software",
  "role_keyword": "Software Engineer",
  "active": true
}
```

### 4. Run Locally

```bash
uvicorn main:app --reload
```

### 5. Test

```bash
# Health check
curl http://localhost:8000/health

# Trigger job check
curl -X POST http://localhost:8000/check-jobs
```

## Deployment to Cloud Run

### Prerequisites
- Google Cloud SDK installed (`gcloud`)
- Authenticated: `gcloud auth login`

### Deploy Commands

```bash
# Set your project
gcloud config set project agent-portfolio

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com

# Build and deploy to Cloud Run
gcloud run deploy referral-agent \
  --source . \
  --region us-central1 \
  --no-allow-unauthenticated \
  --set-env-vars "GOOGLE_API_KEY=your-gemini-api-key"

# Get the Cloud Run URL
CLOUD_RUN_URL=$(gcloud run services describe referral-agent --region us-central1 --format 'value(status.url)')

# Create a service account for Cloud Scheduler
gcloud iam service-accounts create scheduler-invoker \
  --display-name "Cloud Scheduler Invoker"

# Grant permission to invoke Cloud Run
gcloud run services add-iam-policy-binding referral-agent \
  --region us-central1 \
  --member "serviceAccount:scheduler-invoker@agent-portfolio.iam.gserviceaccount.com" \
  --role "roles/run.invoker"

# Create Cloud Scheduler job (9 AM daily, US Central time)
gcloud scheduler jobs create http referral-agent-daily \
  --location us-central1 \
  --schedule "0 9 * * *" \
  --time-zone "America/Chicago" \
  --uri "${CLOUD_RUN_URL}/check-jobs" \
  --http-method POST \
  --oidc-service-account-email "scheduler-invoker@agent-portfolio.iam.gserviceaccount.com"
```

### Manual Trigger (for testing)
```bash
gcloud scheduler jobs run referral-agent-daily --location us-central1
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Basic health check |
| `/health` | GET | Detailed health check with Firestore status |
| `/check-jobs` | POST | Trigger job scanning workflow |

## Project Structure

```
referral-agent/
├── main.py           # FastAPI entry point
├── config.py         # Environment & Firebase initialization
├── agent.py          # CrewAI job extraction logic
├── storage.py        # Firestore operations
├── notifier.py       # Email/Slack/Discord notifications
├── models.py         # Pydantic data models
├── scraper_utils.py  # Retry logic & rate limiting
├── Dockerfile        # Container configuration
└── requirements.txt  # Python dependencies
```

## License

MIT
