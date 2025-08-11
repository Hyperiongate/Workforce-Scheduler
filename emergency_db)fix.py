#!/usr/bin/env python3
"""Emergency database fix - run this on Render"""
import os
import subprocess

def fix_database():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("No DATABASE_URL found!")
        return
    
    # List of SQL commands to fix the database
    sql_commands = [
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS requester_id INTEGER;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS requested_with_id INTEGER;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS requester_schedule_id INTEGER;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS requested_schedule_id INTEGER;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending';",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS reason TEXT;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS reviewed_by_id INTEGER;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;",
        "ALTER TABLE shift_swap_request ADD COLUMN IF NOT EXISTS reviewer_notes TEXT;"
    ]
    
    for sql in sql_commands:
        try:
            # Use subprocess to run psql
            result = subprocess.run(
                ["psql", database_url, "-c", sql],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"✓ Success: {sql[:50]}...")
            else:
                print(f"✗ Error: {result.stderr}")
        except Exception as e:
            print(f"✗ Failed: {e}")
    
    print("\nDatabase fix complete!")

if __name__ == "__main__":
    fix_database()
