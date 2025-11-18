// API Base URL - Use current origin for production compatibility
const API_BASE = window.location.origin;

// Session management - Use sessionStorage instead of localStorage
// sessionStorage automatically clears when tab/browser closes
function getToken() {
    return sessionStorage.getItem('access_token');
}

function setToken(token) {
    sessionStorage.setItem('access_token', token);
}

function removeToken() {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('role');
}

// Socket.IO connection
const token = getToken();
const socket = io(API_BASE, token ? { auth: { token: `Bearer ${token}` } } : {});

const SENTIMENT_CLASSES = ['positive', 'negative', 'neutral', 'mixed'];
const URGENCY_CLASSES = ['critical', 'high', 'medium', 'low'];

const SecurityUtils = {
    escapeHtml(text = '') {
        const div = document.createElement('div');
        div.textContent = text ?? '';
        return div.innerHTML;
    },
    safeClass(value, allowed = []) {
        return allowed.includes(value) ? value : '';
    }
};

function redirectToLogin() {
    try { removeToken(); } catch {}
    showAlert('Session expired. Redirecting to staff login...', 'error');
    setTimeout(() => { window.location.href = '/staff'; }, 1000);
}

function renderAuthControls() {
    const container = document.getElementById('authControls');
    if (!container) return;
    const currentToken = getToken();
    if (currentToken) {
        container.innerHTML = `<button class="btn btn-secondary" id="logoutBtn"><i class="fas fa-sign-out-alt"></i> Logout</button>`;
        const btn = document.getElementById('logoutBtn');
        btn && btn.addEventListener('click', () => {
            try { removeToken(); } catch {}
            window.location.href = '/staff';
        });
    } else {
        container.innerHTML = `<a class="btn btn-secondary" href="/staff"><i class="fas fa-sign-in-alt"></i> Staff Login</a>`;
    }
}

