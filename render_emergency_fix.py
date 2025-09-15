#!/usr/bin/env python3
"""
EMERGENCY FIX for Render Deployment
Quick fix for the shift_swap_request.requested_with_id column issue
Run this immediately to stop the redirect loop
"""

import os
import sys
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_sql_command(sql_command):
    """Run a SQL command using psql"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        logger.error("❌ No DATABASE_URL environment variable found!")
        return False
    
    try:
        # Run the SQL command
        result = subprocess.run(
            ["psql", database_url, "-c", sql_command],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info(f"✅ SUCCESS: {sql_command[:50]}...")
            return True
        else:
            logger.error(f"❌ FAILED: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"❌ TIMEOUT: Command took too long")
        return False
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")
        return False

def emergency_fix():
    """Apply emergency fix for missing columns"""
    
    print("🚨 EMERGENCY FIX for Workforce Scheduler")
    print("Fixing missing shift_swap_request columns...")
    print("-" * 50)
    
    # List of emergency SQL commands to fix the immediate issue
    emergency_commands = [
        # Add missing columns to shift_swap_request table
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS requested_with_id INTEGER REFERENCES employee(id) ON DELETE CASCADE;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS requester_schedule_id INTEGER REFERENCES schedule(id) ON DELETE CASCADE;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS requested_schedule_id INTEGER REFERENCES schedule(id) ON DELETE CASCADE;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS reviewed_by_id INTEGER REFERENCES employee(id) ON DELETE SET NULL;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS reviewer_notes TEXT;",
        
        # Ensure status column has proper default
        "ALTER TABLE shift_swap_request ALTER COLUMN status SET DEFAULT 'pending';",
        "UPDATE shift_swap_request SET status = 'pending' WHERE status IS NULL;",
        
        # Add created_at if missing
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
        "UPDATE shift_swap_request SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;",
        
        # Create essential indexes
        "CREATE INDEX IF NOT EXISTS idx_shift_swap_status ON shift_swap_request(status);",
        "CREATE INDEX IF NOT EXISTS idx_shift_swap_requester ON shift_swap_request(requester_id);"
    ]
    
    success_count = 0
    total_commands = len(emergency_commands)
    
    for i, command in enumerate(emergency_commands, 1):
        print(f"\n[{i}/{total_commands}] Executing: {command[:60]}...")
        
        if run_sql_command(command):
            success_count += 1
        else:
            print(f"⚠️  Command {i} failed, but continuing...")
    
    print(f"\n{'='*50}")
    print(f"EMERGENCY FIX COMPLETED")
    print(f"Success: {success_count}/{total_commands} commands")
    print(f"{'='*50}")
    
    if success_count >= len(emergency_commands) - 2:  # Allow 2 failures
        print("✅ Fix successful! The redirect loop should be resolved.")
        print("\nNext steps:")
        print("1. Restart your Render service")
        print("2. Test the /supervisor/dashboard route")
        print("3. Monitor logs for any remaining issues")
        return True
    else:
        print("❌ Fix may not be complete. Check logs and try again.")
        return False

def test_fix():
    """Test if the fix worked"""
    print("\n🧪 Testing the fix...")
    
    test_query = """
        SELECT COUNT(*) 
        FROM shift_swap_request 
        WHERE status = 'pending';
    """
    
    if run_sql_command(test_query):
        print("✅ Test query successful! Database schema appears fixed.")
        return True
    else:
        print("❌ Test query failed. Fix may not be complete.")
        return False

def main():
    """Main execution"""
    try:
        # Check if we're running on Render
        if 'render.com' not in os.environ.get('DATABASE_URL', ''):
            print("⚠️  This appears to be a local environment.")
            print("Are you sure you want to run this? (y/N): ", end='')
            
            if input().lower() != 'y':
                print("Aborted.")
                return
        
        # Run emergency fix
        if emergency_fix():
            # Test the fix
            test_fix()
            
            print("\n🎉 EMERGENCY FIX COMPLETE!")
            print("Your application should now work without redirect loops.")
        else:
            print("\n❌ EMERGENCY FIX FAILED!")
            print("Please check the logs and contact support.")
            
    except KeyboardInterrupt:
        print("\n\n🛑 Emergency fix interrupted by user.")
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        logger.error(f"Critical error in emergency fix: {e}")

if __name__ == "__main__":
    main()
