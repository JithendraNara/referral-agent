# CI/CD Setup Guide

## Connecting GitHub to Cloud Build

Since Cloud Build requires OAuth authentication with GitHub, you need to complete this step in the Google Cloud Console:

### Step 1: Connect GitHub Repository

1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers?project=agent-portfolio)
2. Click **"Connect Repository"**
3. Select **"GitHub (Cloud Build GitHub App)"**
4. Click **"Continue"**
5. Authenticate with GitHub and authorize Google Cloud Build
6. Select the repository: `JithendraNara/referral-agent`
7. Click **"Connect"**

### Step 2: Create the Trigger

1. After connecting, click **"Create Trigger"**
2. Configure:
   - **Name:** `referral-agent-deploy`
   - **Region:** `global`
   - **Event:** `Push to a branch`
   - **Source:** Select your connected repo
   - **Branch:** `^main$`
   - **Configuration:** `Cloud Build configuration file`
   - **Location:** `cloudbuild.yaml`
3. Click **"Create"**

### Step 3: Test the Pipeline

Make a small change and push:
```bash
git add .
git commit -m "Test CI/CD pipeline"
git push origin main
```

Then check the build status at:
https://console.cloud.google.com/cloud-build/builds?project=agent-portfolio

## Quick Links

- **Cloud Build Triggers:** https://console.cloud.google.com/cloud-build/triggers?project=agent-portfolio
- **Cloud Build History:** https://console.cloud.google.com/cloud-build/builds?project=agent-portfolio
- **Cloud Run Service:** https://console.cloud.google.com/run/detail/us-central1/referral-agent?project=agent-portfolio
- **GitHub Repo:** https://github.com/JithendraNara/referral-agent

## Troubleshooting

### Build fails with permission error
Make sure Cloud Build has the right permissions:
```bash
gcloud projects add-iam-policy-binding agent-portfolio \
  --member="serviceAccount:950187173455@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding agent-portfolio \
  --member="serviceAccount:950187173455@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

### Image not found
Enable Container Registry:
```bash
gcloud services enable containerregistry.googleapis.com --project agent-portfolio
```