// Session management - Handle tab change and browser close
function setupSessionManagement() {
    // Detect tab visibility change (user switches tabs)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            // Tab hidden - user switched to another tab
            // Don't clear session yet, just log
            console.log('Tab hidden');
        } else {
            // Tab visible again - check if session still valid
            const currentToken = getToken();
            if (currentToken) {
                // Validate token when tab becomes visible
                fetch(`${API_BASE}/auth/me`, {
                    method: 'GET',
                    headers: { 'Authorization': `Bearer ${currentToken}` }
                }).catch(() => {
                    // If validation fails, clear session
                    removeToken();
                });
            }
        }
    });
    
    // Detect browser close/refresh
    window.addEventListener('beforeunload', () => {
        // sessionStorage automatically clears on tab close
        // But we can also explicitly clear if needed
        console.log('Page unloading - session will be cleared');
    });
    
    // Detect page navigation (back/forward)
    window.addEventListener('pageshow', (event) => {
        // If page loaded from cache (back/forward navigation)
        if (event.persisted) {
            // Check if token still exists
            const currentToken = getToken();
            if (!currentToken) {
                // Token cleared (tab was closed), redirect to login
                window.location.href = '/staff';
            }
        }
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Setup session management
    setupSessionManagement();
    
    // Check if user is logged in
    const currentToken = getToken();
    const isStaff = !!currentToken;

    renderAuthControls();

    // Toggle UI based on role
    const submitBtn = document.getElementById('submitTabBtn');
    const dashboardBtn = document.getElementById('dashboardTabBtn');
    const urgentBtn = document.getElementById('urgentTabBtn');
    const analyticsBtn = document.getElementById('analyticsTabBtn');

    const submitTabEl = document.getElementById('submitTab');
    const dashboardTabEl = document.getElementById('dashboardTab');
    const urgentTabEl = document.getElementById('urgentTab');
    const analyticsTabEl = document.getElementById('analyticsTab');

    if (isStaff) {
        // Hide patient form for staff
        if (submitBtn) submitBtn.style.display = 'none';
        if (submitTabEl) submitTabEl.style.display = 'none';

        // Ensure a staff tab is active
        dashboardBtn && dashboardBtn.classList.add('active');
        dashboardTabEl && dashboardTabEl.classList.add('active');
        // Remove active from submit if present
        submitBtn && submitBtn.classList.remove('active');
        submitTabEl && submitTabEl.classList.remove('active');
    } else {
        // Hide staff tabs for patients
        if (dashboardBtn) dashboardBtn.style.display = 'none';
        if (urgentBtn) urgentBtn.style.display = 'none';
        if (analyticsBtn) analyticsBtn.style.display = 'none';
        if (dashboardTabEl) dashboardTabEl.style.display = 'none';
        if (urgentTabEl) urgentTabEl.style.display = 'none';
        if (analyticsTabEl) analyticsTabEl.style.display = 'none';

        // Ensure submit is active
        submitBtn && submitBtn.classList.add('active');
        submitTabEl && submitTabEl.classList.add('active');
    }

    // Set default visit date to today
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('visitDate').value = now.toISOString().slice(0, 16);

    // Load initial data
    if (document.getElementById('dashboardTab').classList.contains('active')) {
        loadFeedback();
    }
    if (document.getElementById('urgentTab').classList.contains('active')) {
        loadUrgentFeedback();
    }
    if (document.getElementById('analyticsTab').classList.contains('active')) {
        loadAnalytics();
    }
    
    // Auto-refresh urgent tab every 30 seconds if it's active
    setInterval(() => {
        if (document.getElementById('urgentTab').classList.contains('active')) {
            loadUrgentFeedback();
        }
    }, 30000); // 30 seconds

    // Socket.IO event listeners
    socket.on('connect', () => {
        console.log('Connected to server');
        showAlert('Connected to real-time updates', 'success');
    });

    socket.on('new_feedback', (data) => {
        showAlert(`New feedback received from ${data.department}`, 'info');
        if (document.getElementById('dashboardTab').classList.contains('active')) {
            loadFeedback();
        }
        // Note: new_feedback doesn't auto-refresh urgent tab since it may not be critical yet
    });

    socket.on('urgent_alert', (data) => {
        showCriticalAlert(data);
        showAlert(`🚨 URGENT: Critical feedback from ${data.department} - ${data.urgency_reason}`, 'error');
        if (document.getElementById('dashboardTab').classList.contains('active')) {
            loadFeedback();
        }
        // Auto-refresh urgent tab if it's currently active
        if (document.getElementById('urgentTab').classList.contains('active')) {
            loadUrgentFeedback();
        }
    });

    socket.on('analysis_complete', (data) => {
        showAlert(`Analysis complete for feedback #${data.feedback_id}`, 'success');
        if (document.getElementById('dashboardTab').classList.contains('active')) {
            loadFeedback();
        }
        // If analysis completes and it's critical, refresh urgent tab if active
        if (document.getElementById('urgentTab').classList.contains('active')) {
            loadUrgentFeedback();
        }
    });
});

// Tab switching
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab
    document.getElementById(tabName + 'Tab').classList.add('active');
    event.target.closest('.tab-btn').classList.add('active');

    // Load data if needed
    if (tabName === 'dashboard') {
        loadFeedback();
    } else if (tabName === 'urgent') {
        console.log('Urgent tab activated - loading urgent feedback');
        loadUrgentFeedback();
    } else if (tabName === 'analytics') {
        loadAnalytics();
    }
}

// Rating display
function updateRatingDisplay(value) {
    document.getElementById('ratingValue').textContent = value;
    const stars = '★'.repeat(value) + '☆'.repeat(5 - value);
    document.getElementById('starsDisplay').textContent = stars;
}

