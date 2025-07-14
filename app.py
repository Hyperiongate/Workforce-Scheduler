<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced News Analyzer - Facts & Fakes AI</title>
    <meta name="description" content="AI-powered news verification with bias detection, fact-checking, and credibility analysis. Detect fake news instantly with our advanced algorithms.">
    
    <!-- Bootstrap CSS from cdnjs (CSP approved) -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css" rel="stylesheet">
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <style>
        /* Professional Color Scheme */
        :root {
            --primary-blue: #4a90e2;
            --primary-blue-dark: #357abd;
            --primary-gradient: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
            --success-color: #27ae60;
            --warning-color: #f39c12;
            --danger-color: #e74c3c;
            --text-primary: #2c3e50;
            --text-secondary: #7f8c8d;
            --border-color: #ecf0f1;
            --bg-light: #f8f9fa;
            --shadow-light: 0 4px 20px rgba(0, 0, 0, 0.1);
            --shadow-medium: 0 8px 30px rgba(74, 144, 226, 0.2);
        }

        /* Enhanced Trust Meter - Larger and More Prominent */
        .trust-meter-container {
            position: relative;
            width: 250px;
            height: 250px;
            margin: 30px auto;
            background: linear-gradient(135deg, #f0f4ff 0%, #e0e7ff 100%);
            border-radius: 50%;
            box-shadow: 0 10px 40px rgba(74, 144, 226, 0.3);
            padding: 20px;
            animation: float 6s ease-in-out infinite;
        }
        
        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-20px); }
        }
        
        .trust-meter {
            position: relative;
            width: 100%;
            height: 100%;
        }
        
        .trust-meter-circle {
            width: 100%;
            height: 100%;
            transform: rotate(-90deg);
        }
        
        .trust-meter-bg {
            fill: none;
            stroke: #e5e7eb;
            stroke-width: 20;
        }
        
        .trust-meter-fill {
            fill: none;
            stroke-width: 20;
            stroke-linecap: round;
            transition: all 1.5s cubic-bezier(0.4, 0, 0.2, 1);
            filter: drop-shadow(0 0 10px currentColor);
        }
        
        .trust-meter-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }
        
        .trust-score {
            font-size: 48px;
            font-weight: 700;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: block;
        }
        
        .trust-label {
            font-size: 14px;
            color: #6b7280;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        /* Sticky Upgrade Button */
        .sticky-upgrade {
            position: fixed;
            bottom: 30px;
            right: 30px;
            z-index: 1000;
            animation: pulse 2s infinite;
        }
        
        .sticky-upgrade button {
            background: var(--primary-gradient);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 50px;
            font-weight: 600;
            font-size: 16px;
            cursor: pointer;
            box-shadow: 0 10px 30px rgba(74, 144, 226, 0.4);
            transition: all 0.3s ease;
        }
        
        .sticky-upgrade button:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 40px rgba(74, 144, 226, 0.5);
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }

        /* Tooltips */
        .tooltip-container {
            position: relative;
            display: inline-block;
            cursor: help;
        }
        
        .tooltip-icon {
            width: 16px;
            height: 16px;
            background: #e5e7eb;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            color: #6b7280;
            margin-left: 5px;
            transition: all 0.2s ease;
        }
        
        .tooltip-icon:hover {
            background: var(--primary-blue);
            color: white;
        }
        
        .tooltip-content {
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: #1f2937;
            color: white;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 14px;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
            margin-bottom: 10px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            max-width: 300px;
            white-space: normal;
            z-index: 1000;
        }
        
        .tooltip-container:hover .tooltip-content {
            opacity: 1;
        }
        
        .tooltip-content::after {
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: #1f2937;
        }

        /* Analysis Timestamp and Version */
        .analysis-meta {
            background: var(--bg-light);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }
        
        .meta-item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .meta-item i {
            color: var(--primary-blue);
        }

        /* Confidence Intervals */
        .confidence-bar {
            position: relative;
            height: 30px;
            background: var(--bg-light);
            border-radius: 15px;
            overflow: hidden;
            margin: 10px 0;
        }
        
        .confidence-fill {
            height: 100%;
            background: linear-gradient(90deg, #ef4444 0%, #f59e0b 50%, #10b981 100%);
            transition: width 1s ease;
            position: relative;
        }
        
        .confidence-marker {
            position: absolute;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 4px;
            height: 20px;
            background: #1f2937;
            border-radius: 2px;
        }
        
        .confidence-label {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: white;
            font-weight: 600;
            font-size: 14px;
            text-shadow: 0 1px 2px rgba(0,0,0,0.3);
        }

        /* Pro Features Preview (Grayed Out) */
        .pro-feature-locked {
            position: relative;
            opacity: 0.6;
            filter: grayscale(100%);
            pointer-events: none;
        }
        
        .pro-feature-locked::after {
            content: 'PRO FEATURE';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(-15deg);
            background: var(--primary-blue);
            color: white;
            padding: 5px 20px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 12px;
            box-shadow: 0 4px 10px rgba(74, 144, 226, 0.3);
        }

        /* Why This Matters Sections */
        .why-matters-box {
            background: #fef3c7;
            border: 1px solid #fcd34d;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }
        
        .why-matters-box h4 {
            color: #92400e;
            margin: 0 0 8px 0;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .why-matters-box p {
            color: #78350f;
            margin: 0;
            font-size: 14px;
            line-height: 1.6;
        }

        /* Methodology Snippets */
        .methodology-snippet {
            background: #ede9fe;
            border: 1px solid #c7d2fe;
            border-radius: 8px;
            padding: 12px;
            margin: 10px 0;
            font-size: 13px;
            color: #5b21b6;
        }
        
        .methodology-snippet code {
            background: #ddd6fe;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
        }

        /* Learn More Links */
        .learn-more-link {
            color: var(--primary-blue);
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            transition: all 0.2s ease;
        }
        
        .learn-more-link:hover {
            color: var(--primary-blue-dark);
            gap: 8px;
        }

        /* Floating particles background */
        @keyframes float-particle {
            0%, 100% { transform: translate(0, 0) rotate(0deg); opacity: 0; }
            10% { opacity: 1; }
            90% { opacity: 1; }
            100% { transform: translate(100px, -100vh) rotate(720deg); opacity: 0; }
        }
        
        .particle {
            position: fixed;
            pointer-events: none;
            opacity: 0;
            animation: float-particle 10s infinite;
        }
        
        .particle:nth-child(odd) { animation-duration: 15s; }
        .particle:nth-child(even) { animation-duration: 20s; animation-delay: 5s; }

        /* Animated dropdowns with colorful borders */
        .analysis-dropdown {
            margin-bottom: 15px;
            border-radius: 12px;
            overflow: hidden;
            transition: all 0.3s ease;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        }
        
        .analysis-dropdown:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.12);
        }
        
        .dropdown-header {
            padding: 20px;
            cursor: pointer;
            background: white;
            border: 2px solid transparent;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .dropdown-header::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(74, 144, 226, 0.1), transparent);
            transition: left 0.5s ease;
        }
        
        .dropdown-header:hover::before {
            left: 100%;
        }
        
        .dropdown-header h3 {
            margin: 0;
            font-size: 20px;
            display: flex;
            align-items: center;
            color: var(--text-primary);
        }
        
        .dropdown-header i {
            font-size: 24px;
            margin-right: 15px;
        }
        
        .dropdown-content {
            padding: 0;
            max-height: 0;
            overflow: hidden;
            transition: all 0.3s ease;
            background: var(--bg-light);
        }
        
        .dropdown-content.show {
            max-height: 2000px;
            padding: 20px;
        }
        
        /* Colorful borders for different sections */
        .border-trust { border-left: 4px solid #10b981 !important; }
        .border-bias { border-left: 4px solid #f59e0b !important; }
        .border-fact { border-left: 4px solid #3b82f6 !important; }
        .border-author { border-left: 4px solid #8b5cf6 !important; }
        .border-quality { border-left: 4px solid #ec4899 !important; }
        .border-agenda { border-left: 4px solid #ef4444 !important; }
        .border-clickbait { border-left: 4px solid #f97316 !important; }
        .border-emotion { border-left: 4px solid #06b6d4 !important; }
        .border-diversity { border-left: 4px solid #84cc16 !important; }
        .border-time { border-left: 4px solid var(--primary-blue) !important; }
        .border-ai { border-left: 4px solid #14b8a6 !important; }

        /* Gauge styles */
        .gauge-container {
            width: 200px;
            height: 100px;
            position: relative;
            margin: 20px auto;
        }
        
        .gauge {
            width: 100%;
            height: 200px;
            border-radius: 100px 100px 0 0;
            background: linear-gradient(to right, #10b981 0%, #f59e0b 50%, #ef4444 100%);
            position: relative;
            overflow: hidden;
        }
        
        .gauge-mask {
            width: 160px;
            height: 160px;
            background: white;
            border-radius: 80px 80px 0 0;
            position: absolute;
            bottom: 0;
            left: 50%;
            transform: translateX(-50%);
        }
        
        .gauge-needle {
            width: 4px;
            height: 90px;
            background: #1f2937;
            position: absolute;
            bottom: 0;
            left: 50%;
            transform-origin: bottom center;
            transform: translateX(-50%) rotate(-90deg);
            transition: transform 1s ease-out;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
        }
        
        /* Gauge labels */
        .gauge-labels {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            padding: 0 10px;
        }

        /* Progress bar for loading */
        .progress-container {
            background: #e5e7eb;
            border-radius: 10px;
            padding: 4px;
            margin: 20px 0;
        }
        
        .progress-bar {
            height: 30px;
            background: var(--primary-gradient);
            border-radius: 8px;
            width: 0%;
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
            font-size: 14px;
        }

        /* Claim cards */
        .claim-card {
            background: white;
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            border: 2px solid #e5e7eb;
            transition: all 0.3s ease;
        }
        
        .claim-card:hover {
            transform: translateX(5px);
            border-color: var(--primary-blue);
            box-shadow: 0 5px 15px rgba(74, 144, 226, 0.2);
        }
        
        .claim-status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            margin-top: 10px;
        }
        
        .status-verified {
            background: #d1fae5;
            color: #065f46;
        }
        
        .status-false {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .status-unverified {
            background: #fed7aa;
            color: #92400e;
        }

        /* Glowing effect for important elements */
        @keyframes glow {
            0% { box-shadow: 0 0 5px rgba(74, 144, 226, 0.5); }
            50% { box-shadow: 0 0 20px rgba(74, 144, 226, 0.8), 0 0 30px rgba(74, 144, 226, 0.6); }
            100% { box-shadow: 0 0 5px rgba(74, 144, 226, 0.5); }
        }
        
        .glow-effect {
            animation: glow 2s ease-in-out infinite;
        }

        /* PDF button */
        .pdf-button {
            background: var(--primary-gradient);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        .pdf-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(74, 144, 226, 0.4);
        }

        /* Source comparison grid */
        .source-comparison {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .source-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            transition: all 0.3s ease;
        }
        
        .source-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        
        .source-logo {
            width: 50px;
            height: 50px;
            margin: 0 auto 10px;
            background: var(--bg-light);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            color: var(--text-secondary);
        }
        
        .source-score {
            font-size: 24px;
            font-weight: 700;
            margin: 5px 0;
        }

        /* Historical accuracy chart */
        .accuracy-chart {
            height: 200px;
            background: var(--bg-light);
            border-radius: 8px;
            padding: 20px;
            position: relative;
            margin: 20px 0;
        }
        
        .chart-grid {
            position: absolute;
            top: 20px;
            left: 20px;
            right: 20px;
            bottom: 40px;
            border-left: 2px solid #e5e7eb;
            border-bottom: 2px solid #e5e7eb;
        }
        
        .chart-line {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: var(--primary-blue);
        }

        /* Enhanced loading animation stages */
        .analysis-stage {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 15px;
            background: white;
            border-radius: 8px;
            margin: 10px 0;
            opacity: 0.5;
            transition: all 0.3s ease;
        }
        
        .analysis-stage.active {
            opacity: 1;
            background: #eef2ff;
            transform: scale(1.02);
            box-shadow: 0 5px 15px rgba(74, 144, 226, 0.2);
        }
        
        .analysis-stage.complete {
            opacity: 1;
        }
        
        .stage-icon {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: #e5e7eb;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }
        
        .analysis-stage.active .stage-icon {
            background: var(--primary-blue);
            color: white;
            animation: rotate 1s linear infinite;
        }
        
        .analysis-stage.complete .stage-icon {
            background: #10b981;
            color: white;
        }
        
        @keyframes rotate {
            to { transform: rotate(360deg); }
        }

        /* Pricing dropdown */
        .pricing-info {
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border: 2px solid #fbbf24;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }
        
        .pricing-tier {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 10px 0;
            padding: 10px;
            background: white;
            border-radius: 8px;
        }
        
        .pricing-tier h4 {
            margin: 0;
            color: #92400e;
        }
        
        .pricing-tier .price {
            font-size: 24px;
            font-weight: 700;
            color: #dc2626;
        }

        /* Mobile responsive */
        @media (max-width: 768px) {
            .trust-meter-container {
                width: 200px;
                height: 200px;
            }
            
            .trust-score {
                font-size: 36px;
            }
            
            .analysis-dropdown {
                margin-bottom: 10px;
            }
            
            .dropdown-header {
                padding: 15px;
            }
            
            .dropdown-header h3 {
                font-size: 18px;
            }
            
            .source-comparison {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .sticky-upgrade {
                bottom: 20px;
                right: 20px;
            }
            
            .sticky-upgrade button {
                padding: 12px 20px;
                font-size: 14px;
            }
        }

        /* Input section styling */
        .input-section {
            background: linear-gradient(135deg, var(--bg-light) 0%, #e5e7eb 100%);
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: var(--shadow-light);
        }
        
        .input-tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .input-tab {
            flex: 1;
            padding: 12px;
            background: white;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            cursor: pointer;
            text-align: center;
            transition: all 0.3s ease;
            font-weight: 600;
        }
        
        .input-tab.active {
            background: var(--primary-gradient);
            color: white;
            border-color: transparent;
        }
        
        .input-tab:hover:not(.active) {
            background: var(--bg-light);
            border-color: var(--primary-blue);
        }
        
        #news-url, #news-text {
            width: 100%;
            padding: 15px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s ease;
        }
        
        #news-url:focus, #news-text:focus {
            outline: none;
            border-color: var(--primary-blue);
            box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
        }
        
        #news-text {
            min-height: 150px;
            resize: vertical;
        }
        
        .analyze-button {
            width: 100%;
            padding: 15px;
            background: var(--primary-gradient);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 20px;
        }
        
        .analyze-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(74, 144, 226, 0.3);
        }
        
        .analyze-button:active {
            transform: translateY(0);
        }

        /* News container styling */
        .news-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header styling */
        .news-header {
            text-align: center;
            margin-bottom: 40px;
            padding: 40px 20px;
            background: white;
            border-radius: 15px;
            box-shadow: var(--shadow-light);
            position: relative;
            overflow: hidden;
        }

        .news-header::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 5px;
            background: var(--primary-gradient);
        }

        .news-header h1 {
            font-size: 2.5em;
            margin-bottom: 15px;
            font-weight: 700;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .news-header p {
            font-size: 1.2em;
            color: var(--text-secondary);
            max-width: 600px;
            margin: 0 auto;
            line-height: 1.6;
        }

        /* Loading overlay styles */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.95);
            z-index: 9999;
            backdrop-filter: blur(10px);
            justify-content: center;
            align-items: center;
        }

        .loading-content {
            text-align: center;
            max-width: 500px;
            width: 90%;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
        }

        .loading-spinner {
            width: 80px;
            height: 80px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid var(--primary-blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 30px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .loading-text {
            font-size: 1.3em;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--text-primary);
        }

        .loading-subtext {
            color: var(--text-secondary);
            margin-bottom: 20px;
        }

        /* Results section styling */
        .results-section {
            display: none;
            margin-top: 40px;
        }

        .results-header {
            background: var(--primary-gradient);
            color: white;
            padding: 30px;
            border-radius: 15px 15px 0 0;
            text-align: center;
        }

        .results-header h2 {
            font-size: 2em;
            margin-bottom: 10px;
        }

        .results-content {
            background: white;
            border-radius: 0 0 15px 15px;
            box-shadow: var(--shadow-light);
            overflow: hidden;
        }

        /* Enhanced error container styling */
        .error-container {
            display: none;
            background: #fef2f2;
            border: 2px solid #fed7d7;
            border-radius: 12px;
            padding: 30px;
            margin: 20px 0;
            text-align: center;
            box-shadow: 0 5px 15px rgba(231, 76, 60, 0.1);
        }

        .error-container i {
            font-size: 3em;
            color: var(--danger-color);
            margin-bottom: 20px;
        }

        .error-container h3 {
            color: var(--danger-color);
            margin-bottom: 15px;
            font-size: 1.5em;
        }

        .error-container p {
            color: #742a2a;
            margin-bottom: 20px;
            line-height: 1.6;
        }

        .error-suggestions {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: left;
        }

        .error-suggestions h4 {
            color: #742a2a;
            margin-bottom: 15px;
            font-size: 1.2em;
        }

        .error-suggestions ul {
            list-style: none;
            padding: 0;
        }

        .error-suggestions li {
            padding: 10px 0 10px 35px;
            position: relative;
            color: #5a2121;
            line-height: 1.5;
        }

        .error-suggestions li:before {
            content: "→";
            position: absolute;
            left: 10px;
            color: var(--danger-color);
            font-weight: bold;
        }

        .retry-btn {
            background: var(--danger-color);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
            font-size: 16px;
            margin-top: 10px;
        }

        .retry-btn:hover {
            background: #c53030;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(231, 76, 60, 0.3);
        }

        .alternate-action {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #fed7d7;
        }

        .alternate-btn {
            background: var(--primary-blue);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
            margin: 5px;
        }

        .alternate-btn:hover {
            background: var(--primary-blue-dark);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(74, 144, 226, 0.3);
        }
    </style>
</head>
<body>
    <!-- Floating particles for visual appeal -->
    <div class="particle" style="left: 10%; top: 20%; width: 6px; height: 6px; background: var(--primary-blue); border-radius: 50%;"></div>
    <div class="particle" style="left: 80%; top: 40%; width: 8px; height: 8px; background: var(--primary-blue-dark); border-radius: 50%;"></div>
    <div class="particle" style="left: 60%; top: 60%; width: 5px; height: 5px; background: #10b981; border-radius: 50%;"></div>
    <div class="particle" style="left: 30%; top: 80%; width: 7px; height: 7px; background: #f59e0b; border-radius: 50%;"></div>

    <!-- Facts & Fakes AI Navigation Header --> 
    <style>
    /* Reset any conflicting styles */
    .ff-nav * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }

    /* Main navigation bar */
    .ff-nav {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 9999;
        height: 60px;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }

    .ff-nav-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 0 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        height: 60px;
    }

    /* Logo */
    .ff-nav-logo {
        display: flex;
        align-items: center;
        gap: 10px;
        text-decoration: none;
        color: #667eea;
        font-weight: 700;
        font-size: 1.1rem;
        transition: transform 0.3s ease;
    }

    .ff-nav-logo:hover {
        transform: scale(1.05);
    }

    .ff-nav-logo i {
        font-size: 1.4rem;
    }

    /* Navigation links */
    .ff-nav-links {
        display: flex;
        gap: 5px;
        align-items: center;
    }

    .ff-nav-link {
        color: #4a5568;
        text-decoration: none;
        padding: 8px 16px;
        border-radius: 8px;
        transition: all 0.3s ease;
        font-weight: 500;
        font-size: 0.9rem;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .ff-nav-link:hover {
        background: rgba(102, 126, 234, 0.1);
        color: #667eea;
        transform: translateY(-2px);
    }

    .ff-nav-link.active {
        background: rgba(102, 126, 234, 0.15);
        color: #667eea;
        font-weight: 600;
    }

    .ff-nav-link i {
        font-size: 0.9rem;
    }

    /* Auth buttons */
    .ff-nav-auth {
        display: flex;
        gap: 10px;
        align-items: center;
        position: relative;
    }

    .ff-nav-login, .ff-nav-signup {
        padding: 8px 20px;
        text-decoration: none;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        transition: all 0.3s ease;
    }

    .ff-nav-login {
        color: #667eea;
        border: 2px solid #667eea;
    }

    .ff-nav-login:hover {
        background: #667eea;
        color: white;
        transform: translateY(-2px);
    }

    .ff-nav-signup {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: 2px solid transparent;
    }

    .ff-nav-signup:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
    }

    /* Beta balloon */
    .ff-beta-balloon {
        position: absolute;
        top: -35px;
        right: 50px;
        background: linear-gradient(135deg, #ff6b35, #f7931e);
        color: white;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        white-space: nowrap;
        animation: ff-bounce 2s infinite;
        box-shadow: 0 4px 15px rgba(255, 107, 53, 0.3);
    }

    .ff-beta-balloon::after {
        content: '';
        position: absolute;
        bottom: -6px;
        right: 20px;
        width: 0;
        height: 0;
        border-left: 6px solid transparent;
        border-right: 6px solid transparent;
        border-top: 6px solid #f7931e;
    }

    @keyframes ff-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-5px); }
    }

    /* User menu */
    .ff-user-menu {
        position: relative;
        display: none;
    }

    .ff-user-menu-toggle {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 16px;
        background: rgba(102, 126, 234, 0.1);
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.3s ease;
        color: #4a5568;
        font-weight: 500;
        font-size: 0.9rem;
    }

    .ff-user-menu-toggle:hover {
        background: rgba(102, 126, 234, 0.2);
    }

    .ff-user-dropdown {
        position: absolute;
        top: 100%;
        right: 0;
        margin-top: 10px;
        background: white;
        border-radius: 12px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(0, 0, 0, 0.1);
        min-width: 280px;
        opacity: 0;
        visibility: hidden;
        transform: translateY(-10px);
        transition: all 0.3s ease;
    }

    .ff-user-dropdown.active {
        opacity: 1;
        visibility: visible;
        transform: translateY(0);
    }

    /* Mobile menu button */
    .ff-mobile-menu-btn {
        display: none;
        background: none;
        border: none;
        color: #4a5568;
        font-size: 1.5rem;
        cursor: pointer;
        padding: 8px;
        transition: all 0.3s ease;
    }

    .ff-mobile-menu-btn:hover {
        color: #667eea;
    }

    /* Mobile responsive */
    @media (max-width: 768px) {
        .ff-nav-links {
            display: none;
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            flex-direction: column;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
            border-top: 1px solid #e2e8f0;
        }
        
        .ff-nav-links.active {
            display: flex;
        }
        
        .ff-nav-link {
            width: 100%;
            padding: 12px 20px;
        }
        
        .ff-mobile-menu-btn {
            display: block;
        }
        
        .ff-nav-auth {
            display: none;
        }
        
        .ff-user-menu {
            display: none !important;
        }
        
        .ff-beta-balloon {
            display: none;
        }
    }
    </style>

    <nav class="ff-nav">
        <div class="ff-nav-container">
            <a href="/" class="ff-nav-logo">
                <i class="fas fa-shield-alt"></i>
                <span>Facts & Fakes AI</span>
            </a>
            
            <div class="ff-nav-links" id="ffNavLinks">
                <a href="/" class="ff-nav-link"><i class="fas fa-home"></i> Home</a>
                <a href="/news" class="ff-nav-link"><i class="fas fa-newspaper"></i> News Verify</a>
                <a href="/speech" class="ff-nav-link"><i class="fas fa-microphone"></i> Speech Check</a>
                <a href="/unified" class="ff-nav-link"><i class="fas fa-search"></i> Content Check</a>
                <a href="/imageanalysis" class="ff-nav-link"><i class="fas fa-image"></i> Image Analysis</a>
                <a href="/missionstatement" class="ff-nav-link"><i class="fas fa-bullseye"></i> Mission</a>
                <a href="/pricingplan" class="ff-nav-link"><i class="fas fa-tags"></i> Pricing</a>
                <a href="/contact" class="ff-nav-link"><i class="fas fa-envelope"></i> Contact</a>
            </div>
            
            <div class="ff-nav-auth" id="ffNavAuth">
                <a href="/login" class="ff-nav-login">Login</a>
                <a href="/pricingplan" class="ff-nav-signup">Sign Up</a>
                <div class="ff-beta-balloon">
                    sign up now to start your free trial
                </div>
            </div>
            
            <div class="ff-user-menu" id="ffUserMenu">
                <div class="ff-user-menu-toggle" onclick="ffToggleUserDropdown()">
                    <span id="ffUserEmail">user@example.com</span>
                    <i class="fas fa-chevron-down"></i>
                </div>
                <div class="ff-user-dropdown" id="ffUserDropdown">
                    <div style="padding: 20px; border-bottom: 1px solid #e2e8f0;">
                        <div style="font-weight: 600; color: #2d3748; margin-bottom: 4px;" id="ffUserEmailDropdown">user@example.com</div>
                        <div style="font-size: 0.85rem; color: #667eea; font-weight: 500;" id="ffUserPlan">Free Plan</div>
                    </div>
                    <div style="padding: 20px; border-bottom: 1px solid #e2e8f0;">
                        <div style="font-size: 0.85rem; color: #718096; margin-bottom: 8px; font-weight: 500;">Daily Usage</div>
                        <div style="background: #e2e8f0; height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: 8px;">
                            <div id="ffUsageProgress" style="height: 100%; background: linear-gradient(135deg, #667eea, #764ba2); width: 0%; transition: width 0.5s ease;"></div>
                        </div>
                        <div style="font-size: 0.8rem; color: #4a5568;" id="ffUsageText">0 / 5 analyses used</div>
                    </div>
                    <div style="padding: 10px 0;">
                        <a href="/account" style="display: flex; align-items: center; gap: 10px; padding: 12px 20px; color: #4a5568; text-decoration: none; transition: all 0.3s ease; font-size: 0.9rem;"><i class="fas fa-user"></i> Account Settings</a>
                        <a href="/billing" style="display: flex; align-items: center; gap: 10px; padding: 12px 20px; color: #4a5568; text-decoration: none; transition: all 0.3s ease; font-size: 0.9rem;"><i class="fas fa-credit-card"></i> Billing</a>
                        <a href="/api-keys" style="display: flex; align-items: center; gap: 10px; padding: 12px 20px; color: #4a5568; text-decoration: none; transition: all 0.3s ease; font-size: 0.9rem;"><i class="fas fa-key"></i> API Keys</a>
                        <a href="#" onclick="ffLogout()" style="display: flex; align-items: center; gap: 10px; padding: 12px 20px; color: #4a5568; text-decoration: none; transition: all 0.3s ease; font-size: 0.9rem;"><i class="fas fa-sign-out-alt"></i> Logout</a>
                    </div>
                </div>
            </div>
            
            <button class="ff-mobile-menu-btn" onclick="ffToggleMobileMenu()">
                <i class="fas fa-bars"></i>
            </button>
        </div>
    </nav>

    <script>
    // Namespace all functions to avoid conflicts
    window.ffNav = {
        checkAuthStatus: async function() {
            try {
                const response = await fetch('/api/user/status');
                
                // Check if response is OK and content type is JSON
                if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
                    console.log('Auth endpoint not available or not returning JSON');
                    return;
                }
                
                const data = await response.json();
                
                if (data.authenticated) {
                    document.getElementById('ffNavAuth').style.display = 'none';
                    document.getElementById('ffUserMenu').style.display = 'block';
                    
                    document.getElementById('ffUserEmail').textContent = data.email || 'User';
                    document.getElementById('ffUserEmailDropdown').textContent = data.email || 'User';
                    document.getElementById('ffUserPlan').textContent = data.plan === 'pro' ? 'Pro Plan' : 'Free Plan';
                    
                    const usagePercent = (data.usage_today / data.daily_limit) * 100;
                    document.getElementById('ffUsageProgress').style.width = usagePercent + '%';
                    document.getElementById('ffUsageText').textContent = `${data.usage_today} / ${data.daily_limit} analyses used`;
                }
            } catch (error) {
                // Silently fail - user is not authenticated or endpoint doesn't exist
                console.log('Auth check skipped:', error.message);
            }
        },
        
        init: function() {
            this.checkAuthStatus();
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(event) {
                const userMenu = document.querySelector('.ff-user-menu');
                if (userMenu && !userMenu.contains(event.target)) {
                    document.getElementById('ffUserDropdown').classList.remove('active');
                }
            });
            
            // Add active class to current page
            const currentPath = window.location.pathname;
            document.querySelectorAll('.ff-nav-link').forEach(link => {
                if (link.getAttribute('href') === currentPath) {
                    link.classList.add('active');
                }
            });
        }
    };

    // Global functions for onclick handlers
    function ffToggleMobileMenu() {
        const navLinks = document.getElementById('ffNavLinks');
        navLinks.classList.toggle('active');
    }

    function ffToggleUserDropdown() {
        const dropdown = document.getElementById('ffUserDropdown');
        dropdown.classList.toggle('active');
    }

    async function ffLogout() {
        try {
            await fetch('/api/logout', { method: 'POST' });
            window.location.href = '/';
        } catch (error) {
            console.error('Logout failed:', error);
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.ffNav.init();
        });
    } else {
        window.ffNav.init();
    }
    </script>

    <!-- Add spacing after fixed header -->
    <div style="height: 60px;"></div>

    <div class="news-container">
        <!-- Header Section -->
        <div class="news-header">
            <h1>
                <i class="fas fa-newspaper text-primary me-3"></i>
                Advanced News Analyzer
            </h1>
            <p>
                Verify news authenticity with AI-powered analysis
                <span class="tooltip-container">
                    <span class="tooltip-icon">?</span>
                    <span class="tooltip-content">
                        Our AI analyzes 15+ factors including source credibility, writing patterns, 
                        bias indicators, and cross-references with fact-checking databases.
                    </span>
                </span>
            </p>
            <!-- Overview Process Button -->
            <button class="btn btn-outline-primary mt-3" onclick="showAnalysisProcess()">
                <i class="fas fa-info-circle me-2"></i>View Our Analysis Process
            </button>
        </div>

        <!-- Input Section with animated gradient background -->
        <div class="input-section">
            <div class="input-tabs">
                <div class="input-tab active" onclick="switchInputType('url')">
                    <i class="fas fa-link me-2"></i>Analyze URL
                </div>
                <div class="input-tab" onclick="switchInputType('text')">
                    <i class="fas fa-file-alt me-2"></i>Paste Text
                </div>
            </div>
            
            <div id="url-input-section">
                <input type="url" id="news-url" placeholder="https://example.com/article" />
                <small class="text-muted d-block mt-2">
                    <i class="fas fa-info-circle me-1"></i>
                    We'll extract the full article, metadata, and verify the source
                </small>
                <small class="text-muted d-block mt-1">
                    <i class="fas fa-lightbulb me-1"></i>
                    <strong>Tip:</strong> Some news sites block automated access. If you encounter issues, use the "Paste Text" tab instead.
                </small>
            </div>
            
            <div id="text-input-section" style="display: none;">
                <textarea id="news-text" placeholder="Paste the article text here..."></textarea>
                <small class="text-muted d-block mt-2">
                    <i class="fas fa-info-circle me-1"></i>
                    Include the headline and author if available for best results
                </small>
            </div>
            
            <button class="analyze-button glow-effect" onclick="analyzeArticle()">
                <i class="fas fa-search me-2"></i>Analyze Now
            </button>
        </div>

        <!-- Loading Section with Enhanced Progress -->
        <div id="loading-section" style="display: none;">
            <!-- Compact Fixed Progress Bar -->
            <div style="position: fixed; top: 0; left: 0; right: 0; background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.1); z-index: 1000; padding: 20px;">
                <div class="container">
                    <h5 class="mb-2">
                        <i class="fas fa-brain fa-pulse me-2 text-primary"></i>
                        AI Analysis in Progress...
                    </h5>
                    <div class="progress-container" style="margin-bottom: 10px;">
                        <div class="progress-bar" id="analysis-progress">0%</div>
                    </div>
                    <p class="mb-0 text-muted" id="current-stage-text">Initializing analysis...</p>
                </div>
            </div>
            
            <!-- Stages (below fixed header) -->
            <div class="card shadow-lg border-0 mb-5" style="margin-top: 120px;">
                <div class="card-body p-4">
                    <!-- Enhanced stages -->
                    <div class="analysis-stage" id="stage-1">
                        <div class="stage-icon">
                            <i class="fas fa-download"></i>
                        </div>
                        <div class="flex-grow-1">
                            <h5 class="mb-1">Extracting Content</h5>
                            <small class="text-muted">Retrieving article text, metadata, and author information</small>
                        </div>
                    </div>
                    
                    <div class="analysis-stage" id="stage-2">
                        <div class="stage-icon">
                            <i class="fas fa-brain"></i>
                        </div>
                        <div class="flex-grow-1">
                            <h5 class="mb-1">AI Deep Analysis (GPT-4)</h5>
                            <small class="text-muted">Analyzing writing patterns, style, and authenticity markers</small>
                        </div>
                    </div>
                    
                    <div class="analysis-stage" id="stage-3">
                        <div class="stage-icon">
                            <i class="fas fa-check-double"></i>
                        </div>
                        <div class="flex-grow-1">
                            <h5 class="mb-1">Cross-Reference Fact Checking</h5>
                            <small class="text-muted">Verifying claims against multiple fact-checking databases</small>
                        </div>
                    </div>
                    
                    <div class="analysis-stage" id="stage-4">
                        <div class="stage-icon">
                            <i class="fas fa-balance-scale"></i>
                        </div>
                        <div class="flex-grow-1">
                            <h5 class="mb-1">Bias & Manipulation Detection</h5>
                            <small class="text-muted">Scanning for political bias, emotional manipulation, and agenda</small>
                        </div>
                    </div>
                    
                    <div class="analysis-stage" id="stage-5">
                        <div class="stage-icon">
                            <i class="fas fa-chart-line"></i>
                        </div>
                        <div class="flex-grow-1">
                            <h5 class="mb-1">Source Reliability Analysis</h5>
                            <small class="text-muted">Checking historical accuracy and credibility patterns</small>
                        </div>
                    </div>
                    
                    <div class="analysis-stage" id="stage-6">
                        <div class="stage-icon">
                            <i class="fas fa-file-alt"></i>
                        </div>
                        <div class="flex-grow-1">
                            <h5 class="mb-1">Generating Comprehensive Report</h5>
                            <small class="text-muted">Compiling findings with confidence intervals and recommendations</small>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Results Section -->
        <div id="results-section" style="display: none;">
            <!-- Analysis Metadata -->
            <div class="analysis-meta">
                <div class="meta-item">
                    <i class="fas fa-clock"></i>
                    <span>Analyzed: <span id="analysis-time"></span></span>
                </div>
                <div class="meta-item">
                    <i class="fas fa-code-branch"></i>
                    <span>Model Version: GPT-4 v2.1</span>
                </div>
                <div class="meta-item">
                    <i class="fas fa-server"></i>
                    <span>Analysis ID: <span id="analysis-id"></span></span>
                </div>
                <div class="meta-item">
                    <button class="pdf-button" onclick="generatePDF()">
                        <i class="fas fa-file-pdf"></i>Generate PDF Report
                    </button>
                </div>
            </div>

            <!-- Enhanced Trust Meter (Larger) -->
            <div class="trust-meter-container">
                <div class="trust-meter">
                    <svg class="trust-meter-circle" viewBox="0 0 200 200">
                        <circle class="trust-meter-bg" cx="100" cy="100" r="90"/>
                        <circle class="trust-meter-fill" cx="100" cy="100" r="90"
                                stroke-dasharray="565.48" stroke-dashoffset="565.48"/>
                    </svg>
                    <div class="trust-meter-text">
                        <span class="trust-score" id="trust-score">0</span>
                        <span class="trust-label">Trust Score</span>
                    </div>
                </div>
            </div>

            <!-- Overall Assessment (Always Open) -->
            <div class="analysis-dropdown border-trust">
                <div class="dropdown-header">
                    <h3><i class="fas fa-chart-pie"></i>Overall Assessment</h3>
                </div>
                <div class="dropdown-content show">
                    <div id="overall-assessment"></div>
                    
                    <!-- Why This Matters -->
                    <div class="why-matters-box">
                        <h4><i class="fas fa-lightbulb"></i>Why This Matters</h4>
                        <p id="why-overall-matters">
                            Understanding the overall credibility helps you make informed decisions about 
                            sharing, citing, or acting on this information. High credibility means the article 
                            is more likely to be factual and trustworthy.
                        </p>
                    </div>
                    
                    <!-- Confidence Interval -->
                    <div class="mt-3">
                        <h5>Confidence Level
                            <span class="tooltip-container">
                                <span class="tooltip-icon">?</span>
                                <span class="tooltip-content">
                                    Our confidence in this assessment based on available data and analysis certainty
                                </span>
                            </span>
                        </h5>
                        <div class="confidence-bar">
                            <div class="confidence-fill" id="overall-confidence" style="width: 0%">
                                <div class="confidence-label">0%</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="key-findings mt-4">
                        <h5>Key Findings:</h5>
                        <ul id="key-findings-list"></ul>
                    </div>
                    
                    <div class="red-flags mt-3">
                        <h5>Red Flags:</h5>
                        <ul id="red-flags-list"></ul>
                    </div>
                    
                    <a href="#" class="learn-more-link mt-3" onclick="showMethodology()">
                        Learn about our methodology <i class="fas fa-arrow-right"></i>
                    </a>
                </div>
            </div>

            <!-- Source Credibility -->
            <div class="analysis-dropdown border-author">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-globe"></i>Source Credibility & Comparison</h3>
                </div>
                <div class="dropdown-content">
                    <div id="source-credibility"></div>
                    
                    <!-- Source Comparison Grid -->
                    <h5 class="mt-4">How This Source Compares</h5>
                    <div class="source-comparison">
                        <div class="source-card">
                            <div class="source-logo">CNN</div>
                            <div class="source-score text-success">85%</div>
                            <small class="text-muted">Avg. Accuracy</small>
                        </div>
                        <div class="source-card">
                            <div class="source-logo">FOX</div>
                            <div class="source-score text-warning">72%</div>
                            <small class="text-muted">Avg. Accuracy</small>
                        </div>
                        <div class="source-card">
                            <div class="source-logo">BBC</div>
                            <div class="source-score text-success">91%</div>
                            <small class="text-muted">Avg. Accuracy</small>
                        </div>
                        <div class="source-card">
                            <div class="source-logo">THIS</div>
                            <div class="source-score" id="this-source-score">--</div>
                            <small class="text-muted">This Source</small>
                        </div>
                    </div>
                    
                    <!-- Historical Accuracy (Pro Feature Preview) -->
                    <div class="pro-feature-locked mt-4">
                        <h5>Historical Accuracy Trend</h5>
                        <div class="accuracy-chart">
                            <div class="chart-grid">
                                <div class="chart-line"></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="methodology-snippet">
                        <strong>How we calculate this:</strong> Source credibility = 
                        <code>0.4 × historical_accuracy + 0.3 × transparency + 0.2 × corrections_policy + 0.1 × awards</code>
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="source-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="source-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Author Credibility -->
            <div class="analysis-dropdown border-author">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-user-check"></i>Author Credibility & Background</h3>
                </div>
                <div class="dropdown-content">
                    <div id="author-credibility"></div>
                    
                    <!-- Author Research Links -->
                    <div class="mt-3">
                        <h5>Research This Author:</h5>
                        <div class="btn-group" role="group">
                            <a href="#" class="btn btn-outline-primary btn-sm" id="author-twitter" target="_blank">
                                <i class="fab fa-twitter me-1"></i>Twitter
                            </a>
                            <a href="#" class="btn btn-outline-primary btn-sm" id="author-google" target="_blank">
                                <i class="fab fa-google me-1"></i>Google
                            </a>
                            <a href="#" class="btn btn-outline-primary btn-sm" id="author-linkedin" target="_blank">
                                <i class="fab fa-linkedin me-1"></i>LinkedIn
                            </a>
                        </div>
                    </div>
                    
                    <div class="why-matters-box mt-3">
                        <h4><i class="fas fa-lightbulb"></i>Why This Matters</h4>
                        <p>
                            Authors with established expertise and transparent backgrounds are more likely 
                            to produce accurate, well-researched content. Anonymous or unverifiable authors 
                            should be approached with more skepticism.
                        </p>
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="author-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="author-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Writing Quality -->
            <div class="analysis-dropdown border-quality">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-pen-fancy"></i>Writing Quality & Professionalism</h3>
                </div>
                <div class="dropdown-content">
                    <div id="writing-quality"></div>
                    
                    <div class="methodology-snippet">
                        <strong>Analysis includes:</strong> Grammar scoring, readability index (Flesch-Kincaid), 
                        vocabulary diversity, sentence structure variation, and professional tone markers.
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="quality-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="quality-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Fact-Checking -->
            <div class="analysis-dropdown border-fact">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-check-double"></i>Fact-Checking Results</h3>
                </div>
                <div class="dropdown-content">
                    <div id="fact-checking"></div>
                    
                    <!-- Confidence Intervals for Each Claim -->
                    <div class="mt-4" id="claim-confidence-section">
                        <!-- Dynamically populated -->
                    </div>
                    
                    <div class="why-matters-box mt-3">
                        <h4><i class="fas fa-lightbulb"></i>Why This Matters</h4>
                        <p>
                            False or misleading claims can shape opinions and decisions. We verify each 
                            claim against multiple trusted fact-checking databases and provide confidence 
                            levels for our assessments.
                        </p>
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="fact-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="fact-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Political Bias -->
            <div class="analysis-dropdown border-bias">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-balance-scale"></i>Political Bias Detection</h3>
                </div>
                <div class="dropdown-content">
                    <!-- Bias spectrum bar -->
                    <div class="bias-spectrum mt-3 mb-4">
                        <div style="position: relative; height: 30px; background: linear-gradient(to right, #3b82f6 0%, #e5e7eb 50%, #ef4444 100%); border-radius: 15px;">
                            <div id="bias-marker" style="position: absolute; top: -5px; width: 40px; height: 40px; background: white; border: 3px solid #1f2937; border-radius: 50%; left: 50%; transform: translateX(-50%); box-shadow: 0 2px 10px rgba(0,0,0,0.3);"></div>
                        </div>
                        <div class="d-flex justify-content-between mt-2">
                            <small>Far Left</small>
                            <small>Center</small>
                            <small>Far Right</small>
                        </div>
                    </div>
                    
                    <div id="political-bias"></div>
                    
                    <div class="methodology-snippet">
                        <strong>Bias detection algorithm:</strong> We analyze word choice, framing, 
                        source selection, and compare against our database of 50,000+ politically-charged 
                        terms weighted by context and frequency.
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="bias-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="bias-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Hidden Agenda -->
            <div class="analysis-dropdown border-agenda">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-user-secret"></i>Hidden Agenda Detection</h3>
                </div>
                <div class="dropdown-content">
                    <div id="hidden-agenda"></div>
                    
                    <div class="why-matters-box mt-3">
                        <h4><i class="fas fa-lightbulb"></i>Why This Matters</h4>
                        <p>
                            Articles with hidden agendas may appear objective but subtly push commercial, 
                            political, or ideological interests. Recognizing these helps you understand 
                            the true purpose behind the content.
                        </p>
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="agenda-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="agenda-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Clickbait Analysis -->
            <div class="analysis-dropdown border-clickbait">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-mouse-pointer"></i>Clickbait & Sensationalism</h3>
                </div>
                <div class="dropdown-content">
                    <div id="clickbait-analysis"></div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="clickbait-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="clickbait-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Emotional Manipulation -->
            <div class="analysis-dropdown border-emotion">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-theater-masks"></i>Emotional Manipulation Check</h3>
                </div>
                <div class="dropdown-content">
                    <!-- Emotional gauge -->
                    <div class="gauge-container">
                        <div class="gauge">
                            <div class="gauge-mask"></div>
                            <div class="gauge-needle" id="emotion-needle"></div>
                        </div>
                        <div class="gauge-labels">
                            <small>0%</small>
                            <small>50%</small>
                            <small>100%</small>
                        </div>
                    </div>
                    
                    <div id="emotional-manipulation"></div>
                    
                    <div class="methodology-snippet">
                        <strong>Emotional analysis:</strong> Using sentiment analysis and psychological 
                        trigger word detection across 8 emotional categories (fear, anger, joy, sadness, 
                        disgust, surprise, trust, anticipation).
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="emotion-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="emotion-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Source Diversity -->
            <div class="analysis-dropdown border-diversity">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-project-diagram"></i>Source Diversity & Balance</h3>
                </div>
                <div class="dropdown-content">
                    <!-- Progress bar for source diversity -->
                    <div class="progress-container mb-3">
                        <div class="progress-bar" id="diversity-bar" style="width: 0%">0%</div>
                    </div>
                    
                    <div id="source-diversity"></div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="diversity-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="diversity-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Timeliness Check -->
            <div class="analysis-dropdown border-time">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-calendar-check"></i>Timeliness & Relevance</h3>
                </div>
                <div class="dropdown-content">
                    <div id="timeliness-check"></div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="timeliness-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="timeliness-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- AI-Generated Content Detection (New Feature) -->
            <div class="analysis-dropdown border-ai">
                <div class="dropdown-header" onclick="toggleDropdown(this)">
                    <h3><i class="fas fa-robot"></i>AI-Generated Content Detection</h3>
                </div>
                <div class="dropdown-content">
                    <h5>AI Content Probability</h5>
                    <div class="confidence-bar mb-3">
                        <div class="confidence-fill" id="ai-probability" style="width: 0%">
                            <div class="confidence-label">0%</div>
                        </div>
                    </div>
                    
                    <div class="mt-3">
                        <h6>AI Pattern Indicators:</h6>
                        <ul id="ai-patterns">
                            <!-- Dynamically populated -->
                        </ul>
                    </div>
                    
                    <div class="methodology-snippet">
                        <strong>Detection method:</strong> Perplexity analysis, burstiness scoring, 
                        repetitive phrasing detection, and comparison against known AI writing patterns 
                        from GPT, Claude, and other models.
                    </div>
                    
                    <div class="what-this-means mt-3">
                        <h5>What This Means:</h5>
                        <p id="ai-explanation"></p>
                    </div>
                    
                    <div class="how-detected mt-3">
                        <h5>How We Detected This:</h5>
                        <p id="ai-methodology"></p>
                    </div>
                </div>
            </div>

            <!-- Pricing Information -->
            <div class="pricing-info">
                <h4><i class="fas fa-crown me-2"></i>Upgrade for More Features</h4>
                <div class="pricing-tier">
                    <div>
                        <h4>Free Tier</h4>
                        <p class="mb-0">1 analysis per day</p>
                    </div>
                    <div class="price">$0</div>
                </div>
                <div class="pricing-tier">
                    <div>
                        <h4>Pro Tier</h4>
                        <p class="mb-0">Unlimited analyses + API access</p>
                    </div>
                    <div class="price">$19/mo</div>
                </div>
            </div>

            <!-- Download Complete Report Button -->
            <div class="text-center mt-5">
                <button class="btn btn-success btn-lg" onclick="downloadFullReport()">
                    <i class="fas fa-file-pdf me-2"></i>Download Complete Analysis Report (PDF)
                </button>
            </div>
        </div>

        <!-- Enhanced Error Container -->
        <div class="error-container" id="error-container">
            <i class="fas fa-exclamation-triangle"></i>
            <h3>Analysis Error</h3>
            <p id="error-message">An error occurred during analysis.</p>
            
            <!-- Suggestions section (hidden by default) -->
            <div class="error-suggestions" id="error-suggestions" style="display: none;">
                <h4>Here's what you can do:</h4>
                <ul id="suggestion-list">
                    <!-- Populated dynamically -->
                </ul>
            </div>
            
            <!-- Alternate actions -->
            <div class="alternate-action">
                <button class="retry-btn" onclick="retryAnalysis()">
                    <i class="fas fa-redo"></i> Retry Analysis
                </button>
                <button class="alternate-btn" onclick="switchInputType('text')">
                    <i class="fas fa-file-alt"></i> Switch to Text Input
                </button>
            </div>
        </div>
    </div>

    <!-- Loading Overlay -->
    <div class="loading-overlay" id="loading-overlay">
        <div class="loading-content">
            <div class="loading-spinner"></div>
            <div class="loading-text" id="loading-text">Initializing Analysis...</div>
            <div class="loading-subtext" id="loading-subtext">Please wait while we process your content</div>
            <div class="progress-container">
                <div class="progress-bar" id="progress-fill" style="width: 0%"></div>
            </div>
        </div>
    </div>

    <!-- Sticky Upgrade Button -->
    <div class="sticky-upgrade">
        <button onclick="window.location.href='/pricing'">
            <i class="fas fa-crown me-2"></i>Upgrade to Pro
        </button>
    </div>

    <!-- Analysis Process Modal -->
    <div class="modal fade" id="analysisProcessModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">
                        <i class="fas fa-cogs me-2"></i>Our Comprehensive Analysis Process
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <h6>Our AI-powered analysis examines:</h6>
                    <div class="row mt-3">
                        <div class="col-md-6">
                            <ul>
                                <li><strong>Source Credibility:</strong> Historical accuracy, transparency, corrections policy</li>
                                <li><strong>Author Background:</strong> Expertise, publication history, credentials</li>
                                <li><strong>Writing Quality:</strong> Grammar, structure, professionalism</li>
                                <li><strong>Fact Verification:</strong> Cross-reference with multiple databases</li>
                                <li><strong>Political Bias:</strong> 50,000+ term analysis, framing detection</li>
                            </ul>
                        </div>
                        <div class="col-md-6">
                            <ul>
                                <li><strong>Hidden Agendas:</strong> Commercial interests, persuasion tactics</li>
                                <li><strong>Clickbait Detection:</strong> Headline-content matching</li>
                                <li><strong>Emotional Manipulation:</strong> 8 emotion categories analyzed</li>
                                <li><strong>Source Diversity:</strong> Variety and balance assessment</li>
                                <li><strong>AI Content Detection:</strong> Pattern analysis across models</li>
                            </ul>
                        </div>
                    </div>
                    <hr>
                    <p><strong>Technology Stack:</strong></p>
                    <ul>
                        <li>GPT-4 for deep content analysis</li>
                        <li>Natural Language Processing for linguistic patterns</li>
                        <li>Machine Learning models trained on 1M+ articles</li>
                        <li>Real-time fact-checking API integrations</li>
                        <li>Proprietary bias detection algorithms</li>
                    </ul>
                    <hr>
                    <p class="text-muted mb-0">Each analysis generates 100+ data points to ensure comprehensive, accurate results you can trust.</p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS from cdnjs (CSP approved) -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js"></script>
    
    <script>
    // Initialize page
    document.addEventListener('DOMContentLoaded', function() {
        // Initialize any needed components
        console.log('News analyzer ready');
    });

    // Global variable to store current analysis results
    let currentAnalysisResults = null;

    // Switch between URL and text input
    function switchInputType(type) {
        const urlSection = document.getElementById('url-input-section');
        const textSection = document.getElementById('text-input-section');
        const tabs = document.querySelectorAll('.input-tab');
        
        tabs.forEach(tab => tab.classList.remove('active'));
        
        if (type === 'url') {
            urlSection.style.display = 'block';
            textSection.style.display = 'none';
            tabs[0].classList.add('active');
        } else {
            urlSection.style.display = 'none';
            textSection.style.display = 'block';
            tabs[1].classList.add('active');
        }
        
        // Hide error container if switching tabs
        document.getElementById('error-container').style.display = 'none';
    }

    // ENHANCED analysis function with better error handling
    async function analyzeArticle() {
        const urlInput = document.getElementById('news-url');
        const textInput = document.getElementById('news-text');
        const loadingSection = document.getElementById('loading-section');
        const resultsSection = document.getElementById('results-section');
        const errorContainer = document.getElementById('error-container');
        
        // Get input based on active section
        const isUrlMode = document.getElementById('url-input-section').style.display !== 'none';
        const input = isUrlMode ? urlInput.value.trim() : textInput.value.trim();
        
        if (!input) {
            alert('Please enter a URL or paste article text');
            return;
        }
        
        // Hide any previous errors
        errorContainer.style.display = 'none';
        
        // Show loading
        loadingSection.style.display = 'block';
        resultsSection.style.display = 'none';
        
        // Reset stages
        document.querySelectorAll('.analysis-stage').forEach(stage => {
            stage.classList.remove('active', 'complete');
        });
        
        // Initialize progress tracking
        let progress = 0;
        const progressBar = document.getElementById('analysis-progress');
        const stages = document.querySelectorAll('.analysis-stage');
        let currentStage = 0;
        let progressInterval;
        
        try {
            // Start progress animation
            progressInterval = setInterval(() => {
                if (progress < 90) {
                    progress += 5;
                    progressBar.style.width = progress + '%';
                    progressBar.textContent = progress + '%';
                    
                    // Update stages
                    const stageProgress = Math.floor((progress / 100) * stages.length);
                    if (stageProgress > currentStage && currentStage < stages.length) {
                        if (currentStage > 0) {
                            stages[currentStage - 1].classList.remove('active');
                            stages[currentStage - 1].classList.add('complete');
                        }
                        stages[currentStage].classList.add('active');
                        currentStage = stageProgress;
                    }
                }
            }, 200);
            
            // Prepare request body
            const requestBody = {
                content: input,
                type: isUrlMode ? 'url' : 'text',
                is_pro: true
            };
            
            console.log('Sending analysis request:', requestBody);
            
            // CALL YOUR ACTUAL BACKEND
            const response = await fetch('/api/analyze-news', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody)
            });
            
            clearInterval(progressInterval);
            
            // Check response
            if (!response.ok) {
                let errorMessage = `Server error: ${response.status}`;
                let suggestions = [];
                
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.error || errorData.message || errorMessage;
                    suggestions = errorData.suggestions || [];
                } catch (e) {
                    console.error('Error parsing error response:', e);
                }
                
                const errorObj = new Error(errorMessage);
                errorObj.suggestions = suggestions;
                throw errorObj;
            }
            
            const data = await response.json();
            console.log('Analysis response:', data);
            
            // Complete progress
            progressBar.style.width = '100%';
            progressBar.textContent = '100%';
            stages.forEach(stage => {
                stage.classList.remove('active');
                stage.classList.add('complete');
            });
            
            // Check for success - handle both success flag and presence of results
            if (data.success === true || (data.trust_score !== undefined && !data.error)) {
                // Store results globally for PDF generation - data is at root level
                currentAnalysisResults = data;
                
                // Display REAL results from YOUR backend - pass data directly
                setTimeout(() => {
                    displayRealResults(data);
                    loadingSection.style.display = 'none';
                    resultsSection.style.display = 'block';
                    
                    // Scroll to results
                    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 500);
            } else {
                // Log the full response for debugging
                console.error('Analysis failed. Server response:', data);
                
                // Extract error details
                const errorObj = new Error(data.error || data.message || 'Analysis failed');
                errorObj.suggestions = data.suggestions || [];
                throw errorObj;
            }
            
        } catch (error) {
            console.error('Analysis error:', error);
            loadingSection.style.display = 'none';
            
            // Clear any running intervals
            if (progressInterval) {
                clearInterval(progressInterval);
            }
            
            // Show enhanced error message with suggestions
            showEnhancedError(error.message, error.suggestions || []);
        }
    }

    // Enhanced error display function
    function showEnhancedError(message, suggestions = []) {
        const errorContainer = document.getElementById('error-container');
        const errorMessage = document.getElementById('error-message');
        const errorSuggestions = document.getElementById('error-suggestions');
        const suggestionList = document.getElementById('suggestion-list');
        
        // Set the error message
        errorMessage.textContent = message;
        
        // Handle suggestions if provided
        if (suggestions && suggestions.length > 0) {
            errorSuggestions.style.display = 'block';
            suggestionList.innerHTML = suggestions.map(suggestion => 
                `<li>${suggestion}</li>`
            ).join('');
        } else {
            // Default suggestions based on error type
            const defaultSuggestions = [];
            
            if (message.toLowerCase().includes('extract') || 
                message.toLowerCase().includes('timeout') ||
                message.toLowerCase().includes('blocked')) {
                defaultSuggestions.push(
                    'Copy and paste the article text using the "Paste Text" tab',
                    'Try a different news article or source',
                    'Check if the URL is correctly formatted',
                    'Some major news sites (CNN, NYTimes, WSJ) block automated access'
                );
            } else if (message.includes('fetch')) {
                defaultSuggestions.push(
                    'Check your internet connection',
                    'Try again in a few moments',
                    'Use the "Paste Text" option instead'
                );
            } else {
                defaultSuggestions.push(
                    'Try again with a different article',
                    'Use the "Paste Text" tab for better results',
                    'Contact support if the issue persists'
                );
            }
            
            if (defaultSuggestions.length > 0) {
                errorSuggestions.style.display = 'block';
                suggestionList.innerHTML = defaultSuggestions.map(suggestion => 
                    `<li>${suggestion}</li>`
                ).join('');
            } else {
                errorSuggestions.style.display = 'none';
            }
        }
        
        // Show error container
        errorContainer.style.display = 'block';
        
        // Hide results
        document.getElementById('results-section').style.display = 'none';
        
        // Scroll to error
        errorContainer.scrollIntoView({ behavior: 'smooth' });
    }

    // Fixed display function that matches your API structure
    function displayRealResults(results) {
        console.log('Displaying results:', results);
        
        // Update timestamp
        const now = new Date();
        document.getElementById('analysis-time').textContent = now.toLocaleString();
        document.getElementById('analysis-id').textContent = results.analysis_id || 'AN-' + Date.now().toString(36).toUpperCase();
        
        // Get trust_score - check both root level and analysis object
        const trustScore = results.trust_score || results.analysis?.trust_score || 0;
        animateTrustMeter(trustScore);
        
        // Get summary - check both locations
        const summary = results.summary || results.analysis?.summary || 'Analysis completed';
        
        // Overall Assessment
        const overallAssessment = {
            credibility: trustScore >= 80 ? 'High' : trustScore >= 60 ? 'Moderate' : 'Low',
            summary: summary
        };
        
        // Get recommendations from either location
        const recommendations = results.recommendations || results.analysis?.recommendations || [];
        const recommendationsHTML = recommendations.length > 0 ? `
            <div class="mt-3">
                <h5>Recommendations:</h5>
                <ul>
                    ${recommendations.map(rec => `<li>${rec}</li>`).join('')}
                </ul>
            </div>
        ` : '';
        
        document.getElementById('overall-assessment').innerHTML = `
            <div class="alert alert-${trustScore >= 80 ? 'success' : trustScore >= 60 ? 'warning' : 'danger'} mb-3">
                <h4 class="alert-heading">
                    <i class="fas fa-${trustScore >= 80 ? 'check-circle' : trustScore >= 60 ? 'exclamation-triangle' : 'times-circle'} me-2"></i>
                    Credibility: ${overallAssessment.credibility}
                </h4>
                <p class="mb-0">${overallAssessment.summary}</p>
            </div>
            ${recommendationsHTML}
        `;
        
        // Update confidence
        const confidence = results.confidence_level || 85;
        const confidenceBar = document.getElementById('overall-confidence');
        setTimeout(() => {
            confidenceBar.style.width = confidence + '%';
            confidenceBar.querySelector('.confidence-label').textContent = confidence + '%';
        }, 200);
        
        // Handle key findings and red flags
        const keyFindings = results.key_claims || results.analysis?.key_claims || [];
        const manipulationTactics = results.manipulation_tactics || results.analysis?.manipulation_tactics || [];
        
        // Display key findings
        if (keyFindings.length > 0) {
            const findingsHTML = keyFindings.map(claim => {
                if (typeof claim === 'object' && claim.claim) {
                    return `<li>${claim.importance ? `<strong>${claim.importance.toUpperCase()}:</strong> ` : ''}${claim.claim}</li>`;
                }
                return `<li>${claim}</li>`;
            }).join('');
            document.getElementById('key-findings-list').innerHTML = findingsHTML;
        } else {
            document.getElementById('key-findings-list').innerHTML = `
                <li>Trust score: ${trustScore}%</li>
                <li>Credibility score: ${Math.round((results.credibility_score || 0) * 100)}%</li>
                ${results.bias_score !== undefined ? `<li>Bias score: ${results.bias_score}</li>` : ''}
            `;
        }
        
        // Display red flags (manipulation tactics)
        if (manipulationTactics.length > 0) {
            const redFlagsHTML = manipulationTactics.map(tactic => {
                if (typeof tactic === 'object') {
                    return `<li><strong>${tactic.tactic || tactic.name}:</strong> ${tactic.description || ''}${
                        tactic.example ? ` <em>(Example: "${tactic.example}")</em>` : ''
                    }</li>`;
                }
                return `<li>${tactic}</li>`;
            }).join('');
            document.getElementById('red-flags-list').innerHTML = redFlagsHTML;
        } else {
            document.getElementById('red-flags-list').innerHTML = `<li>No significant manipulation tactics detected</li>`;
        }
        
        // Call the detailed populate function with the full results
        populateDetailedSections(results);
    }

    // New detailed populate function that handles your API structure
    function populateDetailedSections(results) {
        console.log('Populating detailed sections with:', results);
        
        // Merge analysis data with root level data for easier access
        const analysis = results.analysis || {};
        const mergedResults = { ...results, ...analysis };
        const manipulationTactics = results.manipulation_tactics || results.analysis?.manipulation_tactics || [];
        
        // Author Credibility
        const author = results.article_info?.author || results.article?.author || 'Unknown';
        if (author && author !== 'Unknown') {
            document.getElementById('author-credibility').innerHTML = `
                <h5>Author: ${author}</h5>
                <p>Author credibility assessment based on available information</p>
                <ul>
                    <li>Name verification: ${author.includes(' ') ? 'Full name provided' : 'Single name only'}</li>
                    <li>Attribution: Author identified</li>
                    <li>Transparency: ${author.length > 3 ? 'Good' : 'Limited'}</li>
                </ul>
            `;
            
            // Update author research links
            const authorQuery = encodeURIComponent(author);
            document.getElementById('author-twitter').href = `https://twitter.com/search?q=${authorQuery}`;
            document.getElementById('author-google').href = `https://www.google.com/search?q=${authorQuery}%20journalist`;
            document.getElementById('author-linkedin').href = `https://www.linkedin.com/search/results/all/?keywords=${authorQuery}`;
            
            document.getElementById('author-explanation').textContent = 
                `${author} is listed as the author. Verify their credentials and expertise in this subject area.`;
            document.getElementById('author-methodology').textContent = 
                'Author extracted from article metadata and byline detection';
        } else {
            document.getElementById('author-credibility').innerHTML = `
                <h5>Author: Unknown</h5>
                <p>No author information was found in the article</p>
                <ul>
                    <li>This may indicate lower transparency</li>
                    <li>Consider verifying the source independently</li>
                </ul>
            `;
            document.getElementById('author-explanation').textContent = 
                'No author information provided, which may indicate lower credibility.';
            document.getElementById('author-methodology').textContent = 
                'Searched for author in metadata, bylines, and common author locations';
        }
        
        // Source Credibility
        const sourceData = results.source_credibility || {};
        const domain = results.article_info?.domain || results.article?.domain || 'Unknown';
        const credScore = Math.round((results.credibility_score || 0) * 100);
        
        document.getElementById('source-credibility').innerHTML = `
            <h5>Source: ${domain}</h5>
            <p>Credibility Score: <strong>${credScore}/100</strong></p>
            ${sourceData.credibility ? `<p>Known Credibility: <strong>${sourceData.credibility}</strong></p>` : ''}
            ${sourceData.bias ? `<p>Known Bias: <strong>${sourceData.bias}</strong></p>` : ''}
            ${sourceData.type ? `<p>Source Type: <strong>${sourceData.type}</strong></p>` : ''}
            <ul>
                <li>Trust Score: ${results.trust_score || 0}</li>
                <li>Article Title: ${results.article_info?.title || results.article?.title || 'N/A'}</li>
                ${results.article_info?.publish_date ? `<li>Published: ${results.article_info.publish_date}</li>` : ''}
            </ul>
        `;
        
        document.getElementById('this-source-score').textContent = `${credScore}%`;
        document.getElementById('source-explanation').textContent = 
            sourceData.credibility ? 
            `${domain} is a ${sourceData.type || 'news source'} with ${sourceData.credibility} credibility and ${sourceData.bias || 'unknown'} bias.` :
            'Source credibility assessed based on trust score and analysis results';
        document.getElementById('source-methodology').textContent = 
            'Analysis based on historical accuracy, transparency, and editorial standards';
        
        // Writing Quality
        const qualityMetrics = {
            trustScore: results.trust_score || 0,
            credibilityScore: Math.round((results.credibility_score || 0) * 100),
            factChecks: mergedResults.fact_checks?.length || 0,
            claims: mergedResults.key_claims?.length || 0,
            sources: mergedResults.source_diversity?.sources_count || 1,
            author: author,
            textLength: results.article_info?.text?.length || results.article?.text?.length || 0
        };
        
        document.getElementById('writing-quality').innerHTML = `
            <h5>Quality Metrics:</h5>
            <div class="row">
                <div class="col-md-6">
                    <ul>
                        <li>Overall Trust Score: <strong>${qualityMetrics.trustScore}/100</strong></li>
                        <li>Credibility Score: <strong>${qualityMetrics.credibilityScore}/100</strong></li>
                        <li>Author: <strong>${qualityMetrics.author}</strong></li>
                    </ul>
                </div>
                <div class="col-md-6">
                    <ul>
                        <li>Claims Identified: <strong>${qualityMetrics.claims}</strong></li>
                        <li>Fact Checks: <strong>${qualityMetrics.factChecks}</strong></li>
                        <li>Article Length: <strong>${qualityMetrics.textLength} characters</strong></li>
                    </ul>
                </div>
            </div>
        `;
        
        document.getElementById('quality-explanation').textContent = 
            qualityMetrics.trustScore >= 80 ? 'High quality writing with strong credibility indicators' :
            qualityMetrics.trustScore >= 60 ? 'Moderate quality with some areas for improvement' :
            'Lower quality indicators suggest caution when evaluating this content';
        document.getElementById('quality-methodology').textContent = 
            'Quality assessed through trust scoring, credibility analysis, and content structure evaluation';
        
        // Fact-Checking Results
        const factChecks = mergedResults.fact_checks || [];
        const claims = mergedResults.key_claims || [];
        
        if (factChecks.length > 0 && typeof factChecks[0] === 'object' && factChecks[0].verdict) {
            // Detailed fact checks available
            const factCheckHTML = factChecks.map((check, index) => {
                const verdictClass = {
                    'true': 'status-verified',
                    'false': 'status-false',
                    'misleading': 'status-false',
                    'unverified': 'status-unverified'
                }[check.verdict] || 'status-unverified';
                
                return `
                    <div class="claim-card">
                        <p><strong>Claim ${index + 1}:</strong> "${check.claim}"</p>
                        <span class="claim-status ${verdictClass}">${check.verdict.toUpperCase()}</span>
                        <p class="mt-2">${check.explanation}</p>
                        ${check.confidence ? `<p class="mt-1"><small>Confidence: ${check.confidence}%</small></p>` : ''}
                        ${check.sources && check.sources.length > 0 ? 
                            `<p class="mt-1"><small>Sources: ${check.sources.join(', ')}</small></p>` : ''}
                    </div>
                `;
            }).join('');
            
            document.getElementById('fact-checking').innerHTML = `
                <h5>Fact-Check Results: ${factChecks.length} claims verified</h5>
                ${factCheckHTML}
            `;
        } else if (claims.length > 0) {
            // Only claims available, no verdicts
            const claimsHTML = claims.map((claim, index) => {
                const claimText = typeof claim === 'object' ? claim.claim : claim;
                const importance = typeof claim === 'object' ? claim.importance : 'medium';
                
                return `
                    <div class="claim-card">
                        <p><strong>Claim ${index + 1}:</strong> "${claimText}"</p>
                        <span class="claim-status status-unverified">REQUIRES VERIFICATION</span>
                        <p class="mt-2"><small>Importance: ${importance || 'Medium'}</small></p>
                    </div>
                `;
            }).join('');
            
            document.getElementById('fact-checking').innerHTML = `
                <h5>Claims Identified: ${claims.length}</h5>
                <p class="text-muted">These claims require external fact-checking for verification</p>
                ${claimsHTML}
            `;
        } else {
            document.getElementById('fact-checking').innerHTML = `
                <p>No specific claims identified for fact-checking</p>
            `;
        }
        
        document.getElementById('fact-explanation').textContent = 
            factChecks.length > 0 ? 'Claims have been analyzed and fact-checked' :
            claims.length > 0 ? 'Key claims identified but require external verification' :
            'No specific factual claims were identified in this article';
        document.getElementById('fact-methodology').textContent = 
            'Claims extracted using natural language processing and verified against available data';
        
        // Political Bias
        const biasScore = results.bias_score;
        const biasData = mergedResults.bias_explanation ? mergedResults : {};
        
        if (biasScore !== undefined && biasScore !== 'N/A') {
            const biasPosition = ((parseFloat(biasScore) + 1) / 2) * 100;
            const biasMarker = document.getElementById('bias-marker');
            biasMarker.style.left = biasPosition + '%';
            
            const biasLabel = biasScore < -0.5 ? 'Far Left' :
                             biasScore < -0.2 ? 'Left-Leaning' :
                             biasScore < 0.2 ? 'Center/Neutral' :
                             biasScore < 0.5 ? 'Right-Leaning' : 'Far Right';
            
            document.getElementById('political-bias').innerHTML = `
                <h5>Bias Assessment: <strong>${biasLabel}</strong></h5>
                <p>Bias Score: <strong>${biasScore.toFixed(2)}</strong> (scale: -1 to +1)</p>
                ${biasData.bias_explanation ? `<p>${biasData.bias_explanation}</p>` : ''}
                ${biasData.bias_examples && biasData.bias_examples.length > 0 ? `
                    <h6 class="mt-3">Examples Found:</h6>
                    <ul>
                        ${biasData.bias_examples.map(ex => `<li>${ex}</li>`).join('')}
                    </ul>
                ` : ''}
            `;
            
            document.getElementById('bias-explanation').textContent = 
                biasData.bias_explanation || `Article shows ${biasLabel.toLowerCase()} bias based on language analysis.`;
            document.getElementById('bias-methodology').textContent = 
                'Bias detected through analysis of word choice, framing, and political terminology';
        } else {
            document.getElementById('bias-marker').style.left = '50%';
            document.getElementById('political-bias').innerHTML = `
                <h5>Bias Assessment: Not Available</h5>
                <p>Insufficient data to determine political bias</p>
            `;
            document.getElementById('bias-explanation').textContent = 'Bias analysis was not conclusive';
            document.getElementById('bias-methodology').textContent = 'Content may be too neutral or short for bias detection';
        }
        
        // Hidden Agenda
        const hiddenAgenda = mergedResults.hidden_agenda || {};
        const hasHiddenAgenda = hiddenAgenda.detected || manipulationTactics.length > 3;
        
        document.getElementById('hidden-agenda').innerHTML = `
            <h5>Hidden Agenda Detection: <strong>${hasHiddenAgenda ? 'WARNING' : 'Clear'}</strong></h5>
            ${hasHiddenAgenda ? `
                <div class="alert alert-warning mt-3">
                    ${hiddenAgenda.type ? `<h6>Type: ${hiddenAgenda.type.charAt(0).toUpperCase() + hiddenAgenda.type.slice(1)}</h6>` : ''}
                    <p>${hiddenAgenda.explanation || 'Multiple manipulation tactics suggest potential hidden agenda'}</p>
                    ${hiddenAgenda.evidence && hiddenAgenda.evidence.length > 0 ? `
                        <h6>Evidence:</h6>
                        <ul>
                            ${hiddenAgenda.evidence.map(e => `<li>${e}</li>`).join('')}
                        </ul>
                    ` : ''}
                </div>
            ` : '<p>No clear hidden agenda detected in this article.</p>'}
            ${manipulationTactics.length > 0 ? `
                <h6 class="mt-3">Manipulation Tactics Found (${manipulationTactics.length}):</h6>
                <ul>
                    ${manipulationTactics.slice(0, 5).map(t => 
                        `<li>${typeof t === 'object' ? t.tactic || t.name : t}</li>`
                    ).join('')}
                    ${manipulationTactics.length > 5 ? `<li>...and ${manipulationTactics.length - 5} more</li>` : ''}
                </ul>
            ` : ''}
        `;
        
        document.getElementById('agenda-explanation').textContent = 
            hasHiddenAgenda ? 'Analysis suggests this article may have ulterior motives beyond informing readers' :
            'Article appears to be straightforward in its intent';
        document.getElementById('agenda-methodology').textContent = 
            'Hidden agenda detected through analysis of persuasion techniques, manipulation tactics, and rhetorical devices';
        
        // Populate remaining sections with available data
        populateRemainingSection('clickbait', mergedResults);
        populateRemainingSection('emotion', mergedResults, manipulationTactics);
        populateRemainingSection('diversity', mergedResults);
        populateRemainingSection('timeliness', results);
        populateRemainingSection('ai', mergedResults);
    }

    // Helper function for remaining sections
    function populateRemainingSection(section, data, manipulationTactics) {
        switch(section) {
            case 'clickbait':
                const clickbaitData = data.clickbait_analysis || {};
                const clickbaitScore = clickbaitData.score || 20;
                const title = data.article_info?.title || data.article?.title || '';
                
                document.getElementById('clickbait-analysis').innerHTML = `
                    <h5>Clickbait Score: <strong>${clickbaitScore}/100</strong></h5>
                    <div class="progress mt-3 mb-3" style="height: 30px;">
                        <div class="progress-bar ${
                            clickbaitScore > 70 ? 'bg-danger' : 
                            clickbaitScore > 40 ? 'bg-warning' : 'bg-success'
                        }" role="progressbar" style="width: ${clickbaitScore}%">
                            ${clickbaitScore}%
                        </div>
                    </div>
                    <p>Title: "${title}"</p>
                    ${clickbaitData.indicators && clickbaitData.indicators.length > 0 ? `
                        <h6>Indicators:</h6>
                        <ul>${clickbaitData.indicators.map(ind => `<li>${ind}</li>`).join('')}</ul>
                    ` : ''}
                `;
                
                document.getElementById('clickbait-explanation').textContent = 
                    clickbaitScore > 70 ? 'High clickbait score - title may be misleading' :
                    clickbaitScore > 40 ? 'Moderate clickbait elements detected' :
                    'Low clickbait score - title appears straightforward';
                document.getElementById('clickbait-methodology').textContent = 
                    'Clickbait detected through headline analysis, sensational language patterns, and title-content matching';
                break;
                
            case 'emotion':
                const emotionData = data.emotional_manipulation || {};
                const emotionScore = emotionData.score || (manipulationTactics?.length || 0) * 15;
                const emotionNeedle = document.getElementById('emotion-needle');
                const emotionAngle = -90 + Math.min(emotionScore * 1.8, 180);
                emotionNeedle.style.transform = `translateX(-50%) rotate(${emotionAngle}deg)`;
                
                document.getElementById('emotional-manipulation').innerHTML = `
                    <h5>Emotional Manipulation: <strong>${
                        emotionScore > 60 ? 'High' : emotionScore > 30 ? 'Medium' : 'Low'
                    }</strong> (${emotionScore}/100)</h5>
                    ${emotionData.techniques && emotionData.techniques.length > 0 ? `
                        <h6>Techniques Detected:</h6>
                        <ul>${emotionData.techniques.map(tech => `<li>${tech}</li>`).join('')}</ul>
                    ` : '<p>No specific emotional manipulation techniques identified</p>'}
                `;
                
                document.getElementById('emotion-explanation').textContent = 
                    emotionScore > 60 ? 'High emotional manipulation - article uses strong emotional triggers' :
                    emotionScore > 30 ? 'Moderate emotional language present' :
                    'Minimal emotional manipulation detected';
                document.getElementById('emotion-methodology').textContent = 
                    'Emotional content analyzed through sentiment analysis and psychological trigger detection';
                break;
                
            case 'diversity':
                const diversityData = data.source_diversity || {};
                const diversityScore = diversityData.score || 25;
                const diversityBar = document.getElementById('diversity-bar');
                diversityBar.style.width = diversityScore + '%';
                diversityBar.textContent = diversityScore + '%';
                
                document.getElementById('source-diversity').innerHTML = `
                    <h5>Source Diversity Score: <strong>${diversityScore}/100</strong></h5>
                    <p>Sources Referenced: <strong>${diversityData.sources_count || 1}</strong></p>
                    ${diversityScore < 50 ? `
                        <div class="alert alert-info mt-3">
                            <p><strong>Note:</strong> This is a single-article analysis. For comprehensive verification, 
                            consider checking multiple sources covering the same topic.</p>
                        </div>
                    ` : ''}
                    ${diversityData.missing_perspectives && diversityData.missing_perspectives.length > 0 ? `
                        <h6>Recommended Additional Perspectives:</h6>
                        <ul>${diversityData.missing_perspectives.map(p => `<li>${p}</li>`).join('')}</ul>
                    ` : ''}
                `;
                
                document.getElementById('diversity-explanation').textContent = 
                    'Source diversity measures how many different sources and perspectives are included';
                document.getElementById('diversity-methodology').textContent = 
                    'Analyzed by counting unique sources, quotes, and referenced materials within the article';
                break;
                
            case 'timeliness':
                const publishDate = data.article_info?.publish_date || data.article?.publish_date;
                const currentDate = new Date();
                
                document.getElementById('timeliness-check').innerHTML = `
                    <h5>Timeliness Assessment:</h5>
                    <ul>
                        <li>Article date: <strong>${publishDate || 'Unknown'}</strong></li>
                        <li>Analysis date: <strong>${currentDate.toLocaleDateString()}</strong></li>
                        <li>Source: <strong>${data.article_info?.domain || 'Unknown'}</strong></li>
                        ${publishDate ? `<li>Age: <strong>${calculateAge(publishDate)}</strong></li>` : ''}
                    </ul>
                    ${!publishDate ? `
                        <div class="alert alert-warning mt-3">
                            <p>Publication date not found. Consider the timeliness of this information carefully.</p>
                        </div>
                    ` : ''}
                `;
                
                document.getElementById('timeliness-explanation').textContent = 
                    publishDate ? 'Article date information helps assess relevance and currency of information' :
                    'Missing publication date makes it difficult to assess information currency';
                document.getElementById('timeliness-methodology').textContent = 
                    'Publication date extracted from article metadata and HTML markup';
                break;
                
            case 'ai':
                const aiData = data.ai_content_probability || {};
                const aiScore = aiData.score || 15;
                const aiBar = document.getElementById('ai-probability');
                setTimeout(() => {
                    aiBar.style.width = aiScore + '%';
                    aiBar.querySelector('.confidence-label').textContent = aiScore + '%';
                }, 300);
                
                document.getElementById('ai-patterns').innerHTML = `
                    <li><strong>AI Probability: ${
                        aiScore > 70 ? 'High' : aiScore > 40 ? 'Medium' : 'Low'
                    }</strong></li>
                    ${aiData.indicators && aiData.indicators.map(ind => 
                        `<li><i class="fas fa-${aiScore > 50 ? 'exclamation' : 'check'}-circle text-${
                            aiScore > 50 ? 'warning' : 'success'
                        } me-2"></i>${ind}</li>`
                    ).join('') || '<li>Natural writing patterns detected</li>'}
                `;
                
                document.getElementById('ai-explanation').textContent = 
                    aiData.explanation || `${
                        aiScore > 70 ? 'High' : aiScore > 40 ? 'Medium' : 'Low'
                    } probability of AI-generated content`;
                document.getElementById('ai-methodology').textContent = 
                    'AI detection through perplexity analysis, repetition patterns, and stylistic consistency checks';
                break;
        }
    }

    // Helper function to calculate article age
    function calculateAge(publishDate) {
        const published = new Date(publishDate);
        const now = new Date();
        const diffTime = Math.abs(now - published);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return '1 day ago';
        if (diffDays < 7) return `${diffDays} days ago`;
        if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
        if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
        return `${Math.floor(diffDays / 365)} years ago`;
    }

    // Animate trust meter with REAL score
    function animateTrustMeter(trustScore) {
        const trustMeter = document.querySelector('.trust-meter-fill');
        const trustScoreEl = document.getElementById('trust-score');
        const circumference = 2 * Math.PI * 90;
        const offset = circumference - (trustScore / 100) * circumference;
        
        // Set color based on REAL score
        let color = '#10b981'; // green
        if (trustScore < 60) color = '#ef4444'; // red
        else if (trustScore < 80) color = '#f59e0b'; // orange
        
        setTimeout(() => {
            trustMeter.style.stroke = color;
            trustMeter.style.strokeDashoffset = offset;
            
            // Animate number
            let current = 0;
            const interval = setInterval(() => {
                if (current < trustScore) {
                    current += 2;
                    trustScoreEl.textContent = Math.min(current, trustScore);
                } else {
                    clearInterval(interval);
                }
            }, 30);
        }, 100);
    }

    // Show error
    function showError(message) {
        const errorContainer = document.getElementById('error-container');
        const errorMessage = document.getElementById('error-message');
        
        // Convert newlines to <br> and bullet points to proper HTML
        let formattedMessage = message
            .replace(/\n/g, '<br>')
            .replace(/•/g, '<br>•');
        
        errorMessage.innerHTML = formattedMessage;
        errorContainer.style.display = 'block';
        
        // Hide results
        document.getElementById('results-section').style.display = 'none';
        
        // Scroll to error
        errorContainer.scrollIntoView({ behavior: 'smooth' });
    }

    // Retry analysis
    function retryAnalysis() {
        document.getElementById('error-container').style.display = 'none';
        analyzeArticle();
    }

    // Toggle dropdown
    function toggleDropdown(header) {
        const content = header.nextElementSibling;
        const isOpen = content.classList.contains('show');
        
        if (isOpen) {
            content.classList.remove('show');
            header.style.borderColor = 'transparent';
        } else {
            content.classList.add('show');
            header.style.borderColor = 'var(--primary-blue)';
        }
    }

    // Generate enhanced PDF report
    async function generatePDF() {
        if (!currentAnalysisResults) {
            alert('Please run an analysis first');
            return;
        }
        
        const btn = event.target;
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Generating...';
        btn.disabled = true;
        
        try {
            // Call your backend to generate PDF
            const response = await fetch('/api/generate-pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    analysis_type: 'news',
                    results: currentAnalysisResults
                })
            });
            
            if (!response.ok) {
                throw new Error('PDF generation failed');
            }
            
            // If backend returns PDF blob
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `news-analysis-${Date.now()}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            
        } catch (error) {
            console.error('PDF generation error:', error);
            // Fallback: Generate client-side PDF with enhanced results
            generateEnhancedClientSidePDF();
        } finally {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    }

    // Enhanced client-side PDF generation with full details
    function generateEnhancedClientSidePDF() {
        if (!currentAnalysisResults) {
            alert('Please run an analysis first');
            return;
        }
        
        const results = currentAnalysisResults;
        
        // Helper function to safely get nested values
        const safeGet = (obj, path, defaultValue = 'N/A') => {
            return path.split('.').reduce((o, p) => o?.[p], obj) || defaultValue;
        };
        
        // Create a new window with comprehensive results
        const printWindow = window.open('', '_blank');
        printWindow.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Comprehensive News Analysis Report - Facts & Fakes AI</title>
                <style>
                    @page { margin: 1in; }
                    body { 
                        font-family: Arial, sans-serif; 
                        line-height: 1.6;
                        color: #333;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 20px;
                    }
                    h1 { 
                        color: #4a90e2; 
                        border-bottom: 3px solid #4a90e2;
                        padding-bottom: 10px;
                    }
                    h2 { 
                        color: #2c3e50; 
                        margin-top: 30px;
                        border-bottom: 2px solid #e0e0e0;
                        padding-bottom: 8px;
                    }
                    h3 { 
                        color: #34495e;
                        margin-top: 20px;
                    }
                    .header {
                        text-align: center;
                        margin-bottom: 40px;
                    }
                    .logo {
                        font-size: 24px;
                        font-weight: bold;
                        color: #4a90e2;
                    }
                    .score-box {
                        background: #f8f9fa;
                        border: 2px solid #4a90e2;
                        border-radius: 10px;
                        padding: 20px;
                        text-align: center;
                        margin: 20px 0;
                    }
                    .trust-score {
                        font-size: 48px;
                        font-weight: bold;
                        color: ${results.trust_score >= 80 ? '#27ae60' : results.trust_score >= 60 ? '#f39c12' : '#e74c3c'};
                    }
                    .section {
                        margin-bottom: 30px;
                        padding: 20px;
                        background: #f8f9fa;
                        border-radius: 8px;
                        page-break-inside: avoid;
                    }
                    .alert {
                        padding: 15px;
                        border-radius: 5px;
                        margin: 15px 0;
                    }
                    .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
                    .alert-warning { background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }
                    .alert-danger { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
                    .claim-box {
                        background: white;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        padding: 15px;
                        margin: 10px 0;
                    }
                    .verdict {
                        display: inline-block;
                        padding: 5px 15px;
                        border-radius: 20px;
                        font-weight: bold;
                        margin: 5px 0;
                    }
                    .verdict-true { background: #d4edda; color: #155724; }
                    .verdict-false { background: #f8d7da; color: #721c24; }
                    .verdict-unverified { background: #fff3cd; color: #856404; }
                    .metric {
                        display: flex;
                        justify-content: space-between;
                        padding: 8px 0;
                        border-bottom: 1px solid #e0e0e0;
                    }
                    .metric:last-child { border-bottom: none; }
                    .footer {
                        margin-top: 50px;
                        padding-top: 20px;
                        border-top: 2px solid #e0e0e0;
                        text-align: center;
                        color: #666;
                        font-size: 12px;
                    }
                    ul { padding-left: 20px; }
                    li { margin: 5px 0; }
                    strong { color: #2c3e50; }
                    .progress-bar {
                        background: #e0e0e0;
                        height: 20px;
                        border-radius: 10px;
                        overflow: hidden;
                        margin: 10px 0;
                    }
                    .progress-fill {
                        height: 100%;
                        background: #4a90e2;
                        text-align: center;
                        color: white;
                        font-size: 12px;
                        line-height: 20px;
                    }
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="logo">Facts & Fakes AI</div>
                    <h1>Comprehensive News Analysis Report</h1>
                    <p>Generated: ${new Date().toLocaleString()}</p>
                    <p>Analysis ID: ${safeGet(results, 'analysis_id', 'AN-' + Date.now().toString(36).toUpperCase())}</p>
                </div>
                
                <div class="score-box">
                    <h2>Overall Trust Score</h2>
                    <div class="trust-score">${results.trust_score || 0}%</div>
                    <p>${results.trust_score >= 80 ? 'HIGH CREDIBILITY' : results.trust_score >= 60 ? 'MODERATE CREDIBILITY' : 'LOW CREDIBILITY'}</p>
                </div>
                
                <div class="section">
                    <h2>Executive Summary</h2>
                    <p>${safeGet(results, 'summary', 'Analysis completed')}</p>
                    ${results.recommendations && results.recommendations.length > 0 ? `
                        <h3>Key Recommendations:</h3>
                        <ul>
                            ${results.recommendations.map(rec => `<li>${rec}</li>`).join('')}
                        </ul>
                    ` : ''}
                </div>
                
                <div class="section">
                    <h2>Article Information</h2>
                    <div class="metric">
                        <strong>Title:</strong>
                        <span>${safeGet(results, 'article_info.title', 'Not provided')}</span>
                    </div>
                    <div class="metric">
                        <strong>Author:</strong>
                        <span>${safeGet(results, 'article_info.author', 'Unknown')}</span>
                    </div>
                    <div class="metric">
                        <strong>Source Domain:</strong>
                        <span>${safeGet(results, 'article_info.domain', 'Unknown')}</span>
                    </div>
                    <div class="metric">
                        <strong>Published Date:</strong>
                        <span>${safeGet(results, 'article_info.publish_date', 'Not available')}</span>
                    </div>
                    <div class="metric">
                        <strong>Analysis Date:</strong>
                        <span>${new Date().toLocaleDateString()}</span>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Credibility Scores</h2>
                    <div class="metric">
                        <strong>Trust Score:</strong>
                        <span>${results.trust_score || 0}/100</span>
                    </div>
                    <div class="metric">
                        <strong>Credibility Score:</strong>
                        <span>${Math.round((results.credibility_score || 0) * 100)}/100</span>
                    </div>
                    <div class="metric">
                        <strong>Factual Accuracy:</strong>
                        <span>${results.factual_accuracy ? Math.round(results.factual_accuracy * 100) : 'N/A'}/100</span>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Political Bias Analysis</h2>
                    ${results.bias_score !== 'N/A' && results.bias_score !== undefined ? `
                        <div class="alert ${Math.abs(results.bias_score) < 0.3 ? 'alert-success' : 'alert-warning'}">
                            <strong>Bias Score:</strong> ${results.bias_score.toFixed(2)} 
                            (${results.bias_score < -0.5 ? 'Far Left' :
                               results.bias_score < -0.2 ? 'Left-Leaning' :
                               results.bias_score < 0.2 ? 'Center/Neutral' :
                               results.bias_score < 0.5 ? 'Right-Leaning' : 'Far Right'})
                        </div>
                        <p><strong>Explanation:</strong> ${safeGet(results, 'bias_explanation', 'Bias analysis based on language patterns')}</p>
                        ${results.bias_examples && results.bias_examples.length > 0 ? `
                            <h3>Examples Found:</h3>
                            <ul>
                                ${results.bias_examples.map(ex => `<li>${ex}</li>`).join('')}
                            </ul>
                        ` : ''}
                    ` : '<p>Insufficient data to determine political bias</p>'}
                </div>
                
                <div class="section">
                    <h2>Fact-Checking Results</h2>
                    <p><strong>Claims Analyzed:</strong> ${results.fact_checks?.length || results.key_claims?.length || 0}</p>
                    ${results.fact_checks && results.fact_checks.length > 0 ? 
                        results.fact_checks.map((check, index) => {
                            if (typeof check === 'object' && check.verdict) {
                                return `
                                    <div class="claim-box">
                                        <h4>Claim ${index + 1}</h4>
                                        <p><strong>Statement:</strong> "${check.claim}"</p>
                                        <div class="verdict verdict-${check.verdict}">${check.verdict.toUpperCase()}</div>
                                        <p><strong>Explanation:</strong> ${check.explanation}</p>
                                        <p><strong>Confidence:</strong> ${check.confidence || 0}%</p>
                                        ${check.sources && check.sources.length > 0 ? 
                                            `<p><strong>Sources:</strong> ${check.sources.join(', ')}</p>` : ''}
                                    </div>
                                `;
                            }
                            return `<div class="claim-box"><p>${check}</p></div>`;
                        }).join('') : 
                        results.key_claims && results.key_claims.length > 0 ? `
                            <h3>Key Claims Identified:</h3>
                            <ul>
                                ${results.key_claims.map(claim => `<li>${typeof claim === 'object' ? claim.claim : claim}</li>`).join('')}
                            </ul>
                            <p><em>Note: These claims require external fact-checking for verification</em></p>
                        ` : '<p>No fact checks performed</p>'}
                </div>
                
                <div class="section">
                    <h2>Manipulation Tactics</h2>
                    ${results.manipulation_tactics && results.manipulation_tactics.length > 0 ? `
                        <div class="alert alert-warning">
                            <strong>${results.manipulation_tactics.length} manipulation tactics detected</strong>
                        </div>
                        <ul>
                            ${results.manipulation_tactics.map(tactic => {
                                if (typeof tactic === 'object') {
                                    return `<li><strong>${tactic.tactic}:</strong> ${tactic.description}${
                                        tactic.example ? ` (Example: "${tactic.example}")` : ''
                                    }</li>`;
                                }
                                return `<li>${tactic}</li>`;
                            }).join('')}
                        </ul>
                    ` : '<p>No manipulation tactics detected</p>'}
                </div>
                
                <div class="section">
                    <h2>Hidden Agenda Analysis</h2>
                    ${results.hidden_agenda && typeof results.hidden_agenda === 'object' ? `
                        <div class="alert ${results.hidden_agenda.detected ? 'alert-warning' : 'alert-success'}">
                            <strong>Hidden Agenda:</strong> ${results.hidden_agenda.detected ? 'DETECTED' : 'Not Detected'}
                        </div>
                        ${results.hidden_agenda.detected ? `
                            <p><strong>Type:</strong> ${results.hidden_agenda.type || 'Unknown'}</p>
                            <p><strong>Explanation:</strong> ${results.hidden_agenda.explanation}</p>
                            ${results.hidden_agenda.evidence && results.hidden_agenda.evidence.length > 0 ? `
                                <h3>Evidence:</h3>
                                <ul>
                                    ${results.hidden_agenda.evidence.map(e => `<li>${e}</li>`).join('')}
                                </ul>
                            ` : ''}
                        ` : ''}
                    ` : '<p>Hidden agenda analysis not available</p>'}
                </div>
                
                <div class="section">
                    <h2>Additional Analysis</h2>
                    
                    <h3>Clickbait Analysis</h3>
                    ${results.clickbait_analysis ? `
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${results.clickbait_analysis.score}%">
                                Clickbait Score: ${results.clickbait_analysis.score}%
                            </div>
                        </div>
                        ${results.clickbait_analysis.indicators?.length > 0 ? `
                            <ul>${results.clickbait_analysis.indicators.map(i => `<li>${i}</li>`).join('')}</ul>
                        ` : ''}
                    ` : '<p>Not analyzed</p>'}
                    
                    <h3>Emotional Manipulation</h3>
                    ${results.emotional_manipulation ? `
                        <p><strong>Score:</strong> ${results.emotional_manipulation.score}/100</p>
                        ${results.emotional_manipulation.techniques?.length > 0 ? `
                            <ul>${results.emotional_manipulation.techniques.map(t => `<li>${t}</li>`).join('')}</ul>
                        ` : ''}
                    ` : '<p>Not analyzed</p>'}
                    
                    <h3>Source Diversity</h3>
                    ${results.source_diversity ? `
                        <p><strong>Score:</strong> ${results.source_diversity.score}/100</p>
                        <p><strong>Sources Count:</strong> ${results.source_diversity.sources_count || 1}</p>
                        ${results.source_diversity.missing_perspectives?.length > 0 ? `
                            <p><strong>Missing Perspectives:</strong></p>
                            <ul>${results.source_diversity.missing_perspectives.map(p => `<li>${p}</li>`).join('')}</ul>
                        ` : ''}
                    ` : '<p>Not analyzed</p>'}
                    
                    <h3>AI Content Detection</h3>
                    ${results.ai_content_probability ? `
                        <p><strong>AI Probability:</strong> ${results.ai_content_probability.score}%</p>
                        <p>${results.ai_content_probability.explanation || 'Analysis based on writing patterns'}</p>
                    ` : '<p>Not analyzed</p>'}
                </div>
                
                <div class="footer">
                    <p>This report was generated by Facts & Fakes AI</p>
                    <p>Advanced news verification powered by artificial intelligence</p>
                    <p>For more information, visit factsandfakes.com</p>
                </div>
            </body>
            </html>
        `);
        
        printWindow.document.close();
        
        // Auto-trigger print dialog
        printWindow.onload = function() {
            printWindow.print();
        };
    }

    // Show analysis process modal
    function showAnalysisProcess() {
        const modal = document.getElementById('analysisProcessModal');
        if (modal) {
            // If Bootstrap is available
            if (typeof bootstrap !== 'undefined') {
                const bsModal = new bootstrap.Modal(modal);
                bsModal.show();
            } else {
                // Fallback
                modal.style.display = 'block';
                modal.classList.add('show');
            }
        }
    }

    // Show methodology
    function showMethodology() {
        showAnalysisProcess();
    }

    // Download full report
    async function downloadFullReport() {
        if (!currentAnalysisResults) {
            alert('Please run an analysis first');
            return;
        }
        
        // Same as generatePDF but with more comprehensive data
        generatePDF();
    }
    </script>
</body>
</html>
