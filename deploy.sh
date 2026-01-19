#!/bin/bash
# Deployment script for Referral Agent to Google Cloud Run
# Project: agent-portfolio (950187173455)

set -e  # Exit on error

PROJECT_ID="agent-portfolio"
REGION="us-central1"
SERVICE_NAME="referral-agent"
SCHEDULER_SA="scheduler-invoker"

echo "🚀 Deploying Referral Agent to GCP..."
echo "   Project: $PROJECT_ID"
echo "   Region:  $REGION"
echo ""

# Set project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "📦 Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com

# Deploy to Cloud Run
echo "🐳 Building and deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --no-allow-unauthenticated \
  --memory 512Mi \
  --timeout 300 \
  --set-env-vars "GOOGLE_API_KEY=${GOOGLE_API_KEY}"

# Get the service URL
CLOUD_RUN_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')
echo "✅ Deployed to: $CLOUD_RUN_URL"

# Check if service account exists
if ! gcloud iam service-accounts describe "${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" &>/dev/null; then
  echo "🔐 Creating service account for Cloud Scheduler..."
  gcloud iam service-accounts create $SCHEDULER_SA \
    --display-name "Cloud Scheduler Invoker"
fi

# Grant invoker permission
echo "🔑 Granting Cloud Run invoker permission..."
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --region $REGION \
  --member "serviceAccount:${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/run.invoker"

# Create or update scheduler job
echo "⏰ Setting up Cloud Scheduler (9 AM daily)..."
if gcloud scheduler jobs describe referral-agent-daily --location $REGION &>/dev/null; then
  echo "   Updating existing scheduler job..."
  gcloud scheduler jobs update http referral-agent-daily \
    --location $REGION \
    --schedule "0 9 * * *" \
    --time-zone "America/Chicago" \
    --uri "${CLOUD_RUN_URL}/check-jobs" \
    --http-method POST \
    --oidc-service-account-email "${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
else
  echo "   Creating new scheduler job..."
  gcloud scheduler jobs create http referral-agent-daily \
    --location $REGION \
    --schedule "0 9 * * *" \
    --time-zone "America/Chicago" \
    --uri "${CLOUD_RUN_URL}/check-jobs" \
    --http-method POST \
    --oidc-service-account-email "${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
fi

echo ""
echo "✨ Deployment complete!"
echo ""
echo "📋 Summary:"
echo "   Service URL:  $CLOUD_RUN_URL"
echo "   Health Check: $CLOUD_RUN_URL/health"
echo "   Schedule:     Daily at 9 AM (America/Chicago)"
echo ""
echo "🧪 Test commands:"
echo "   # Manual trigger:"
echo "   gcloud scheduler jobs run referral-agent-daily --location $REGION"
echo ""
echo "   # View logs:"
echo "   gcloud run logs read --service $SERVICE_NAME --region $REGION"
