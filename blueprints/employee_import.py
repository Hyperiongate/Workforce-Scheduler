/* static/css/styles.css - Original Working Version */

/* CSS Variables */
:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --primary-light: #818cf8;
    --secondary: #10b981;
    --secondary-dark: #059669;
    --danger: #ef4444;
    --warning: #f59e0b;
    --info: #3b82f6;
    --dark: #1f2937;
    --gray: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-200: #e5e7eb;
    --gray-100: #f3f4f6;
    --gray-50: #f9fafb;
    --light-gray: #f3f4f6;
    --white: #ffffff;
    --shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    --radius: 8px;
    --transition: all 0.2s ease;
    
    /* Spacing */
    --space-xs: 0.25rem;
    --space-sm: 0.5rem;
    --space-md: 0.75rem;
    --space-lg: 1rem;
    --space-xl: 1.5rem;
}

/* Reset & Base */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    background: #f8fafc;
    color: var(--dark);
    line-height: 1.5;
    overflow-x: hidden;
}

/* Container */
.container {
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 var(--space-lg);
}

/* Header */
.header {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    color: white;
    padding: var(--space-md) 0;
    box-shadow: var(--shadow-sm);
    position: sticky;
    top: 0;
    z-index: 100;
}

.header-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-md);
}

.logo-section {
    display: flex;
    align-items: center;
    gap: var(--space-md);
}

.logo-icon {
    font-size: 1.5rem;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

.header h1 {
    font-size: 1.5rem;
    font-weight: 800;
    margin: 0;
}

.tagline {
    font-size: 0.75rem;
    opacity: 0.9;
    margin: 0;
}

.header-nav {
    display: flex;
    gap: var(--space-sm);
}

.nav-btn {
    padding: var(--space-sm) var(--space-lg);
    border: 1px solid rgba(255, 255, 255, 0.3);
    background: rgba(255, 255, 255, 0.1);
    color: white;
    border-radius: var(--radius);
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    font-size: 0.875rem;
}

.nav-btn:hover {
    background: rgba(255, 255, 255, 0.2);
    transform: translateY(-1px);
}

.nav-btn.premium {
    background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
    border-color: transparent;
}

/* Main Content */
.main-content {
    padding: var(--space-xl) 0;
    min-height: calc(100vh - 60px);
}

/* Input Section */
.input-section {
    margin-bottom: var(--space-xl);
}

.input-card {
    background: white;
    border-radius: var(--radius);
    padding: var(--space-xl);
    box-shadow: var(--shadow);
    animation: slideUp 0.5s ease-out;
}

@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.section-title {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: var(--space-xs);
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.section-subtitle {
    color: var(--gray);
    margin-bottom: var(--space-lg);
    font-size: 0.875rem;
}

/* Input Tabs */
.input-tabs {
    display: flex;
    gap: var(--space-sm);
    margin-bottom: var(--space-lg);
}

.mode-btn {
    flex: 1;
    padding: var(--space-md);
    border: 2px solid var(--light-gray);
    background: white;
    border-radius: var(--radius);
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-sm);
}

.mode-btn:hover {
    border-color: var(--primary-light);
}

.mode-btn.active {
    background: var(--primary);
    color: white;
    border-color: var(--primary);
}

/* Tab Explanation */
.tab-explanation {
    background: var(--light-gray);
    padding: var(--space-md);
    border-radius: var(--radius);
    margin-bottom: var(--space-md);
    font-size: 0.875rem;
    color: var(--gray);
}

.tab-explanation i {
    color: var(--info);
    margin-right: var(--space-sm);
}

/* Input Fields */
.input-group {
    display: flex;
    gap: var(--space-md);
}

.input-field {
    flex: 1;
    padding: var(--space-md) var(--space-lg);
    border: 2px solid var(--light-gray);
    border-radius: var(--radius);
    font-size: 1rem;
    transition: var(--transition);
}

.input-field:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.text-input {
    width: 100%;
    min-height: 120px;
    padding: var(--space-md) var(--space-lg);
    border: 2px solid var(--light-gray);
    border-radius: var(--radius);
    font-size: 1rem;
    resize: vertical;
    transition: var(--transition);
    font-family: inherit;
}

.text-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

/* Buttons */
.btn {
    padding: var(--space-md) var(--space-xl);
    border: none;
    border-radius: var(--radius);
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    display: inline-flex;
    align-items: center;
    gap: var(--space-sm);
}

.btn.btn-primary {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    color: white;
}

.btn.btn-secondary {
    background: white;
    color: var(--primary);
    border: 2px solid var(--primary);
}

.btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.analyze-btn {
    padding: var(--space-md) var(--space-xl);
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    color: white;
    border: none;
    border-radius: var(--radius);
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    align-items: center;
    gap: var(--space-sm);
}

.analyze-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.analyze-btn.full-width {
    width: 100%;
    justify-content: center;
}

/* Results Section */
.results-section {
    display: none;
    animation: fadeIn 0.5s ease-out;
}

.results-section.active {
    display: block;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Trust Summary Container */
.trust-summary-container {
    display: grid;
    grid-template-columns: 300px 1fr;
    gap: var(--space-lg);
    margin-bottom: var(--space-xl);
}

/* Trust Score Card */
.trust-score-card {
    background: white;
    border-radius: var(--radius);
    padding: var(--space-xl);
    box-shadow: var(--shadow);
    text-align: center;
}

.trust-gauge-container {
    position: relative;
    margin-bottom: var(--space-lg);
}

.trust-score-display {
    text-align: center;
}

#trustScoreNumber {
    font-size: 3rem;
    font-weight: 700;
    color: var(--primary);
    line-height: 1;
}

.trust-score-label {
    font-size: 0.875rem;
    color: var(--gray);
    margin-top: var(--space-xs);
}

.trust-level-indicator {
    padding: var(--space-sm) var(--space-lg);
    background: var(--light-gray);
    border-radius: var(--radius);
    display: inline-flex;
    align-items: center;
    gap: var(--space-sm);
}

.trust-level-icon {
    font-size: 1.25rem;
}

/* Conversational Summary Card */
.conversational-summary-card {
    background: white;
    border-radius: var(--radius);
    padding: var(--space-xl);
    box-shadow: var(--shadow);
}

.summary-header {
    font-size: 1.25rem;
    margin-bottom: var(--space-lg);
    color: var(--dark);
}

.summary-section {
    margin-bottom: var(--space-lg);
}

.summary-section:last-child {
    margin-bottom: 0;
}

/* Article Info Bar */
.article-info-bar {
    background: white;
    border-radius: var(--radius);
    padding: var(--space-lg);
    box-shadow: var(--shadow);
    margin-bottom: var(--space-xl);
}

#articleTitle {
    font-size: 1.25rem;
    margin-bottom: var(--space-md);
    color: var(--dark);
}

