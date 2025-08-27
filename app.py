"""
News Analyzer API - Complete Fixed Version
Delivers exactly 5 things: Trust Score, Article Summary, Source, Author, Findings Summary
DRY RUN TESTED AND FIXED - All issues resolved
"""
import os
import sys
import logging
import time
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List
import json

# Flask imports
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Application imports
from config import Config
from services.news_analyzer import NewsAnalyzer
from services.service_registry import get_service_registry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Enable CORS
CORS(app, origins=["*"])

# Setup rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour", "20 per minute"],
    storage_uri="memory://"
)

# Initialize services
try:
    logger.info("=" * 80)
    logger.info("INITIALIZING NEWS ANALYZER")
    news_analyzer = NewsAnalyzer()
    logger.info("NewsAnalyzer initialized successfully")
    
    # Check available services
    available = news_analyzer.get_available_services()
    logger.info(f"Available services: {available}")
    
    # Log ScraperAPI status
    scraperapi_key = os.getenv('SCRAPERAPI_KEY')
    if scraperapi_key:
        logger.info(f"ScraperAPI: ENABLED (key ends with: ...{scraperapi_key[-4:]})")
    else:
        logger.info("ScraperAPI: NOT CONFIGURED")
    
    logger.info("=" * 80)
except Exception as e:
    logger.error(f"CRITICAL: Failed to initialize NewsAnalyzer: {str(e)}", exc_info=True)
    news_analyzer = None

def calculate_trust_score(pipeline_results: Dict[str, Any]) -> int:
    """
    Calculate a single trust score from all services
    Returns a number from 0-100
    """
    scores = []
    weights = {
        'source_credibility': 2.0,
        'author_analyzer': 1.5,
        'fact_checker': 2.0,
        'bias_detector': 1.5,  # Inverted - less bias = higher trust
        'transparency_analyzer': 1.0,
        'manipulation_detector': 1.5,  # Inverted - less manipulation = higher trust
        'content_analyzer': 1.0,
        'openai_enhancer': 0.5  # Lower weight for AI enhancement
    }
    
    try:
        # Check data.detailed_analysis first (from NewsAnalyzer)
        if 'data' in pipeline_results and 'detailed_analysis' in pipeline_results['data']:
            detailed = pipeline_results['data']['detailed_analysis']
            
            for service_name, service_data in detailed.items():
                if service_name in weights and isinstance(service_data, dict):
                    score = extract_score_from_service(service_data)
                    
                    if score is not None:
                        # Invert scores for bias and manipulation (lower = better)
                        if service_name in ['bias_detector', 'manipulation_detector']:
                            score = 100 - score
                        
                        scores.append((score, weights[service_name]))
        
        # Also check direct service results (from pipeline)
        for service_name in weights:
            if service_name in pipeline_results and isinstance(pipeline_results[service_name], dict):
                service_data = pipeline_results[service_name]
                if service_data.get('success'):
                    score = extract_score_from_service(service_data)
                    if score is not None:
                        if service_name in ['bias_detector', 'manipulation_detector']:
                            score = 100 - score
                        scores.append((score, weights[service_name]))
        
        if scores:
            weighted_sum = sum(score * weight for score, weight in scores)
            total_weight = sum(weight for _, weight in scores)
            return max(0, min(100, int(weighted_sum / total_weight)))
        
        # Check if trust_score was already calculated by pipeline
        if 'trust_score' in pipeline_results:
            return int(pipeline_results['trust_score'])
        
        return 50  # Default middle score if no services available
        
    except Exception as e:
        logger.error(f"Trust score calculation error: {e}")
        return 0

