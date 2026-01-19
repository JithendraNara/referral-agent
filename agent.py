"""
AI Agent for job scraping using CrewAI.
Professional implementation with improved prompting and error handling.
"""
import json
import ast
import logging
from typing import List, Dict, Any, Optional
from crewai import Agent, Task, Crew, Process
from crewai_tools import ScrapeWebsiteTool

from models import JobListing, JobSearchResult
from scraper_utils import (
    retry_with_backoff,
    rate_limiter,
    circuit_breaker,
    scrape_cache,
    extract_domain,
    normalize_url
)

logger = logging.getLogger(__name__)


# Enhanced few-shot examples for better LLM output
FEW_SHOT_EXAMPLES = """
Example Input (Raw HTML snippet):
<div class="job-card">
  <h3><a href="/careers/swe-123">Senior Software Engineer</a></h3>
  <span class="location">San Francisco, CA</span>
  <span class="date">Posted Jan 15, 2026</span>
</div>
<div class="job-listing">
  <a href="https://boards.greenhouse.io/company/jobs/456">ML Engineer</a>
  <p>New York, NY (Hybrid)</p>
  <time datetime="2026-01-13">2 days ago</time>
</div>
<div class="position-item">
  <h4>Backend Engineer</h4>
  <a class="apply-button" href="/apply/789">Apply Now</a>
  <span>Remote - US</span>
</div>

Example Output:
[
  {"title": "Senior Software Engineer", "url": "/careers/swe-123", "location": "San Francisco, CA", "posted_date": "Jan 15, 2026"},
  {"title": "ML Engineer", "url": "https://boards.greenhouse.io/company/jobs/456", "location": "New York, NY (Hybrid)", "posted_date": "2 days ago"},
  {"title": "Backend Engineer", "url": "/apply/789", "location": "Remote - US", "posted_date": null}
]

CRITICAL URL RULES:
1. The URL MUST be from an href attribute, NOT visible button text
2. "Apply Now", "View Job", "Learn More" are button labels, NOT URLs
3. Look inside <a href="..."> to find the real URL
4. Relative URLs like "/jobs/123" are valid
5. If job links to Greenhouse, Lever, Workday - include the full URL

CRITICAL TITLE RULES:
1. Extract the actual job title, not "Apply Now" or generic text
2. Include level indicators: "Senior", "Staff", "Principal", etc.
3. Clean up extra whitespace and formatting
"""


