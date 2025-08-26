{% extends "base.html" %}
{% block title %}Supervisor Dashboard{% endblock %}

{% block content %}
<div class="container-fluid">
    <div class="row mb-4">
        <div class="col-12">
            <h1 class="h2">Supervisor Dashboard</h1>
            <p class="text-muted">Welcome back, {{ current_user.name }}!</p>
        </div>
    </div>

    <!-- Statistics Row -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card stat-card">
                <div class="card-body">
                    <h6 class="text-muted">Pending Time Off</h6>
                    <h3>{{ pending_time_off or 0 }}</h3>
                    <small class="text-muted">Requests awaiting approval</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card stat-card">
                <div class="card-body">
                    <h6 class="text-muted">Pending Swaps</h6>
                    <h3>{{ pending_swaps or 0 }}</h3>
                    <small class="text-muted">Shift swap requests</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card stat-card">
                <div class="card-body">
                    <h6 class="text-muted">Total Employees</h6>
                    <h3>{{ total_employees or 0 }}</h3>
                    <small class="text-muted">Active workforce</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card stat-card">
                <div class="card-body">
                    <h6 class="text-muted">Coverage Gaps</h6>
                    <h3>{{ coverage_gaps or 0 }}</h3>
                    <small class="text-muted">Positions needing coverage</small>
                </div>
            </div>
        </div>
    </div>

    <!-- Quick Actions -->
    <div class="row mb-4">
        <div class="col-12">
            <h2 class="h4 mb-3">Quick Actions</h2>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.time_off_requests') }}" class="action-card text-center">
                <i class="bi bi-calendar-check action-icon"></i>
                <h5>Time Off Requests</h5>
                <p class="text-muted mb-0">Review and approve</p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.shift_swaps') }}" class="action-card text-center">
                <i class="bi bi-shuffle action-icon"></i>
                <h5>Shift Swaps</h5>
                <p class="text-muted mb-0">Manage swap requests</p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('schedule.view_schedules') }}" class="action-card text-center">
                <i class="bi bi-calendar3 action-icon"></i>
                <h5>View Schedule</h5>
                <p class="text-muted mb-0">Current schedules</p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('employee_import.upload_employees') }}" class="action-card text-center">
                <i class="bi bi-upload action-icon"></i>
                <h5>Upload Data</h5>
                <p class="text-muted mb-0">Import employees</p>
            </a>
        </div>
    </div>

    <!-- Schedule Management -->
    <div class="row mb-4">
        <div class="col-12">
            <h2 class="h4 mb-3">Schedule Management</h2>
        </div>
        <div class="col-md-4 mb-3">
            <a href="{{ url_for('schedule.view_schedules') }}" class="action-card">
                <i class="bi bi-calendar-week action-icon"></i>
                <h5>View Schedule</h5>
                <p class="text-muted mb-0">Current schedule</p>
            </a>
        </div>
        <div class="col-md-4 mb-3">
            <a href="{{ url_for('schedule.schedule_select') }}" class="action-card">
                <i class="bi bi-calendar-plus action-icon"></i>
                <h5>Create Schedule</h5>
                <p class="text-muted mb-0">Pattern-based scheduler</p>
            </a>
        </div>
        <div class="col-md-4 mb-3">
            <a href="{{ url_for('supervisor.vacation_calendar') }}" class="action-card">
                <i class="bi bi-calendar-heart action-icon"></i>
                <h5>Vacation Calendar</h5>
                <p class="text-muted mb-0">Time off overview</p>
            </a>
        </div>
    </div>

    <!-- Data Management -->
    <div class="row mb-4">
        <div class="col-12">
            <h2 class="h4 mb-3">Data Management</h2>
        </div>
        <div class="col-md-4 mb-3">
            <a href="{{ url_for('employee_import.upload_employees') }}" class="action-card">
                <i class="bi bi-file-earmark-excel action-icon"></i>
                <h5>Import Employees</h5>
                <p class="text-muted mb-0">Upload Excel files</p>
            </a>
        </div>
        <div class="col-md-4 mb-3">
            <a href="{{ url_for('employee_import.upload_overtime') }}" class="action-card">
                <i class="bi bi-clock-history action-icon"></i>
                <h5>Import Overtime</h5>
                <p class="text-muted mb-0">13-week history</p>
            </a>
        </div>
        <div class="col-md-4 mb-3">
            <a href="{{ url_for('employee_import.upload_history') }}" class="action-card">
                <i class="bi bi-clock-fill action-icon"></i>
                <h5>Upload History</h5>
                <p class="text-muted mb-0">View past uploads</p>
            </a>
        </div>
    </div>

    <!-- Employee Management -->
    <div class="row mb-4">
        <div class="col-12">
            <h2 class="h4 mb-3">Employee Management</h2>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('main.view_crews') }}" class="action-card">
                <i class="bi bi-people action-icon"></i>
                <h5>View All Crews</h5>
                <p class="text-muted mb-0">Crew assignments</p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.crew_management') }}" class="action-card">
                <i class="bi bi-people-fill action-icon"></i>
                <h5>Crew Management</h5>
                <p class="text-muted mb-0">Manage assignments</p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.employee_management') }}" class="action-card">
                <i class="bi bi-person-badge action-icon"></i>
                <h5>Employee List</h5>
                <p class="text-muted mb-0">All employees</p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('main.overtime_management') }}" class="action-card">
                <i class="bi bi-graph-up action-icon"></i>
                <h5>Overtime</h5>
                <p class="text-muted mb-0">Track overtime</p>
            </a>
        </div>
    </div>

    <!-- Requests & Coverage -->
    <div class="row mb-4">
        <div class="col-12">
            <h2 class="h4 mb-3">Requests & Coverage</h2>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.time_off_requests') }}" class="action-card">
                <i class="bi bi-calendar-x action-icon"></i>
                <h5>Time Off Requests</h5>
                <p class="text-muted mb-0">
                    {% if pending_time_off %}
                        <span class="badge bg-danger">{{ pending_time_off }} pending</span>
                    {% else %}
                        No pending
                    {% endif %}
                </p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.shift_swaps') }}" class="action-card">
                <i class="bi bi-arrow-left-right action-icon"></i>
                <h5>Shift Swaps</h5>
                <p class="text-muted mb-0">
                    {% if pending_swaps %}
                        <span class="badge bg-warning">{{ pending_swaps }} pending</span>
                    {% else %}
                        No pending
                    {% endif %}
                </p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.coverage_gaps') }}" class="action-card">
                <i class="bi bi-exclamation-triangle action-icon"></i>
                <h5>Coverage Gaps</h5>
                <p class="text-muted mb-0">Identify gaps</p>
            </a>
        </div>
        <div class="col-md-3 mb-3">
            <a href="{{ url_for('supervisor.coverage_needs') }}" class="action-card">
                <i class="bi bi-shield-check action-icon"></i>
                <h5>Coverage Needs</h5>
                <p class="text-muted mb-0">Requirements</p>
            </a>
        </div>
    </div>
</div>

<style>
.stat-card {
    background: linear-gradient(135deg, #4e73df 0%, #224abe 100%);
    color: white;
    border: none;
    transition: transform 0.2s;
}

.stat-card .card-body h6,
.stat-card .card-body h3,
.stat-card .card-body small {
    color: white !important;
}

.stat-card:hover {
    transform: translateY(-2px);
}

.stat-card h3 {
    font-size: 2.5rem;
    margin-bottom: 0;
}

.action-card {
    display: block;
    padding: 1.5rem;
    background: white;
    border-radius: 8px;
    text-decoration: none;
    color: inherit;
    transition: all 0.3s;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    height: 100%;
}

.action-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    text-decoration: none;
    color: inherit;
}

.action-icon {
    font-size: 2rem;
    color: #667eea;
    margin-bottom: 1rem;
    display: block;
}

.action-card h5 {
    color: #333;
    margin-bottom: 0.5rem;
}

.action-card p {
    color: #6c757d;
    font-size: 0.9rem;
}
</style>
{% endblock %}
