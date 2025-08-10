# create_error_templates.py - Create missing error template files
"""
Creates the missing error template files in templates/errors/
"""

import os

# Error templates content
error_404_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Not Found - Workforce Scheduler</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .error-container {
            text-align: center;
            padding: 2rem;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .error-code {
            font-size: 6rem;
            font-weight: 700;
            color: #dc3545;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-code">404</div>
        <h1 class="h3 mb-3">Page Not Found</h1>
        <p class="text-muted mb-4">The page you're looking for doesn't exist or has been moved.</p>
        <div class="d-flex gap-2 justify-content-center">
            <a href="/" class="btn btn-primary">Go Home</a>
            <a href="javascript:history.back()" class="btn btn-outline-secondary">Go Back</a>
        </div>
    </div>
</body>
</html>"""

error_500_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Server Error - Workforce Scheduler</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .error-container {
            text-align: center;
            padding: 2rem;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            max-width: 500px;
        }
        .error-code {
            font-size: 6rem;
            font-weight: 700;
            color: #dc3545;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-code">500</div>
        <h1 class="h3 mb-3">Server Error</h1>
        <p class="text-muted mb-4">Something went wrong on our end. We're working to fix it.</p>
        <p class="text-muted small mb-4">If this problem persists, please contact your system administrator.</p>
        <div class="d-flex gap-2 justify-content-center">
            <a href="/" class="btn btn-primary">Go Home</a>
            <a href="javascript:location.reload()" class="btn btn-outline-secondary">Try Again</a>
        </div>
    </div>
</body>
</html>"""

def create_error_templates():
    """Create the error template files"""
    # Create templates/errors directory
    os.makedirs('templates/errors', exist_ok=True)
    
    # Create 404.html
    with open('templates/errors/404.html', 'w') as f:
        f.write(error_404_template)
    print("✓ Created templates/errors/404.html")
    
    # Create 500.html
    with open('templates/errors/500.html', 'w') as f:
        f.write(error_500_template)
    print("✓ Created templates/errors/500.html")
    
    print("\n✓ Error templates created successfully!")

if __name__ == "__main__":
    create_error_templates()
