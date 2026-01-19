/**
 * Referral Agent Dashboard - Professional Edition
 */

const API = '';
let targets = [];
let jobs = [];
let filteredJobs = [];
let currentPage = 1;
const perPage = 20;

// Filters
let filters = {
    company: '',
    location: '',
    dateRange: 'all',
    status: 'all',
    search: ''
};

// DOM Ready
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    loadData();
    setInterval(loadHealth, 30000);
});

function initApp() {
    // Search
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', debounce((e) => {
            filters.search = e.target.value.toLowerCase();
            applyFilters();
        }, 300));
    }

    // Filter selects
    document.querySelectorAll('.filter-select').forEach(select => {
        select.addEventListener('change', (e) => {
            const filterType = e.target.dataset.filter;
            filters[filterType] = e.target.value;
            applyFilters();
        });
    });

    // Navigation - Sidebar
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const view = item.dataset.view;
            if (view) switchView(view);
        });
    });
    
    // Navigation - Header tabs (mobile)
    document.querySelectorAll('.header-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const view = tab.dataset.view;
            if (view) {
                switchView(view);
                // Update header tabs active state
                document.querySelectorAll('.header-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
            }
        });
    });

    // Modal close on overlay click
    document.getElementById('modal-overlay')?.addEventListener('click', (e) => {
        if (e.target.id === 'modal-overlay') closeModal();
    });

    // Form submit
    document.getElementById('target-form')?.addEventListener('submit', saveTarget);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
        if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            document.getElementById('search-input')?.focus();
        }
    });
}

async function loadData() {
    await Promise.all([loadHealth(), loadTargets(), loadJobs()]);
}

