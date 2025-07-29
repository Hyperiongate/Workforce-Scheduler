// static/js/dashboard.js
// Operations Center Dashboard JavaScript

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Set up auto-refresh
    setInterval(refreshDashboard, 60000); // Refresh every minute
    
    // Set up quick action buttons
    setupQuickActions();
    
    // Set up priority action buttons
    setupPriorityActions();
    
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
});

// Refresh dashboard data
function refreshDashboard() {
    fetch('/api/dashboard-stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateDashboardStats(data.data);
                showNotification('Dashboard updated', 'success');
            }
        })
        .catch(error => {
            console.error('Error refreshing dashboard:', error);
        });
}

// Update dashboard statistics
function updateDashboardStats(data) {
    // Update staffing card
    const staffingCard = document.querySelector('.status-card:first-child');
    if (staffingCard) {
        staffingCard.querySelector('h3').textContent = `${data.current_staffing}/${data.total_required}`;
        staffingCard.querySelector('small').textContent = `${data.shortage} positions unfilled`;
        
        // Update card border color based on severity
        staffingCard.classList.remove('status-critical', 'status-warning', 'status-good');
        if (data.shortage > 2) {
            staffingCard.classList.add('status-critical');
        } else if (data.shortage > 0) {
            staffingCard.classList.add('status-warning');
        } else {
            staffingCard.classList.add('status-good');
        }
    }
    
    // Update time
    document.querySelector('.live-indicator span:last-child').textContent = 
        `Live Status • ${new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })} • ${new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}`;
}

// Set up quick action buttons
function setupQuickActions() {
    document.querySelectorAll('.quick-action-btn').forEach(btn => {
        btn.addEventListener('click', handleQuickAction);
    });
}

// Handle quick action clicks
async function handleQuickAction(e) {
    e.preventDefault();
    const action = e.currentTarget.querySelector('span').textContent.toLowerCase().replace(/\s+/g, '_');
    
    try {
        const response = await fetch('/api/quick-action', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: action,
                data: {}
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            if (result.redirect) {
                window.location.href = result.redirect;
            } else if (result.casuals) {
                showCasualWorkersModal(result.casuals);
            } else {
                showNotification('Action completed successfully', 'success');
            }
        } else {
            showNotification(result.error || 'Action failed', 'danger');
        }
    } catch (error) {
        showNotification('Error performing action', 'danger');
        console.error('Quick action error:', error);
    }
}

// Set up priority action buttons
function setupPriorityActions() {
    // Post Overtime buttons
    document.querySelectorAll('.btn-post-overtime').forEach(btn => {
        btn.addEventListener('click', handlePostOvertime);
    });
    
    // Mandate buttons
    document.querySelectorAll('.btn-mandate').forEach(btn => {
        btn.addEventListener('click', handleMandate);
    });
    
    // Review buttons
    document.querySelectorAll('.btn-review').forEach(btn => {
        btn.addEventListener('click', handleReview);
    });
    
    // Coverage gap buttons
    document.querySelectorAll('.btn-fill-gap').forEach(btn => {
        btn.addEventListener('click', handleFillGap);
    });
}

// Handle post overtime action
async function handlePostOvertime(e) {
    const actionItem = e.target.closest('.action-item');
    const positionId = actionItem.dataset.positionId;
    const crew = actionItem.dataset.crew;
    const shift = actionItem.dataset.shift || 'day';
    
    try {
        const response = await fetch('/overtime/api/post', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                position_id: positionId,
                date: new Date().toISOString().split('T')[0],
                shift_type: shift,
                crew: crew,
                urgent: true
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(`Overtime posted to ${result.notifications_sent} employees`, 'success');
            // Remove or update the action item
            actionItem.style.opacity = '0.5';
            e.target.disabled = true;
            e.target.textContent = 'Posted';
        } else {
            showNotification(result.error || 'Failed to post overtime', 'danger');
        }
    } catch (error) {
        showNotification('Error posting overtime', 'danger');
        console.error('Post overtime error:', error);
    }
}

// Handle mandatory assignment
async function handleMandate(e) {
    if (!confirm('Are you sure you want to assign mandatory overtime? This will assign to the employee with least seniority.')) {
        return;
    }
    
    const actionItem = e.target.closest('.action-item');
    const positionId = actionItem.dataset.positionId;
    const shift = actionItem.dataset.shift || 'day';
    
    try {
        const response = await fetch('/overtime/api/assign-mandatory', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                position_id: positionId,
                date: new Date().toISOString().split('T')[0],
                shift_type: shift
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(`Mandatory overtime assigned to ${result.assigned_to.name}`, 'success');
            actionItem.style.opacity = '0.5';
            e.target.disabled = true;
            e.target.textContent = 'Assigned';
        } else {
            showNotification(result.error || 'Failed to assign overtime', 'danger');
        }
    } catch (error) {
        showNotification('Error assigning overtime', 'danger');
        console.error('Mandate error:', error);
    }
}

// Handle review actions
function handleReview(e) {
    const actionItem = e.target.closest('.action-item');
    const requestId = actionItem.dataset.requestId;
    const swapId = actionItem.dataset.swapId;
    
    if (requestId) {
        window.location.href = `/supervisor/time-off-requests#request-${requestId}`;
    } else if (swapId) {
        window.location.href = `/supervisor/swap-requests#swap-${swapId}`;
    }
}

// Handle fill gap action
async function handleFillGap(e) {
    const row = e.target.closest('tr');
    const date = row.dataset.date;
    const shift = row.dataset.shift;
    const position = row.dataset.position;
    
    try {
        const response = await fetch('/api/fill-gap', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                date: date,
                shift: shift,
                position: position
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(result.message, 'success');
            e.target.disabled = true;
            e.target.textContent = 'Posted';
        } else {
            showNotification(result.error || 'Failed to fill gap', 'danger');
        }
    } catch (error) {
        showNotification('Error filling gap', 'danger');
        console.error('Fill gap error:', error);
    }
}

// Show casual workers modal
function showCasualWorkersModal(casuals) {
    // Create modal HTML
    const modalHtml = `
        <div class="modal fade" id="casualWorkersModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Available Casual Workers</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Phone</th>
                                    <th>Rating</th>
                                    <th>Last Worked</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${casuals.map(casual => `
                                    <tr>
                                        <td>${casual.name}</td>
                                        <td><a href="tel:${casual.phone}">${casual.phone}</a></td>
                                        <td>${'⭐'.repeat(casual.rating || 0)}</td>
                                        <td>${casual.last_worked || 'Never'}</td>
                                        <td>
                                            <button class="btn btn-sm btn-primary" onclick="callCasual('${casual.phone}', '${casual.name}')">
                                                <i class="bi bi-telephone"></i> Call
                                            </button>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('casualWorkersModal'));
    modal.show();
    
    // Clean up on close
    document.getElementById('casualWorkersModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

// Call casual worker
function callCasual(phone, name) {
    if (confirm(`Call ${name} at ${phone}?`)) {
        window.location.href = `tel:${phone}`;
        showNotification(`Calling ${name}...`, 'info');
    }
}

// Show notification
function showNotification(message, type = 'info') {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show position-fixed top-0 end-0 m-3" style="z-index: 9999;">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', alertHtml);
    
    // Auto-dismiss after 3 seconds
    setTimeout(() => {
        const alert = document.querySelector('.alert:last-child');
        if (alert) {
            alert.remove();
        }
    }, 3000);
}

// Export functions for use in templates
window.dashboardFunctions = {
    refreshDashboard,
    showNotification,
    handlePostOvertime,
    handleMandate
};
