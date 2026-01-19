// Referral Agent Dashboard JavaScript

const API_BASE = '';  // Same origin

// State
let targets = [];
let jobs = [];
let healthStatus = null;

// DOM Elements
const healthDot = document.getElementById('health-dot');
const healthText = document.getElementById('health-text');
const statsTargets = document.getElementById('stats-targets');
const statsJobs = document.getElementById('stats-jobs');
const statsNew = document.getElementById('stats-new');
const statsLast = document.getElementById('stats-last');
const targetsGrid = document.getElementById('targets-grid');
const jobsTableBody = document.getElementById('jobs-table-body');
const modalOverlay = document.getElementById('modal-overlay');
const targetForm = document.getElementById('target-form');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadHealth();
    loadTargets();
    loadJobs();
    
    // Refresh health every 30 seconds
    setInterval(loadHealth, 30000);
});

// Toast Notification
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${type === 'success' ? '✅' : '❌'}</span>
        <span>${message}</span>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Health Check
async function loadHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        healthStatus = await response.json();
        
        healthDot.className = 'health-dot';
        if (healthStatus.status !== 'healthy') {
            healthDot.classList.add('unhealthy');
            healthText.textContent = 'Unhealthy';
        } else {
            healthText.textContent = 'Healthy';
        }
        
        statsTargets.textContent = healthStatus.checks?.active_targets || 0;
    } catch (error) {
        healthDot.classList.add('unhealthy');
        healthText.textContent = 'Error';
        console.error('Health check failed:', error);
    }
}

// Load Targets
async function loadTargets() {
    try {
        const response = await fetch(`${API_BASE}/api/targets`);
        if (!response.ok) throw new Error('Failed to load targets');
        targets = await response.json();
        renderTargets();
    } catch (error) {
        console.error('Failed to load targets:', error);
        targetsGrid.innerHTML = `
            <div class="empty-state">
                <div class="icon">⚠️</div>
                <p>Failed to load targets</p>
            </div>
        `;
    }
}

// Render Targets
function renderTargets() {
    if (targets.length === 0) {
        targetsGrid.innerHTML = `
            <div class="empty-state">
                <div class="icon">🎯</div>
                <p>No targets configured yet</p>
                <button class="btn btn-primary" onclick="openModal()">
                    <span>➕</span> Add Your First Target
                </button>
            </div>
        `;
        return;
    }
    
    targetsGrid.innerHTML = targets.map(target => `
        <div class="target-card" data-id="${target.id}">
            <div class="company">
                🏢 ${escapeHtml(target.company_name)}
                <span class="status-badge ${target.active ? 'active' : 'inactive'}">
                    ${target.active ? '● Active' : '○ Inactive'}
                </span>
            </div>
            <span class="keyword">${escapeHtml(target.role_keyword)}</span>
            <div class="url">${escapeHtml(target.careers_url)}</div>
            <div class="actions">
                <button class="btn btn-outline" onclick="toggleTarget('${target.id}', ${!target.active})">
                    ${target.active ? '⏸️ Pause' : '▶️ Resume'}
                </button>
                <button class="btn btn-outline" onclick="editTarget('${target.id}')">
                    ✏️ Edit
                </button>
                <button class="btn btn-danger" onclick="deleteTarget('${target.id}')">
                    🗑️
                </button>
            </div>
        </div>
    `).join('');
}