def extract_article_summary(pipeline_results: Dict[str, Any]) -> str:
    """
    Extract article summary from pipeline results
    """
    try:
        # Try OpenAI enhancer first (best quality)
        if 'openai_enhancer' in pipeline_results and pipeline_results['openai_enhancer'].get('success'):
            ai_summary = pipeline_results['openai_enhancer'].get('ai_summary', '')
            if ai_summary and len(ai_summary) > 50:
                return ai_summary
        
        # Try from data.detailed_analysis
        if ('data' in pipeline_results and 
            'detailed_analysis' in pipeline_results['data'] and
            'openai_enhancer' in pipeline_results['data']['detailed_analysis']):
            
            openai_data = pipeline_results['data']['detailed_analysis']['openai_enhancer']
            if isinstance(openai_data, dict):
                ai_summary = openai_data.get('ai_summary', openai_data.get('summary', ''))
                if ai_summary and len(ai_summary) > 50:
                    return ai_summary
        
        # Try article summary
        if 'article' in pipeline_results and isinstance(pipeline_results['article'], dict):
            article_text = pipeline_results['article'].get('text', '')
            if article_text and len(article_text) > 200:
                # Create summary from first part of article
                sentences = article_text.split('. ')
                if len(sentences) > 2:
                    return '. '.join(sentences[:3]) + '.'
                elif len(article_text) > 100:
                    return article_text[:200] + '...'
        
        # Try from data.article
        if 'data' in pipeline_results and 'article' in pipeline_results['data']:
            article = pipeline_results['data']['article']
            if isinstance(article, dict):
                text = article.get('text', '')
                if text and len(text) > 200:
                    sentences = text.split('. ')
                    if len(sentences) > 2:
                        return '. '.join(sentences[:3]) + '.'
        
        # Try summary field
        if 'summary' in pipeline_results:
            return pipeline_results['summary']
        
        return "Article summary not available"
        
    except Exception as e:
        logger.error(f"Summary extraction error: {e}")
        return "Error extracting summary"

