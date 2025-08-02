"""
Transcript Fact Checker - Main Application
A focused tool for fact-checking transcripts from various sources
Production-ready with Redis job storage for scalability
"""
import os 
import sys
import json
import logging
import uuid
import redis
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from threading import Thread
import traceback
from typing import Dict, Optional

# Debug logging for Render deployment
print(f"Starting app on Render...", file=sys.stderr)
print(f"Python version: {sys.version}", file=sys.stderr)
print(f"Port: {os.environ.get('PORT', 'NOT SET')}", file=sys.stderr)
print(f"Redis URL Set: {'REDIS_URL' in os.environ}", file=sys.stderr)
print(f"Secret Key Set: {'SECRET_KEY' in os.environ}", file=sys.stderr)
print(f"Google API Key Set: {'GOOGLE_FACTCHECK_API_KEY' in os.environ}", file=sys.stderr)

# Import configuration
from config import Config

# Import services
from services.transcript import TranscriptProcessor
from services.claims import ClaimExtractor
from services.factcheck import FactChecker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Validate configuration
Config.validate()

# Initialize services
transcript_processor = TranscriptProcessor()
claim_extractor = ClaimExtractor()
fact_checker = FactChecker()

# Job Storage Class
class JobStore:
    """Redis-backed job storage with in-memory fallback"""
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_client = None
        self._memory_store = {}
        
        if redis_url:
            try:
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                # Test connection
                self.redis_client.ping()
                logger.info("✓ Redis connected successfully")
            except Exception as e:
                logger.error(f"Redis connection failed: {str(e)}")
                logger.warning("Falling back to in-memory storage")
                self.redis_client = None
        else:
            logger.warning("No Redis URL provided, using in-memory storage")
    
    def _get_key(self, job_id: str) -> str:
        """Get Redis key for job"""
        return f"factcheck:job:{job_id}"
    
    def set_job(self, job_id: str, job_data: Dict) -> bool:
        """Store job data"""
        try:
            if self.redis_client:
                # Store in Redis with 2 hour expiration
                return self.redis_client.setex(
                    self._get_key(job_id),
                    7200,  # 2 hour TTL
                    json.dumps(job_data)
                )
            else:
                self._memory_store[job_id] = job_data
                return True
        except Exception as e:
            logger.error(f"Error storing job {job_id}: {str(e)}")
            # Fallback to memory
            self._memory_store[job_id] = job_data
            return True
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Retrieve job data"""
        try:
            if self.redis_client:
                data = self.redis_client.get(self._get_key(job_id))
                if data:
                    return json.loads(data)
                # Check memory fallback
                return self._memory_store.get(job_id)
            else:
                return self._memory_store.get(job_id)
        except Exception as e:
            logger.error(f"Error retrieving job {job_id}: {str(e)}")
            return self._memory_store.get(job_id)
    
    def update_job(self, job_id: str, updates: Dict) -> bool:
        """Update job data"""
        try:
            job = self.get_job(job_id)
            if job:
                job.update(updates)
                return self.set_job(job_id, job)
            return False
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {str(e)}")
            return False
    
    def delete_job(self, job_id: str) -> bool:
        """Delete job data"""
        try:
            if self.redis_client:
                self.redis_client.delete(self._get_key(job_id))
            self._memory_store.pop(job_id, None)
            return True
        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {str(e)}")
            return False
    
    def list_jobs(self) -> list:
        """List all job IDs"""
        try:
            jobs = []
            if self.redis_client:
                pattern = self._get_key("*")
                keys = self.redis_client.keys(pattern)
                prefix_len = len("factcheck:job:")
                jobs.extend([key[prefix_len:] for key in keys])
            # Add memory store jobs
            jobs.extend(self._memory_store.keys())
            return list(set(jobs))  # Remove duplicates
        except Exception as e:
            logger.error(f"Error listing jobs: {str(e)}")
            return list(self._memory_store.keys())
    
    def get_active_job_count(self) -> int:
        """Get count of active jobs"""
        return len(self.list_jobs())

# Initialize job store
REDIS_URL = os.getenv('REDIS_URL')
job_store = JobStore(REDIS_URL)

# Routes
@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'transcript-factchecker',
        'version': '1.0.0',
        'storage': 'redis' if job_store.redis_client else 'memory',
        'active_jobs': job_store.get_active_job_count()
    }), 200

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Start analysis job"""
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            input_type = data.get('type', 'text')
        else:
            data = {}
            input_type = request.form.get('type', 'text')
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        logger.info(f"Creating new job: {job_id}")
        
        # Initialize job
        job_data = {
            'id': job_id,
            'status': 'processing',
            'progress': 0,
            'created_at': datetime.now().isoformat(),
            'input_type': input_type,
            'results': None,
            'error': None
        }
        
        # Store job
        if not job_store.set_job(job_id, job_data):
            return jsonify({'success': False, 'error': 'Failed to create job'}), 500
        
        logger.info(f"Starting transcript processing for job {job_id}")
        
        # Process based on input type
        if input_type == 'text':
            transcript = data.get('content', '') if request.is_json else request.form.get('content', '')
            if not transcript:
                job_store.update_job(job_id, {'status': 'error', 'error': 'No transcript text provided'})
                return jsonify({'success': False, 'error': "No transcript text provided"}), 400
            
            # Process transcript in a background thread
            thread = Thread(target=process_transcript_wrapper, args=(job_id, transcript, 'Direct Input'))
            thread.daemon = True
            thread.start()
                
        elif input_type == 'file':
            if 'file' not in request.files:
                job_store.update_job(job_id, {'status': 'error', 'error': 'No file uploaded'})
                return jsonify({'success': False, 'error': "No file uploaded"}), 400
            
            file = request.files['file']
            if file.filename == '':
                job_store.update_job(job_id, {'status': 'error', 'error': 'No file selected'})
                return jsonify({'success': False, 'error': "No file selected"}), 400
            
            # Check file extension
            if not allowed_file(file.filename):
                error_msg = f"Invalid file type. Allowed: {', '.join(Config.ALLOWED_EXTENSIONS)}"
                job_store.update_job(job_id, {'status': 'error', 'error': error_msg})
                return jsonify({'success': False, 'error': error_msg}), 400
            
            # Read file content
            content = file.read().decode('utf-8')
            
            # Process transcript in a background thread
            thread = Thread(target=process_transcript_wrapper, args=(job_id, content, file.filename))
            thread.daemon = True
            thread.start()
                
        elif input_type == 'youtube':
            url = data.get('url', '') if request.is_json else request.form.get('url', '')
            if not url:
                job_store.update_job(job_id, {'status': 'error', 'error': 'No YouTube URL provided'})
                return jsonify({'success': False, 'error': "No YouTube URL provided"}), 400
            
            # Process YouTube URL in a background thread
            thread = Thread(target=process_youtube_wrapper, args=(job_id, url))
            thread.daemon = True
            thread.start()
                
        else:
            error_msg = f"Invalid input type: {input_type}"
            job_store.update_job(job_id, {'status': 'error', 'error': error_msg})
            return jsonify({'success': False, 'error': error_msg}), 400
        
        logger.info(f"Job {job_id} created successfully")
        return jsonify({
            'success': True,
            'job_id': job_id
        })
        
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/status/<job_id>')
def get_status(job_id):
    """Get job status"""
    job = job_store.get_job(job_id)
    
    if not job:
        logger.error(f"Job {job_id} not found. Available jobs: {job_store.list_jobs()}")
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify({
        'id': job['id'],
        'status': job['status'],
        'progress': job['progress'],
        'created_at': job['created_at'],
        'error': job.get('error')
    })

