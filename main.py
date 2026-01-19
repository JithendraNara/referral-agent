import json
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI

# Import configuration (initializes Firebase)
from config import GOOGLE_API_KEY, db

# Import our custom modules
from storage import get_active_targets, is_job_seen, save_job
from agent import find_jobs
from notifier import send_all_notifications
from models import JobCheckResult, JobListing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Referral Agent API",
    description="AI-powered job monitoring agent that tracks career pages and notifies you of new opportunities",
    version="2.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# Pydantic models for API
class TargetCreate(BaseModel):
    company_name: str
    careers_url: str
    role_keyword: str
    active: bool = True


class TargetUpdate(BaseModel):
    company_name: Optional[str] = None
    careers_url: Optional[str] = None
    role_keyword: Optional[str] = None
    active: Optional[bool] = None


def get_llm():
    """Initialize and return the Gemini LLM instance."""
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY not configured")
    
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0.0,  # Deterministic output for consistent JSON
        google_api_key=GOOGLE_API_KEY
    )


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the frontend dashboard."""
    with open("templates/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/status")
def api_status():
    """API status endpoint."""
    return {
        "status": "ok", 
        "message": "Referral Agent API is running",
        "version": "2.0.0"
    }


@app.get("/health")
def detailed_health_check():
    """Detailed health check for monitoring."""
    try:
        targets = get_active_targets()
        firestore_ok = True
        target_count = len(targets)
    except Exception as e:
        firestore_ok = False
        target_count = 0
        logger.error(f"Firestore health check failed: {e}")
    
    llm_configured = bool(GOOGLE_API_KEY)
    
    return {
        "status": "healthy" if (firestore_ok and llm_configured) else "degraded",
        "checks": {
            "firestore": "ok" if firestore_ok else "error",
            "llm_configured": "ok" if llm_configured else "missing",
            "active_targets": target_count
        }
    }


@app.post("/check-jobs", response_model=JobCheckResult)
def check_jobs_endpoint():
    """
    Main workflow:
    1. Fetch active targets from Firestore.
    2. Scrape each target for jobs using the CrewAI agent.
    3. Filter out jobs we've already seen.
    4. Save new jobs to Firestore.
    5. Send notifications via all configured channels.
    """
    errors = []
    
    try:
        llm = get_llm()
        targets = get_active_targets()
        new_jobs_found = []
        
        logger.info(f"🚀 Starting job check for {len(targets)} active targets")

        for target in targets:
            careers_url = target.get('careers_url')
            role_keyword = target.get('role_keyword', 'Software Engineer')
            company_name = target.get('company_name', 'Unknown Company')
            
            try:
                # 1. Run the agent (now returns parsed list directly)
                jobs = find_jobs(target, llm)
                
                # 2. Process each job
                for job in jobs:
                    job_url = job.get('url')
                    if not job_url:
                        continue
                        
                    # Handle relative URLs
                    if job_url.startswith('/'):
                        job_url = urljoin(careers_url, job_url)
                        job['url'] = job_url
                    
                    # 3. Check & Save
                    if not is_job_seen(job_url):
                        job['company_name'] = company_name
                        job['careers_url'] = careers_url
                        job['role_keyword'] = role_keyword
                        
                        save_job(job)
                        new_jobs_found.append(job)
                        logger.info(f"✅ New job: {job.get('title')} at {company_name}")
                    else:
                        logger.debug(f"Already seen: {job_url}")
                        
            except Exception as e:
                error_msg = f"Error processing {company_name}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue

        # 4. Send notifications
        if new_jobs_found:
            send_all_notifications(new_jobs_found)
        
        logger.info(f"✨ Job check complete. Found {len(new_jobs_found)} new jobs.")
        
        return JobCheckResult(
            status="success",
            targets_checked=len(targets),
            new_jobs_count=len(new_jobs_found),
            new_jobs=[JobListing(**j) for j in new_jobs_found],
            errors=errors,
            message=f"Found {len(new_jobs_found)} new jobs" if new_jobs_found else "No new jobs found"
        )

    except Exception as e:
        logger.error(f"Critical error in check-jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# API Endpoints for Frontend Dashboard
# ============================================================================

@app.get("/api/targets")
def list_targets():
    """Get all targets from Firestore."""
    try:
        targets_ref = db.collection('targets')
        docs = targets_ref.stream()
        
        targets = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            targets.append(data)
        
        return targets
    except Exception as e:
        logger.error(f"Error listing targets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/targets")
def create_target(target: TargetCreate):
    """Create a new target in Firestore."""
    try:
        targets_ref = db.collection('targets')
        doc_ref = targets_ref.add(target.model_dump())
        
        return {"id": doc_ref[1].id, **target.model_dump()}
    except Exception as e:
        logger.error(f"Error creating target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/targets/{target_id}")
def update_target(target_id: str, target: TargetCreate):
    """Update an existing target."""
    try:
        doc_ref = db.collection('targets').document(target_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Target not found")
        
        doc_ref.update(target.model_dump())
        return {"id": target_id, **target.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/targets/{target_id}")
def patch_target(target_id: str, target: TargetUpdate):
    """Partially update a target (e.g., toggle active status)."""
    try:
        doc_ref = db.collection('targets').document(target_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Target not found")
        
        # Only update provided fields
        update_data = {k: v for k, v in target.model_dump().items() if v is not None}
        doc_ref.update(update_data)
        
        return {"id": target_id, **update_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error patching target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/targets/{target_id}")
def delete_target(target_id: str):
    """Delete a target from Firestore."""
    try:
        doc_ref = db.collection('targets').document(target_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Target not found")
        
        doc_ref.delete()
        return {"message": "Target deleted", "id": target_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
def list_jobs(limit: int = 100):
    """Get recent jobs from Firestore."""
    try:
        jobs_ref = db.collection('job_history')
        docs = jobs_ref.order_by('found_at', direction='DESCENDING').limit(limit).stream()
        
        jobs = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            jobs.append(data)
        
        return jobs
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a job from history."""
    try:
        doc_ref = db.collection('job_history').document(job_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Job not found")
        
        doc_ref.delete()
        return {"message": "Job deleted", "id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        raise HTTPException(status_code=500, detail=str(e))
