# COMPLETE FIX PACKAGE FOR AUTHOR DISPLAY ISSUE
# Deploy these files to fix the author not showing in UI

## FILE 1: app.py
## This is the main Flask application file
## Location: app.py

"""
app.py - Flask app with fixed author data flow
"""

import os
import io
import json
import logging
import time
import hashlib
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash

# Import services
from services.news_analyzer import NewsAnalyzer
from services.news_extractor import NewsExtractor
from services.fact_checker import FactChecker
from services.source_credibility import SOURCE_CREDIBILITY
from services.author_analyzer import AuthorAnalyzer

# Import database models
from models import db, User, Analysis, Source, Author, APIUsage, FactCheckCache, init_db

# Configure logging early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import PDF generator
try:
    from services.pdf_generator import PDFGenerator
    pdf_generator = PDFGenerator()
    PDF_EXPORT_ENABLED = True
except ImportError:
    logger.warning("ReportLab not installed - PDF export feature disabled")
    pdf_generator = None
    PDF_EXPORT_ENABLED = False

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///news_analyzer.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure database connection pooling
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Test connections before using
    'pool_recycle': 300,    # Recycle connections after 5 minutes
    'pool_size': 10,        # Number of connections to maintain
    'max_overflow': 20      # Maximum overflow connections
}

# Initialize extensions
CORS(app)
db.init_app(app)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["100 per hour"]
)

# Initialize services
analyzer = NewsAnalyzer()
news_extractor = NewsExtractor()
fact_checker = FactChecker()
author_analyzer = AuthorAnalyzer()

# Create tables and seed data
with app.app_context():
    try:
        db.create_all()
        from models import seed_sources
        seed_sources()
    except Exception as e:
        logger.warning(f"Could not initialize database: {e}")

@app.before_request
def log_request():
    """Log API usage with proper error handling"""
    if request.path.startswith('/api/'):
        try:
            usage = APIUsage(
                user_id=session.get('user_id'),
                endpoint=request.path,
                method=request.method,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')[:500]
            )
            db.session.add(usage)
            db.session.commit()
        except Exception as e:
            logger.error(f"Could not log API usage: {e}")
            # IMPORTANT: Clean up the session
            try:
                db.session.rollback()
            except:
                # If rollback fails, remove the session entirely
                db.session.remove()

@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    """Return empty favicon to avoid 404 errors"""
    return '', 204

