"""
Referral Agent - Professional FastAPI Application
AI-powered job monitoring with comprehensive API endpoints.
"""
import time
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI

# Import configuration
from config import settings, db

# Import modules
from storage import (
    job_storage, target_storage,
    get_active_targets, is_job_seen, save_job
)
from agent import find_jobs, JobScraperAgent
from notifier import notification_service, send_all_notifications
from models import (
    JobCheckResult, JobListing, JobStatus, JobStatusUpdate,
    TargetCreate, TargetUpdate, StatsResponse, HealthStatus
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get base directory
BASE_DIR = Path(__file__).resolve().parent

# Track uptime
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("🚀 Starting Referral Agent API")
    logger.info(f"   Environment: {settings.APP_ENV}")
    logger.info(f"   LLM configured: {settings.llm_configured}")
    logger.info(f"   Email configured: {settings.email_configured}")
    logger.info(f"   Notification channels: {notification_service.get_configured_channels()}")
    yield
    # Shutdown
    logger.info("👋 Shutting down Referral Agent API")


# Create FastAPI app
app = FastAPI(
    title="Referral Agent API",
    description="AI-powered job monitoring agent that tracks career pages and notifies you of opportunities",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# =============================================================================
# Helper Functions
# =============================================================================

def get_llm():
    """Initialize and return the Gemini LLM instance."""
    if not settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY not configured")
    
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        temperature=0.0,
        google_api_key=settings.GOOGLE_API_KEY
    )


# =============================================================================
# Core Endpoints
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the frontend dashboard."""
    template_path = BASE_DIR / "templates" / "index.html"
    if template_path.exists():
        with open(template_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h1>Referral Agent API</h1><p>API is running. Dashboard not available.</p>"
    )


@app.get("/health", response_model=HealthStatus)
def health_check():
    """Comprehensive health check for monitoring."""
    checks = {}
    status = "healthy"
    
    # Check Firestore
    try:
        targets = get_active_targets()
        checks["firestore"] = {"status": "ok", "active_targets": len(targets)}
    except Exception as e:
        checks["firestore"] = {"status": "error", "message": str(e)}
        status = "degraded"
    
    # Check LLM
    if settings.llm_configured:
        checks["llm"] = {"status": "ok", "model": settings.GEMINI_MODEL}
    else:
        checks["llm"] = {"status": "warning", "message": "API key not configured"}
        status = "degraded"
    
    # Check notifications
    channels = notification_service.get_configured_channels()
    checks["notifications"] = {
        "status": "ok" if channels else "warning",
        "configured_channels": channels
    }
    
    return HealthStatus(
        status=status,
        version="2.0.0",
        uptime_seconds=time.time() - START_TIME,
        checks=checks
    )


@app.get("/api/status")
def api_status():
    """Quick API status check."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "environment": settings.APP_ENV
    }


# =============================================================================
# Job Check Endpoint
# =============================================================================

