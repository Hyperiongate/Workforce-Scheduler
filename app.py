# app.py - Updated version with automatic schema management
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_required, login_user, logout_user, current_user 
from flask_migrate import Migrate, stamp
from models import (
    db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, 
    Position, Skill, OvertimeHistory, Schedule, PositionCoverage,
    # New models for staffing management
    OvertimeOpportunity, OvertimeResponse, CoverageGap, EmployeeSkill,
    FatigueTracking, MandatoryOvertimeLog, ShiftPattern, CoverageNotificationResponse,
    FileUpload  # Added FileUpload model
)
from werkzeug.security import check_password_hash
import os
from datetime import datetime, timedelta, date
import random
from sqlalchemy import and_, func, text
import logging

# Import the schema manager
from database_schema_manager import DatabaseSchemaManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# FIXED UPLOAD FOLDER CONFIGURATION
app.config['UPLOAD_FOLDER'] = 'upload_files'  # Changed from 'uploads' to 'upload_files'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Handle the upload folder creation properly
upload_folder = app.config['UPLOAD_FOLDER']

# Get absolute path
if not os.path.isabs(upload_folder):
    upload_folder = os.path.join(app.root_path, upload_folder)

# Check if path exists and is a folder
if os.path.exists(upload_folder):
    if not os.path.isdir(upload_folder):
        # It's a file, not a folder - remove it
        os.remove(upload_folder)
        os.makedirs(upload_folder)
else:
    # Create the folder
    os.makedirs(upload_folder)

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# AUTOMATIC SCHEMA SYNCHRONIZATION
def check_and_sync_database():
    """Automatically check and synchronize database schema on startup"""
    with app.app_context():
        try:
            logger.info("🔄 Checking database schema...")
            
            # First ensure all tables exist
            db.create_all()
            logger.info("✅ Base tables created/verified")
            
            # Then run the schema manager to fix any column mismatches
            schema_manager = DatabaseSchemaManager(app, db)
            success = schema_manager.run_full_check()
            
            if success:
                logger.info("✅ Database schema synchronized successfully")
            else:
                logger.error("⚠️  Some schema issues could not be resolved automatically")
                
        except Exception as e:
            logger.error(f"❌ Error during schema synchronization: {e}")
            # Don't crash the app, just log the error
            
# Run schema check before first request
@app.before_first_request
def initialize_database():
    """Initialize database and check schema before handling any requests"""
    check_and_sync_database()

# Alternative: Run on startup (for newer Flask versions)
with app.app_context():
    # Only run if not in a migration context
    if not os.environ.get('FLASK_MIGRATE'):
        check_and_sync_database()