// Form submission
document.getElementById('feedbackForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = {
        patient_name: document.getElementById('patientName').value || null,
        visit_date: document.getElementById('visitDate').value,
        department: document.getElementById('department').value,
        doctor_name: document.getElementById('doctorName').value || null,
        feedback_text: document.getElementById('feedbackText').value,
        rating: parseInt(document.getElementById('rating').value)
    };

    try {
        const response = await fetch(`${API_BASE}/feedback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        if (response.ok) {
            const data = await response.json();
            // Show confirmation page
            showConfirmation();
        } else {
            const error = await response.json();
            showAlert(`Error: ${error.detail || 'Failed to submit feedback'}`, 'error');
        }
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
    }
});

// Show confirmation page
function showConfirmation() {
    document.getElementById('feedbackFormContainer').style.display = 'none';
    document.getElementById('confirmationMessage').style.display = 'block';
}

// Reset form
function resetForm() {
    document.getElementById('feedbackForm').reset();
    document.getElementById('confirmationMessage').style.display = 'none';
    document.getElementById('feedbackFormContainer').style.display = 'block';
    updateRatingDisplay(3);
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('visitDate').value = now.toISOString().slice(0, 16);
}

// Load feedback list (table format)
async function loadFeedback() {
    const tableBody = document.getElementById('feedbackTableBody');
    tableBody.innerHTML = '<tr><td colspan="9" class="loading">Loading feedback...</td></tr>';

    const department = document.getElementById('filterDepartment')?.value || '';
    const status = document.getElementById('filterStatus')?.value || '';
    const urgency = document.getElementById('filterUrgency')?.value || '';

    try {
        let url = `${API_BASE}/feedback/all?limit=100`;
        if (department) url += `&department=${encodeURIComponent(department)}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        if (urgency) url += `&priority=${encodeURIComponent(urgency)}`;

        const headers = {};
        const currentToken = getToken();
        if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
        const response = await fetch(url, { headers });
        const data = await response.json();
        if (response.status === 401) {
            return redirectToLogin();
        }

        if (data.feedbacks && data.feedbacks.length > 0) {
            tableBody.innerHTML = '';
            let criticalCount = 0;
            let pendingCount = 0;

            data.feedbacks.forEach(feedback => {
                const row = createFeedbackTableRow(feedback);
                tableBody.appendChild(row);
                if (feedback.urgency === 'critical') criticalCount++;
                if (feedback.status === 'pending_analysis') pendingCount++;
            });

            // Update stats
            document.getElementById('totalCount').textContent = data.total || data.feedbacks.length;
            document.getElementById('criticalCount').textContent = criticalCount;
            document.getElementById('pendingCount').textContent = pendingCount;
        } else {
            tableBody.innerHTML = '<tr><td colspan="9" class="loading">No feedback found</td></tr>';
        }
    } catch (error) {
        tableBody.innerHTML = `<tr><td colspan="9" class="loading">Error loading feedback: ${SecurityUtils.escapeHtml(error.message || 'Unknown error')}</td></tr>`;
    }
}

