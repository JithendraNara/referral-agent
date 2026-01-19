"""
Pydantic models for structured data validation.
Ensures LLM outputs are properly validated and typed.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class JobListing(BaseModel):
    """Represents a single job listing extracted from a careers page."""
    title: str = Field(..., description="Job title")
    url: str = Field(..., description="URL to the job posting")
    location: str = Field(default="Not specified", description="Job location")
    
    class Config:
        extra = "allow"  # Allow additional fields from LLM


class JobSearchResult(BaseModel):
    """Container for job search results."""
    jobs: List[JobListing] = Field(default_factory=list)
    error: Optional[str] = None


class TargetConfig(BaseModel):
    """Configuration for a target company to monitor."""
    id: Optional[str] = None
    company_name: str
    careers_url: str
    role_keyword: str = "Software Engineer"
    active: bool = True
    
    # Optional advanced config
    custom_headers: Optional[dict] = None
    scrape_strategy: str = "default"  # default, firecrawl, playwright


class NotificationConfig(BaseModel):
    """Configuration for notifications."""
    email_enabled: bool = True
    slack_enabled: bool = False
    slack_webhook_url: Optional[str] = None
    discord_enabled: bool = False
    discord_webhook_url: Optional[str] = None


class JobCheckResult(BaseModel):
    """Result of a job check operation."""
    status: str
    targets_checked: int = 0
    new_jobs_count: int = 0
    new_jobs: List[JobListing] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    message: Optional[str] = None