@app.post("/check-jobs", response_model=JobCheckResult)
def check_jobs_endpoint(background_tasks: BackgroundTasks = None):
    """
    Main job check workflow:
    1. Fetch active targets from Firestore
    2. Scrape each target for jobs
    3. Filter out already-seen jobs
    4. Save new jobs to Firestore
    5. Send notifications
    """
    start_time = time.time()
    errors = []
    
    try:
        llm = get_llm()
        targets = get_active_targets()
        new_jobs_found = []
        
        logger.info(f"🚀 Starting job check for {len(targets)} active targets")
        
        for target in targets:
            careers_url = target.get('careers_url')
            company_name = target.get('company_name', 'Unknown')
            
            try:
                # Run the AI agent
                jobs = find_jobs(target, llm)
                
                # Process each job
                for job in jobs:
                    job_url = job.get('url')
                    if not job_url:
                        continue
                    
                    # Handle relative URLs
                    if job_url.startswith('/'):
                        job_url = urljoin(careers_url, job_url)
                        job['url'] = job_url
                    
                    # Check if already seen
                    if not is_job_seen(job_url):
                        # Enrich job data
                        job['company_name'] = company_name
                        job['careers_url'] = careers_url
                        job['role_keyword'] = target.get('role_keyword')
                        job['status'] = JobStatus.NEW.value
                        
                        save_job(job)
                        new_jobs_found.append(job)
                        logger.info(f"✅ New: {job.get('title')} at {company_name}")
                        
            except Exception as e:
                error_msg = f"Error processing {company_name}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Send notifications
        if new_jobs_found:
            send_all_notifications(new_jobs_found)
        
        duration = time.time() - start_time
        logger.info(f"✨ Job check complete in {duration:.1f}s. Found {len(new_jobs_found)} new jobs.")
        
        return JobCheckResult(
            status="success",
            targets_checked=len(targets),
            new_jobs_count=len(new_jobs_found),
            new_jobs=[JobListing(**j) for j in new_jobs_found],
            errors=errors,
            message=f"Found {len(new_jobs_found)} new jobs" if new_jobs_found else "No new jobs found",
            duration_seconds=round(duration, 2)
        )
        
    except Exception as e:
        logger.error(f"Critical error in check-jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Target Management API
# =============================================================================

@app.get("/api/targets")
def list_targets():
    """Get all targets."""
    try:
        return target_storage.get_all_targets()
    except Exception as e:
        logger.error(f"Error listing targets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/targets/{target_id}")
def get_target(target_id: str):
    """Get a specific target."""
    target = target_storage.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@app.post("/api/targets")
def create_target(target: TargetCreate):
    """Create a new target."""
    try:
        target_id = target_storage.create_target(target.model_dump())
        return {"id": target_id, **target.model_dump()}
    except Exception as e:
        logger.error(f"Error creating target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/targets/{target_id}")
def update_target(target_id: str, target: TargetCreate):
    """Update an existing target (full update)."""
    if not target_storage.get_target(target_id):
        raise HTTPException(status_code=404, detail="Target not found")
    
    try:
        target_storage.update_target(target_id, target.model_dump())
        return {"id": target_id, **target.model_dump()}
    except Exception as e:
        logger.error(f"Error updating target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/targets/{target_id}")
def patch_target(target_id: str, target: TargetUpdate):
    """Partially update a target."""
    if not target_storage.get_target(target_id):
        raise HTTPException(status_code=404, detail="Target not found")
    
    try:
        update_data = {k: v for k, v in target.model_dump().items() if v is not None}
        target_storage.update_target(target_id, update_data)
        return {"id": target_id, **update_data}
    except Exception as e:
        logger.error(f"Error patching target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/targets/{target_id}")
def delete_target(target_id: str):
    """Delete a target."""
    if not target_storage.delete_target(target_id):
        raise HTTPException(status_code=404, detail="Target not found")
    return {"message": "Target deleted", "id": target_id}


# =============================================================================
# Job Management API
# =============================================================================

@app.get("/api/jobs")
def list_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    company: Optional[str] = None,
    status: Optional[str] = None,
    days: Optional[int] = Query(default=None, ge=1, le=365)
):
    """
    Get jobs with filtering and pagination.
    
    - **limit**: Maximum number of jobs to return (1-500)
    - **offset**: Number of jobs to skip
    - **company**: Filter by company name
    - **status**: Filter by job status
    - **days**: Only return jobs from the last N days
    """
    try:
        since = None
        if days:
            since = datetime.utcnow() - timedelta(days=days)
        
        return job_storage.get_jobs(
            limit=limit,
            offset=offset,
            company=company,
            status=status,
            since=since
        )
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Get a specific job."""
    job = job_storage.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.patch("/api/jobs/{job_id}/status")
def update_job_status(job_id: str, update: JobStatusUpdate):
    """Update job status (mark as applied, saved, etc.)."""
    if not job_storage.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    
    success = job_storage.update_job_status(
        job_id=job_id,
        status=update.status,
        notes=update.notes,
        referral_contact=update.referral_contact
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update status")
    
    return {"message": "Status updated", "id": job_id, "status": update.status.value}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a job from history."""
    if not job_storage.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job deleted", "id": job_id}


# =============================================================================
# Analytics & Stats API
# =============================================================================

@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    """Get dashboard statistics."""
    try:
        stats = job_storage.get_stats()
        targets = target_storage.get_active_targets()
        
        return StatsResponse(
            total_jobs=stats['total_jobs'],
            new_today=stats['new_today'],
            active_targets=len(targets),
            jobs_by_company=stats['jobs_by_company'],
            jobs_by_status=stats['jobs_by_status'],
            recent_activity=[]  # TODO: Implement activity log
        )
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/companies")
def list_companies():
    """Get list of unique companies with job counts."""
    try:
        stats = job_storage.get_stats()
        companies = [
            {"name": name, "job_count": count}
            for name, count in stats['jobs_by_company'].items()
        ]
        return sorted(companies, key=lambda x: x['job_count'], reverse=True)
    except Exception as e:
        logger.error(f"Error listing companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Notification API
# =============================================================================

@app.get("/api/notifications/channels")
def get_notification_channels():
    """Get configured notification channels."""
    return {
        "configured": notification_service.get_configured_channels(),
        "available": ["email", "slack", "discord"]
    }


@app.post("/api/notifications/test")
def test_notifications():
    """Send a test notification to all configured channels."""
    test_job = {
        "title": "Test Job - Software Engineer",
        "url": "https://example.com/jobs/test",
        "location": "San Francisco, CA",
        "company_name": "Test Company",
        "posted_date": "Just now"
    }
    
    results = notification_service.send_all([test_job])
    
    return {
        "message": "Test notifications sent",
        "results": {
            name: {"success": r.success, "error": r.error}
            for name, r in results.items()
        }
    }


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.DEBUG
    )