@app.route('/api/analyze', methods=['POST'])
@limiter.limit("20 per hour")
def analyze():
    """Enhanced analyze endpoint with database integration"""
    start_time = time.time()
    
    try:
        # Ensure clean database session at the start
        try:
            db.session.rollback()
        except:
            # If rollback fails, create new session
            db.session.remove()
            db.session = db.create_scoped_session()
        
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Determine content type
        if 'url' in data:
            content = data['url']
            content_type = 'url'
        elif 'text' in data:
            content = data['text']
            content_type = 'text'
        else:
            return jsonify({'success': False, 'error': 'Please provide either URL or text'}), 400
        
        # Get user ID from session (if authenticated)
        user_id = session.get('user_id')
        
        # Check for force_fresh parameter
        force_fresh = data.get('force_fresh', False)
        
        # Try to check for cached analysis, but don't fail if database is down
        recent_analysis = None
        if not force_fresh:  # Only check cache if not forcing fresh
            try:
                if content_type == 'url':
                    recent_analysis = Analysis.query.filter_by(url=content)\
                        .filter(Analysis.created_at > datetime.utcnow() - timedelta(hours=24))\
                        .first()
                    
                    if recent_analysis and recent_analysis.full_analysis:
                        # Validate that cached data has required fields
                        cached_data = recent_analysis.full_analysis
                        required_fields = ['success', 'article', 'bias_analysis', 'trust_score']
                        
                        # Check if all required fields exist
                        if all(field in cached_data for field in required_fields):
                            # Check if the cached data has the new analysis fields
                            if 'persuasion_analysis' not in cached_data or 'connection_analysis' not in cached_data:
                                # Cached data is old format, perform fresh analysis
                                logger.info(f"Cached data for {content} is outdated, performing fresh analysis")
                                recent_analysis = None
                            else:
                                logger.info(f"Returning cached analysis for {content}")
                                return jsonify({
                                    'success': True,
                                    'cached': True,
                                    **cached_data,
                                    'processing_time': recent_analysis.processing_time
                                })
                        else:
                            # Cached data is incomplete, perform fresh analysis
                            logger.info(f"Cached data for {content} is incomplete, performing fresh analysis")
                            recent_analysis = None
            except Exception as e:
                logger.warning(f"Could not check cache: {e}")
                try:
                    db.session.rollback()
                except:
                    db.session.remove()
                # Continue without cache
        
        # Development mode: always provide full analysis but track plan selection
        selected_plan = data.get('plan', 'free')
        is_development = True  # Set to False for production
        
        # In development, everyone gets pro features
        if is_development:
            is_pro = True
            analysis_mode = 'development'
        else:
            is_pro = selected_plan == 'pro'
            analysis_mode = selected_plan
        
        # Perform analysis using existing analyzer
        result = analyzer.analyze(content, content_type, is_pro)
        
        if not result.get('success'):
            return jsonify(result), 400
        
        # Add plan info to result
        result['selected_plan'] = selected_plan
        result['analysis_mode'] = analysis_mode
        result['development_mode'] = is_development
        
        # Enhanced fact checking with caching (wrapped in try-catch)
        if is_pro and result.get('key_claims'):
            try:
                cached_facts = []
                new_claims = []
                
                for claim in result['key_claims'][:5]:
                    claim_text = claim.get('text', claim) if isinstance(claim, dict) else claim
                    claim_hash = hashlib.sha256(claim_text.encode()).hexdigest()
                    
                    # Try to check cache
                    try:
                        cached = FactCheckCache.query.filter_by(claim_hash=claim_hash)\
                            .filter(FactCheckCache.expires_at > datetime.utcnow()).first()
                        
                        if cached:
                            cached_facts.append(cached.result)
                        else:
                            new_claims.append(claim_text)
                    except:
                        # If cache check fails, treat as new claim
                        new_claims.append(claim_text)
                
                # Check new claims
                if new_claims:
                    new_results = fact_checker.check_claims(new_claims)
                    
                    # Try to cache new results, but don't fail if database is down
                    try:
                        for i, fc_result in enumerate(new_results):
                            if i < len(new_claims):
                                cache_entry = FactCheckCache(
                                    claim_hash=hashlib.sha256(new_claims[i].encode()).hexdigest(),
                                    claim_text=new_claims[i],
                                    result=fc_result,
                                    source='google',
                                    expires_at=datetime.utcnow() + timedelta(days=7)
                                )
                                db.session.add(cache_entry)
                        db.session.commit()
                    except Exception as e:
                        logger.warning(f"Could not cache fact checks: {e}")
                        try:
                            db.session.rollback()
                        except:
                            db.session.remove()
                    
                    cached_facts.extend(new_results)
                
                result['fact_checks'] = cached_facts
            except Exception as e:
                logger.warning(f"Fact checking error: {e}")
                # Continue without enhanced fact checking
        
        # Try to store analysis in database, but don't fail if database is down
        try:
            # Update or create source record
            source = None
            if result.get('article', {}).get('domain'):
                domain = result['article']['domain']
                source = Source.query.filter_by(domain=domain).first()
                if not source:
                    # Get credibility info from SOURCE_CREDIBILITY dictionary
                    source_info = SOURCE_CREDIBILITY.get(domain, {})
                    source = Source(
                        domain=domain,
                        name=source_info.get('name', domain),
                        credibility_score=_map_credibility_to_score(source_info.get('credibility', 'Unknown')),
                        political_lean=source_info.get('bias', 'Unknown')
                    )
                    db.session.add(source)
                    db.session.flush()  # Get source.id without committing
                
                # Fix: Initialize values if None
                if source.total_articles_analyzed is None:
                    source.total_articles_analyzed = 0
                if source.average_trust_score is None:
                    source.average_trust_score = 0
                    
                source.total_articles_analyzed += 1
                
                if result.get('trust_score'):
                    # Update average trust score
                    if source.average_trust_score == 0:
                        source.average_trust_score = result['trust_score']
                    else:
                        source.average_trust_score = (
                            (source.average_trust_score * (source.total_articles_analyzed - 1) + 
                             result['trust_score']) / source.total_articles_analyzed
                        )
            
            # Update or create author record
            author = None
            if result.get('article', {}).get('author'):
                author_name = result['article']['author']
                author = Author.query.filter_by(name=author_name).first()
                if not author:
                    author = Author(
                        name=author_name,
                        primary_source_id=source.id if source else None
                    )
                    db.session.add(author)
                    db.session.flush()
                
                # Fix: Initialize values if None
                if author.total_articles_analyzed is None:
                    author.total_articles_analyzed = 0
                    
                author.total_articles_analyzed += 1
                author.last_seen = datetime.utcnow()
                
                # Update author credibility from analysis
                if result.get('author_analysis', {}).get('credibility_score'):
                    author.credibility_score = result['author_analysis']['credibility_score']
            
            # Create analysis record
            analysis = Analysis(
                user_id=user_id,
                url=content if content_type == 'url' else None,
                title=result.get('article', {}).get('title'),
                trust_score=result.get('trust_score', 0),
                bias_score=abs(result.get('bias_analysis', {}).get('political_lean', 0)) if result.get('bias_analysis') else 0,
                clickbait_score=result.get('clickbait_score', 0),
                full_analysis=result,
                author_data=result.get('author_analysis', {}),
                source_data=result.get('analysis', {}).get('source_credibility', {}),
                bias_analysis=result.get('bias_analysis', {}),
                fact_check_results=result.get('fact_checks', []),
                processing_time=time.time() - start_time
            )
            db.session.add(analysis)
            
            # Commit all changes
            db.session.commit()
            
            # Add analysis ID for export
            result['analysis_id'] = str(analysis.id)
            
        except Exception as e:
            logger.error(f"Database error (non-critical): {str(e)}")
            try:
                db.session.rollback()
            except:
                db.session.remove()
            # Continue - the analysis still works without database storage
        
        # Add export status
        result['export_enabled'] = PDF_EXPORT_ENABLED
        result['processing_time'] = time.time() - start_time
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        # Ensure session is rolled back
        try:
            db.session.rollback()
        except:
            db.session.remove()
        return jsonify({
            'success': False,
            'error': f'Analysis failed: {str(e)}'
        }), 500