def extract_article_info(pipeline_results: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract article basic info (source, author) from pipeline results
    """
    article_info = {
        'source': 'Unknown',
        'author': 'Unknown',
        'title': '',
        'url': '',
        'domain': ''
    }
    
    try:
        # Try article field first (from pipeline)
        if 'article' in pipeline_results and isinstance(pipeline_results['article'], dict):
            article = pipeline_results['article']
            article_info.update({
                'source': article.get('domain', article.get('source', 'Unknown')),
                'author': article.get('author', 'Unknown'),
                'title': article.get('title', ''),
                'url': article.get('url', ''),
                'domain': article.get('domain', '')
            })
        
        # Try article_extractor results
        if 'article_extractor' in pipeline_results and isinstance(pipeline_results['article_extractor'], dict):
            extractor = pipeline_results['article_extractor']
            if extractor.get('success'):
                article_info.update({
                    'source': extractor.get('domain', article_info['source']),
                    'author': extractor.get('author', article_info['author']),
                    'title': extractor.get('title', article_info['title']),
                    'url': extractor.get('url', article_info['url']),
                    'domain': extractor.get('domain', article_info['domain'])
                })
        
        # Try data.article_info (from NewsAnalyzer)
        if ('data' in pipeline_results and 
            'article_info' in pipeline_results['data']):
            
            info = pipeline_results['data']['article_info']
            if article_info['source'] == 'Unknown':
                article_info['source'] = info.get('source', info.get('domain', 'Unknown'))
            if article_info['author'] == 'Unknown':
                article_info['author'] = info.get('author', 'Unknown')
            if not article_info['title']:
                article_info['title'] = info.get('title', '')
            if not article_info['url']:
                article_info['url'] = info.get('url', '')
            if not article_info['domain']:
                article_info['domain'] = info.get('domain', '')
        
        # Try data.article (from NewsAnalyzer)
        if ('data' in pipeline_results and 
            'article' in pipeline_results['data'] and
            isinstance(pipeline_results['data']['article'], dict)):
            
            article = pipeline_results['data']['article']
            if article_info['source'] == 'Unknown':
                article_info['source'] = article.get('domain', article.get('source', 'Unknown'))
            if article_info['author'] == 'Unknown':
                article_info['author'] = article.get('author', 'Unknown')
    
    except Exception as e:
        logger.error(f"Error extracting article info: {e}")
    
    # Clean up author if it's a list
    if isinstance(article_info['author'], list):
        article_info['author'] = ', '.join(article_info['author']) if article_info['author'] else 'Unknown'
    
    # Clean "By" prefix from author
    if isinstance(article_info['author'], str) and article_info['author'].lower().startswith('by '):
        article_info['author'] = article_info['author'][3:].strip()
    
    # Extract domain from URL if not set
    if article_info['url'] and not article_info['domain']:
        from urllib.parse import urlparse
        parsed = urlparse(article_info['url'])
        article_info['domain'] = parsed.netloc
    
    # Use domain as source if source is unknown
    if article_info['source'] == 'Unknown' and article_info['domain']:
        article_info['source'] = article_info['domain']
    
    return article_info

def extract_author_details(pipeline_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract comprehensive author details from pipeline results
    """
    author_details = {
        'author': 'Unknown',
        'author_bio': '',
        'author_position': '',
        'author_credibility': 0,
        'author_score': 0,
        'author_photo': None,
        'author_articles': 0,
        'author_expertise': [],
        'author_awards': [],
        'author_linkedin': None,
        'author_twitter': None,
        'author_link': None,
        'author_recent_articles': []
    }
    
    try:
        # First check direct author_analyzer results (from pipeline)
        if 'author_analyzer' in pipeline_results and isinstance(pipeline_results['author_analyzer'], dict):
            author_data = pipeline_results['author_analyzer']
            
            if author_data.get('success'):
                # Extract all available author data
                author_details['author'] = author_data.get('author_name') or author_data.get('author') or 'Unknown'
                author_details['author_bio'] = author_data.get('bio', '')
                author_details['author_position'] = author_data.get('position', '')
                author_details['author_credibility'] = author_data.get('credibility_score', author_data.get('score', 0))
                author_details['author_score'] = author_data.get('score', author_data.get('credibility_score', 0))
                author_details['author_photo'] = author_data.get('author_photo')
                author_details['author_articles'] = author_data.get('article_count', 0)
                author_details['author_expertise'] = author_data.get('expertise_areas', [])
                author_details['author_awards'] = author_data.get('awards', [])
                author_details['author_linkedin'] = author_data.get('linkedin_profile')
                author_details['author_twitter'] = author_data.get('twitter_profile')
                author_details['author_link'] = author_data.get('author_link')
                author_details['author_recent_articles'] = author_data.get('recent_articles', [])
        
        # Check in data.detailed_analysis.author_analyzer
        elif ('data' in pipeline_results and 
            'detailed_analysis' in pipeline_results['data'] and
            'author_analyzer' in pipeline_results['data']['detailed_analysis']):
            
            author_data = pipeline_results['data']['detailed_analysis']['author_analyzer']
            
            author_details['author'] = author_data.get('author_name', 'Unknown')
            author_details['author_bio'] = author_data.get('bio', '')
            author_details['author_position'] = author_data.get('position', '')
            author_details['author_credibility'] = author_data.get('credibility_score', 0)
            author_details['author_score'] = author_data.get('score', 0)
            author_details['author_photo'] = author_data.get('author_photo')
            author_details['author_articles'] = author_data.get('article_count', 0)
            author_details['author_expertise'] = author_data.get('expertise_areas', [])
            author_details['author_awards'] = author_data.get('awards', [])
            author_details['author_linkedin'] = author_data.get('linkedin_profile')
            author_details['author_twitter'] = author_data.get('twitter_profile')
            author_details['author_link'] = author_data.get('author_link')
            author_details['author_recent_articles'] = author_data.get('recent_articles', [])
        
        # If author name is still unknown, try to extract from article_extractor
        if author_details['author'] == 'Unknown' or author_details['author'] is None:
            # Check article_extractor
            if 'article_extractor' in pipeline_results and isinstance(pipeline_results['article_extractor'], dict):
                extracted_author = pipeline_results['article_extractor'].get('author')
                if extracted_author and extracted_author != 'Unknown':
                    author_details['author'] = extracted_author
            
            # Check article field
            if author_details['author'] == 'Unknown' and 'article' in pipeline_results:
                article = pipeline_results['article']
                if isinstance(article, dict):
                    extracted_author = article.get('author')
                    if extracted_author and extracted_author != 'Unknown':
                        author_details['author'] = extracted_author
            
            # Check in data structures
            if author_details['author'] == 'Unknown' and 'data' in pipeline_results:
                if 'article' in pipeline_results['data']:
                    extracted_author = pipeline_results['data']['article'].get('author')
                    if extracted_author and extracted_author != 'Unknown':
                        author_details['author'] = extracted_author
        
        # Clean up None values to empty strings/defaults
        if author_details['author'] is None:
            author_details['author'] = 'Unknown'
        
        logger.info(f"Extracted author details: name={author_details['author']}, "
                   f"credibility={author_details['author_credibility']}, "
                   f"bio_length={len(author_details.get('author_bio', ''))}")
    
    except Exception as e:
        logger.error(f"Error extracting author details: {e}")
    
    return author_details

def generate_findings_summary(pipeline_results: Dict[str, Any], trust_score: int) -> str:
    """
    Generate a conversational summary of what the analysis found
    """
    findings = []
    
    # Get all service results
    services = {}
    
    # Collect services from pipeline results
    for key in ['source_credibility', 'author_analyzer', 'bias_detector', 
                'fact_checker', 'transparency_analyzer', 'manipulation_detector']:
        if key in pipeline_results and isinstance(pipeline_results[key], dict):
            if pipeline_results[key].get('success'):
                services[key] = pipeline_results[key]
    
    # Also check in data.detailed_analysis
    if 'data' in pipeline_results and 'detailed_analysis' in pipeline_results['data']:
        for key, value in pipeline_results['data']['detailed_analysis'].items():
            if key not in services and isinstance(value, dict) and value.get('success'):
                services[key] = value
    
    # Process each service for findings
    for service_name, service_data in services.items():
        try:
            if service_name == 'source_credibility':
                score = extract_score_from_service(service_data)
                if score is not None:
                    if score >= 80:
                        findings.append("Source has high credibility")
                    elif score >= 60:
                        findings.append("Source has moderate credibility")
                    else:
                        findings.append("Source has questionable credibility")
            
            elif service_name == 'bias_detector':
                bias_score = service_data.get('bias_score', 0)
                if bias_score < 30:
                    findings.append("Minimal bias detected")
                elif bias_score < 60:
                    findings.append("Moderate bias detected")
                else:
                    findings.append("High bias detected")
            
            elif service_name == 'fact_checker':
                verified = service_data.get('verified_claims', 0)
                disputed = service_data.get('disputed_claims', 0)
                if verified > 0 or disputed > 0:
                    findings.append(f"Fact-checked {verified + disputed} claims")
            
            elif service_name == 'author_analyzer':
                author_score = service_data.get('author_score', service_data.get('score', 0))
                if author_score >= 70:
                    findings.append("Author has strong credentials")
                elif author_score >= 40:
                    findings.append("Author has moderate credentials")
                else:
                    findings.append("Limited author information available")
            
            elif service_name == 'manipulation_detector':
                manip_score = service_data.get('manipulation_score', 0)
                if manip_score < 30:
                    findings.append("No significant manipulation detected")
                elif manip_score < 60:
                    findings.append("Some manipulation tactics detected")
                else:
                    findings.append("Significant manipulation detected")
        
        except Exception as e:
            logger.error(f"Error processing {service_name} for findings: {e}")
            continue
    
    # Generate overall assessment based on trust score
    if trust_score >= 80:
        overall = "This article is highly trustworthy."
    elif trust_score >= 60:
        overall = "This article is generally trustworthy."
    elif trust_score >= 40:
        overall = "This article has moderate trustworthiness."
    else:
        overall = "This article has low trustworthiness."
    
    # Combine findings
    if findings:
        return f"{overall} {'. '.join(findings)}."
    else:
        return overall

def extract_score_from_service(service_data: Any) -> Optional[float]:
    """
    Extract score from service data regardless of structure
    """
    if not isinstance(service_data, dict):
        return None
    
    # Direct score fields
    score_fields = ['score', 'credibility_score', 'bias_score', 'transparency_score', 
                   'author_score', 'manipulation_score', 'overall_score', 'content_score',
                   'quality_score', 'trust_score']
    
    for field in score_fields:
        if field in service_data:
            try:
                return float(service_data[field])
            except (ValueError, TypeError):
                continue
    
    # Check in data wrapper
    if 'data' in service_data and isinstance(service_data['data'], dict):
        for field in score_fields:
            if field in service_data['data']:
                try:
                    return float(service_data['data'][field])
                except (ValueError, TypeError):
                    continue
    
    return None

# MAIN ROUTES

@app.route('/')
def index():
    """Serve the main application page"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': 'ready' if news_analyzer else 'initializing'
    })

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """
    Main analysis endpoint - Returns exactly 5 things:
    1. Trust Score
    2. Article Summary
    3. Source
    4. Author
    5. Findings Summary
    Plus comprehensive author details for the author card
    """
    if not news_analyzer:
        logger.error("NewsAnalyzer not initialized")
        return jsonify({
            'success': False,
            'error': 'Analysis service not available',
            'trust_score': 0,
            'article_summary': 'Service initialization failed',
            'source': 'Unknown',
            'author': 'Unknown',
            'findings_summary': 'Service initialization failed'
        }), 503
    
    try:
        # Get and validate input
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        url = data.get('url', '').strip()
        text = data.get('text', '').strip()
        
        if not url and not text:
            return jsonify({'error': 'Please provide either a URL or article text'}), 400
        
        content = url if url else text
        content_type = 'url' if url else 'text'
        
        logger.info(f"Analyzing {content_type}: {content[:100]}...")
        
        # Run analysis with pro mode enabled
        start_time = time.time()
        pipeline_results = news_analyzer.analyze(content, content_type, pro_mode=True)
        analysis_time = time.time() - start_time
        
        logger.info(f"Analysis completed in {analysis_time:.2f} seconds")
        
        # Extract the 5 required pieces of information
        trust_score = calculate_trust_score(pipeline_results)
        article_summary = extract_article_summary(pipeline_results)
        article_info = extract_article_info(pipeline_results)
        findings_summary = generate_findings_summary(pipeline_results, trust_score)
        
        # Extract comprehensive author details
        author_details = extract_author_details(pipeline_results)
        
        # Create simplified response that frontend expects
        response_data = {
            'success': True,
            'trust_score': trust_score,
            'article_summary': article_summary,
            'source': article_info['source'],
            'author': author_details['author'],  # Use author from detailed extraction
            'findings_summary': findings_summary,
            'analysis_time': analysis_time,
            'timestamp': datetime.now().isoformat(),
            # Add all author details for the author card
            **author_details  # This spreads all author fields into the response
        }
        
        logger.info(f"Sending response with trust_score: {trust_score}, source: {article_info['source']}, author: {author_details['author']}")
        logger.info(f"Author details: bio={bool(author_details.get('author_bio'))}, "
                   f"linkedin={bool(author_details.get('author_linkedin'))}, "
                   f"articles={author_details.get('author_articles', 0)}")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Analysis failed: {str(e)}',
            'trust_score': 0,
            'article_summary': 'Error analyzing article',
            'source': 'Unknown',
            'author': 'Unknown',
            'findings_summary': f'Analysis could not be completed: {str(e)}'
        }), 200  # Return 200 so frontend can handle it

@app.route('/api/test', methods=['GET', 'POST'])
def test_endpoint():
    """Test endpoint that returns simple data without analysis"""
    logger.info("TEST ENDPOINT HIT")
    
    # Check if NewsAnalyzer exists
    analyzer_status = "initialized" if news_analyzer else "failed"
    
    # Try to get service status
    try:
        registry = get_service_registry()
        service_status = registry.get_service_status()
        services = list(service_status.get('services', {}).keys())
    except Exception as e:
        services = f"Error: {str(e)}"
    
    # Check ScraperAPI status
    scraperapi_status = "enabled" if os.getenv('SCRAPERAPI_KEY') else "not configured"
    
    return jsonify({
        'success': True,
        'message': 'Test endpoint working',
        'news_analyzer': analyzer_status,
        'services': services,
        'scraperapi': scraperapi_status,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/status')
def api_status():
    """Simple status check"""
    scraperapi_available = bool(os.getenv('SCRAPERAPI_KEY'))
    
    return jsonify({
        'status': 'online', 
        'services': 'ready',
        'scraperapi': 'enabled' if scraperapi_available else 'not configured',
        'timestamp': datetime.now().isoformat()
    })

# Debug Routes (helpful for development)
@app.route('/api/debug/services')
def debug_services():
    """Debug endpoint to check service status"""
    if not news_analyzer:
        return jsonify({'error': 'NewsAnalyzer not initialized'}), 500
    
    try:
        registry = get_service_registry()
        status = registry.get_service_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/config')
def debug_config():
    """Debug endpoint to check configuration (without exposing secrets)"""
    config_info = {
        'openai_configured': bool(Config.OPENAI_API_KEY),
        'scraperapi_configured': bool(Config.SCRAPERAPI_KEY),
        'scrapingbee_configured': bool(Config.SCRAPINGBEE_API_KEY),
        'google_factcheck_configured': bool(Config.GOOGLE_FACT_CHECK_API_KEY or Config.GOOGLE_FACTCHECK_API_KEY),
        'news_api_configured': bool(Config.NEWS_API_KEY or Config.NEWSAPI_KEY),
        'environment': Config.ENV,
        'debug': Config.DEBUG
    }
    
    return jsonify(config_info)

@app.route('/templates/<path:filename>')
def serve_template(filename):
    """Serve template files"""
    try:
        if '..' in filename or filename.startswith('/'):
            return "Invalid path", 400
        return send_from_directory('templates', filename)
    except Exception as e:
        return f"Error: {str(e)}", 500

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded', 'message': str(e.description)}), 429

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
