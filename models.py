"""
Pydantic models for structured data validation.
Professional-grade type definitions with comprehensive validation.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict
import re


class JobStatus(str, Enum):
    """Status of a job in the tracking workflow."""
    NEW = "new"
    VIEWED = "viewed"
    SAVED = "saved"
    APPLIED = "applied"
    REJECTED = "rejected"
    INTERVIEWING = "interviewing"
    OFFER = "offer"


class ScrapeStrategy(str, Enum):
    """Available scraping strategies."""
    DEFAULT = "default"
    PLAYWRIGHT = "playwright"
    FIRECRAWL = "firecrawl"


class JobListing(BaseModel):
    """Represents a single job listing extracted from a careers page."""
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    
    title: str = Field(..., min_length=1, max_length=500, description="Job title")
    url: str = Field(..., min_length=1, description="URL to the job posting")
    location: str = Field(default="Not specified", description="Job location")
    posted_date: Optional[str] = Field(
        default=None, 
        description="Date the job was posted (e.g., '01/15/2026', 'Jan 15', '2 days ago')"
    )
    
    # Extended fields for richer data
    company_name: Optional[str] = None
    department: Optional[str] = None
    employment_type: Optional[str] = None
    salary_range: Optional[str] = None
    description_snippet: Optional[str] = None
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL is not button text like 'Apply Now'."""
        invalid_patterns = ['apply now', 'view job', 'learn more', 'click here']
        if v.lower().strip() in invalid_patterns:
            raise ValueError(f"Invalid URL: '{v}' appears to be button text, not a URL")
        return v.strip()
    
    @field_validator('title')
    @classmethod
    def clean_title(cls, v: str) -> str:
        """Clean up job title formatting."""
        v = ' '.join(v.split())
        v = re.sub(r'\s*-\s*Apply Now.*$', '', v, flags=re.IGNORECASE)
        return v.strip()


class JobWithMetadata(JobListing):
    """Job listing with additional tracking metadata."""
    id: Optional[str] = None
    status: JobStatus = JobStatus.NEW
    found_at: Optional[datetime] = None
    careers_url: Optional[str] = None
    role_keyword: Optional[str] = None
    notes: Optional[str] = None
    referral_contact: Optional[str] = None


class TargetConfig(BaseModel):
    """Configuration for a target company to monitor."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    id: Optional[str] = None
    company_name: str = Field(..., min_length=1, max_length=200)
    careers_url: str = Field(..., min_length=10)
    role_keyword: str = Field(default="Software Engineer", min_length=1)
    active: bool = True
    
    # Advanced configuration
    custom_headers: Optional[Dict[str, str]] = None
    scrape_strategy: ScrapeStrategy = ScrapeStrategy.DEFAULT
    scrape_interval_hours: int = Field(default=24, ge=1, le=168)
    max_jobs_per_scan: int = Field(default=50, ge=1, le=200)
    
    # Filtering
    exclude_keywords: List[str] = Field(default_factory=list)
    include_locations: List[str] = Field(default_factory=list)
    
    @field_validator('careers_url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Basic URL validation."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("careers_url must start with http:// or https://")
        return v.strip()


class TargetCreate(BaseModel):
    """Request model for creating a target."""
    company_name: str = Field(..., min_length=1, max_length=200)
    careers_url: str = Field(..., min_length=10)
    role_keyword: str = Field(default="Software Engineer")
    active: bool = True
    exclude_keywords: List[str] = Field(default_factory=list)
    include_locations: List[str] = Field(default_factory=list)


class TargetUpdate(BaseModel):
    """Request model for updating a target (partial update)."""
    company_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    careers_url: Optional[str] = Field(default=None, min_length=10)
    role_keyword: Optional[str] = None
    active: Optional[bool] = None
    exclude_keywords: Optional[List[str]] = None
    include_locations: Optional[List[str]] = None


class JobStatusUpdate(BaseModel):
    """Request model for updating job status."""
    status: JobStatus
    notes: Optional[str] = None
    referral_contact: Optional[str] = None


class JobSearchResult(BaseModel):
    """Container for job search results from scraping."""
    jobs: List[JobListing] = Field(default_factory=list)
    total_found: int = 0
    parsing_errors: int = 0
    error: Optional[str] = None


class JobCheckResult(BaseModel):
    """Result of a job check operation."""
    status: str
    targets_checked: int = 0
    new_jobs_count: int = 0
    new_jobs: List[JobListing] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    message: Optional[str] = None
    duration_seconds: Optional[float] = None


class HealthStatus(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime_seconds: float
    checks: Dict[str, Any]


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int


class StatsResponse(BaseModel):
    """Dashboard statistics."""
    total_jobs: int
    new_today: int
    active_targets: int
    jobs_by_company: Dict[str, int]
    jobs_by_status: Dict[str, int]
    recent_activity: List[Dict[str, Any]]


class NotificationConfig(BaseModel):
    """Configuration for notifications."""
    email_enabled: bool = True
    email_recipients: List[str] = Field(default_factory=list)
    slack_enabled: bool = False
    slack_webhook_url: Optional[str] = None
    discord_enabled: bool = False
    discord_webhook_url: Optional[str] = None
    notify_on_new_jobs: bool = True
    notify_daily_digest: bool = False
    digest_time: str = "09:00"
