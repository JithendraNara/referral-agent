import json
import logging
from typing import List, Dict, Any
from crewai import Agent, Task, Crew, Process
from crewai_tools import ScrapeWebsiteTool

from models import JobListing
from scraper_utils import retry_with_backoff, rate_limiter, extract_domain

logger = logging.getLogger(__name__)

# Few-shot examples for the LLM to produce consistent output
FEW_SHOT_EXAMPLES = """
Example Input (Raw HTML snippet):
<div class="job-card">
  <h3><a href="/careers/swe-123">Senior Software Engineer</a></h3>
  <span class="location">San Francisco, CA</span>
  <span class="date">01/15/2026</span>
</div>
<div class="job-listing">
  <a href="https://boards.greenhouse.io/company/jobs/456">ML Engineer</a>
  <p>New York, NY</p>
  <time>Posted 2 days ago</time>
</div>

Example Output:
[
  {"title": "Senior Software Engineer", "url": "/careers/swe-123", "location": "San Francisco, CA", "posted_date": "01/15/2026"},
  {"title": "ML Engineer", "url": "https://boards.greenhouse.io/company/jobs/456", "location": "New York, NY", "posted_date": "2 days ago"}
]

IMPORTANT URL RULES:
- The URL must be an actual link (href attribute), NOT button text like "Apply Now" or "View Job"
- Look for <a href="..."> tags to find the real URLs
- Relative URLs like "/jobs/123" are fine
- If you can't find a proper URL, construct one from the base URL + job ID
"""


@retry_with_backoff(max_retries=2, base_delay=2.0)
def find_jobs(target: Dict[str, Any], llm) -> List[Dict]:
    """
    Scrapes a target company's careers page for specific roles using CrewAI.

    Args:
        target (dict): Configuration for the target with fields:
            - careers_url: The URL to scrape
            - role_keyword: The role to search for (e.g., "Software Engineer")
            - company_name: Name of the company
        llm: The initialized LLM instance to be used by the agent.

    Returns:
        List of job dictionaries with 'title', 'url', 'location' keys.
    """
    
    careers_url = target.get('careers_url')
    role_keyword = target.get('role_keyword', 'Software Engineer')
    company_name = target.get('company_name', 'Unknown')
    
    logger.info(f"🔍 Scraping {company_name}: {careers_url}")
    
    # Apply rate limiting
    domain = extract_domain(careers_url)
    rate_limiter.wait(domain)

    # Initialize the scraping tool with the specific target URL
    scraper = ScrapeWebsiteTool(website_url=careers_url)

    # Create the Recruiter Agent with enhanced instructions
    recruiter = Agent(
        role='Expert Tech Recruiter',
        goal=f'Extract ALL job listings matching "{role_keyword}" from the careers page',
        backstory=(
            "You are a meticulous technical recruiter with 10 years of experience. "
            "You excel at parsing complex career pages, JavaScript-rendered job boards, "
            "and identifying relevant positions even when titles vary slightly. "
            "You ALWAYS return valid JSON and never include markdown formatting."
        ),
        tools=[scraper],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,  # Limit iterations to prevent infinite loops
    )

    # Enhanced task with few-shot examples
    task = Task(
        description=f"""
        GOAL: Extract job listings from {company_name}'s careers page.
        
        STEPS:
        1. Scrape the careers page at: {careers_url}
        2. Find ALL jobs that match or relate to: "{role_keyword}"
        3. Include variations like "Senior {role_keyword}", "Staff {role_keyword}", etc.
        
        OUTPUT FORMAT (strict JSON, no markdown):
        Return a JSON array. Each object must have exactly these fields:
        - "title": The job title (string)
        - "url": The ACTUAL job URL from the href attribute - NOT button text like "Apply Now" (string)  
        - "location": The job location, or "Remote" or "Not specified" (string)
        - "posted_date": When the job was posted - look for dates like "01/15/2026", "Jan 15", "2 days ago", "Posted yesterday" (string or null)
        
        {FEW_SHOT_EXAMPLES}
        
        CRITICAL RULES:
        - The "url" field MUST be a real URL path (like "/jobs/123" or "https://..."), NOT button text
        - If a job's link text says "Apply Now" but href="/careers/job-456", use "/careers/job-456" as the url
        - Extract the posting date if visible - check for date patterns, "Posted X days ago", timestamps, etc.
        - Return ONLY the JSON array, no explanation or markdown
        - If no matching jobs found, return: []
        - Include partial matches (e.g., "ML Engineer" matches "Engineer")
        """,
        expected_output="A JSON array of job objects with title, url, and location fields",
        agent=recruiter
    )

    # Create and run the Crew
    crew = Crew(
        agents=[recruiter],
        tasks=[task],
        process=Process.sequential,
        verbose=True
    )

    result = crew.kickoff()
    
    # Parse and validate the result
    jobs = _parse_and_validate_result(result, company_name)
    logger.info(f"✅ Found {len(jobs)} matching jobs at {company_name}")
    
    return jobs


def _parse_and_validate_result(result: Any, company_name: str) -> List[Dict]:
    """
    Parse the CrewAI result and validate each job using Pydantic.
    
    Args:
        result: Raw result from CrewAI
        company_name: Company name for logging
        
    Returns:
        List of validated job dictionaries
    """
    import ast
    
    try:
        # Get raw text from result
        text_output = str(result)
        
        # Clean up common LLM formatting issues
        text_output = text_output.strip()
        text_output = text_output.replace("```json", "").replace("```", "")
        text_output = text_output.strip()
        
        # Handle case where LLM adds explanation before/after JSON
        # Find the JSON array boundaries
        start_idx = text_output.find('[')
        end_idx = text_output.rfind(']')
        
        if start_idx != -1 and end_idx != -1:
            text_output = text_output[start_idx:end_idx + 1]
        
        # Try JSON parsing first
        try:
            raw_jobs = json.loads(text_output)
        except json.JSONDecodeError:
            # Fallback: try Python literal eval (handles single quotes)
            raw_jobs = ast.literal_eval(text_output)
        
        if not isinstance(raw_jobs, list):
            logger.warning(f"Expected list, got {type(raw_jobs)} for {company_name}")
            return []
        
        # Validate each job with Pydantic
        validated_jobs = []
        for raw_job in raw_jobs:
            try:
                job = JobListing(**raw_job)
                validated_jobs.append(job.model_dump())
            except Exception as e:
                logger.debug(f"Skipping invalid job entry: {raw_job} - {e}")
                continue
        
        return validated_jobs
        
    except Exception as e:
        logger.error(f"Failed to parse jobs for {company_name}: {e}")
        logger.debug(f"Raw output was: {str(result)[:500]}...")
        return []
