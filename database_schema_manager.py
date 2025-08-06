-- Complete Database Fix for vacation_calendar table
-- This script includes full validation and error handling

-- Step 1: Create a transaction for safety
BEGIN;

-- Step 2: Check if the table exists
DO $$ 
DECLARE
    table_exists boolean;
    column_exists boolean;
BEGIN
    -- Check if vacation_calendar table exists
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'vacation_calendar'
    ) INTO table_exists;
    
    IF NOT table_exists THEN
        RAISE NOTICE 'Table vacation_calendar does not exist. Creating it...';
        
        -- Create the table if it doesn't exist
        CREATE TABLE vacation_calendar (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER NOT NULL,
            date DATE NOT NULL,
            shift_type VARCHAR(20),
            reason VARCHAR(50),
            status VARCHAR(20) DEFAULT 'approved',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_employee 
                FOREIGN KEY(employee_id) 
                REFERENCES employee(id) 
                ON DELETE CASCADE
        );
        
        -- Create indexes
        CREATE INDEX idx_vacation_calendar_employee_date 
            ON vacation_calendar(employee_id, date);
        CREATE INDEX idx_vacation_calendar_date 
            ON vacation_calendar(date);
        CREATE INDEX idx_vacation_calendar_status 
            ON vacation_calendar(status);
            
        RAISE NOTICE 'Table vacation_calendar created successfully';
    ELSE
        -- Table exists, check if status column exists
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'vacation_calendar' 
            AND column_name = 'status'
        ) INTO column_exists;
        
        IF NOT column_exists THEN
            RAISE NOTICE 'Adding status column to vacation_calendar table...';
            
            -- Add the status column
            ALTER TABLE vacation_calendar 
            ADD COLUMN status VARCHAR(20) DEFAULT 'approved';
            
            -- Update any existing records
            UPDATE vacation_calendar 
            SET status = 'approved' 
            WHERE status IS NULL;
            
            -- Add index on status
            CREATE INDEX IF NOT EXISTS idx_vacation_calendar_status 
                ON vacation_calendar(status);
            
            RAISE NOTICE 'Column status added successfully';
        ELSE
            RAISE NOTICE 'Column status already exists';
            
            -- Ensure default value is set
            ALTER TABLE vacation_calendar 
            ALTER COLUMN status SET DEFAULT 'approved';
            
            -- Update any NULL values
            UPDATE vacation_calendar 
            SET status = 'approved' 
            WHERE status IS NULL;
        END IF;
    END IF;
    
    -- Add check constraint if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'chk_vacation_status'
    ) THEN
        ALTER TABLE vacation_calendar 
        ADD CONSTRAINT chk_vacation_status 
        CHECK (status IN ('pending', 'approved', 'denied', 'cancelled'));
        
        RAISE NOTICE 'Check constraint added successfully';
    END IF;
    
END $$;

-- Step 3: Verify the changes
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'vacation_calendar'
ORDER BY ordinal_position;

-- Step 4: Show sample data
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT status) as unique_statuses,
    status,
    COUNT(*) as count_per_status
FROM vacation_calendar
GROUP BY status
ORDER BY count_per_status DESC;

-- Step 5: Commit the transaction
COMMIT;

-- Step 6: Create a helper function for coverage gap calculations
CREATE OR REPLACE FUNCTION get_coverage_gaps(
    p_start_date DATE,
    p_end_date DATE,
    p_crew VARCHAR(1) DEFAULT NULL
)
RETURNS TABLE (
    gap_date DATE,
    crew VARCHAR(1),
    employees_scheduled INTEGER,
    employees_on_leave INTEGER,
    coverage_percentage NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        d.date_value as gap_date,
        c.crew_value as crew,
        COALESCE(s.scheduled_count, 0) as employees_scheduled,
        COALESCE(v.leave_count, 0) as employees_on_leave,
        CASE 
            WHEN COALESCE(s.scheduled_count, 0) = 0 THEN 0
            ELSE ROUND(
                (COALESCE(s.scheduled_count, 0) - COALESCE(v.leave_count, 0))::NUMERIC / 
                COALESCE(s.scheduled_count, 0) * 100, 2
            )
        END as coverage_percentage
    FROM 
        generate_series(p_start_date, p_end_date, '1 day'::interval) d(date_value)
    CROSS JOIN 
        (SELECT unnest(ARRAY['A', 'B', 'C', 'D']) as crew_value) c
    LEFT JOIN (
        SELECT 
            date, 
            crew, 
            COUNT(*) as scheduled_count
        FROM schedule
        WHERE date BETWEEN p_start_date AND p_end_date
        GROUP BY date, crew
    ) s ON d.date_value = s.date AND c.crew_value = s.crew
    LEFT JOIN (
        SELECT 
            vc.date, 
            e.crew,
            COUNT(*) as leave_count
        FROM vacation_calendar vc
        JOIN employee e ON vc.employee_id = e.id
        WHERE vc.date BETWEEN p_start_date AND p_end_date
        AND vc.status = 'approved'
        GROUP BY vc.date, e.crew
    ) v ON d.date_value = v.date AND c.crew_value = v.crew
    WHERE (p_crew IS NULL OR c.crew_value = p_crew)
    ORDER BY d.date_value, c.crew_value;
END;
$$ LANGUAGE plpgsql;

-- Step 7: Grant permissions (skip if user has all privileges)
-- Note: Replace 'your_app_user' with your actual database user
-- Or comment out these lines if your user already has full access
-- GRANT SELECT, INSERT, UPDATE, DELETE ON vacation_calendar TO your_app_user;
-- GRANT USAGE ON SEQUENCE vacation_calendar_id_seq TO your_app_user;

-- Final verification output
SELECT 
    'Database fix completed successfully!' as message,
    (SELECT COUNT(*) FROM vacation_calendar) as total_vacation_records,
    (SELECT COUNT(DISTINCT status) FROM vacation_calendar) as distinct_statuses;

-- ROLLBACK; -- Uncomment this line if you want to test without committing
