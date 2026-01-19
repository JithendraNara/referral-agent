"""
Enhanced scraping utilities with retry logic, custom headers, and fallback strategies.
"""
import logging
import random
import time
from typing import Optional, Dict
from functools import wraps

logger = logging.getLogger(__name__)

# Rotate through realistic User-Agent strings to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def get_random_user_agent() -> str:
    """Get a random User-Agent string."""
    return random.choice(USER_AGENTS)


def get_default_headers() -> Dict[str, str]:
    """Get default headers that mimic a real browser."""
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        # Exponential backoff with jitter
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed: {e}")
            
            raise last_exception
        return wrapper
    return decorator


class RateLimiter:
    """Simple rate limiter to be polite to career pages."""
    
    def __init__(self, min_delay: float = 2.0, max_delay: float = 5.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time: Dict[str, float] = {}
    
    def wait(self, domain: str):
        """Wait before making a request to the given domain."""
        now = time.time()
        
        if domain in self.last_request_time:
            elapsed = now - self.last_request_time[domain]
            required_delay = random.uniform(self.min_delay, self.max_delay)
            
            if elapsed < required_delay:
                sleep_time = required_delay - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s for {domain}")
                time.sleep(sleep_time)
        
        self.last_request_time[domain] = time.time()


# Global rate limiter instance
rate_limiter = RateLimiter()


def extract_domain(url: str) -> str:
    """Extract domain from URL for rate limiting."""
    from urllib.parse import urlparse
    return urlparse(url).netloc
