from flask import Flask, render_template, jsonify, request
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Basic route for homepage
@app.route('/')
def index():
    return render_template('index.html')

# Route for supervisor dashboard
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# API endpoint to get today's schedule
@app.route('/api/schedule/today')
def get_today_schedule():
    # For now, return dummy data
    return jsonify({
        'success': True,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'shifts': [
            {
                'position': 'Cashier',
                'time': '9:00 AM - 5:00 PM',
                'employee': 'John Doe',
                'status': 'confirmed'
            },
            {
                'position': 'Stock Clerk',
                'time': '9:00 AM - 5:00 PM',
                'employee': 'Jane Smith',
                'status': 'confirmed'
            },
            {
                'position': 'Supervisor',
                'time': '8:00 AM - 6:00 PM',
                'employee': 'Mike Johnson',
                'status': 'confirmed'
            }
        ]
    })

# API endpoint to report absence
@app.route('/api/absence/report', methods=['POST'])
def report_absence():
    data = request.get_json()
    # For now, just return success
    return jsonify({
        'success': True,
        'message': 'Absence reported and coverage request sent'
    })

if __name__ == '__main__':
    app.run(debug=True)