@app.route('/api/results/<job_id>')
def get_results(job_id):
    """Get analysis results"""
    job = job_store.get_job(job_id)
    
    if not job:
        logger.error(f"Job {job_id} not found for results")
        return jsonify({'error': 'Job not found'}), 404
    
    if job['status'] != 'complete':
        return jsonify({'error': 'Analysis not complete'}), 400
    
    return jsonify({
        'success': True,
        'results': job['results']
    })

@app.route('/api/export/<job_id>', methods=['POST'])
def export_results(job_id):
    """Export results in various formats"""
    job = job_store.get_job(job_id)
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job['status'] != 'complete':
        return jsonify({'error': 'Analysis not complete'}), 400
    
    data = request.get_json()
    format_type = data.get('format', 'json')
    
    if format_type not in Config.EXPORT_FORMATS:
        return jsonify({'error': f'Invalid format. Allowed: {", ".join(Config.EXPORT_FORMATS)}'}), 400
    
    try:
        if format_type == 'json':
            filename = f'factcheck_report_{job_id}.json'
            return jsonify({
                'success': True,
                'download_url': f'/api/download/{job_id}/json',
                'filename': filename
            })
        
        elif format_type == 'pdf':
            filename = f'factcheck_report_{job_id}.pdf'
            return jsonify({
                'success': True,
                'download_url': f'/api/download/{job_id}/pdf',
                'filename': filename
            })
        
        else:
            filename = f'factcheck_report_{job_id}.txt'
            return jsonify({
                'success': True,
                'download_url': f'/api/download/{job_id}/txt',
                'filename': filename
            })
            
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        return jsonify({'error': 'Export failed'}), 500