def _map_credibility_to_score(credibility_text):
    """Map credibility text to numeric score"""
    mapping = {
        'High': 85,
        'Medium': 60,
        'Low': 30,
        'Very Low': 10,
        'Unknown': 50
    }
    return mapping.get(credibility_text, 50)

@app.route('/api/export/pdf', methods=['POST'])
def export_pdf():
    """Export analysis as PDF"""
    if not PDF_EXPORT_ENABLED:
        return jsonify({'error': 'PDF export feature not available'}), 503
    
    try:
        data = request.json
        analysis_data = data.get('analysis_data', {})
        
        if not analysis_data:
            # Try to get from database
            try:
                analysis_id = data.get('analysis_id')
                if analysis_id:
                    analysis = Analysis.query.get(analysis_id)
                    if analysis:
                        analysis_data = analysis.full_analysis
            except Exception as e:
                logger.warning(f"Could not fetch analysis from database: {e}")
                try:
                    db.session.rollback()
                except:
                    db.session.remove()
        
        if not analysis_data:
            return jsonify({'error': 'No analysis data provided'}), 400
        
        # Generate PDF
        pdf_buffer = pdf_generator.generate_analysis_pdf(analysis_data)
        
        # Create filename
        domain = analysis_data.get('article', {}).get('domain', 'article')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"news_analysis_{domain}_{timestamp}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"PDF export error: {str(e)}")
        return jsonify({'error': 'PDF export failed'}), 500

@app.route('/api/export/json', methods=['POST'])
def export_json():
    """Export analysis as JSON"""
    try:
        data = request.json
        analysis_data = data.get('analysis_data', {})
        
        if not analysis_data:
            # Try to get from database
            try:
                analysis_id = data.get('analysis_id')
                if analysis_id:
                    analysis = Analysis.query.get(analysis_id)
                    if analysis:
                        analysis_data = analysis.full_analysis
            except Exception as e:
                logger.warning(f"Could not fetch analysis from database: {e}")
                try:
                    db.session.rollback()
                except:
                    db.session.remove()
        
        if not analysis_data:
            return jsonify({'error': 'No analysis data provided'}), 400
        
        # Create clean JSON export
        export_data = {
            'metadata': {
                'exported_at': datetime.utcnow().isoformat(),
                'version': '1.0',
                'source': 'News Analyzer AI'
            },
            'analysis': analysis_data
        }
        
        return jsonify(export_data)
        
    except Exception as e:
        logger.error(f"JSON export error: {str(e)}")
        return jsonify({'error': 'JSON export failed'}), 500

@app.route('/api/history')
def get_history():
    """Get user's analysis history"""
    try:
        user_id = session.get('user_id')
        
        # For now, return recent analyses for all users if not logged in
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        query = Analysis.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        analyses = query.order_by(Analysis.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'analyses': [{
                'id': a.id,
                'url': a.url,
                'title': a.title,
                'trust_score': a.trust_score,
                'created_at': a.created_at.isoformat()
            } for a in analyses.items],
            'total': analyses.total,
            'pages': analyses.pages,
            'current_page': page
        })
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        try:
            db.session.rollback()
        except:
            db.session.remove()
        return jsonify({
            'analyses': [],
            'total': 0,
            'pages': 0,
            'current_page': 1,
            'error': 'Could not fetch history'
        })

@app.route('/api/sources/stats')
def source_statistics():
    """Get source credibility statistics"""
    try:
        sources = Source.query.filter(Source.total_articles_analyzed > 0)\
            .order_by(Source.average_trust_score.desc())\
            .limit(20).all()
        
        return jsonify({
            'sources': [{
                'domain': s.domain,
                'name': s.name,
                'credibility_score': s.credibility_score,
                'political_lean': s.political_lean,
                'articles_analyzed': s.total_articles_analyzed,
                'average_trust_score': round(s.average_trust_score, 1) if s.average_trust_score else 0
            } for s in sources]
        })
    except Exception as e:
        logger.error(f"Source statistics error: {e}")
        try:
            db.session.rollback()
        except:
            db.session.remove()
        return jsonify({
            'sources': [],
            'error': 'Could not fetch source statistics'
        })

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        db_status = 'healthy'
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        try:
            db.session.rollback()
        except:
            db.session.remove()
        db_status = 'unhealthy'
    
    return jsonify({
        'status': 'healthy',
        'service': 'news-analyzer',
        'version': '2.0.0',
        'database': db_status,
        'pdf_export_enabled': PDF_EXPORT_ENABLED,
        'development_mode': True,
        'features': {
            'ai_analysis': bool(os.environ.get('OPENAI_API_KEY')),
            'fact_checking': bool(os.environ.get('GOOGLE_FACT_CHECK_API_KEY')),
            'news_api': bool(os.environ.get('NEWS_API_KEY'))
        }
    })