.article-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-lg);
}

.meta-item {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    font-size: 0.875rem;
    color: var(--gray);
}

.meta-item i {
    color: var(--primary);
}

/* Trust Breakdown Section */
.trust-breakdown-section {
    background: white;
    border-radius: var(--radius);
    padding: var(--space-xl);
    box-shadow: var(--shadow);
    margin-bottom: var(--space-xl);
}

.section-header {
    font-size: 1.25rem;
    margin-bottom: var(--space-lg);
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    color: var(--dark);
}

.breakdown-grid {
    display: grid;
    gap: var(--space-lg);
}

.breakdown-item {
    display: grid;
    gap: var(--space-sm);
}

.breakdown-label {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    font-weight: 600;
    color: var(--dark);
}

.breakdown-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
}

.breakdown-value {
    font-size: 1.125rem;
    font-weight: 700;
    color: var(--primary);
}

.breakdown-explanation {
    font-size: 0.875rem;
    color: var(--gray);
    line-height: 1.5;
}

.breakdown-bar {
    height: 8px;
    background: var(--light-gray);
    border-radius: 4px;
    overflow: hidden;
}

.breakdown-fill {
    height: 100%;
    transition: width 1s ease-out;
}

/* Services Section */
.services-section {
    background: white;
    border-radius: var(--radius);
    padding: var(--space-xl);
    box-shadow: var(--shadow);
    margin-bottom: var(--space-xl);
}

.services-progress {
    height: 4px;
    background: var(--light-gray);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: var(--space-xl);
}

.services-progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
    transition: width 0.5s ease;
}

/* Service Cards Grid */
.services-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: var(--space-lg);
}

/* Service Card Styles */
.service-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: var(--radius);
    padding: var(--space-lg);
    transition: var(--transition);
    cursor: pointer;
    text-decoration: none;
    color: inherit;
    display: block;
    position: relative;
    overflow: hidden;
}

.service-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow);
    border-color: var(--primary-light);
}

.service-card.loading {
    opacity: 0.6;
    pointer-events: none;
}

.service-card.pending {
    background: var(--gray-50);
}

.service-card-header {
    display: flex;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
}

.service-icon-wrapper {
    width: 48px;
    height: 48px;
    background: var(--light-gray);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.service-icon-wrapper i {
    font-size: 1.25rem;
    color: var(--primary);
}

.service-info {
    flex: 1;
}

.service-info h3 {
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: var(--space-xs);
    color: var(--dark);
}

.service-status {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    font-size: 0.75rem;
}

.service-status.complete {
    color: var(--secondary);
}

.service-status.pending {
    color: var(--gray);
}

.service-preview {
    font-size: 0.875rem;
    color: var(--gray-700);
    line-height: 1.5;
    margin-bottom: var(--space-md);
}

.service-metrics {
    display: flex;
    gap: var(--space-lg);
    margin-bottom: var(--space-md);
}

.metric-item {
    text-align: center;
}

.metric-value {
    display: block;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--primary);
    line-height: 1;
}

