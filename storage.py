import hashlib
from datetime import datetime
from firebase_admin import firestore

# Import config to ensure Firebase is initialized
import config  # noqa: F401

# Get Firestore client
db = firestore.client()

def get_active_targets():
    """
    Fetches documents from 'targets' collection where 'active' is True.
    Returns a list of dictionaries containing the target configuration.
    
    Expected document fields:
        - company_name: str
        - careers_url: str
        - role_keyword: str (e.g., "Software Engineer")
        - active: bool
    """
    docs = db.collection('targets').where('active', '==', True).stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

def _get_url_hash(url: str) -> str:
    """Helper to generate a consistent hash for a URL."""
    return hashlib.sha256(url.encode('utf-8')).hexdigest()

def is_job_seen(job_url: str) -> bool:
    """
    Checks if a document exists in 'job_history' collection.
    The document ID is the hash of the URL.
    """
    job_hash = _get_url_hash(job_url)
    doc_ref = db.collection('job_history').document(job_hash)
    doc = doc_ref.get()
    return doc.exists

def save_job(job_data: dict):
    """
    Saves a job to 'job_history' with a server timestamp.
    Uses the job URL hash as the document ID to prevent duplicates.
    """
    if 'url' not in job_data:
        raise ValueError("Job data must contain a 'url' field.")
        
    job_hash = _get_url_hash(job_data['url'])
    
    # Add server timestamp to the job data
    data_to_save = job_data.copy()
    data_to_save['found_at'] = firestore.SERVER_TIMESTAMP
    
    # Save to Firestore
    db.collection('job_history').document(job_hash).set(data_to_save)