# Add admin route to clear cache (TEMPORARY - remove in production)
@app.route('/api/admin/clear-cache', methods=['POST'])
def clear_cache():
    """Clear all cached analyses - TEMPORARY ADMIN ROUTE"""
    try:
        # Get password from request
        data = request.get_json()
        password = data.get('password')
        
        # Simple password check (change this!)
        if password != 'admin123':
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Delete all analyses
        deleted = Analysis.query.delete()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'deleted_count': deleted,
            'message': f'Cleared {deleted} cached analyses'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'error': 'Rate limit exceeded',
        'message': str(e.description)
    }), 429

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)


## FILE 2: services/news_analyzer.py
## This is the main analyzer orchestrator that needs to be fixed
## Location: services/news_analyzer.py

"""
services/news_analyzer.py - Main orchestrator with FIXED author data flow
"""

import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# Import all analysis services
from services.news_extractor import NewsExtractor
from services.bias_analyzer import BiasAnalyzer
from services.fact_checker import FactChecker
from services.source_credibility import SourceCredibility
from services.author_analyzer import AuthorAnalyzer
from services.manipulation_detector import ManipulationDetector
from services.transparency_analyzer import TransparencyAnalyzer
from services.clickbait_analyzer import ClickbaitAnalyzer
from services.content_analyzer import ContentAnalyzer
from services.connection_analyzer import ConnectionAnalyzer

# OpenAI integration
try:
    import openai
    OPENAI_AVAILABLE = bool(os.environ.get('OPENAI_API_KEY'))
    if OPENAI_AVAILABLE:
        openai.api_key = os.environ.get('OPENAI_API_KEY')
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

