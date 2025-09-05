"""
Shift Scheduling Algorithm - Based on Expert Knowledge
======================================================
Core rules and tradeoffs for 24/7 scheduling with 4 crews
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum
import math
from datetime import datetime, timedelta

# ==========================================
# FUNDAMENTAL CONSTANTS
# ==========================================

HOURS_PER_WEEK = 168  # 24 * 7
STANDARD_CREWS = 4    # Optimal for ~40 hour work week
TARGET_WORK_WEEK = 42  # Actual average for 24/7 coverage with 4 crews

# Pay calculation constants
OVERTIME_THRESHOLD = 40  # Hours before overtime kicks in
OVERTIME_MULTIPLIER = 1.5

@dataclass
class ShiftConstants:
    """Fundamental constraints based on shift length"""
    shift_length: int
    max_consecutive_shifts: int
    annual_days_on: int
    annual_days_off: int
    typical_pattern_weeks: List[int]  # Common week patterns (36, 48 hours, etc.)
    avg_work_hours_per_week: float
    avg_pay_hours_per_week: float
    
    @classmethod
    def for_8_hour(cls):
        return cls(
            shift_length=8,
            max_consecutive_shifts=7,
            annual_days_on=273,  # ~74.8% of year
            annual_days_off=91,   # ~24.9% of year
            typical_pattern_weeks=[40, 48],  # 75% at 40, 25% at 48
            avg_work_hours_per_week=42,
            avg_pay_hours_per_week=43  # Due to overtime on 48-hour weeks
        )
    
    @classmethod
    def for_12_hour(cls):
        return cls(
            shift_length=12,
            max_consecutive_shifts=5,
            annual_days_on=182,   # 50% of year
            annual_days_off=182,  # 50% of year
            typical_pattern_weeks=[36, 48],  # Alternating pattern
            avg_work_hours_per_week=42,
            avg_pay_hours_per_week=44  # More OT due to 48-hour weeks
        )

# ==========================================
# PREFERENCE TRADEOFFS
# ==========================================

@dataclass
class PreferenceTradeoff:
    """Represents a scheduling tradeoff"""
    name: str
    option_a: str
    option_b: str
    current_value: float = 0.5  # 0 = fully A, 1 = fully B, 0.5 = balanced
    
    def describe(self) -> str:
        if self.current_value < 0.3:
            return f"Strongly prefer {self.option_a}"
        elif self.current_value < 0.5:
            return f"Slightly prefer {self.option_a}"
        elif self.current_value == 0.5:
            return f"Balanced between both"
        elif self.current_value < 0.7:
            return f"Slightly prefer {self.option_b}"
        else:
            return f"Strongly prefer {self.option_b}"

class CoreTradeoffs:
    """The fundamental tradeoffs in shift scheduling"""
    
    def __init__(self):
        self.tradeoffs = {
            "work_stretch": PreferenceTradeoff(
                name="Work Stretch vs Days Off",
                option_a="Shorter work stretches (2-3 days)",
                option_b="Longer days off in a row (4-7 days)",
                current_value=0.5
            ),
            "shift_length": PreferenceTradeoff(
                name="Shift Length Preference",
                option_a="8-hour shifts (more days at work, shorter days)",
                option_b="12-hour shifts (fewer days at work, longer days)",
                current_value=0.5
            ),
            "weekend_distribution": PreferenceTradeoff(
                name="Weekend Coverage",
                option_a="Every other weekend off",
                option_b="More weekends off but work some full weekends",
                current_value=0.3  # Most prefer every other
            ),
            "rotation_type": PreferenceTradeoff(
                name="Schedule Type",
                option_a="Fixed shifts (always same hours)",
                option_b="Rotating shifts (variety, fairness)",
                current_value=0.6  # Slight preference for rotation
            ),
            "days_off_pattern": PreferenceTradeoff(
                name="Days Off Pattern",
                option_a="Fixed days off (predictable)",
                option_b="Rotating days off (fair distribution)",
                current_value=0.7  # Usually rotating for fairness
            )
        }

# ==========================================
# PATTERN GENERATOR
# ==========================================

class PatternRule:
    """Rules that must be followed in pattern generation"""
    
    @staticmethod
    def validate_consecutive_shifts(pattern: List[int], shift_type: str) -> Tuple[bool, str]:
        """Check if consecutive shift limits are exceeded"""
        constants = ShiftConstants.for_8_hour() if shift_type == "8-hour" else ShiftConstants.for_12_hour()
        max_consecutive = constants.max_consecutive_shifts
        
        consecutive_count = 0
        max_found = 0
        
        for day in pattern:
            if day == 1:  # Working
                consecutive_count += 1
                max_found = max(max_found, consecutive_count)
            else:  # Off
                consecutive_count = 0
        
        if max_found > max_consecutive:
            return False, f"Exceeds maximum {max_consecutive} consecutive {shift_type} shifts (found {max_found})"
        return True, "OK"
    
    @staticmethod
    def calculate_coverage(patterns: Dict[str, List[int]], shift_length: int) -> Dict[int, int]:
        """Calculate coverage for each hour of the week"""
        coverage = {}
        shifts_per_day = 24 // shift_length
        
        for hour in range(168):  # Every hour of the week
            day_index = hour // 24
            hour_of_day = hour % 24
            shift_index = hour_of_day // shift_length
            
            crews_working = 0
            for crew, pattern in patterns.items():
                if pattern[day_index] == 1:  # Crew is working this day
                    # Need to determine which shift they're on
                    # This depends on rotation scheme
                    crews_working += 1
            
            coverage[hour] = crews_working
        
        return coverage
    
    @staticmethod
    def calculate_pay_hours(pattern: List[int], shift_length: int, cycle_weeks: int) -> Dict:
        """Calculate work and pay hours for a pattern"""
        total_shifts = sum(pattern)
        total_work_hours = total_shifts * shift_length
        
        # Calculate weekly distribution
        weekly_hours = []
        for week in range(cycle_weeks):
            week_start = week * 7
            week_end = week_start + 7
            week_shifts = sum(pattern[week_start:week_end])
            week_hours = week_shifts * shift_length
            weekly_hours.append(week_hours)
        
        # Calculate pay hours (with overtime)
        pay_hours = 0
        for week_hours in weekly_hours:
            if week_hours <= 40:
                pay_hours += week_hours
            else:
                regular = 40
                overtime = week_hours - 40
                pay_hours += regular + (overtime * OVERTIME_MULTIPLIER)
        
        return {
            "total_work_hours": total_work_hours,
            "total_pay_hours": pay_hours,
            "avg_work_hours_per_week": total_work_hours / cycle_weeks,
            "avg_pay_hours_per_week": pay_hours / cycle_weeks,
            "weekly_distribution": weekly_hours
        }

# ==========================================
# COMMON PATTERNS
# ==========================================

class CommonPatterns:
    """Repository of common shift patterns used in industry"""
    
    @staticmethod
    def pitman_12_hour():
        """2-2-3 pattern, 12-hour shifts"""
        return {
            "name": "Pitman (2-2-3)",
            "shift_length": 12,
            "cycle_days": 14,
            "pattern": {
                "Crew A": [1,1,0,0,1,1,1,0,0,1,1,0,0,0],
                "Crew B": [0,0,1,1,0,0,0,1,1,0,0,1,1,1],
                "Crew C": [1,0,0,1,1,0,0,0,1,1,0,0,1,1],
                "Crew D": [0,1,1,0,0,1,1,1,0,0,1,1,0,0]
            },
            "features": {
                "max_consecutive": 3,
                "weekends_off": "Every other weekend",
                "avg_hours_week": 42
            }
        }
    
    @staticmethod
    def southern_swing():
        """8-hour Southern Swing schedule"""
        return {
            "name": "Southern Swing",
            "shift_length": 8,
            "cycle_days": 28,
            "pattern": {
                # 7 days on each shift, rotating
                "Crew A": [1]*7 + [0]*7 + [1]*7 + [0]*7,  # Days week 1, Evenings week 3
                "Crew B": [0]*7 + [1]*7 + [0]*7 + [1]*7,  # Days week 2, Evenings week 4
                "Crew C": [1]*7 + [0]*7 + [1]*7 + [0]*7,  # Nights week 1, off week 2
                "Crew D": [0]*7 + [1]*7 + [0]*7 + [1]*7   # Relief crew
            },
            "features": {
                "max_consecutive": 7,
                "rotation": "Forward (Days→Evenings→Nights)",
                "avg_hours_week": 42
            }
        }
    
    @staticmethod
    def dupont_12_hour():
        """DuPont 12-hour rotating schedule"""
        return {
            "name": "DuPont",
            "shift_length": 12,
            "cycle_days": 28,
            "pattern": {
                # Complex 4-week rotation
                "Crew A": [1,1,1,0,0,0,1,1,1,0,0,0,0,0,0,1,1,1,0,0,0,1,1,1,0,0,0,0],
                "Crew B": [0,0,0,1,1,1,0,0,0,1,1,1,0,0,0,0,0,0,1,1,1,0,0,0,1,1,1,0],
                "Crew C": [0,1,1,1,0,0,0,1,1,1,0,0,0,0,0,1,1,1,0,0,0,1,1,1,0,0,0,0],
                "Crew D": [0,0,0,0,0,0,1,0,0,0,1,1,1,1,1,0,0,0,1,1,1,0,0,0,1,1,1,1]
            },
            "features": {
                "max_consecutive": 3,
                "long_break": "7 days off every 4 weeks",
                "avg_hours_week": 42
            }
        }
    
    @staticmethod
    def fixed_8_hour():
        """Fixed 8-hour shifts (no rotation)"""
        return {
            "name": "Fixed 8-Hour",
            "shift_length": 8,
            "cycle_days": 14,
            "pattern": {
                "Crew A (Days)": [1,1,1,1,1,0,0,1,1,1,1,1,0,0],      # Fixed day shift
                "Crew B (Evenings)": [1,1,1,1,1,0,0,1,1,1,1,1,0,0],  # Fixed evening shift
                "Crew C (Nights)": [1,1,1,1,1,0,0,1,1,1,1,1,0,0],    # Fixed night shift
                "Crew D (Relief)": [0,0,0,0,0,1,1,0,0,0,0,0,1,1]     # Covers days off
            },
            "features": {
                "max_consecutive": 5,
                "rotation": "None (fixed)",
                "predictability": "High",
                "avg_hours_week": 40
            }
        }

# ==========================================
# PATTERN ANALYZER
# ==========================================

class PatternAnalyzer:
    """Analyzes patterns for key metrics"""
    
    @staticmethod
    def analyze_pattern(pattern_dict: Dict) -> Dict:
        """Complete analysis of a shift pattern"""
        pattern = pattern_dict["pattern"]
        shift_length = pattern_dict["shift_length"]
        cycle_days = pattern_dict["cycle_days"]
        
        analysis = {
            "name": pattern_dict["name"],
            "shift_length": shift_length,
            "cycle_days": cycle_days,
            "crews": {}
        }
        
        for crew_name, crew_pattern in pattern.items():
            crew_analysis = PatternAnalyzer._analyze_crew(crew_pattern, shift_length, cycle_days)
            analysis["crews"][crew_name] = crew_analysis
        
        # Overall statistics
        analysis["coverage"] = PatternAnalyzer._analyze_coverage(pattern, shift_length)
        analysis["fairness"] = PatternAnalyzer._analyze_fairness(analysis["crews"])
        
        return analysis
    
    @staticmethod
    def _analyze_crew(pattern: List[int], shift_length: int, cycle_days: int) -> Dict:
        """Analyze a single crew's pattern"""
        # Count consecutive stretches
        work_stretches = []
        off_stretches = []
        current_stretch = 0
        current_type = None
        
        for day in pattern:
            if day == 1:  # Working
                if current_type == "work":
                    current_stretch += 1
                else:
                    if current_type == "off" and current_stretch > 0:
                        off_stretches.append(current_stretch)
                    current_type = "work"
                    current_stretch = 1
            else:  # Off
                if current_type == "off":
                    current_stretch += 1
                else:
                    if current_type == "work" and current_stretch > 0:
                        work_stretches.append(current_stretch)
                    current_type = "off"
                    current_stretch = 1
        
        # Add final stretch
        if current_type == "work":
            work_stretches.append(current_stretch)
        elif current_type == "off":
            off_stretches.append(current_stretch)
        
        # Calculate weekends
        weekends_off = 0
        for week in range(cycle_days // 7):
            saturday = week * 7 + 5
            sunday = week * 7 + 6
            if saturday < len(pattern) and sunday < len(pattern):
                if pattern[saturday] == 0 and pattern[sunday] == 0:
                    weekends_off += 1
        
        # Calculate hours
        total_shifts = sum(pattern)
        hours_calc = PatternRule.calculate_pay_hours(pattern, shift_length, cycle_days // 7)
        
        return {
            "days_on": total_shifts,
            "days_off": cycle_days - total_shifts,
            "work_stretches": work_stretches,
            "off_stretches": off_stretches,
            "max_consecutive_work": max(work_stretches) if work_stretches else 0,
            "max_consecutive_off": max(off_stretches) if off_stretches else 0,
            "weekends_off": weekends_off,
            "work_hours": hours_calc["avg_work_hours_per_week"],
            "pay_hours": hours_calc["avg_pay_hours_per_week"],
            "weekly_hours": hours_calc["weekly_distribution"]
        }
    
    @staticmethod
    def _analyze_coverage(pattern: Dict[str, List[int]], shift_length: int) -> Dict:
        """Analyze coverage provided by pattern"""
        # Simple analysis - count crews working each day
        cycle_days = len(next(iter(pattern.values())))
        daily_coverage = []
        
        for day in range(cycle_days):
            crews_working = sum(1 for crew_pattern in pattern.values() if crew_pattern[day] == 1)
            daily_coverage.append(crews_working)
        
        return {
            "min_crews": min(daily_coverage),
            "max_crews": max(daily_coverage),
            "avg_crews": sum(daily_coverage) / len(daily_coverage),
            "daily_coverage": daily_coverage
        }
    
    @staticmethod
    def _analyze_fairness(crews_analysis: Dict) -> Dict:
        """Analyze fairness across crews"""
        work_hours = [crew["work_hours"] for crew in crews_analysis.values()]
        pay_hours = [crew["pay_hours"] for crew in crews_analysis.values()]
        weekends_off = [crew["weekends_off"] for crew in crews_analysis.values()]
        
        return {
            "work_hours_variance": max(work_hours) - min(work_hours),
            "pay_hours_variance": max(pay_hours) - min(pay_hours),
            "weekends_variance": max(weekends_off) - min(weekends_off),
            "is_fair": (max(work_hours) - min(work_hours)) < 2
        }

# ==========================================
# MAIN ALGORITHM
# ==========================================

class ShiftPatternAlgorithm:
    """Main algorithm incorporating expert knowledge"""
    
    def __init__(self, preferences: Optional[Dict] = None):
        self.tradeoffs = CoreTradeoffs()
        if preferences:
            self._apply_preferences(preferences)
        
        # Load pattern library
        self.patterns = {
            "pitman": CommonPatterns.pitman_12_hour(),
            "southern_swing": CommonPatterns.southern_swing(),
            "dupont": CommonPatterns.dupont_12_hour(),
            "fixed_8": CommonPatterns.fixed_8_hour()
        }
    
    def _apply_preferences(self, preferences: Dict):
        """Apply user preferences to tradeoffs"""
        for key, value in preferences.items():
            if key in self.tradeoffs.tradeoffs:
                self.tradeoffs.tradeoffs[key].current_value = value
    
    def recommend_pattern(self) -> Dict:
        """Recommend best pattern based on preferences"""
        scores = {}
        
        for name, pattern in self.patterns.items():
            score = self._score_pattern(pattern)
            scores[name] = score
        
        best_pattern = max(scores, key=scores.get)
        
        return {
            "recommended": self.patterns[best_pattern],
            "scores": scores,
            "analysis": PatternAnalyzer.analyze_pattern(self.patterns[best_pattern])
        }
    
    def _score_pattern(self, pattern: Dict) -> float:
        """Score a pattern based on current preferences"""
        score = 0
        
        # Shift length preference
        shift_pref = self.tradeoffs.tradeoffs["shift_length"].current_value
        if pattern["shift_length"] == 12:
            score += shift_pref * 10
        else:
            score += (1 - shift_pref) * 10
        
        # Weekend preference
        if "Every other" in pattern.get("features", {}).get("weekends_off", ""):
            score += 15  # Most people prefer this
        
        # Work stretch preference
        max_consecutive = pattern.get("features", {}).get("max_consecutive", 5)
        if max_consecutive <= 3:
            score += (1 - self.tradeoffs.tradeoffs["work_stretch"].current_value) * 10
        else:
            score += self.tradeoffs.tradeoffs["work_stretch"].current_value * 10
        
        # Rotation preference
        if "fixed" in pattern["name"].lower():
            score += (1 - self.tradeoffs.tradeoffs["rotation_type"].current_value) * 10
        else:
            score += self.tradeoffs.tradeoffs["rotation_type"].current_value * 10
        
        return score
    
    def generate_custom_pattern(self, requirements: Dict) -> Dict:
        """Generate a custom pattern based on specific requirements"""
        # This would implement the full generation logic
        # For now, return a template
        return {
            "name": "Custom Generated",
            "shift_length": requirements.get("shift_length", 8),
            "cycle_days": 28,
            "pattern": {},  # Would be generated
            "features": {}
        }

# ==========================================
# USAGE EXAMPLE
# ==========================================

def demonstrate_algorithm():
    """Demonstrate the algorithm with expert knowledge"""
    
    print("SHIFT PATTERN ALGORITHM - EXPERT KNOWLEDGE DEMONSTRATION")
    print("=" * 60)
    
    # Create algorithm with balanced preferences
    algo = ShiftPatternAlgorithm()
    
    print("\n1. FUNDAMENTAL CONSTRAINTS:")
    print("-" * 40)
    constants_8 = ShiftConstants.for_8_hour()
    constants_12 = ShiftConstants.for_12_hour()
    
    print(f"8-Hour Shifts:")
    print(f"  - Max consecutive: {constants_8.max_consecutive_shifts} shifts")
    print(f"  - Annual: {constants_8.annual_days_on} days on, {constants_8.annual_days_off} days off")
    print(f"  - Average: {constants_8.avg_work_hours_per_week} work hrs/week, {constants_8.avg_pay_hours_per_week} pay hrs/week")
    
    print(f"\n12-Hour Shifts:")
    print(f"  - Max consecutive: {constants_12.max_consecutive_shifts} shifts")
    print(f"  - Annual: {constants_12.annual_days_on} days on, {constants_12.annual_days_off} days off")
    print(f"  - Average: {constants_12.avg_work_hours_per_week} work hrs/week, {constants_12.avg_pay_hours_per_week} pay hrs/week")
    
    print("\n2. ANALYZING COMMON PATTERNS:")
    print("-" * 40)
    
    # Analyze Pitman pattern
    pitman = CommonPatterns.pitman_12_hour()
    analysis = PatternAnalyzer.analyze_pattern(pitman)
    
    print(f"\n{pitman['name']} Analysis:")
    print(f"  - Shift length: {pitman['shift_length']} hours")
    print(f"  - Cycle: {pitman['cycle_days']} days")
    
    for crew, stats in analysis["crews"].items():
        if "A" in crew:  # Just show one crew as example
            print(f"  - {crew}:")
            print(f"    * Work stretches: {stats['work_stretches']}")
            print(f"    * Off stretches: {stats['off_stretches']}")
            print(f"    * Weekends off: {stats['weekends_off']}/{pitman['cycle_days']//7}")
            print(f"    * Avg hours: {stats['work_hours']:.1f} work, {stats['pay_hours']:.1f} pay")
            break
    
    print(f"  - Coverage: {analysis['coverage']['min_crews']}-{analysis['coverage']['max_crews']} crews")
    print(f"  - Fairness: {'Yes' if analysis['fairness']['is_fair'] else 'No'}")
    
    print("\n3. PREFERENCE-BASED RECOMMENDATION:")
    print("-" * 40)
    
    # Set some preferences
    preferences = {
        "shift_length": 0.7,  # Prefer 12-hour shifts
        "work_stretch": 0.3,  # Prefer shorter work stretches
        "weekend_distribution": 0.2,  # Strong preference for every other weekend
        "rotation_type": 0.6   # Slight preference for rotation
    }
    
    algo_with_prefs = ShiftPatternAlgorithm(preferences)
    recommendation = algo_with_prefs.recommend_pattern()
    
    print(f"Based on preferences, recommended: {recommendation['recommended']['name']}")
    print(f"\nPattern Scores:")
    for pattern_name, score in recommendation['scores'].items():
        print(f"  - {pattern_name}: {score:.1f}")
    
    return algo

if __name__ == "__main__":
    demonstrate_algorithm()