@app.route('/api/download/<job_id>/<format_type>')
def download_file(job_id, format_type):
    """Download exported file"""
    job = job_store.get_job(job_id)
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job['status'] != 'complete':
        return jsonify({'error': 'Analysis not complete'}), 400
    
    # Generate file content based on format
    if format_type == 'json':
        content = json.dumps(job['results'], indent=2)
        mimetype = 'application/json'
    elif format_type == 'txt':
        content = generate_text_report(job['results'])
        mimetype = 'text/plain'
    else:
        return jsonify({'error': 'Format not implemented yet'}), 501
    
    # Return file
    return content, 200, {
        'Content-Type': mimetype,
        'Content-Disposition': f'attachment; filename=factcheck_report_{job_id}.{format_type}'
    }

# Helper functions
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def process_transcript_wrapper(job_id, transcript, source):
    """Wrapper to handle errors in transcript processing"""
    try:
        process_transcript(job_id, transcript, source)
    except Exception as e:
        logger.error(f"Error processing transcript for job {job_id}: {str(e)}")
        logger.error(traceback.format_exc())
        job_store.update_job(job_id, {'status': 'error', 'error': str(e)})

def process_youtube_wrapper(job_id, url):
    """Wrapper to handle YouTube processing"""
    try:
        # Update progress
        job_store.update_job(job_id, {'progress': 10})
        
        # Extract transcript from YouTube
        transcript_data = transcript_processor.parse_youtube(url)
        
        if not transcript_data['success']:
            job_store.update_job(job_id, {
                'status': 'error',
                'error': transcript_data.get('error', 'Failed to extract YouTube transcript')
            })
            return
        
        # Process the transcript
        process_transcript(job_id, transcript_data['transcript'], transcript_data['title'])
        
    except Exception as e:
        logger.error(f"Error processing YouTube for job {job_id}: {str(e)}")
        logger.error(traceback.format_exc())
        job_store.update_job(job_id, {'status': 'error', 'error': str(e)})

def process_transcript(job_id, transcript, source):
    """Process transcript through the fact-checking pipeline"""
    try:
        # Ensure job exists
        job = job_store.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found in job store")
            return
        
        # Clean transcript
        job_store.update_job(job_id, {'progress': 20})
        cleaned_transcript = transcript_processor.clean_transcript(transcript)
        
        # Extract claims
        job_store.update_job(job_id, {'progress': 40})
        claims = claim_extractor.extract_claims(cleaned_transcript)
        logger.info(f"Job {job_id}: Extracted {len(claims)} claims")
        
        # Prioritize and filter claims
        job_store.update_job(job_id, {'progress': 50})
        verified_claims = claim_extractor.filter_verifiable(claims)
        prioritized_claims = claim_extractor.prioritize_claims(verified_claims)
        logger.info(f"Job {job_id}: Checking {len(prioritized_claims)} prioritized claims")
        
        # Ensure we have strings, not dictionaries
        if prioritized_claims and isinstance(prioritized_claims[0], dict):
            logger.warning("Claims are dictionaries, extracting text")
            prioritized_claims = [claim['text'] if isinstance(claim, dict) else claim for claim in prioritized_claims]
        
        # Fact check claims
        job_store.update_job(job_id, {'progress': 70})
        fact_check_results = []
        
        # Use batch_check but with error handling for individual claims
        claims_to_check = prioritized_claims[:Config.MAX_CLAIMS_PER_TRANSCRIPT]
        
        for i in range(0, len(claims_to_check), Config.FACT_CHECK_BATCH_SIZE):
            batch = claims_to_check[i:i + Config.FACT_CHECK_BATCH_SIZE]
            try:
                batch_results = fact_checker.batch_check(batch)
                fact_check_results.extend(batch_results)
                # Update progress
                progress = 70 + int((len(fact_check_results) / len(claims_to_check)) * 20)
                job_store.update_job(job_id, {'progress': progress})
            except Exception as e:
                logger.error(f"Error checking batch starting at {i}: {str(e)}")
                # Add unverified results for failed batch
                for claim in batch:
                    fact_check_results.append({
                        'claim': claim,
                        'verdict': 'unverified',
                        'confidence': 0,
                        'explanation': 'Error during fact-checking',
                        'publisher': 'Error',
                        'url': '',
                        'sources': []
                    })
        
        # Calculate overall credibility
        job_store.update_job(job_id, {'progress': 90})
        credibility_score = fact_checker.calculate_credibility(fact_check_results)
        
        # Compile results
        results = {
            'source': source,
            'transcript_length': len(transcript),
            'word_count': len(transcript.split()),
            'total_claims': len(claims),
            'verified_claims': len(verified_claims),
            'checked_claims': len(fact_check_results),
            'credibility_score': credibility_score,
            'credibility_label': get_credibility_label(credibility_score),
            'fact_checks': fact_check_results,
            'summary': generate_summary(fact_check_results, credibility_score),
            'analyzed_at': datetime.now().isoformat()
        }
        
        # Complete job
        job_store.update_job(job_id, {
            'progress': 100,
            'status': 'complete',
            'results': results
        })
        
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Processing error for job {job_id}: {str(e)}")
        logger.error(traceback.format_exc())
        job_store.update_job(job_id, {'status': 'error', 'error': str(e)})