class NewsAnalyzer:
    """Main orchestrator for comprehensive news analysis"""
    
    def __init__(self):
        """Initialize all analysis components"""
        # Core services
        self.extractor = NewsExtractor()
        self.bias_analyzer = BiasAnalyzer()
        self.fact_checker = FactChecker()
        self.source_credibility = SourceCredibility()
        self.author_analyzer = AuthorAnalyzer()
        self.manipulation_detector = ManipulationDetector()
        self.transparency_analyzer = TransparencyAnalyzer()
        self.clickbait_analyzer = ClickbaitAnalyzer()
        self.content_analyzer = ContentAnalyzer()
        self.connection_analyzer = ConnectionAnalyzer()
        
    def analyze(self, content: str, content_type: str = 'url', is_pro: bool = False) -> Dict[str, Any]:
        """
        Perform comprehensive analysis on news content
        
        Args:
            content: URL or text to analyze
            content_type: 'url' or 'text'
            is_pro: Whether to use premium features
            
        Returns:
            Comprehensive analysis results
        """
        try:
            # Step 1: Extract article content
            if content_type == 'url':
                article_data = self.extractor.extract_article(content)
                if not article_data:
                    return {
                        'success': False,
                        'error': 'Could not extract article content'
                    }
            else:
                # For text input, create article data structure
                article_data = {
                    'title': self._extract_title_from_text(content),
                    'text': content,
                    'author': None,  # No author for pasted text
                    'publish_date': None,
                    'url': None,
                    'domain': 'user_input'
                }
            
            # Log what we extracted
            logger.info(f"Extracted article data: {article_data.get('title', 'No title')}")
            logger.info(f"Author from extraction: {article_data.get('author', 'No author')}")
            
            # Step 2: Perform all analyses
            analysis_results = {}
            
            # Core analyses (always performed)
            analysis_results['bias_analysis'] = self.bias_analyzer.analyze(article_data['text'])
            analysis_results['clickbait_score'] = self.clickbait_analyzer.analyze_headline(
                article_data.get('title', ''),
                article_data['text']
            )
            analysis_results['source_credibility'] = self.source_credibility.check_credibility(
                article_data.get('domain', 'unknown')
            )
            
            # CRITICAL FIX: Ensure author is properly analyzed
            if article_data.get('author'):
                logger.info(f"Analyzing author: {article_data['author']} from domain: {article_data.get('domain')}")
                # Call the correct method name
                analysis_results['author_analysis'] = self.author_analyzer.analyze_single_author(
                    article_data['author'],
                    article_data.get('domain')
                )
            else:
                logger.info("No author found in article data")
                analysis_results['author_analysis'] = {
                    'found': False,
                    'name': None,
                    'credibility_score': 50,
                    'bio': 'No author information available',
                    'verification_status': {
                        'verified': False,
                        'journalist_verified': False
                    }
                }
            
            # Content analysis
            analysis_results['content_analysis'] = self.content_analyzer.analyze(article_data['text'])
            analysis_results['transparency_analysis'] = self.transparency_analyzer.analyze(
                article_data['text'],
                article_data.get('author')
            )
            
            # Pro features
            if is_pro:
                # Enhanced fact checking
                key_claims = self._extract_key_claims(article_data['text'])
                analysis_results['key_claims'] = key_claims
                
                # Manipulation detection
                analysis_results['persuasion_analysis'] = self.manipulation_detector.analyze_persuasion(
                    article_data['text'],
                    article_data.get('title', '')
                )
                
                # Connection analysis
                analysis_results['connection_analysis'] = self.connection_analyzer.analyze_connections(
                    article_data['text'],
                    article_data.get('title', ''),
                    analysis_results.get('key_claims', [])
                )
                
                # AI-powered summary if available
                if OPENAI_AVAILABLE:
                    analysis_results['article_summary'] = self._generate_ai_summary(article_data['text'])
                    analysis_results['conversational_summary'] = self._generate_conversational_summary(
                        article_data, analysis_results
                    )
            
            # Step 3: Calculate overall trust score
            trust_score = self._calculate_trust_score(analysis_results, article_data)
            
            # Step 4: Compile final results with proper structure
            return {
                'success': True,
                'article': {
                    'title': article_data.get('title'),
                    'author': article_data.get('author'),  # ENSURE THIS IS SET
                    'publish_date': article_data.get('publish_date'),
                    'url': article_data.get('url'),
                    'domain': article_data.get('domain'),
                    'text_preview': article_data['text'][:500] + '...' if len(article_data['text']) > 500 else article_data['text']
                },
                'trust_score': trust_score,
                'is_pro': is_pro,
                **analysis_results  # This includes author_analysis with all the detailed info
            }
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': f'Analysis failed: {str(e)}'
            }
    
    def _extract_title_from_text(self, text: str) -> str:
        """Extract title from pasted text (first line or first sentence)"""
        lines = text.strip().split('\n')
        if lines:
            # Use first non-empty line as title
            for line in lines:
                if line.strip():
                    title = line.strip()
                    # Limit length
                    if len(title) > 200:
                        title = title[:197] + '...'
                    return title
        return 'Untitled Article'
    
    def _extract_key_claims(self, text: str) -> List[Dict[str, Any]]:
        """Extract key factual claims from article text"""
        claims = []
        sentences = re.split(r'[.!?]+', text)
        
        # Patterns for factual claims
        claim_patterns = [
            r'\b\d+\s*(?:percent|%)',  # Percentages
            r'\b(?:study|research|report|survey)\s+(?:shows|finds|found|reveals)',  # Studies
            r'\b(?:according to|data from|statistics show)',  # Data references
            r'\b(?:increased|decreased|rose|fell)\s+(?:by|to)\s+\d+',  # Changes
            r'\b\d+\s+(?:million|billion|thousand)',  # Large numbers
            r'\b(?:first|largest|smallest|fastest|slowest)\b',  # Superlatives
        ]
        
        for sentence in sentences[:20]:  # Check first 20 sentences
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
                
            # Check if sentence contains claim patterns
            for pattern in claim_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    claims.append({
                        'text': sentence,
                        'type': 'factual_claim',
                        'confidence': 0.8
                    })
                    break
            
            if len(claims) >= 10:  # Limit to 10 key claims
                break
        
        return claims
    
    def _calculate_trust_score(self, analysis_results: Dict[str, Any], article_data: Dict[str, Any]) -> int:
        """Calculate overall trust score based on all factors"""
        score_components = []
        weights = []
        
        # Source credibility (30% weight)
        source_cred = analysis_results.get('source_credibility', {})
        source_score = {
            'High': 90,
            'Medium': 60,
            'Low': 30,
            'Very Low': 10,
            'Unknown': 50
        }.get(source_cred.get('rating', 'Unknown'), 50)
        score_components.append(source_score)
        weights.append(0.30)
        
        # Author credibility (20% weight) - CHECK IF AUTHOR EXISTS
        if article_data.get('author') and analysis_results.get('author_analysis', {}).get('found'):
            author_score = analysis_results['author_analysis'].get('credibility_score', 50)
        else:
            author_score = 50  # Default if no author
        score_components.append(author_score)
        weights.append(0.20)
        
        # Bias impact (15% weight)
        bias_data = analysis_results.get('bias_analysis', {})
        objectivity = bias_data.get('objectivity_score', 0.5)
        bias_score = objectivity * 100
        score_components.append(bias_score)
        weights.append(0.15)
        
        # Transparency (15% weight)
        transparency = analysis_results.get('transparency_analysis', {})
        trans_score = transparency.get('transparency_score', 50)
        score_components.append(trans_score)
        weights.append(0.15)
        
        # Manipulation (10% weight)
        if 'persuasion_analysis' in analysis_results:
            persuasion = analysis_results['persuasion_analysis']
            manip_score = 100 - persuasion.get('persuasion_score', 50)
            score_components.append(manip_score)
            weights.append(0.10)
        else:
            # If no persuasion analysis, adjust weights
            weights = [w / 0.9 for w in weights[:4]]
        
        # Clickbait (10% weight)
        clickbait = analysis_results.get('clickbait_score', 50)
        clickbait_trust = 100 - clickbait  # Inverse relationship
        score_components.append(clickbait_trust)
        weights.append(0.10)
        
        # Calculate weighted average
        total_score = sum(score * weight for score, weight in zip(score_components, weights))
        
        # Round to integer
        return max(0, min(100, round(total_score)))
    
    def _generate_ai_summary(self, text: str) -> Optional[str]:
        """Generate AI-powered article summary"""
        if not OPENAI_AVAILABLE:
            return None
            
        try:
            # Limit text length for API
            max_chars = 4000
            if len(text) > max_chars:
                text = text[:max_chars] + '...'
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a news analyst. Provide a concise, neutral summary of the article's main points in 2-3 sentences."
                    },
                    {
                        "role": "user",
                        "content": f"Summarize this article:\n\n{text}"
                    }
                ],
                max_tokens=150,
                temperature=0.3
            )
            
            return response.choices[0].message['content'].strip()
            
        except Exception as e:
            logger.error(f"AI summary generation failed: {e}")
            return None
    
    def _generate_conversational_summary(self, article_data: Dict[str, Any], 
                                       analysis_results: Dict[str, Any]) -> Optional[str]:
        """Generate conversational analysis summary"""
        if not OPENAI_AVAILABLE:
            return None
            
        try:
            # Prepare analysis context
            context = f"""
            Article: {article_data.get('title', 'Untitled')}
            Source: {article_data.get('domain', 'Unknown')}
            Author: {article_data.get('author', 'Unknown')}
            
            Trust Score: {self._calculate_trust_score(analysis_results, article_data)}%
            Bias Level: {analysis_results.get('bias_analysis', {}).get('overall_bias', 'Unknown')}
            Clickbait Score: {analysis_results.get('clickbait_score', 0)}%
            Source Credibility: {analysis_results.get('source_credibility', {}).get('rating', 'Unknown')}
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a friendly news analyst. Provide a conversational 2-3 sentence assessment of the article's credibility and what readers should know."
                    },
                    {
                        "role": "user",
                        "content": f"Based on this analysis, what should readers know?\n\n{context}"
                    }
                ],
                max_tokens=150,
                temperature=0.5
            )
            
            return response.choices[0].message['content'].strip()
            
        except Exception as e:
            logger.error(f"Conversational summary generation failed: {e}")
            return None

    def analyze_batch(self, urls: List[str], is_pro: bool = False) -> List[Dict[str, Any]]:
        """
        Analyze multiple articles in batch
        
        Args:
            urls: List of URLs to analyze
            is_pro: Whether to use premium features
            
        Returns:
            List of analysis results
        """
        results = []
        for url in urls[:10]:  # Limit to 10 URLs per batch
            try:
                result = self.analyze(url, 'url', is_pro)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch analysis error for {url}: {e}")
                results.append({
                    'success': False,
                    'url': url,
                    'error': str(e)
                })
        
        return results
    
    def get_analysis_metadata(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key metadata from analysis results"""
        return {
            'trust_score': analysis_results.get('trust_score', 0),
            'bias_level': analysis_results.get('bias_analysis', {}).get('overall_bias', 'Unknown'),
            'political_lean': analysis_results.get('bias_analysis', {}).get('political_lean', 0),
            'clickbait_score': analysis_results.get('clickbait_score', 0),
            'source_credibility': analysis_results.get('source_credibility', {}).get('rating', 'Unknown'),
            'author_credibility': analysis_results.get('author_analysis', {}).get('credibility_score', 50),
            'transparency_score': analysis_results.get('transparency_analysis', {}).get('transparency_score', 50),
            'fact_check_count': len(analysis_results.get('fact_checks', [])),
            'manipulation_score': analysis_results.get('persuasion_analysis', {}).get('persuasion_score', 0)
        }
    
    def generate_report_summary(self, analysis_results: Dict[str, Any]) -> str:
        """Generate a comprehensive report summary"""
        metadata = self.get_analysis_metadata(analysis_results)
        article = analysis_results.get('article', {})
        
        summary = f"""
# News Analysis Report

## Article Information
- **Title**: {article.get('title', 'Unknown')}
- **Source**: {article.get('domain', 'Unknown')}
- **Author**: {article.get('author', 'Unknown')}
- **Date**: {article.get('publish_date', 'Unknown')}

## Credibility Assessment
- **Overall Trust Score**: {metadata['trust_score']}%
- **Source Credibility**: {metadata['source_credibility']}
- **Author Credibility**: {metadata['author_credibility']}/100

## Content Analysis
- **Bias Level**: {metadata['bias_level']}
- **Political Lean**: {'Left' if metadata['political_lean'] < -20 else 'Right' if metadata['political_lean'] > 20 else 'Center'}
- **Clickbait Score**: {metadata['clickbait_score']}%
- **Transparency Score**: {metadata['transparency_score']}%
- **Manipulation Score**: {metadata['manipulation_score']}%

## Key Findings
"""
        
        # Add key findings based on scores
        findings = []
        
        if metadata['trust_score'] < 40:
            findings.append("⚠️ Low trust score indicates significant credibility concerns")
        elif metadata['trust_score'] > 70:
            findings.append("✓ High trust score suggests reliable information")
            
        if metadata['clickbait_score'] > 60:
            findings.append("⚠️ High clickbait score - headline may be misleading")
            
        if abs(metadata['political_lean']) > 50:
            findings.append("⚠️ Strong political bias detected")
            
        if metadata['manipulation_score'] > 60:
            findings.append("⚠️ High manipulation tactics detected")
            
        if metadata['transparency_score'] < 40:
            findings.append("⚠️ Low transparency - sources not well documented")
            
        for finding in findings:
            summary += f"- {finding}\n"
        
        return summary
    
    def export_analysis(self, analysis_results: Dict[str, Any], format: str = 'json') -> Any:
        """
        Export analysis results in various formats
        
        Args:
            analysis_results: The analysis results
            format: Export format ('json', 'txt', 'csv')
            
        Returns:
            Formatted export data
        """
        if format == 'json':
            return analysis_results
            
        elif format == 'txt':
            return self.generate_report_summary(analysis_results)
            
        elif format == 'csv':
            # CSV format for spreadsheet analysis
            metadata = self.get_analysis_metadata(analysis_results)
            article = analysis_results.get('article', {})
            
            headers = [
                'URL', 'Title', 'Author', 'Source', 'Date',
                'Trust Score', 'Bias Level', 'Political Lean',
                'Clickbait Score', 'Source Credibility', 
                'Author Credibility', 'Transparency Score',
                'Manipulation Score', 'Fact Checks'
            ]
            
            values = [
                article.get('url', ''),
                article.get('title', ''),
                article.get('author', ''),
                article.get('domain', ''),
                article.get('publish_date', ''),
                metadata['trust_score'],
                metadata['bias_level'],
                metadata['political_lean'],
                metadata['clickbait_score'],
                metadata['source_credibility'],
                metadata['author_credibility'],
                metadata['transparency_score'],
                metadata['manipulation_score'],
                metadata['fact_check_count']
            ]
            
            return {
                'headers': headers,
                'values': values
            }
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def compare_articles(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare multiple article analyses
        
        Args:
            analyses: List of analysis results to compare
            
        Returns:
            Comparison results
        """
        if not analyses:
            return {'error': 'No analyses to compare'}
            
        comparison = {
            'article_count': len(analyses),
            'average_trust_score': 0,
            'average_bias': 0,
            'most_credible': None,
            'least_credible': None,
            'bias_distribution': {
                'left': 0,
                'center': 0,
                'right': 0
            },
            'source_credibility_distribution': {
                'High': 0,
                'Medium': 0,
                'Low': 0,
                'Very Low': 0,
                'Unknown': 0
            }
        }
        
        trust_scores = []
        bias_scores = []
        
        for analysis in analyses:
            if not analysis.get('success'):
                continue
                
            # Trust score
            trust = analysis.get('trust_score', 0)
            trust_scores.append(trust)
            
            # Track most/least credible
            if not comparison['most_credible'] or trust > comparison['most_credible']['trust_score']:
                comparison['most_credible'] = {
                    'title': analysis.get('article', {}).get('title'),
                    'trust_score': trust,
                    'url': analysis.get('article', {}).get('url')
                }
                
            if not comparison['least_credible'] or trust < comparison['least_credible']['trust_score']:
                comparison['least_credible'] = {
                    'title': analysis.get('article', {}).get('title'),
                    'trust_score': trust,
                    'url': analysis.get('article', {}).get('url')
                }
            
            # Bias analysis
            bias = analysis.get('bias_analysis', {}).get('political_lean', 0)
            bias_scores.append(bias)
            
            if bias < -20:
                comparison['bias_distribution']['left'] += 1
            elif bias > 20:
                comparison['bias_distribution']['right'] += 1
            else:
                comparison['bias_distribution']['center'] += 1
            
            # Source credibility
            source_cred = analysis.get('source_credibility', {}).get('rating', 'Unknown')
            comparison['source_credibility_distribution'][source_cred] += 1
        
        # Calculate averages
        if trust_scores:
            comparison['average_trust_score'] = round(sum(trust_scores) / len(trust_scores), 1)
            
        if bias_scores:
            comparison['average_bias'] = round(sum(bias_scores) / len(bias_scores), 1)
        
        return comparison
    
    def get_reading_time(self, text: str) -> int:
        """
        Estimate reading time in minutes
        
        Args:
            text: Article text
            
        Returns:
            Estimated reading time in minutes
        """
        # Average reading speed is 200-250 words per minute
        words = len(text.split())
        return max(1, round(words / 225))
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract named entities from text (people, organizations, locations)
        
        Args:
            text: Article text
            
        Returns:
            Dictionary of entity types and their values
        """
        entities = {
            'people': [],
            'organizations': [],
            'locations': []
        }
        
        # Simple pattern-based extraction
        # In production, you'd use NLP libraries like spaCy or NLTK
        
        # People (simple pattern for "Mr./Ms./Dr. Name" or "FirstName LastName")
        people_pattern = r'\b(?:Mr\.|Ms\.|Dr\.|Prof\.)?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\b'
        entities['people'] = list(set(re.findall(people_pattern, text)))[:10]
        
        # Organizations (words with all caps or ending in Inc., Corp., etc.)
        org_pattern = r'\b([A-Z]{2,}|[A-Za-z]+\s+(?:Inc\.|Corp\.|LLC|Ltd\.|Company|Organization|Association))\b'
        entities['organizations'] = list(set(re.findall(org_pattern, text)))[:10]
        
        # Locations (simple pattern for "City, State" or known location keywords)
        location_keywords = ['City', 'County', 'State', 'Country', 'Province', 'District']
        location_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*,\s*([A-Z][a-z]+)\b'
        entities['locations'] = list(set(re.findall(location_pattern, text)))[:10]
        
        return entities
    
    def get_article_topics(self, text: str, title: str = '') -> List[str]:
        """
        Extract main topics from article
        
        Args:
            text: Article text
            title: Article title
            
        Returns:
            List of identified topics
        """
        topics = []
        
        # Combine title and text for analysis
        full_text = f"{title} {text}".lower()
        
        # Topic categories and their keywords
        topic_keywords = {
            'Politics': ['election', 'president', 'congress', 'senate', 'vote', 'campaign', 'policy', 'government'],
            'Economy': ['economy', 'market', 'stock', 'trade', 'inflation', 'recession', 'gdp', 'unemployment'],
            'Technology': ['tech', 'ai', 'software', 'internet', 'cyber', 'data', 'digital', 'innovation'],
            'Health': ['health', 'medical', 'disease', 'vaccine', 'hospital', 'doctor', 'pandemic', 'medicine'],
            'Environment': ['climate', 'environment', 'pollution', 'carbon', 'renewable', 'conservation', 'sustainability'],
            'Business': ['business', 'company', 'ceo', 'merger', 'acquisition', 'startup', 'entrepreneur'],
            'Science': ['research', 'study', 'scientist', 'discovery', 'experiment', 'laboratory', 'findings'],
            'Sports': ['game', 'player', 'team', 'championship', 'league', 'coach', 'tournament', 'athlete'],
            'Entertainment': ['movie', 'music', 'celebrity', 'film', 'actor', 'singer', 'entertainment', 'hollywood'],
            'International': ['international', 'global', 'foreign', 'diplomatic', 'treaty', 'united nations', 'ambassador']
        }
        
        # Count keyword occurrences for each topic
        topic_scores = {}
        for topic, keywords in topic_keywords.items():
            score = sum(1 for keyword in keywords if keyword in full_text)
            if score > 0:
                topic_scores[topic] = score
        
        # Sort topics by score and return top 3
        sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
        topics = [topic for topic, score in sorted_topics[:3]]
        
        return topics
    
    def check_updates(self, original_analysis: Dict[str, Any], 
                     new_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check for significant changes between analyses
        
        Args:
            original_analysis: Previous analysis results
            new_analysis: New analysis results
            
        Returns:
            Dictionary of changes
        """
        changes = {
            'has_updates': False,
            'trust_score_change': 0,
            'bias_change': 0,
            'significant_changes': []
        }
        
        # Compare trust scores
        old_trust = original_analysis.get('trust_score', 0)
        new_trust = new_analysis.get('trust_score', 0)
        trust_change = new_trust - old_trust
        
        if abs(trust_change) > 5:
            changes['has_updates'] = True
            changes['trust_score_change'] = trust_change
            changes['significant_changes'].append(
                f"Trust score {'increased' if trust_change > 0 else 'decreased'} by {abs(trust_change)} points"
            )
        
        # Compare bias
        old_bias = original_analysis.get('bias_analysis', {}).get('political_lean', 0)
        new_bias = new_analysis.get('bias_analysis', {}).get('political_lean', 0)
        bias_change = new_bias - old_bias
        
        if abs(bias_change) > 10:
            changes['has_updates'] = True
            changes['bias_change'] = bias_change
            changes['significant_changes'].append(
                f"Political bias shifted {'right' if bias_change > 0 else 'left'} by {abs(bias_change)} points"
            )
        
        # Check for new fact checks
        old_facts = len(original_analysis.get('fact_checks', []))
        new_facts = len(new_analysis.get('fact_checks', []))
        
        if new_facts > old_facts:
            changes['has_updates'] = True
            changes['significant_changes'].append(
                f"{new_facts - old_facts} new fact checks added"
            )
        
        return changes