class JobScraperAgent:
    """
    Professional job scraping agent using CrewAI.
    Handles retries, caching, and circuit breaking.
    """
    
    def __init__(self, llm):
        self.llm = llm
        self._agent = None
    
    def _create_agent(self, scraper_tool: ScrapeWebsiteTool) -> Agent:
        """Create a configured recruiter agent."""
        return Agent(
            role='Expert Technical Recruiter & Job Board Analyst',
            goal='Extract ALL job listings from career pages with 100% accuracy',
            backstory=(
                "You are an elite technical recruiter with 15 years of experience parsing "
                "every major ATS system: Greenhouse, Lever, Workday, Ashby, and custom career sites. "
                "You have an exceptional eye for detail and NEVER confuse button text with URLs. "
                "You always return perfectly structured JSON and validate your output before submitting."
            ),
            tools=[scraper_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            max_iter=3,
            memory=False,  # Disable memory for serverless
        )
    
    def _create_task(
        self,
        agent: Agent,
        company_name: str,
        careers_url: str,
        role_keyword: str,
        exclude_keywords: List[str] = None,
        include_locations: List[str] = None
    ) -> Task:
        """Create a scraping task with detailed instructions."""
        
        exclusion_text = ""
        if exclude_keywords:
            exclusion_text = f"\n- EXCLUDE jobs containing: {', '.join(exclude_keywords)}"
        
        location_text = ""
        if include_locations:
            location_text = f"\n- PRIORITIZE locations: {', '.join(include_locations)}"
        
        return Task(
            description=f"""
            MISSION: Extract job listings from {company_name}'s careers page.
            
            TARGET URL: {careers_url}
            TARGET ROLE: "{role_keyword}"
            
            STEP-BY-STEP PROCESS:
            1. Scrape the careers page content
            2. Identify ALL job postings that match or relate to "{role_keyword}"
            3. Include variations: "Senior {role_keyword}", "Staff {role_keyword}", "{role_keyword} II", etc.
            4. Extract the EXACT href URL from each job's link (NOT button text!)
            5. Extract location, handling "Remote", "Hybrid", or specific cities
            6. Extract posting date if visible (any format is acceptable)
            {exclusion_text}
            {location_text}
            
            OUTPUT FORMAT - Return ONLY a JSON array:
            [
              {{"title": "Job Title", "url": "/path/to/job", "location": "City, State", "posted_date": "Jan 15"}},
              ...
            ]
            
            {FEW_SHOT_EXAMPLES}
            
            VALIDATION CHECKLIST (verify before responding):
            ✓ Every "url" field contains an actual URL path, not "Apply Now"
            ✓ Every "title" field is a real job title
            ✓ Output is valid JSON array (no markdown, no explanation)
            ✓ Empty array [] if no matching jobs found
            
            RESPOND WITH JSON ONLY - NO EXPLANATIONS
            """,
            expected_output="A valid JSON array of job objects",
            agent=agent
        )
    
    @retry_with_backoff(max_retries=2, base_delay=3.0)
    def scrape_jobs(
        self,
        target: Dict[str, Any],
        use_cache: bool = True
    ) -> JobSearchResult:
        """
        Scrape jobs from a target company's careers page.
        
        Args:
            target: Target configuration dict
            use_cache: Whether to use cached results
        
        Returns:
            JobSearchResult with found jobs
        """
        careers_url = target.get('careers_url')
        role_keyword = target.get('role_keyword', 'Software Engineer')
        company_name = target.get('company_name', 'Unknown')
        exclude_keywords = target.get('exclude_keywords', [])
        include_locations = target.get('include_locations', [])
        
        domain = extract_domain(careers_url)
        
        # Check circuit breaker
        if not circuit_breaker.can_execute(domain):
            logger.warning(f"Circuit breaker open for {domain}, skipping")
            return JobSearchResult(error=f"Temporarily blocked: {domain}")
        
        # Check cache
        if use_cache:
            cached = scrape_cache.get(careers_url)
            if cached:
                logger.info(f"Using cached results for {company_name}")
                return cached
        
        logger.info(f"🔍 Scraping {company_name}: {careers_url}")
        
        # Apply rate limiting
        rate_limiter.wait(domain)
        
        try:
            # Initialize scraper and agent
            scraper = ScrapeWebsiteTool(website_url=careers_url)
            agent = self._create_agent(scraper)
            task = self._create_task(
                agent,
                company_name,
                careers_url,
                role_keyword,
                exclude_keywords,
                include_locations
            )
            
            # Execute crew
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=True
            )
            
            result = crew.kickoff()
            
            # Parse and validate results
            jobs, parsing_errors = self._parse_result(result, company_name, careers_url)
            
            search_result = JobSearchResult(
                jobs=jobs,
                total_found=len(jobs),
                parsing_errors=parsing_errors
            )
            
            # Cache successful results
            if jobs:
                scrape_cache.set(careers_url, search_result)
            
            # Record success for circuit breaker
            circuit_breaker.record_success(domain)
            
            logger.info(f"✅ Found {len(jobs)} jobs at {company_name}")
            return search_result
            
        except Exception as e:
            circuit_breaker.record_failure(domain)
            logger.error(f"❌ Failed to scrape {company_name}: {e}")
            return JobSearchResult(error=str(e))
    
    def _parse_result(
        self,
        result: Any,
        company_name: str,
        base_url: str
    ) -> tuple[List[JobListing], int]:
        """
        Parse and validate CrewAI result.
        
        Returns:
            Tuple of (validated jobs, parsing error count)
        """
        parsing_errors = 0
        
        try:
            # Get raw text
            text_output = str(result).strip()
            
            # Clean up LLM formatting issues
            text_output = text_output.replace("```json", "").replace("```", "").strip()
            
            # Find JSON array boundaries
            start_idx = text_output.find('[')
            end_idx = text_output.rfind(']')
            
            if start_idx == -1 or end_idx == -1:
                logger.warning(f"No JSON array found for {company_name}")
                return [], 1
            
            text_output = text_output[start_idx:end_idx + 1]
            
            # Try JSON parsing
            try:
                raw_jobs = json.loads(text_output)
            except json.JSONDecodeError:
                # Fallback to Python literal eval
                try:
                    raw_jobs = ast.literal_eval(text_output)
                except:
                    logger.error(f"Failed to parse output for {company_name}")
                    return [], 1
            
            if not isinstance(raw_jobs, list):
                logger.warning(f"Expected list, got {type(raw_jobs)} for {company_name}")
                return [], 1
            
            # Validate each job with Pydantic
            validated_jobs = []
            for raw_job in raw_jobs:
                try:
                    # Normalize URL
                    if 'url' in raw_job and raw_job['url']:
                        raw_job['url'] = normalize_url(raw_job['url'], base_url)
                    
                    job = JobListing(**raw_job)
                    validated_jobs.append(job)
                except Exception as e:
                    logger.debug(f"Invalid job entry: {raw_job} - {e}")
                    parsing_errors += 1
                    continue
            
            return validated_jobs, parsing_errors
            
        except Exception as e:
            logger.error(f"Parse error for {company_name}: {e}")
            return [], 1


def find_jobs(target: Dict[str, Any], llm) -> List[Dict]:
    """
    Legacy function wrapper for backward compatibility.
    
    Args:
        target: Target configuration
        llm: LLM instance
    
    Returns:
        List of job dictionaries
    """
    agent = JobScraperAgent(llm)
    result = agent.scrape_jobs(target)
    
    if result.error:
        logger.error(f"Scrape failed: {result.error}")
        return []
    
    return [job.model_dump() for job in result.jobs]


def scrape_multiple_targets(
    targets: List[Dict[str, Any]],
    llm,
    parallel: bool = False
) -> Dict[str, JobSearchResult]:
    """
    Scrape multiple targets.
    
    Args:
        targets: List of target configurations
        llm: LLM instance
        parallel: Whether to scrape in parallel (not recommended due to rate limiting)
    
    Returns:
        Dict mapping company names to their results
    """
    agent = JobScraperAgent(llm)
    results = {}
    
    for target in targets:
        company = target.get('company_name', 'Unknown')
        results[company] = agent.scrape_jobs(target)
    
    return results