// Health Check
async function loadHealth() {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    
    try {
        const res = await fetch(`${API}/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        
        if (data.status === 'healthy') {
            dot.classList.remove('error');
            text.textContent = 'System Online';
        } else {
            dot.classList.add('error');
            text.textContent = 'System Degraded';
        }
        
        document.getElementById('stats-targets').textContent = data.checks?.active_targets || 0;
    } catch (err) {
        console.error('Health check failed:', err);
        dot.classList.add('error');
        text.textContent = 'Connection Failed';
    }
}

// Targets
async function loadTargets() {
    try {
        const res = await fetch(`${API}/api/targets`);
        targets = await res.json();
        renderTargets();
        updateCompanyFilter();
    } catch (err) {
        console.error('Failed to load targets:', err);
    }
}

function renderTargets() {
    const grid = document.getElementById('targets-grid');
    if (!grid) return;

    if (targets.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <div class="empty-state-icon">🎯</div>
                <div class="empty-state-title">No targets yet</div>
                <div class="empty-state-description">Add a company to start tracking jobs</div>
                <button class="btn btn-primary" onclick="openModal()">Add Target</button>
            </div>
        `;
        return;
    }

    grid.innerHTML = targets.map(t => `
        <div class="target-card">
            <div class="target-header">
                <div class="target-company">🏢 ${esc(t.company_name)}</div>
                <span class="target-status ${t.active ? 'active' : 'paused'}">
                    ${t.active ? 'Active' : 'Paused'}
                </span>
            </div>
            <span class="target-keyword">${esc(t.role_keyword)}</span>
            <div class="target-url">${esc(t.careers_url)}</div>
            <div class="target-actions">
                <button class="btn btn-ghost" onclick="toggleTarget('${t.id}', ${!t.active})">
                    ${t.active ? '⏸ Pause' : '▶ Resume'}
                </button>
                <button class="btn btn-ghost" onclick="editTarget('${t.id}')">Edit</button>
                <button class="btn btn-danger" onclick="deleteTarget('${t.id}')">✕</button>
            </div>
        </div>
    `).join('');
}

// Jobs
async function loadJobs() {
    try {
        const res = await fetch(`${API}/api/jobs?limit=500`);
        jobs = await res.json();
        applyFilters();
        updateStats();
        updateLocationFilter();
    } catch (err) {
        console.error('Failed to load jobs:', err);
    }
}

function applyFilters() {
    filteredJobs = jobs.filter(job => {
        // Search
        if (filters.search) {
            const searchStr = `${job.title} ${job.company_name} ${job.location}`.toLowerCase();
            if (!searchStr.includes(filters.search)) return false;
        }
        
        // Company
        if (filters.company && job.company_name !== filters.company) return false;
        
        // Location
        if (filters.location && !job.location?.includes(filters.location)) return false;
        
        // Date range
        if (filters.dateRange !== 'all') {
            const foundAt = parseDate(job.found_at);
            const now = new Date();
            const dayMs = 86400000;
            
            if (filters.dateRange === 'today' && (now - foundAt) > dayMs) return false;
            if (filters.dateRange === 'week' && (now - foundAt) > 7 * dayMs) return false;
            if (filters.dateRange === 'month' && (now - foundAt) > 30 * dayMs) return false;
        }
        
        // Status
        if (filters.status !== 'all') {
            const status = job.status || 'new';
            if (filters.status !== status) return false;
        }
        
        return true;
    });
    
    currentPage = 1;
    renderJobs();
    updateFilterTags();
}

function renderJobs() {
    const tbody = document.getElementById('jobs-tbody');
    if (!tbody) return;

    if (filteredJobs.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <div class="empty-state-title">No jobs found</div>
                        <div class="empty-state-description">Try adjusting your filters or run a check</div>
                    </div>
                </td>
            </tr>
        `;
        document.getElementById('pagination')?.classList.add('hidden');
        return;
    }

    const start = (currentPage - 1) * perPage;
    const pageJobs = filteredJobs.slice(start, start + perPage);
    const now = new Date();
    const dayMs = 86400000;

    tbody.innerHTML = pageJobs.map(job => {
        const foundAt = parseDate(job.found_at);
        const isNew = (now - foundAt) < dayMs;
        const status = job.status || 'new';
        
        return `
            <tr class="${isNew ? 'is-new' : ''}">
                <td>
                    <div class="job-info">
                        <div class="job-title">
                            ${esc(job.title)}
                            ${isNew ? '<span class="new-badge">New</span>' : ''}
                        </div>
                        <div class="job-company">${esc(job.company_name)}</div>
                    </div>
                </td>
                <td class="job-location">${esc(job.location || 'N/A')}</td>
                <td>
                    <div class="job-date">${esc(job.posted_date || 'N/A')}</div>
                    <div class="job-date-sub">Found: ${formatDate(foundAt)}</div>
                </td>
                <td><span class="job-status ${status}">${status}</span></td>
                <td>
                    <div class="job-actions">
                        <button class="job-action-btn" title="Mark as Applied" onclick="updateJobStatus('${job.id}', 'applied')">✓</button>
                        <button class="job-action-btn" title="Save" onclick="updateJobStatus('${job.id}', 'saved')">★</button>
                        <button class="job-action-btn" title="Delete" onclick="deleteJob('${job.id}')">✕</button>
                    </div>
                </td>
                <td>
                    <a href="${esc(job.url)}" target="_blank" class="job-link">View →</a>
                </td>
            </tr>
        `;
    }).join('');

    renderPagination();
}

function renderPagination() {
    const pagination = document.getElementById('pagination');
    if (!pagination) return;

    const totalPages = Math.ceil(filteredJobs.length / perPage);
    if (totalPages <= 1) {
        pagination.classList.add('hidden');
        return;
    }

    pagination.classList.remove('hidden');
    
    document.getElementById('pagination-info').textContent = 
        `Showing ${(currentPage - 1) * perPage + 1}-${Math.min(currentPage * perPage, filteredJobs.length)} of ${filteredJobs.length}`;
    
    let btns = '';
    btns += `<button class="pagination-btn" onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>←</button>`;
    
    for (let i = 1; i <= Math.min(totalPages, 5); i++) {
        btns += `<button class="pagination-btn ${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }
    
    if (totalPages > 5) {
        btns += `<span style="color: var(--text-tertiary); padding: 0 0.5rem;">...</span>`;
        btns += `<button class="pagination-btn ${totalPages === currentPage ? 'active' : ''}" onclick="goToPage(${totalPages})">${totalPages}</button>`;
    }
    
    btns += `<button class="pagination-btn" onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>→</button>`;
    
    document.getElementById('pagination-controls').innerHTML = btns;
}

function goToPage(page) {
    const totalPages = Math.ceil(filteredJobs.length / perPage);
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    renderJobs();
    document.querySelector('.jobs-table')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function updateStats() {
    document.getElementById('stats-jobs').textContent = jobs.length;
    
    const now = new Date();
    const dayMs = 86400000;
    const newCount = jobs.filter(j => (now - parseDate(j.found_at)) < dayMs).length;
    document.getElementById('stats-new').textContent = newCount;
    
    if (jobs.length > 0) {
        const lastDate = parseDate(jobs[0].found_at);
        document.getElementById('stats-last').textContent = formatRelative(lastDate);
    }
}

function updateCompanyFilter() {
    const select = document.querySelector('[data-filter="company"]');
    if (!select) return;
    
    const companies = [...new Set(targets.map(t => t.company_name))].sort();
    select.innerHTML = '<option value="">All Companies</option>' + 
        companies.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
}

function updateLocationFilter() {
    const select = document.querySelector('[data-filter="location"]');
    if (!select) return;
    
    const locations = [...new Set(jobs.map(j => j.location).filter(Boolean))].sort();
    select.innerHTML = '<option value="">All Locations</option>' + 
        locations.slice(0, 20).map(l => `<option value="${esc(l)}">${esc(l)}</option>`).join('');
}

function updateFilterTags() {
    const container = document.getElementById('filter-tags');
    if (!container) return;
    
    let tags = '';
    if (filters.company) tags += `<span class="filter-tag">${esc(filters.company)} <span class="filter-tag-remove" onclick="removeFilter('company')">×</span></span>`;
    if (filters.location) tags += `<span class="filter-tag">${esc(filters.location)} <span class="filter-tag-remove" onclick="removeFilter('location')">×</span></span>`;
    if (filters.dateRange !== 'all') tags += `<span class="filter-tag">${filters.dateRange} <span class="filter-tag-remove" onclick="removeFilter('dateRange')">×</span></span>`;
    if (filters.status !== 'all') tags += `<span class="filter-tag">${filters.status} <span class="filter-tag-remove" onclick="removeFilter('status')">×</span></span>`;
    
    container.innerHTML = tags;
    
    const clearBtn = document.getElementById('clear-filters');
    if (clearBtn) clearBtn.style.display = tags ? 'block' : 'none';
}

function removeFilter(type) {
    if (type === 'dateRange' || type === 'status') filters[type] = 'all';
    else filters[type] = '';
    
    const select = document.querySelector(`[data-filter="${type}"]`);
    if (select) select.value = filters[type];
    
    applyFilters();
}

function clearFilters() {
    filters = { company: '', location: '', dateRange: 'all', status: 'all', search: '' };
    document.querySelectorAll('.filter-select').forEach(s => s.selectedIndex = 0);
    document.getElementById('search-input').value = '';
    applyFilters();
}

// Run Check
async function runJobCheck() {
    const btn = event.target.closest('button');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Checking...';
    
    try {
        const res = await fetch(`${API}/check-jobs`, { method: 'POST' });
        const data = await res.json();
        showToast(`Found ${data.new_jobs_count || 0} new jobs!`, 'success');
        loadJobs();
        loadHealth();
    } catch (err) {
        showToast('Check failed', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
    }
}

// Target CRUD
function openModal(id = null) {
    document.getElementById('modal-title').textContent = id ? 'Edit Target' : 'Add Target';
    document.getElementById('target-id').value = id || '';
    
    if (id) {
        const t = targets.find(x => x.id === id);
        if (t) {
            document.getElementById('company-name').value = t.company_name;
            document.getElementById('careers-url').value = t.careers_url;
            document.getElementById('role-keyword').value = t.role_keyword;
            document.getElementById('target-active').value = t.active ? 'true' : 'false';
        }
    } else {
        document.getElementById('target-form').reset();
        document.getElementById('target-active').value = 'true';
    }
    
    document.getElementById('modal-overlay').classList.add('active');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('active');
}

function editTarget(id) { openModal(id); }

async function saveTarget(e) {
    e.preventDefault();
    
    const id = document.getElementById('target-id').value;
    const data = {
        company_name: document.getElementById('company-name').value,
        careers_url: document.getElementById('careers-url').value,
        role_keyword: document.getElementById('role-keyword').value,
        active: document.getElementById('target-active').value === 'true'
    };
    
    try {
        const res = await fetch(`${API}/api/targets${id ? '/' + id : ''}`, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!res.ok) throw new Error();
        
        showToast(id ? 'Target updated' : 'Target added', 'success');
        closeModal();
        loadTargets();
        loadHealth();
    } catch (err) {
        showToast('Failed to save', 'error');
    }
}

async function toggleTarget(id, active) {
    try {
        await fetch(`${API}/api/targets/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active })
        });
        showToast(active ? 'Target activated' : 'Target paused', 'success');
        loadTargets();
        loadHealth();
    } catch (err) {
        showToast('Failed to update', 'error');
    }
}

async function deleteTarget(id) {
    if (!confirm('Delete this target?')) return;
    
    try {
        await fetch(`${API}/api/targets/${id}`, { method: 'DELETE' });
        showToast('Target deleted', 'success');
        loadTargets();
        loadHealth();
    } catch (err) {
        showToast('Failed to delete', 'error');
    }
}

// Job Actions
async function updateJobStatus(id, status) {
    try {
        const res = await fetch(`${API}/api/jobs/${id}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });
        
        if (!res.ok) throw new Error();
        
        // Update locally
        const job = jobs.find(j => j.id === id);
        if (job) {
            job.status = status;
            applyFilters();
        }
        showToast(`Marked as ${status}`, 'success');
    } catch (err) {
        // Fallback: update locally anyway
        const job = jobs.find(j => j.id === id);
        if (job) {
            job.status = status;
            applyFilters();
            showToast(`Marked as ${status}`, 'success');
        }
    }
}

async function deleteJob(id) {
    try {
        await fetch(`${API}/api/jobs/${id}`, { method: 'DELETE' });
        jobs = jobs.filter(j => j.id !== id);
        applyFilters();
        updateStats();
        showToast('Job removed', 'success');
    } catch (err) {
        showToast('Failed to delete', 'error');
    }
}

// View Switching
function switchView(view) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`[data-view="${view}"]`)?.classList.add('active');
    
    // Also update header tabs
    document.querySelectorAll('.header-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.header-tab[data-view="${view}"]`)?.classList.add('active');
    
    document.querySelectorAll('.view-section').forEach(s => s.style.display = 'none');
    const section = document.getElementById(`${view}-section`);
    if (section) section.style.display = 'block';
}

// Toast
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : '✕'}</span>
        <span class="toast-message">${message}</span>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Utilities
function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function parseDate(d) {
    if (!d) return new Date();
    if (d._seconds) return new Date(d._seconds * 1000);
    return new Date(d);
}

function formatDate(d) {
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(d);
}

function formatRelative(d) {
    const diff = Date.now() - d;
    const mins = Math.floor(diff / 60000);
    const hrs = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    if (hrs < 24) return `${hrs}h ago`;
    return `${days}d ago`;
}

function debounce(fn, delay) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn(...args), delay);
    };
}
