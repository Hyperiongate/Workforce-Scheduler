# models.py - Add this to your existing models.py file after the current models

from datetime import datetime, timedelta
import json

class CircadianProfile(db.Model):
    """Track employee circadian rhythm and sleep patterns"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Chronotype assessment (morning lark vs night owl)
    chronotype = db.Column(db.String(20))  # 'morning', 'intermediate', 'evening'
    chronotype_score = db.Column(db.Float)  # -2 to +2 scale
    
    # Current shift pattern tracking
    current_shift_type = db.Column(db.String(20))  # 'day', 'evening', 'night'
    days_on_current_pattern = db.Column(db.Integer, default=0)
    last_shift_change = db.Column(db.DateTime)
    
    # Sleep debt tracking
    cumulative_sleep_debt = db.Column(db.Float, default=0.0)  # in hours
    last_sleep_debt_update = db.Column(db.DateTime)
    
    # Adaptation progress
    circadian_adaptation_score = db.Column(db.Float, default=0.0)  # 0-100%
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='circadian_profile')
    sleep_logs = db.relationship('SleepLog', backref='circadian_profile', lazy='dynamic')
    sleep_recommendations = db.relationship('SleepRecommendation', backref='circadian_profile', lazy='dynamic')


class SleepLog(db.Model):
    """Track actual sleep patterns"""
    id = db.Column(db.Integer, primary_key=True)
    circadian_profile_id = db.Column(db.Integer, db.ForeignKey('circadian_profile.id'), nullable=False)
    
    # Sleep timing
    sleep_date = db.Column(db.Date, nullable=False)
    bedtime = db.Column(db.DateTime)
    wake_time = db.Column(db.DateTime)
    
    # Sleep quality metrics
    sleep_duration = db.Column(db.Float)  # hours
    sleep_quality = db.Column(db.Integer)  # 1-10 scale
    sleep_efficiency = db.Column(db.Float)  # percentage
    
    # Factors
    pre_sleep_light_exposure = db.Column(db.String(20))  # 'high', 'moderate', 'low'
    caffeine_cutoff_time = db.Column(db.Time)
    took_nap = db.Column(db.Boolean, default=False)
    nap_duration = db.Column(db.Integer)  # minutes
    
    # Work context
    worked_before_sleep = db.Column(db.Boolean)
    shift_type_before_sleep = db.Column(db.String(20))
    hours_since_last_shift = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SleepRecommendation(db.Model):
    """Personalized sleep recommendations"""
    id = db.Column(db.Integer, primary_key=True)
    circadian_profile_id = db.Column(db.Integer, db.ForeignKey('circadian_profile.id'), nullable=False)
    
    # Recommendation details
    recommendation_date = db.Column(db.DateTime, default=datetime.utcnow)
    recommendation_type = db.Column(db.String(50))  # 'sleep_timing', 'light_exposure', 'nap', 'caffeine', 'meal_timing'
    priority = db.Column(db.String(20))  # 'critical', 'high', 'medium', 'low'
    
    # Content
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    action_items = db.Column(db.JSON)  # List of specific actions
    
    # Timing
    valid_from = db.Column(db.DateTime)
    valid_until = db.Column(db.DateTime)
    
    # Tracking
    was_viewed = db.Column(db.Boolean, default=False)
    viewed_at = db.Column(db.DateTime)
    was_helpful = db.Column(db.Boolean)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ShiftTransitionPlan(db.Model):
    """Help employees transition between different shift patterns"""
    id = db.Column(db.Integer, primary_key=True)
    circadian_profile_id = db.Column(db.Integer, db.ForeignKey('circadian_profile.id'), nullable=False)
    
    # Transition details
    from_shift_type = db.Column(db.String(20))
    to_shift_type = db.Column(db.String(20))
    transition_start_date = db.Column(db.Date)
    transition_duration_days = db.Column(db.Integer)
    
    # Plan details
    plan_data = db.Column(db.JSON)  # Daily sleep/wake recommendations
    is_active = db.Column(db.Boolean, default=True)
    completion_percentage = db.Column(db.Float, default=0.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Relationship
    circadian_profile = db.relationship('CircadianProfile', backref='transition_plans')
