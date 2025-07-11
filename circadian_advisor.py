# circadian_advisor.py - Sleep advice logic (no models, just logic)

from datetime import datetime, timedelta, time
import math
from typing import Dict, List, Tuple, Optional

class CircadianAdvisor:
    """
    Expert system for providing personalized sleep advice based on 
    circadian rhythm science and shift work patterns
    """
    
    # Optimal sleep windows by chronotype (in 24h format)
    CHRONOTYPE_SLEEP_WINDOWS = {
        'morning': {'bedtime': (21, 23), 'wake': (5, 7)},
        'intermediate': {'bedtime': (22, 24), 'wake': (6, 8)},
        'evening': {'bedtime': (0, 2), 'wake': (8, 10)}
    }
    
    # Shift timing definitions
    SHIFT_TIMES = {
        'day': {'start': 7, 'end': 15},
        'evening': {'start': 15, 'end': 23},
        'night': {'start': 23, 'end': 7}
    }
    
    # Circadian adaptation rates (days needed for adjustment)
    ADAPTATION_DAYS = {
        'day_to_evening': 3,
        'day_to_night': 10,
        'evening_to_day': 2,
        'evening_to_night': 5,
        'night_to_day': 10,
        'night_to_evening': 5
    }
    
    def __init__(self, employee, circadian_profile):
        self.employee = employee
        self.profile = circadian_profile
        self.current_date = datetime.now().date()
        
    def assess_chronotype(self, morning_preference_score: int, 
                         energy_peak_time: str, 
                         natural_bedtime: int) -> Tuple[str, float]:
        """
        Assess employee's chronotype based on questionnaire responses
        Returns: (chronotype, score)
        """
        # Simple scoring algorithm
        score = 0.0
        
        # Morning preference (1-5 scale, 5 being strong morning preference)
        score += (morning_preference_score - 3) * 0.5
        
        # Energy peak time scoring
        if energy_peak_time == 'morning':
            score += 1.0
        elif energy_peak_time == 'afternoon':
            score += 0.0
        elif energy_peak_time == 'evening':
            score -= 1.0
        elif energy_peak_time == 'night':
            score -= 1.5
            
        # Natural bedtime scoring
        if natural_bedtime < 22:
            score += 1.0
        elif natural_bedtime < 23:
            score += 0.5
        elif natural_bedtime > 24:
            score -= 1.0
        elif natural_bedtime > 1:
            score -= 1.5
            
        # Determine chronotype
        if score > 1.0:
            chronotype = 'morning'
        elif score < -1.0:
            chronotype = 'evening'
        else:
            chronotype = 'intermediate'
            
        return chronotype, score
    
    def calculate_circadian_phase(self) -> Dict:
        """
        Calculate where the employee is in their circadian rhythm
        based on their current shift pattern and adaptation
        """
        if not self.profile.current_shift_type:
            return {'phase': 'unknown', 'adaptation': 0}
            
        days_adapted = self.profile.days_on_current_pattern
        shift_type = self.profile.current_shift_type
        
        # Get expected adaptation timeline
        if self.profile.last_shift_change:
            prev_shift = self._get_previous_shift_type()
            if prev_shift:
                key = f"{prev_shift}_to_{shift_type}"
                required_days = self.ADAPTATION_DAYS.get(key, 7)
            else:
                required_days = 7
        else:
            required_days = 7
            
        # Calculate adaptation percentage
        adaptation_percent = min(100, (days_adapted / required_days) * 100)
        
        # Determine circadian phase
        if shift_type == 'night':
            if adaptation_percent < 30:
                phase = 'misaligned_severe'
            elif adaptation_percent < 70:
                phase = 'misaligned_moderate'
            else:
                phase = 'adapted'
        elif shift_type == 'evening':
            if adaptation_percent < 50:
                phase = 'misaligned_mild'
            else:
                phase = 'adapted'
        else:  # day shift
            phase = 'adapted' if adaptation_percent > 30 else 'transitioning'
            
        return {
            'phase': phase,
            'adaptation': adaptation_percent,
            'days_adapted': days_adapted,
            'days_needed': required_days
        }
    
    def generate_sleep_recommendations(self) -> List[Dict]:
        """
        Generate personalized sleep recommendations based on current state
        """
        recommendations = []
        phase_info = self.calculate_circadian_phase()
        
        # Get upcoming shifts
        upcoming_shifts = self._get_upcoming_shifts()
        next_shift = upcoming_shifts[0] if upcoming_shifts else None
        
        # Base recommendations on current phase and shift pattern
        if phase_info['phase'] == 'misaligned_severe':
            recommendations.extend(self._get_severe_misalignment_advice(next_shift))
        elif phase_info['phase'] == 'misaligned_moderate':
            recommendations.extend(self._get_moderate_misalignment_advice(next_shift))
        elif phase_info['phase'] == 'misaligned_mild':
            recommendations.extend(self._get_mild_misalignment_advice(next_shift))
        else:
            recommendations.extend(self._get_maintenance_advice(next_shift))
            
        # Add shift-specific recommendations
        if next_shift:
            recommendations.extend(self._get_shift_specific_advice(next_shift))
            
        # Add chronotype-specific advice
        recommendations.extend(self._get_chronotype_advice())
        
        # Sort by priority
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recommendations.sort(key=lambda x: priority_order.get(x['priority'], 4))
        
        return recommendations[:5]  # Return top 5 recommendations
    
    def _get_severe_misalignment_advice(self, next_shift) -> List[Dict]:
        """Advice for severely misaligned circadian rhythm"""
        advice = []
        
        if next_shift and next_shift.shift_type == 'night':
            advice.append({
                'type': 'sleep_timing',
                'priority': 'critical',
                'title': '🚨 Critical: Prepare for Night Shift',
                'description': 'Your body is not yet adapted to night work. You\'re at high risk for fatigue and errors.',
                'action_items': [
                    'Take a 90-minute nap before your shift (5:30 PM - 7:00 PM)',
                    'Avoid driving if extremely drowsy - arrange alternative transport',
                    'Consume caffeine at start of shift, stop by 3 AM',
                    'Take 15-minute breaks every 2 hours if possible'
                ]
            })
            
        advice.append({
            'type': 'light_exposure',
            'priority': 'critical',
            'title': '💡 Light Management Critical',
            'description': 'Proper light exposure is essential for faster adaptation.',
            'action_items': [
                'Wear sunglasses on drive home after night shift',
                'Use blackout curtains for daytime sleep',
                'Expose yourself to bright light during night shift',
                'Avoid screens 2 hours before intended sleep'
            ]
        })
        
        return advice
    
    def _get_moderate_misalignment_advice(self, next_shift) -> List[Dict]:
        """Advice for moderately misaligned circadian rhythm"""
        advice = []
        
        advice.append({
            'type': 'sleep_timing',
            'priority': 'high',
            'title': '😴 Sleep Schedule Adjustment',
            'description': 'You\'re making progress but still adapting. Consistency is key.',
            'action_items': [
                'Maintain consistent sleep times even on days off',
                'Aim for 7-9 hours total sleep in 24 hours',
                'Consider split sleep if needed (4-5 hours main + 2-3 hour nap)',
                'Go to bed immediately after night shift while melatonin is high'
            ]
        })
        
        advice.append({
            'type': 'meal_timing',
            'priority': 'medium',
            'title': '🍽️ Meal Timing for Better Sleep',
            'description': 'Align your meals with your new schedule to help adaptation.',
            'action_items': [
                'Eat main meal before work, not during night shift',
                'Light snacks only during night shift',
                'Avoid heavy meals 3 hours before sleep',
                'Stay hydrated but reduce fluids 2 hours before sleep'
            ]
        })
        
        return advice
    
    def _get_mild_misalignment_advice(self, next_shift) -> List[Dict]:
        """Advice for mild circadian misalignment"""
        advice = []
        
        advice.append({
            'type': 'nap',
            'priority': 'medium',
            'title': '💤 Strategic Napping',
            'description': 'Use naps to boost alertness without disrupting main sleep.',
            'action_items': [
                'Take a 20-minute power nap before evening shift',
                'Avoid naps longer than 30 minutes if working days',
                'No naps within 6 hours of main sleep period',
                'Set alarm to prevent oversleeping during naps'
            ]
        })
        
        return advice
    
    def _get_maintenance_advice(self, next_shift) -> List[Dict]:
        """Advice for maintaining good circadian alignment"""
        advice = []
        
        advice.append({
            'type': 'sleep_timing',
            'priority': 'low',
            'title': '✅ Maintain Your Rhythm',
            'description': 'You\'re well-adapted! Focus on maintaining good habits.',
            'action_items': [
                'Keep consistent sleep-wake times',
                'Continue current light exposure patterns',
                'Monitor for signs of sleep debt accumulation',
                'Plan ahead for upcoming shift changes'
            ]
        })
        
        return advice
    
    def _get_shift_specific_advice(self, shift) -> List[Dict]:
        """Get advice specific to the upcoming shift"""
        advice = []
        hours_until_shift = (shift.start_time - datetime.now()).total_seconds() / 3600
        
        if shift.shift_type == 'night' and hours_until_shift < 24:
            advice.append({
                'type': 'sleep_timing',
                'priority': 'high',
                'title': f'🌙 Night Shift in {int(hours_until_shift)} hours',
                'description': 'Prepare your body for overnight work.',
                'action_items': [
                    'Sleep until at least 3 PM today',
                    'Take a nap from 7-8:30 PM if possible',
                    'Eat a substantial meal before leaving for work',
                    'Prepare bedroom for daytime sleep tomorrow'
                ]
            })
        elif shift.shift_type == 'day' and hours_until_shift < 12:
            advice.append({
                'type': 'sleep_timing',
                'priority': 'high',
                'title': f'☀️ Early Start Tomorrow',
                'description': 'Ensure adequate rest for your day shift.',
                'action_items': [
                    'Wind down activities by 9 PM tonight',
                    'Be in bed by 10 PM for 8 hours sleep',
                    'Set multiple alarms 10 minutes apart',
                    'Prepare clothes and breakfast tonight'
                ]
            })
            
        return advice
    
    def _get_chronotype_advice(self) -> List[Dict]:
        """Get advice based on chronotype"""
        advice = []
        
        if self.profile.chronotype == 'evening' and self.profile.current_shift_type == 'day':
            advice.append({
                'type': 'light_exposure',
                'priority': 'medium',
                'title': '🦉 Night Owl on Day Shift',
                'description': 'Your natural rhythm conflicts with early shifts.',
                'action_items': [
                    'Use bright light therapy upon waking',
                    'Get sunlight exposure during morning break',
                    'Consider melatonin supplement (consult doctor)',
                    'Gradually shift bedtime earlier by 15 min/day'
                ]
            })
        elif self.profile.chronotype == 'morning' and self.profile.current_shift_type == 'night':
            advice.append({
                'type': 'caffeine',
                'priority': 'high',
                'title': '🐤 Early Bird on Night Shift',
                'description': 'Night shifts are especially challenging for your chronotype.',
                'action_items': [
                    'Strategic caffeine use: small amounts frequently',
                    'Take brief walks during shift to stay alert',
                    'Consider requesting day shifts when possible',
                    'Extra vigilance during 3-5 AM danger zone'
                ]
            })
            
        return advice
    
    def calculate_sleep_debt(self, recent_sleep_logs: List) -> float:
        """Calculate accumulated sleep debt"""
        if not recent_sleep_logs:
            return 0.0
            
        total_debt = 0.0
        for log in recent_sleep_logs[-7:]:  # Last 7 days
            optimal_sleep = 8.0  # hours
            actual_sleep = log.sleep_duration or 0
            daily_debt = optimal_sleep - actual_sleep
            total_debt += max(0, daily_debt)  # Only count deficits
            
        return round(total_debt, 1)
    
    def generate_transition_plan(self, from_shift: str, to_shift: str, 
                                start_date: datetime) -> Dict:
        """Generate a plan to transition between shift types"""
        key = f"{from_shift}_to_{to_shift}"
        duration_days = self.ADAPTATION_DAYS.get(key, 7)
        
        plan = {
            'duration_days': duration_days,
            'daily_schedule': []
        }
        
        for day in range(duration_days):
            date = start_date + timedelta(days=day)
            progress = (day + 1) / duration_days
            
            # Calculate gradual shift in sleep times
            if to_shift == 'night':
                # Progressively later bedtime
                bedtime_shift = int(progress * 12)  # Shift up to 12 hours
                wake_shift = int(progress * 12)
            elif to_shift == 'day' and from_shift == 'night':
                # Progressively earlier bedtime
                bedtime_shift = int((1 - progress) * 12)
                wake_shift = int((1 - progress) * 12)
            else:
                # Smaller adjustments for other transitions
                bedtime_shift = int(progress * 4)
                wake_shift = int(progress * 4)
                
            daily_plan = {
                'date': date.strftime('%Y-%m-%d'),
                'day_number': day + 1,
                'bedtime_adjust': f"+{bedtime_shift}h" if bedtime_shift >= 0 else f"{bedtime_shift}h",
                'wake_adjust': f"+{wake_shift}h" if wake_shift >= 0 else f"{wake_shift}h",
                'key_actions': self._get_transition_day_actions(day, progress, to_shift)
            }
            
            plan['daily_schedule'].append(daily_plan)
            
        return plan
    
    def _get_transition_day_actions(self, day: int, progress: float, 
                                   target_shift: str) -> List[str]:
        """Get specific actions for each day of transition"""
        actions = []
        
        if day == 0:
            actions.append("Start light therapy in evening if transitioning to night shift")
            actions.append("Begin adjusting meal times")
        elif progress < 0.5:
            actions.append("Gradually shift bedtime by 1-2 hours")
            actions.append("Use melatonin if recommended by doctor")
        else:
            actions.append("Practice new sleep schedule even on days off")
            actions.append("Minimize social activities that conflict with new schedule")
            
        if target_shift == 'night' and progress > 0.7:
            actions.append("Start using blackout curtains for daytime sleep")
            actions.append("Practice wearing sunglasses after sunrise")
            
        return actions
    
    def _get_upcoming_shifts(self) -> List:
        """Get employee's upcoming shifts"""
        from models import Schedule
        return Schedule.query.filter(
            Schedule.employee_id == self.employee.id,
            Schedule.start_time > datetime.now(),
            Schedule.start_time < datetime.now() + timedelta(days=7)
        ).order_by(Schedule.start_time).limit(5).all()
    
    def _get_previous_shift_type(self) -> Optional[str]:
        """Determine previous shift type from logs"""
        # This would look at historical data to determine previous pattern
        # For now, return None
        return None