// Create table row for feedback
function createFeedbackTableRow(feedback) {
    const row = document.createElement('tr');
    if (feedback.urgency === 'critical') {
        row.classList.add('critical-row');
    }

    const feedbackPreview = feedback.feedback_text.length > 100 
        ? feedback.feedback_text.substring(0, 100) + '...' 
        : feedback.feedback_text;
    const safeSentimentClass = SecurityUtils.safeClass(feedback.sentiment || '', SENTIMENT_CLASSES);
    const safeUrgencyClass = SecurityUtils.safeClass(feedback.urgency || '', URGENCY_CLASSES);

    row.innerHTML = `
        <td>#${SecurityUtils.escapeHtml(String(feedback.id))}</td>
        <td>${SecurityUtils.escapeHtml(feedback.patient_name || 'Anonymous')}</td>
        <td>${SecurityUtils.escapeHtml(feedback.department)}</td>
        <td>${SecurityUtils.escapeHtml(feedbackPreview)}</td>
        <td>
            <span class="badge">${feedback.rating}/5</span>
        </td>
        <td>
            <span class="badge">${SecurityUtils.escapeHtml(feedback.status || 'pending')}</span>
        </td>
        <td>
            ${feedback.sentiment ? `<span class="badge ${safeSentimentClass}">${SecurityUtils.escapeHtml(feedback.sentiment)}</span>` : 
              feedback.status === 'analysis_failed' ? '<span class="badge" style="background: #fee2e2; color: #991b1b;">Analysis Failed</span>' :
              feedback.analysis_status === 'pending' ? '<span class="badge" style="background: #fef3c7; color: #92400e;">Analyzing...</span>' : 
              '<span class="badge" style="background: #e5e7eb; color: #6b7280;">Pending</span>'}
        </td>
        <td>
            ${feedback.urgency ? `<span class="badge ${safeUrgencyClass}">${SecurityUtils.escapeHtml(feedback.urgency)}</span>` : 
              feedback.status === 'analysis_failed' ? '<span class="badge" style="background: #fee2e2; color: #991b1b;">Analysis Failed</span>' :
              feedback.analysis_status === 'pending' ? '<span class="badge" style="background: #fef3c7; color: #92400e;">Analyzing...</span>' : 
              '<span class="badge" style="background: #e5e7eb; color: #6b7280;">Pending</span>'}
        </td>
        <td>
            <div class="action-buttons">
                <button class="btn btn-small btn-view" onclick="viewFeedback(${feedback.id})">
                    <i class="fas fa-eye"></i> View
                </button>
                <button class="btn btn-small btn-action" onclick="openActionModal(${feedback.id})">
                    <i class="fas fa-tasks"></i> Action
                </button>
                ${feedback.status === 'analysis_failed' ? `
                    <button class="btn btn-small" style="background: #f59e0b; color: white;" onclick="retryAnalysis(${feedback.id})" title="Retry AI Analysis">
                        <i class="fas fa-redo"></i> Retry
                    </button>
                ` : ''}
            </div>
        </td>
    `;

    return row;
}

// Load urgent feedback
async function loadUrgentFeedback() {
    const container = document.getElementById('urgentFeedbackList');
    if (!container) {
        console.error('urgentFeedbackList container not found');
        return;
    }
    
    container.innerHTML = '<div class="loading">Loading urgent feedback...</div>';

    try {
        const headers = {};
        const currentToken = getToken();
        if (currentToken) {
            headers['Authorization'] = `Bearer ${currentToken}`;
        } else {
            console.warn('No token found - urgent feedback requires authentication');
            container.innerHTML = '<div class="loading">Please login to view urgent feedback</div>';
            return;
        }
        
        console.log('Fetching urgent feedback from:', `${API_BASE}/feedback/urgent?limit=100`);
        const response = await fetch(`${API_BASE}/feedback/urgent?limit=100`, { headers });
        
        if (response.status === 401) {
            console.error('Unauthorized - redirecting to login');
            return redirectToLogin();
        }
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Failed to load urgent feedback:', response.status, errorText);
            container.innerHTML = `<div class="loading">Error loading urgent feedback: ${response.status} ${response.statusText}</div>`;
            return;
        }
        
        const data = await response.json();
        console.log('Urgent feedback response:', data);

        if (data.urgent_feedbacks && data.urgent_feedbacks.length > 0) {
            container.innerHTML = '';
            data.urgent_feedbacks.forEach(feedback => {
                const item = createUrgentFeedbackItem(feedback);
                container.appendChild(item);
            });
            console.log(`Loaded ${data.urgent_feedbacks.length} urgent feedback items`);
        } else {
            container.innerHTML = '<div class="loading">No urgent feedback found</div>';
            console.log('No urgent feedback found in response');
        }
    } catch (error) {
        console.error('Exception loading urgent feedback:', error);
        container.innerHTML = `<div class="loading">Error loading urgent feedback: ${SecurityUtils.escapeHtml(error.message || 'Unknown error')}</div>`;
    }
}

