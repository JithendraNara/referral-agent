"""
Firestore storage operations with professional patterns.
Includes caching, batching, and proper error handling.
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from functools import lru_cache
from firebase_admin import firestore

from config import db
from models import JobStatus

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Custom exception for storage operations."""
    pass


class JobStorage:
    """
    Handles all job-related storage operations.
    Implements caching and efficient querying patterns.
    """
    
    COLLECTION = 'job_history'
    
    def __init__(self, db_client=None):
        self._db = db_client or db
        self._seen_cache: set = set()
        self._cache_loaded = False
    
    @staticmethod
    def _get_url_hash(url: str) -> str:
        """Generate consistent hash for URL-based document ID."""
        normalized = url.lower().strip().rstrip('/')
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:32]
    
    def _load_seen_cache(self):
        """Load all seen job URLs into memory for fast lookup."""
        if self._cache_loaded:
            return
        
        try:
            docs = self._db.collection(self.COLLECTION).select([]).stream()
            self._seen_cache = {doc.id for doc in docs}
            self._cache_loaded = True
            logger.info(f"Loaded {len(self._seen_cache)} job IDs into cache")
        except Exception as e:
            logger.error(f"Failed to load seen cache: {e}")
            self._seen_cache = set()
    
    def is_job_seen(self, job_url: str) -> bool:
        """
        Check if a job URL has already been processed.
        Uses in-memory cache for performance.
        """
        self._load_seen_cache()
        job_hash = self._get_url_hash(job_url)
        return job_hash in self._seen_cache
    
    def save_job(self, job_data: Dict) -> str:
        """
        Save a job to Firestore with deduplication.
        
        Args:
            job_data: Job dictionary with required 'url' field
        
        Returns:
            Document ID of saved job
        
        Raises:
            StorageError: If job_data is invalid or save fails
        """
        if 'url' not in job_data:
            raise StorageError("Job data must contain a 'url' field")
        
        job_hash = self._get_url_hash(job_data['url'])
        
        # Prepare data for storage
        data_to_save = {
            **job_data,
            'found_at': firestore.SERVER_TIMESTAMP,
            'status': job_data.get('status', JobStatus.NEW.value),
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        try:
            self._db.collection(self.COLLECTION).document(job_hash).set(data_to_save)
            self._seen_cache.add(job_hash)
            logger.debug(f"Saved job: {job_data.get('title', 'Unknown')}")
            return job_hash
        except Exception as e:
            logger.error(f"Failed to save job: {e}")
            raise StorageError(f"Failed to save job: {e}")
    
    def save_jobs_batch(self, jobs: List[Dict]) -> int:
        """
        Save multiple jobs in a batch operation for efficiency.
        
        Args:
            jobs: List of job dictionaries
        
        Returns:
            Number of jobs successfully saved
        """
        if not jobs:
            return 0
        
        batch = self._db.batch()
        saved_count = 0
        
        for job_data in jobs:
            if 'url' not in job_data:
                continue
            
            job_hash = self._get_url_hash(job_data['url'])
            doc_ref = self._db.collection(self.COLLECTION).document(job_hash)
            
            data_to_save = {
                **job_data,
                'found_at': firestore.SERVER_TIMESTAMP,
                'status': job_data.get('status', JobStatus.NEW.value),
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            batch.set(doc_ref, data_to_save)
            self._seen_cache.add(job_hash)
            saved_count += 1
            
            # Firestore batch limit is 500 operations
            if saved_count % 450 == 0:
                batch.commit()
                batch = self._db.batch()
        
        if saved_count % 450 != 0:
            batch.commit()
        
        logger.info(f"Batch saved {saved_count} jobs")
        return saved_count
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get a single job by ID."""
        try:
            doc = self._db.collection(self.COLLECTION).document(job_id).get()
            if doc.exists:
                return {"id": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            return None
    
    def get_jobs(
        self,
        limit: int = 100,
        offset: int = 0,
        company: str = None,
        status: str = None,
        since: datetime = None
    ) -> List[Dict]:
        """
        Get jobs with filtering and pagination.
        
        Args:
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            company: Filter by company name
            status: Filter by job status
            since: Only return jobs found after this datetime
        
        Returns:
            List of job dictionaries
        """
        try:
            query = self._db.collection(self.COLLECTION)
            
            # Apply filters
            if company:
                query = query.where('company_name', '==', company)
            if status:
                query = query.where('status', '==', status)
            if since:
                query = query.where('found_at', '>=', since)
            
            # Order and paginate
            query = query.order_by('found_at', direction=firestore.Query.DESCENDING)
            
            # Firestore doesn't support offset natively, we have to fetch and skip
            docs = query.limit(limit + offset).stream()
            
            jobs = []
            for i, doc in enumerate(docs):
                if i < offset:
                    continue
                if len(jobs) >= limit:
                    break
                data = doc.to_dict()
                data['id'] = doc.id
                jobs.append(data)
            
            return jobs
        except Exception as e:
            logger.error(f"Failed to get jobs: {e}")
            return []
    
    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        notes: str = None,
        referral_contact: str = None
    ) -> bool:
        """
        Update job status and optional metadata.
        
        Args:
            job_id: Document ID of the job
            status: New status
            notes: Optional notes
            referral_contact: Optional referral contact
        
        Returns:
            True if successful, False otherwise
        """
        try:
            doc_ref = self._db.collection(self.COLLECTION).document(job_id)
            
            update_data = {
                'status': status.value,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            if notes is not None:
                update_data['notes'] = notes
            if referral_contact is not None:
                update_data['referral_contact'] = referral_contact
            
            doc_ref.update(update_data)
            logger.info(f"Updated job {job_id} status to {status.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            return False
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        try:
            doc_ref = self._db.collection(self.COLLECTION).document(job_id)
            if not doc_ref.get().exists:
                return False
            
            doc_ref.delete()
            self._seen_cache.discard(job_id)
            logger.info(f"Deleted job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete job: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get job statistics for dashboard."""
        try:
            # Get total count
            all_jobs = list(self._db.collection(self.COLLECTION).stream())
            total = len(all_jobs)
            
            # Calculate stats
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            new_today = 0
            by_company = {}
            by_status = {}
            
            for doc in all_jobs:
                data = doc.to_dict()
                
                # Count new today
                found_at = data.get('found_at')
                if found_at:
                    if hasattr(found_at, 'timestamp'):
                        found_dt = datetime.fromtimestamp(found_at.timestamp())
                    else:
                        found_dt = found_at
                    if found_dt >= today:
                        new_today += 1
                
                # Count by company
                company = data.get('company_name', 'Unknown')
                by_company[company] = by_company.get(company, 0) + 1
                
                # Count by status
                status = data.get('status', 'new')
                by_status[status] = by_status.get(status, 0) + 1
            
            return {
                'total_jobs': total,
                'new_today': new_today,
                'jobs_by_company': by_company,
                'jobs_by_status': by_status
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {'total_jobs': 0, 'new_today': 0, 'jobs_by_company': {}, 'jobs_by_status': {}}


class TargetStorage:
    """Handles all target-related storage operations."""
    
    COLLECTION = 'targets'
    
    def __init__(self, db_client=None):
        self._db = db_client or db
    
    def get_active_targets(self) -> List[Dict]:
        """Get all active targets."""
        try:
            docs = self._db.collection(self.COLLECTION).where('active', '==', True).stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get active targets: {e}")
            return []
    
    def get_all_targets(self) -> List[Dict]:
        """Get all targets regardless of status."""
        try:
            docs = self._db.collection(self.COLLECTION).stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get all targets: {e}")
            return []
    
    def get_target(self, target_id: str) -> Optional[Dict]:
        """Get a single target by ID."""
        try:
            doc = self._db.collection(self.COLLECTION).document(target_id).get()
            if doc.exists:
                return {"id": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            logger.error(f"Failed to get target {target_id}: {e}")
            return None
    
    def create_target(self, data: Dict) -> str:
        """
        Create a new target.
        
        Returns:
            Document ID of created target
        """
        try:
            data['created_at'] = firestore.SERVER_TIMESTAMP
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref = self._db.collection(self.COLLECTION).add(data)
            target_id = doc_ref[1].id
            logger.info(f"Created target: {data.get('company_name')} ({target_id})")
            return target_id
        except Exception as e:
            logger.error(f"Failed to create target: {e}")
            raise StorageError(f"Failed to create target: {e}")
    
    def update_target(self, target_id: str, data: Dict) -> bool:
        """Update an existing target."""
        try:
            doc_ref = self._db.collection(self.COLLECTION).document(target_id)
            if not doc_ref.get().exists:
                return False
            
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.update(data)
            logger.info(f"Updated target {target_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update target: {e}")
            return False
    
    def delete_target(self, target_id: str) -> bool:
        """Delete a target."""
        try:
            doc_ref = self._db.collection(self.COLLECTION).document(target_id)
            if not doc_ref.get().exists:
                return False
            
            doc_ref.delete()
            logger.info(f"Deleted target {target_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete target: {e}")
            return False
    
    def toggle_active(self, target_id: str, active: bool) -> bool:
        """Toggle target active status."""
        return self.update_target(target_id, {'active': active})


# Create singleton instances
job_storage = JobStorage()
target_storage = TargetStorage()


# Legacy function exports for backward compatibility
def get_active_targets() -> List[Dict]:
    """Legacy wrapper for target_storage.get_active_targets()."""
    return target_storage.get_active_targets()


def is_job_seen(job_url: str) -> bool:
    """Legacy wrapper for job_storage.is_job_seen()."""
    return job_storage.is_job_seen(job_url)


def save_job(job_data: Dict) -> str:
    """Legacy wrapper for job_storage.save_job()."""
    return job_storage.save_job(job_data)
