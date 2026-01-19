"""
Enhanced scraping utilities with retry logic, caching, and professional error handling.
"""
import logging
import random
import time
import hashlib
from typing import Optional, Dict, Callable, TypeVar, Any
from functools import wraps
from urllib.parse import urlparse
from datetime import datetime, timedelta
from collections import OrderedDict

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Rotate through realistic User-Agent strings
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
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


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    def __init__(self, message: str, last_exception: Exception = None):
        super().__init__(message)
        self.last_exception = last_exception


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential: bool = True,
    exceptions: tuple = (Exception,)
):
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential: Use exponential backoff if True, else linear
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        if exponential:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                        else:
                            delay = min(base_delay * (attempt + 1), max_delay)
                        
                        # Add jitter to prevent thundering herd
                        delay += random.uniform(0, delay * 0.1)
                        
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed for {func.__name__}: {e}")
            
            raise RetryError(
                f"Failed after {max_retries + 1} attempts",
                last_exception=last_exception
            )
        return wrapper
    return decorator


class RateLimiter:
    """
    Token bucket rate limiter with per-domain tracking.
    Prevents overwhelming career pages with requests.
    """
    
    def __init__(self, min_delay: float = 2.0, max_delay: float = 5.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time: Dict[str, float] = {}
        self._lock_times: Dict[str, float] = {}
    
    def wait(self, domain: str) -> float:
        """
        Wait before making a request to the given domain.
        Returns the actual delay used.
        """
        now = time.time()
        required_delay = random.uniform(self.min_delay, self.max_delay)
        
        if domain in self.last_request_time:
            elapsed = now - self.last_request_time[domain]
            
            if elapsed < required_delay:
                sleep_time = required_delay - elapsed
                logger.debug(f"Rate limiting: waiting {sleep_time:.1f}s for {domain}")
                time.sleep(sleep_time)
                required_delay = sleep_time
        
        self.last_request_time[domain] = time.time()
        return required_delay
    
    def is_locked(self, domain: str) -> bool:
        """Check if domain is temporarily locked due to rate limiting."""
        if domain not in self._lock_times:
            return False
        return time.time() < self._lock_times[domain]
    
    def lock(self, domain: str, duration: float = 60.0):
        """Temporarily lock a domain (e.g., after receiving 429)."""
        self._lock_times[domain] = time.time() + duration
        logger.warning(f"Domain {domain} locked for {duration}s")
    
    def unlock(self, domain: str):
        """Remove lock from domain."""
        self._lock_times.pop(domain, None)


class LRUCache:
    """
    Simple LRU cache for storing scraped content temporarily.
    Useful for avoiding re-scraping the same page within a session.
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple] = OrderedDict()
    
    def _make_key(self, url: str) -> str:
        """Create cache key from URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    def get(self, url: str) -> Optional[Any]:
        """Get cached value if exists and not expired."""
        key = self._make_key(url)
        
        if key not in self._cache:
            return None
        
        value, timestamp = self._cache[key]
        
        # Check TTL
        if time.time() - timestamp > self.ttl_seconds:
            del self._cache[key]
            return None
        
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value
    
    def set(self, url: str, value: Any):
        """Store value in cache."""
        key = self._make_key(url)
        
        # Remove oldest if at capacity
        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        
        self._cache[key] = (value, time.time())
    
    def clear(self):
        """Clear all cached items."""
        self._cache.clear()
    
    def stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds
        }


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent repeated failures.
    Opens circuit after threshold failures, preventing further attempts temporarily.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_requests: int = 1
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests
        
        self._failures: Dict[str, int] = {}
        self._last_failure: Dict[str, float] = {}
        self._state: Dict[str, str] = {}  # closed, open, half-open
    
    def _get_state(self, key: str) -> str:
        """Get current state for a key."""
        if key not in self._state:
            self._state[key] = "closed"
        
        state = self._state[key]
        
        # Check if we should transition from open to half-open
        if state == "open":
            if time.time() - self._last_failure.get(key, 0) > self.recovery_timeout:
                self._state[key] = "half-open"
                return "half-open"
        
        return state
    
    def can_execute(self, key: str) -> bool:
        """Check if execution is allowed."""
        state = self._get_state(key)
        return state in ("closed", "half-open")
    
    def record_success(self, key: str):
        """Record a successful execution."""
        self._failures[key] = 0
        self._state[key] = "closed"
    
    def record_failure(self, key: str):
        """Record a failed execution."""
        self._failures[key] = self._failures.get(key, 0) + 1
        self._last_failure[key] = time.time()
        
        if self._failures[key] >= self.failure_threshold:
            self._state[key] = "open"
            logger.warning(f"Circuit breaker opened for {key}")
    
    def get_status(self, key: str) -> Dict[str, Any]:
        """Get circuit breaker status for a key."""
        return {
            "state": self._get_state(key),
            "failures": self._failures.get(key, 0),
            "threshold": self.failure_threshold
        }


def extract_domain(url: str) -> str:
    """Extract domain from URL for rate limiting."""
    parsed = urlparse(url)
    return parsed.netloc or url


def normalize_url(url: str, base_url: str = None) -> str:
    """
    Normalize a URL, handling relative paths.
    
    Args:
        url: The URL to normalize
        base_url: Base URL for resolving relative paths
    
    Returns:
        Normalized absolute URL
    """
    from urllib.parse import urljoin, urlparse, urlunparse
    
    # Handle relative URLs
    if base_url and not url.startswith(('http://', 'https://')):
        url = urljoin(base_url, url)
    
    # Parse and normalize
    parsed = urlparse(url)
    
    # Remove trailing slash from path (except root)
    path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path
    
    # Reconstruct URL
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        path,
        parsed.params,
        parsed.query,
        ''  # Remove fragment
    ))
    
    return normalized


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two strings using Jaccard index.
    Useful for detecting duplicate job titles.
    """
    if not text1 or not text2:
        return 0.0
    
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    intersection = words1 & words2
    union = words1 | words2
    
    return len(intersection) / len(union) if union else 0.0


# Global instances
rate_limiter = RateLimiter()
scrape_cache = LRUCache(max_size=50, ttl_seconds=1800)  # 30 min cache
circuit_breaker = CircuitBreaker()