// Load Jobs
async function loadJobs() {
    try {
        const response = await fetch(`${API_BASE}/api/jobs`);
        if (!response.ok) throw new Error('Failed to load jobs');
        jobs = await response.json();
        renderJobs();
        
        statsJobs.textContent = jobs.length;
        
        // Count jobs from last 24 hours
        const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
        const newJobs = jobs.filter(job => {
            const jobDate = job.found_at?._seconds 
                ? new Date(job.found_at._seconds * 1000)
                : new Date(job.found_at);
            return jobDate > oneDayAgo;
        });
        statsNew.textContent = newJobs.length;
        
        // Last check time
        if (jobs.length > 0) {
            const lastJob = jobs[0];
            const lastDate = lastJob.found_at?._seconds 
                ? new Date(lastJob.found_at._seconds * 1000)
                : new Date(lastJob.found_at);
            statsLast.textContent = formatRelativeTime(lastDate);
        }
    } catch (error) {
        console.error('Failed to load jobs:', error);
        jobsTableBody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-state">
                    <div class="icon">⚠️</div>
                    <p>Failed to load jobs</p>
                </td>
            </tr>
        `;
    }
}

// Render Jobs
function renderJobs() {
    if (jobs.length === 0) {
        jobsTableBody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-state">
                    <div class="icon">📭</div>
                    <p>No jobs found yet. Run a check to find jobs!</p>
                </td>
            </tr>
        `;
        return;
    }
    
    jobsTableBody.innerHTML = jobs.slice(0, 50).map(job => {
        const foundDate = job.found_at?._seconds 
            ? new Date(job.found_at._seconds * 1000)
            : new Date(job.found_at);
        
        const postedDate = job.posted_date || 'N/A';
        
        return `
            <tr>
                <td>
                    <div class="job-title">${escapeHtml(job.title || 'Unknown Title')}</div>
                    <div class="job-company">${escapeHtml(job.company_name || 'Unknown Company')}</div>
                </td>
                <td>${escapeHtml(job.location || 'N/A')}</td>
                <td class="job-date">
                    <div>${escapeHtml(postedDate)}</div>
                    <div style="font-size: 0.65rem; color: var(--text-secondary);">Found: ${formatDate(foundDate)}</div>
                </td>
                <td>
                    <a href="${escapeHtml(job.url)}" target="_blank" rel="noopener">
                        View Job →
                    </a>
                </td>
            </tr>
        `;
    }).join('');
}

// Modal Functions
function openModal(targetId = null) {
    document.getElementById('modal-title').textContent = targetId ? 'Edit Target' : 'Add Target';
    document.getElementById('target-id').value = targetId || '';
    
    if (targetId) {
        const target = targets.find(t => t.id === targetId);
        if (target) {
            document.getElementById('company-name').value = target.company_name;
            document.getElementById('careers-url').value = target.careers_url;
            document.getElementById('role-keyword').value = target.role_keyword;
            document.getElementById('target-active').value = target.active ? 'true' : 'false';
        }
    } else {
        targetForm.reset();
        document.getElementById('target-active').value = 'true';
    }
    
    modalOverlay.classList.add('active');
}

function closeModal() {
    modalOverlay.classList.remove('active');
    targetForm.reset();
}

function editTarget(targetId) {
    openModal(targetId);
}

// Save Target
async function saveTarget(event) {
    event.preventDefault();
    
    const targetId = document.getElementById('target-id').value;
    const data = {
        company_name: document.getElementById('company-name').value,
        careers_url: document.getElementById('careers-url').value,
        role_keyword: document.getElementById('role-keyword').value,
        active: document.getElementById('target-active').value === 'true'
    };
    
    try {
        const url = targetId 
            ? `${API_BASE}/api/targets/${targetId}`
            : `${API_BASE}/api/targets`;
        
        const response = await fetch(url, {
            method: targetId ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) throw new Error('Failed to save target');
        
        showToast(targetId ? 'Target updated!' : 'Target added!');
        closeModal();
        loadTargets();
        loadHealth();
    } catch (error) {
        showToast('Failed to save target', 'error');
        console.error('Save failed:', error);
    }
}

// Toggle Target Active Status
async function toggleTarget(targetId, active) {
    try {
        const response = await fetch(`${API_BASE}/api/targets/${targetId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active })
        });
        
        if (!response.ok) throw new Error('Failed to update target');
        
        showToast(`Target ${active ? 'activated' : 'paused'}!`);
        loadTargets();
        loadHealth();
    } catch (error) {
        showToast('Failed to update target', 'error');
        console.error('Toggle failed:', error);
    }
}

// Delete Target
async function deleteTarget(targetId) {
    if (!confirm('Are you sure you want to delete this target?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/targets/${targetId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete target');
        
        showToast('Target deleted!');
        loadTargets();
        loadHealth();
    } catch (error) {
        showToast('Failed to delete target', 'error');
        console.error('Delete failed:', error);
    }
}

// Run Job Check
async function runJobCheck() {
    const btn = event.target;
    const originalContent = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Running...';
    
    try {
        const response = await fetch(`${API_BASE}/check-jobs`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error('Check failed');
        
        const result = await response.json();
        showToast(`Found ${result.total_new_jobs || 0} new jobs!`);
        loadJobs();
    } catch (error) {
        showToast('Job check failed', 'error');
        console.error('Job check failed:', error);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalContent;
    }
}

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

function formatDate(date) {
    return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(date);
}

function formatRelativeTime(date) {
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
}

// Event Listeners
modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) closeModal();
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

targetForm.addEventListener('submit', saveTarget);