def get_credibility_label(score):
    """Convert credibility score to label"""
    if score >= 80:
        return "High Credibility"
    elif score >= 60:
        return "Moderate Credibility"
    elif score >= 40:
        return "Low Credibility"
    else:
        return "Very Low Credibility"

def generate_summary(fact_checks, credibility_score):
    """Generate analysis summary"""
    if not fact_checks:
        return "No claims could be fact-checked."
    
    verified_count = sum(1 for fc in fact_checks if fc.get('verdict') in ['true', 'mostly_true'])
    false_count = sum(1 for fc in fact_checks if fc.get('verdict') in ['false', 'mostly_false'])
    unverified_count = sum(1 for fc in fact_checks if fc.get('verdict') == 'unverified')
    
    summary = f"Analysis complete. Out of {len(fact_checks)} claims checked: "
    summary += f"{verified_count} verified as true, {false_count} found to be false, "
    summary += f"and {unverified_count} could not be verified. "
    summary += f"Overall credibility score: {credibility_score}%."
    
    return summary

def generate_text_report(results):
    """Generate plain text report"""
    report = f"""TRANSCRIPT FACT-CHECK REPORT
Generated: {results['analyzed_at']}
Source: {results['source']}

OVERVIEW
--------
Total Claims Identified: {results['total_claims']}
Claims Checked: {results['checked_claims']}
Credibility Score: {results['credibility_score']}% ({results['credibility_label']})

SUMMARY
-------
{results['summary']}

DETAILED FACT CHECKS
-------------------
"""
    
    for i, fc in enumerate(results['fact_checks'], 1):
        report += f"\n{i}. CLAIM: {fc['claim']}\n"
        report += f"   VERDICT: {fc['verdict'].upper()}\n"
        report += f"   CONFIDENCE: {fc.get('confidence', 'N/A')}%\n"
        if fc.get('explanation'):
            report += f"   EXPLANATION: {fc['explanation']}\n"
        if fc.get('sources'):
            report += f"   SOURCES: {', '.join(fc['sources'])}\n"
    
    return report

# Cleanup old jobs periodically (optional)
def cleanup_old_jobs():
    """Remove jobs older than 2 hours"""
    try:
        cutoff_time = datetime.now() - timedelta(hours=2)
        for job_id in job_store.list_jobs():
            job = job_store.get_job(job_id)
            if job:
                created = datetime.fromisoformat(job['created_at'])
                if created < cutoff_time:
                    job_store.delete_job(job_id)
                    logger.info(f"Cleaned up old job: {job_id}")
    except Exception as e:
        logger.error(f"Error during job cleanup: {str(e)}")

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Get port from environment variable (Render provides this)
    port = int(os.environ.get('PORT', 5000))
    
    # Log startup information
    logger.info(f"Starting Flask app on port {port}")
    logger.info(f"Debug mode: {Config.DEBUG}")
    logger.info(f"Storage backend: {'Redis' if job_store.redis_client else 'In-Memory'}")
    logger.info(f"Active APIs: {Config.get_active_apis()}")
    
    # Run the app
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)
