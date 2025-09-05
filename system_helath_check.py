#!/usr/bin/env python3
"""
Excel Upload System Health Check & Auto-Fix Script
Run this to verify and fix your Excel upload system
"""

import os
import sys
import json
from pathlib import Path
import re

class SystemHealthCheck:
    def __init__(self):
        self.issues_found = []
        self.fixes_applied = []
        self.project_root = Path.cwd()
        
    def check_all(self):
        """Run all health checks"""
        print("=" * 60)
        print("EXCEL UPLOAD SYSTEM HEALTH CHECK")
        print("=" * 60)
        
        # Check 1: Upload folder
        self.check_upload_folder()
        
        # Check 2: Required Python packages
        self.check_dependencies()
        
        # Check 3: Blueprint file exists
        self.check_blueprint_file()
        
        # Check 4: Template files
        self.check_templates()
        
        # Check 5: Database models
        self.check_database_models()
        
        # Check 6: App configuration
        self.check_app_config()
        
        # Check 7: Route accessibility
        self.check_routes()
        
        # Summary
        self.print_summary()
        
    def check_upload_folder(self):
        """Check if upload folder exists and is writable"""
        print("\n📁 Checking Upload Folder...")
        
        upload_folder = self.project_root / "upload_files"
        
        if not upload_folder.exists():
            print("  ❌ Upload folder does not exist")
            try:
                upload_folder.mkdir(parents=True, exist_ok=True)
                print("  ✅ Created upload_files folder")
                self.fixes_applied.append("Created upload_files folder")
            except Exception as e:
                self.issues_found.append(f"Cannot create upload folder: {e}")
        else:
            print("  ✅ Upload folder exists")
            
        # Check if writable
        test_file = upload_folder / ".test_write"
        try:
            test_file.touch()
            test_file.unlink()
            print("  ✅ Upload folder is writable")
        except Exception as e:
            self.issues_found.append(f"Upload folder not writable: {e}")
            
    def check_dependencies(self):
        """Check if required Python packages are installed"""
        print("\n📦 Checking Dependencies...")
        
        required_packages = {
            'pandas': 'pandas',
            'openpyxl': 'openpyxl',
            'flask': 'Flask',
            'flask_login': 'Flask-Login',
            'sqlalchemy': 'SQLAlchemy'
        }
        
        missing_packages = []
        
        for import_name, pip_name in required_packages.items():
            try:
                __import__(import_name)
                print(f"  ✅ {pip_name} is installed")
            except ImportError:
                print(f"  ❌ {pip_name} is NOT installed")
                missing_packages.append(pip_name)
                
        if missing_packages:
            self.issues_found.append(f"Missing packages: {', '.join(missing_packages)}")
            print(f"\n  To fix, run: pip install {' '.join(missing_packages)}")
            
    def check_blueprint_file(self):
        """Check if employee_import.py exists and has correct structure"""
        print("\n📄 Checking Blueprint File...")
        
        blueprint_path = self.project_root / "blueprints" / "employee_import.py"
        
        if not blueprint_path.exists():
            print("  ❌ employee_import.py not found")
            self.issues_found.append("employee_import.py blueprint file missing")
            return
            
        print("  ✅ employee_import.py exists")
        
        # Check for key components
        with open(blueprint_path, 'r') as f:
            content = f.read()
            
        # Check for YOUR column format
        if 'Last Name' in content and 'First Name' in content:
            print("  ✅ Using YOUR column format")
        else:
            print("  ⚠️  Column format may need verification")
            
        # Check for key routes
        routes_to_check = [
            ('/upload-employees', 'upload_employees'),
            ('/validate-upload', 'validate_upload'),
            ('/download-employee-template', 'download_employee_template'),
            ('/upload-history', 'upload_history')
        ]
        
        for route, func in routes_to_check:
            if f"@employee_import_bp.route('{route}'" in content:
                print(f"  ✅ Route {route} is defined")
            else:
                print(f"  ❌ Route {route} is missing")
                self.issues_found.append(f"Missing route: {route}")
                
    def check_templates(self):
        """Check for template files"""
        print("\n📝 Checking Templates...")
        
        templates_dir = self.project_root / "templates"
        
        # Templates to check
        templates_needed = [
            "base.html",
            "upload_employees_enhanced.html",
            "supervisor/dashboard.html"
        ]
        
        for template in templates_needed:
            template_path = templates_dir / template
            if template_path.exists():
                print(f"  ✅ {template} exists")
                
                # Check for broken links in supervisor/dashboard.html
                if template == "supervisor/dashboard.html":
                    self.fix_dashboard_routes(template_path)
            else:
                print(f"  ⚠️  {template} not found (optional)")
                
    def fix_dashboard_routes(self, dashboard_path):
        """Fix routes in dashboard.html"""
        with open(dashboard_path, 'r') as f:
            content = f.read()
            
        original = content
        
        # Fix upload routes to use correct endpoints
        replacements = [
            # Fix upload employees route
            (r'/import/upload-employees', '/upload-employees'),
            (r"url_for\('import\.upload_employees'\)", "url_for('employee_import.upload_employees')"),
            
            # Fix other upload routes
            (r'/import/upload-overtime', '/upload-overtime'),
            (r'/import/upload-history', '/upload-history'),
            (r'/import/download-employee-template', '/download-employee-template'),
            
            # Fix navigation routes
            (r"url_for\('employee_import\.upload_overtime'\)", "'/upload-overtime'"),
            (r"url_for\('employee_import\.upload_history'\)", "'/upload-history'")
        ]
        
        for old, new in replacements:
            content = re.sub(old, new, content)
            
        if content != original:
            with open(dashboard_path, 'w') as f:
                f.write(content)
            print("    ✅ Fixed routes in dashboard.html")
            self.fixes_applied.append("Fixed routes in dashboard.html")
            
    def check_database_models(self):
        """Check if required database models exist"""
        print("\n🗄️  Checking Database Models...")
        
        models_path = self.project_root / "models.py"
        
        if not models_path.exists():
            print("  ❌ models.py not found")
            self.issues_found.append("models.py file missing")
            return
            
        with open(models_path, 'r') as f:
            content = f.read()
            
        # Check for required models
        models_needed = ['Employee', 'Position', 'FileUpload', 'OvertimeHistory']
        
        for model in models_needed:
            if f"class {model}" in content:
                print(f"  ✅ {model} model exists")
            else:
                print(f"  ⚠️  {model} model may be missing")
                
    def check_app_config(self):
        """Check app.py configuration"""
        print("\n⚙️  Checking App Configuration...")
        
        app_path = self.project_root / "app.py"
        
        if not app_path.exists():
            print("  ❌ app.py not found")
            self.issues_found.append("app.py file missing")
            return
            
        with open(app_path, 'r') as f:
            content = f.read()
            
        # Check for upload folder configuration
        if "UPLOAD_FOLDER" in content:
            print("  ✅ UPLOAD_FOLDER configured")
        else:
            print("  ⚠️  UPLOAD_FOLDER not configured")
            print("    Add to app.py: app.config['UPLOAD_FOLDER'] = 'upload_files'")
            
        # Check for blueprint registration
        if "employee_import_bp" in content:
            print("  ✅ employee_import blueprint registered")
        else:
            print("  ❌ employee_import blueprint not registered")
            self.issues_found.append("employee_import_bp not registered in app.py")
            
    def check_routes(self):
        """Test route accessibility"""
        print("\n🌐 Checking Route Accessibility...")
        
        print("  ℹ️  Start your Flask app and visit:")
        print("     http://localhost:5000/test-upload-route")
        print("     This should return a JSON response confirming the system is working")
        
    def print_summary(self):
        """Print summary of health check"""
        print("\n" + "=" * 60)
        print("HEALTH CHECK SUMMARY")
        print("=" * 60)
        
        if self.fixes_applied:
            print("\n✅ Fixes Applied:")
            for fix in self.fixes_applied:
                print(f"  • {fix}")
                
        if self.issues_found:
            print("\n⚠️  Issues Found:")
            for issue in self.issues_found:
                print(f"  • {issue}")
        else:
            print("\n✅ No critical issues found!")
            
        print("\n📋 Your Excel Column Format:")
        print("  1. Last Name")
        print("  2. First Name")
        print("  3. Employee ID")
        print("  4. Crew Assigned (A, B, C, or D)")
        print("  5. Current Job Position")
        print("  6. Email")
        print("\n  Default Password: password123")
        
        print("\n🔗 Available Routes:")
        print("  • /upload-employees - Main upload page")
        print("  • /validate-upload - AJAX validation endpoint")
        print("  • /download-employee-template - Download Excel template")
        print("  • /upload-history - View upload history")
        print("  • /export-employees - Export current data")
        print("  • /test-upload-route - Test endpoint")

def main():
    """Run the health check"""
    checker = SystemHealthCheck()
    
    try:
        checker.check_all()
    except Exception as e:
        print(f"\n❌ Error during health check: {e}")
        sys.exit(1)
        
    print("\n✅ Health check complete!")
    print("Run your Flask app and test the upload system.")

if __name__ == "__main__":
    main()