.metric-label {
    display: block;
    font-size: 0.75rem;
    color: var(--gray);
    margin-top: var(--space-xs);
}

.view-details-link {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    font-size: 0.875rem;
    color: var(--primary);
    font-weight: 600;
}

.view-details-link i {
    font-size: 0.75rem;
}

/* Loading state for services */
.services-loading {
    text-align: center;
    padding: var(--space-xl);
    color: var(--gray);
}

.services-loading i {
    font-size: 2rem;
    margin-bottom: var(--space-md);
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Results Actions */
.results-actions {
    display: flex;
    gap: var(--space-md);
    justify-content: center;
    margin-top: var(--space-xl);
}

/* Error Message */
.error-message {
    display: none;
    background: rgba(239, 68, 68, 0.1);
    color: var(--danger);
    padding: var(--space-md) var(--space-lg);
    border-radius: var(--radius);
    margin-top: var(--space-md);
    border: 1px solid rgba(239, 68, 68, 0.2);
    font-size: 0.875rem;
    position: fixed;
    bottom: var(--space-lg);
    right: var(--space-lg);
    max-width: 400px;
    box-shadow: var(--shadow);
    z-index: 1000;
}

.error-message.active {
    display: flex;
    align-items: center;
    gap: var(--space-md);
}

/* Loading Overlay */
.loading-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.loading-overlay.active {
    display: flex;
}

.loading-content {
    background: white;
    padding: var(--space-xl);
    border-radius: var(--radius);
    text-align: center;
    box-shadow: var(--shadow);
}

.loading-spinner {
    width: 60px;
    height: 60px;
    border: 4px solid rgba(99, 102, 241, 0.2);
    border-top-color: var(--primary);
    border-radius: 50%;
    margin: 0 auto var(--space-lg);
    animation: spin 1s linear infinite;
}

.loading-text {
    font-size: 1rem;
    color: var(--dark);
}

/* Key Findings */
.findings-grid {
    display: grid;
    gap: var(--space-md);
}

.finding-item {
    display: flex;
    gap: var(--space-md);
    padding: var(--space-md);
    border-radius: var(--radius);
    background: var(--gray-50);
}

.finding-item.finding-positive {
    background: rgba(16, 185, 129, 0.1);
    border-left: 3px solid var(--secondary);
}

.finding-item.finding-negative {
    background: rgba(239, 68, 68, 0.1);
    border-left: 3px solid var(--danger);
}

.finding-item.finding-warning {
    background: rgba(245, 158, 11, 0.1);
    border-left: 3px solid var(--warning);
}

.finding-icon {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.finding-content {
    flex: 1;
}

.finding-title {
    display: block;
    font-weight: 600;
    margin-bottom: var(--space-xs);
    color: var(--dark);
}

.finding-explanation {
    font-size: 0.875rem;
    color: var(--gray-700);
    line-height: 1.5;
    margin: 0;
}

.no-findings {
    text-align: center;
    color: var(--gray);
    padding: var(--space-xl);
}

/* Trust Level States */
.trust-level-indicator.very-high {
    background: rgba(16, 185, 129, 0.1);
    color: var(--secondary);
}

.trust-level-indicator.high {
    background: rgba(59, 130, 246, 0.1);
    color: var(--info);
}

.trust-level-indicator.moderate {
    background: rgba(245, 158, 11, 0.1);
    color: var(--warning);
}

.trust-level-indicator.low {
    background: rgba(239, 68, 68, 0.1);
    color: var(--danger);
}

.trust-level-indicator.very-low {
    background: rgba(239, 68, 68, 0.2);
    color: var(--danger);
}

/* Responsive Design */
@media (max-width: 768px) {
    .header-content {
        flex-direction: column;
        gap: var(--space-sm);
    }
    
    .trust-summary-container {
        grid-template-columns: 1fr;
    }
    
    .services-grid {
        grid-template-columns: 1fr;
    }
    
    .input-group {
        flex-direction: column;
    }
    
    .results-actions {
        flex-direction: column;
    }
    
    .results-actions .btn {
        width: 100%;
        justify-content: center;
    }
    
    .article-meta {
        flex-direction: column;
        gap: var(--space-sm);
    }
    
    .error-message {
        left: var(--space-lg);
        right: var(--space-lg);
        bottom: var(--space-lg);
        max-width: none;
    }
}

@media (min-width: 769px) and (max-width: 1024px) {
    .services-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}