// Create urgent feedback item
function createUrgentFeedbackItem(feedback) {
    const item = document.createElement('div');
    item.className = 'feedback-item critical';

    const flags = feedback.urgency_flags && feedback.urgency_flags.length > 0
        ? feedback.urgency_flags.map(flag => `<span class="badge critical">${SecurityUtils.escapeHtml(flag)}</span>`).join(' ')
        : '';
    const safeSentimentClass = SecurityUtils.safeClass(feedback.sentiment || '', SENTIMENT_CLASSES);

    item.innerHTML = `
        <div class="feedback-header">
            <div>
                <h3>🚨 Critical: ${SecurityUtils.escapeHtml(feedback.patient_name || 'Anonymous')} - ${SecurityUtils.escapeHtml(feedback.department)}</h3>
                <div class="feedback-meta">
                    <span class="badge critical">CRITICAL</span>
                    ${feedback.sentiment ? `<span class="badge ${safeSentimentClass}">${SecurityUtils.escapeHtml(feedback.sentiment)}</span>` : ''}
                    <span class="badge">Rating: ${feedback.rating}/5</span>
                    ${flags}
                </div>
            </div>
        </div>
        <div class="feedback-text">
            <strong>Urgency Reason:</strong> ${SecurityUtils.escapeHtml(feedback.urgency_reason || 'Not specified')}<br><br>
            <strong>Feedback:</strong> ${SecurityUtils.escapeHtml(feedback.feedback_text)}
        </div>
        ${feedback.actionable_insights ? `
            <div style="margin-top: 15px; padding: 15px; background: #fef3c7; border-radius: 8px;">
                <strong>Actionable Insights:</strong> ${SecurityUtils.escapeHtml(feedback.actionable_insights)}
            </div>
        ` : ''}
        <div class="feedback-footer">
            <span><i class="fas fa-calendar"></i> ${new Date(feedback.visit_date).toLocaleDateString()}</span>
            <span><i class="fas fa-user-md"></i> ${SecurityUtils.escapeHtml(feedback.doctor_name || 'N/A')}</span>
            <span><i class="fas fa-tag"></i> ${SecurityUtils.escapeHtml(feedback.primary_category || 'Uncategorized')}</span>
            <div class="action-buttons">
                <button class="btn btn-small btn-view" onclick="viewFeedback(${feedback.id})">
                    <i class="fas fa-eye"></i> View Details
                </button>
                <button class="btn btn-small btn-action" onclick="openActionModal(${feedback.id})">
                    <i class="fas fa-tasks"></i> Take Action
                </button>
            </div>
        </div>
    `;

    return item;
}

// Show critical alert banner
function showCriticalAlert(data) {
    const container = document.getElementById('criticalAlerts');
    const alert = document.createElement('div');
    alert.className = 'critical-alert-banner';
    alert.innerHTML = `
        <i class="fas fa-exclamation-triangle"></i>
        <div class="critical-alert-content">
            <h3>🚨 Critical Feedback Alert</h3>
            <p><strong>${SecurityUtils.escapeHtml(data.feedback_preview)}</strong></p>
            <p>Department: ${SecurityUtils.escapeHtml(data.department)} | Reason: ${SecurityUtils.escapeHtml(data.urgency_reason || '')}</p>
        </div>
        <button class="btn btn-secondary" onclick="viewFeedback(${data.feedback_id})">
            View Details
        </button>
    `;
    container.appendChild(alert);
    
    // Auto remove after 10 seconds
    setTimeout(() => {
        alert.remove();
    }, 10000);
}

// Open action modal
function openActionModal(feedbackId) {
    document.getElementById('actionFeedbackId').value = feedbackId;
    document.getElementById('actionModal').style.display = 'block';
}

// Close action modal
function closeActionModal() {
    document.getElementById('actionModal').style.display = 'none';
    document.getElementById('actionForm').reset();
}

