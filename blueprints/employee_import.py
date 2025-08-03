# Fixed critical sections of employee_import.py
# Replace these sections in your file

# 1. Fix the supervisor_required decorator (around line 25):
def supervisor_required(f):
    """Decorator to ensure user is a supervisor"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisor privileges required.', 'error')
            return redirect(url_for('main.employee_dashboard'))  # Fixed: added 'main.'
        return f(*args, **kwargs)
    return decorated_function

# 2. Fix all error redirects - here's the pattern to follow:
# ANYWHERE you see:
#   return redirect(url_for('dashboard'))
# REPLACE WITH:
#   return redirect(url_for('main.dashboard'))

# 3. Fix the download_employee_template route (around line 67):
@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee import template"""
    try:
        # ... template generation code ...
        
    except Exception as e:
        current_app.logger.error(f"Error generating template: {str(e)}")
        flash('Error generating template', 'error')
        return redirect(url_for('main.dashboard'))  # Fixed

# 4. Fix the upload_employees route (around line 179):
@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_employees():
    """Employee upload page and processing"""
    if request.method == 'GET':
        try:
            # ... statistics code ...
            
            return render_template('upload_employees_enhanced.html',
                                 employee_count=employee_count,
                                 recent_uploads=recent_uploads,
                                 crew_distribution=crew_distribution)
        except Exception as e:
            current_app.logger.error(f"Error loading upload page: {str(e)}")
            flash('Error loading page', 'error')
            return redirect(url_for('main.dashboard'))  # Fixed
    
    # ... POST handling code ...

# 5. Fix ALL template validation error checks
# In the validate_upload route (around line 703), make sure the response is correct:
@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """Generic validation endpoint that routes to specific validators based on upload type"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        upload_type = request.form.get('type', 'employee')  # Note: 'type' not 'upload_type'
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Route to appropriate validator based on type
        if upload_type == 'employee':
            return validate_employee_data()
        elif upload_type == 'overtime':
            return validate_overtime_data()
        elif upload_type == 'bulk_update':
            return validate_bulk_update()
        else:
            return jsonify({'success': False, 'error': f'Unknown upload type: {upload_type}'})
            
    except Exception as e:
        current_app.logger.error(f"Validation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Validation failed: {str(e)}'
        })

# 6. IMPORTANT: Check your main blueprint has the correct name
# In your app.py, make sure it's registered as 'main':
# from blueprints.main import main_bp
# app.register_blueprint(main_bp)  # This creates routes with 'main.' prefix