// Handle action form submission
document.getElementById('actionForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const feedbackId = document.getElementById('actionFeedbackId').value;
    const status = document.getElementById('actionStatus').value;
    const staffNote = document.getElementById('staffNote').value;
    const assignedDepartment = document.getElementById('assignedDepartment').value;

    try {
        const headers = { 'Content-Type': 'application/json' };
        const currentToken = getToken();
        if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
        const response = await fetch(`${API_BASE}/feedback/${feedbackId}/update`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                status: status,
                staff_note: staffNote || null,
                assigned_department: assignedDepartment || null
            })
        });

        if (response.ok) {
            showAlert('Action saved successfully!', 'success');
            closeActionModal();
            loadFeedback();
            // Also refresh urgent tab if it's active
            if (document.getElementById('urgentTab').classList.contains('active')) {
                loadUrgentFeedback();
            }
        } else {
            const error = await response.json();
            if (response.status === 401) return redirectToLogin();
            showAlert(`Error: ${error.detail || 'Failed to save action'}`, 'error');
        }
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
    }
});

// View feedback details
async function viewFeedback(id) {
    try {
        const headers = {};
        const currentToken = getToken();
        if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
        const response = await fetch(`${API_BASE}/feedback/${id}`, { headers });
        const feedback = await response.json();
        if (response.status === 401) {
            return redirectToLogin();
        }

        const modal = document.getElementById('feedbackModal');
        const modalBody = document.getElementById('modalBody');

        let analysisHtml = '';
        if (feedback.analysis) {
            const a = feedback.analysis;
            const safeSentiment = SecurityUtils.escapeHtml(a.sentiment || '');
            const sentimentClass = SecurityUtils.safeClass(a.sentiment || '', SENTIMENT_CLASSES);
            const urgencyClass = SecurityUtils.safeClass(a.urgency || '', URGENCY_CLASSES);
            analysisHtml = `
                <div class="analytics-section">
                    <h3>AI Analysis</h3>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-icon ${sentimentClass}">
                                <i class="fas fa-brain"></i>
                            </div>
                            <div class="stat-info">
                                <h3>${safeSentiment}</h3>
                                <p>Sentiment (${(a.confidence_score * 100).toFixed(0)}% confidence)</p>
                            </div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-icon ${urgencyClass === 'critical' ? 'critical' : ''}">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="stat-info">
                                <h3>${SecurityUtils.escapeHtml(a.urgency || '')}</h3>
                                <p>Urgency Level</p>
                            </div>
                        </div>
                    </div>
                    ${a.urgency_reason ? `<p><strong>Urgency Reason:</strong> ${SecurityUtils.escapeHtml(a.urgency_reason)}</p>` : ''}
                    ${a.actionable_insights ? `<p><strong>Actionable Insights:</strong> ${SecurityUtils.escapeHtml(a.actionable_insights)}</p>` : ''}
                    ${a.key_points && a.key_points.length > 0 ? `
                        <h4>Key Points:</h4>
                        <ul>
                            ${a.key_points.map(point => `<li>${SecurityUtils.escapeHtml(point)}</li>`).join('')}
                        </ul>
                    ` : ''}
                </div>
            `;
        }

        modalBody.innerHTML = `
            <h2>Feedback Details #${feedback.id}</h2>
            <div class="card">
                <p><strong>Patient:</strong> ${SecurityUtils.escapeHtml(feedback.patient_name || 'Anonymous')}</p>
                <p><strong>Department:</strong> ${SecurityUtils.escapeHtml(feedback.department)}</p>
                <p><strong>Doctor:</strong> ${SecurityUtils.escapeHtml(feedback.doctor_name || 'N/A')}</p>
                <p><strong>Visit Date:</strong> ${new Date(feedback.visit_date).toLocaleString()}</p>
                <p><strong>Rating:</strong> ${feedback.rating}/5</p>
                <p><strong>Status:</strong> ${SecurityUtils.escapeHtml(feedback.status)}</p>
                <h3>Feedback:</h3>
                <p>${SecurityUtils.escapeHtml(feedback.feedback_text)}</p>
            </div>
            ${analysisHtml}
        `;

        modal.style.display = 'block';
    } catch (error) {
        showAlert(`Error loading feedback: ${error.message}`, 'error');
    }
}

// Close modal
function closeModal() {
    document.getElementById('feedbackModal').style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const feedbackModal = document.getElementById('feedbackModal');
    const actionModal = document.getElementById('actionModal');
    if (event.target === feedbackModal) {
        feedbackModal.style.display = 'none';
    }
    if (event.target === actionModal) {
        actionModal.style.display = 'none';
    }
}

// Load analytics
async function loadAnalytics() {
    try {
        const headers = {};
        const currentToken = getToken();
        if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
        const [summaryResponse, trendsResponse] = await Promise.all([
            fetch(`${API_BASE}/analytics/summary`, { headers }),
            fetch(`${API_BASE}/analytics/trends`, { headers })
        ]);
        if (summaryResponse.status === 401 || trendsResponse.status === 401) return redirectToLogin();

        const summary = await summaryResponse.json();
        const trends = await trendsResponse.json();

        // Update stats
        document.getElementById('totalFeedback').textContent = summary.total_feedback || 0;
        document.getElementById('positiveCount').textContent = summary.sentiment_breakdown?.positive || 0;
        document.getElementById('negativeCount').textContent = summary.sentiment_breakdown?.negative || 0;
        
        // Calculate critical count (would need to filter from trends or add to summary)
        document.getElementById('criticalCount').textContent = 'N/A';

        // Department ratings
        const deptContainer = document.getElementById('departmentRatings');
        if (summary.department_ratings && summary.department_ratings.length > 0) {
            deptContainer.innerHTML = summary.department_ratings.map(dept => `
                <div class="department-item">
                    <div>
                        <strong>${dept.department}</strong>
                        <p>${dept.feedback_count} feedback(s)</p>
                    </div>
                    <div>
                        <strong>${dept.average_rating.toFixed(1)}</strong>
                        <p>Average Rating</p>
                    </div>
                </div>
            `).join('');
        } else {
            deptContainer.innerHTML = '<p>No department data available</p>';
        }

        // Top issues
        const issuesContainer = document.getElementById('topIssues');
        if (summary.top_issues && summary.top_issues.length > 0) {
            issuesContainer.innerHTML = summary.top_issues.map(issue => `
                <div class="issue-item">
                    <span>${issue.category}</span>
                    <span class="badge">${issue.count} occurrences</span>
                </div>
            `).join('');
        } else {
            issuesContainer.innerHTML = '<p>No issues data available</p>';
        }
    } catch (error) {
        console.error('Error loading analytics:', error);
        showAlert(`Error loading analytics: ${error.message}`, 'error');
    }
}

// Show alert
function showAlert(message, type = 'info') {
    const container = document.getElementById('alertContainer');
    const alert = document.createElement('div');
    alert.className = `alert ${type}`;
    const icon = document.createElement('i');
    icon.className = `fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}`;
    const span = document.createElement('span');
    span.textContent = message;
    alert.appendChild(icon);
    alert.appendChild(span);
    
    container.appendChild(alert);
    
    setTimeout(() => {
        alert.remove();
    }, 5000);
}

// Retry analysis for failed feedback
async function retryAnalysis(feedbackId) {
    try {
        const headers = { 'Content-Type': 'application/json' };
        const currentToken = getToken();
        if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
        
        const response = await fetch(`${API_BASE}/feedback/${feedbackId}/retry-analysis`, {
            method: 'POST',
            headers
        });
        
        if (response.ok) {
            showAlert('Analysis retry initiated. Please wait...', 'success');
            // Refresh after 3 seconds to see updated status
            setTimeout(() => {
                if (document.getElementById('dashboardTab').classList.contains('active')) {
                    loadFeedback();
                }
            }, 3000);
        } else {
            const error = await response.json();
            if (response.status === 401) return redirectToLogin();
            showAlert(`Error: ${error.detail || 'Failed to retry analysis'}`, 'error');
        }
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
    }
}

// Initialize rating display
updateRatingDisplay(3);

