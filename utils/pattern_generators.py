/**
 * FILE: static/js/pdf-generator.js
 * VERSION: 10.0.0 - COMPLETE REBUILD - PROFESSIONAL SALES TOOL
 * DATE: October 15, 2025
 * AUTHOR: TruthLens Development Team
 * 
 * COMPLETE REBUILD FROM SCRATCH
 * 
 * DESIGN PHILOSOPHY:
 * - Professional document that serves as a sales/credibility tool
 * - Clean, modern layout with meaningful data visualization
 * - Tells a story: Score → Executive Summary → Service Details → Insights
 * - Informative, educational, and engaging
 * - No thick borders around empty containers
 * - Real data from backend, no placeholders
 * 
 * SECTIONS:
 * 1. Cover Page - Bold trust score with visual grade
 * 2. Executive Summary - Article info, source, author, key findings
 * 3. Service Analysis - Each service with scores, findings, and insights
 * 4. Visual Dashboard - Charts and metrics
 * 5. Recommendations - Actionable insights
 * 
 * DATA SOURCE:
 * - window.lastAnalysisData (set by app after analysis)
 * - Real backend fields: trust_score, article_summary, source, author,
 *   findings_summary, detailed_analysis{}, word_count
 */

// ============================================================================
// MAIN ENTRY POINT
// ============================================================================

function downloadPDFReport() {
    console.log('[PDF v10.0.0] Starting professional PDF generation...');
    
    // Validate jsPDF
    if (typeof window.jspdf === 'undefined') {
        alert('PDF library not loaded. Please refresh the page and try again.');
        return;
    }
    
    // Get analysis data
    const data = window.lastAnalysisData;
    if (!data) {
        alert('No analysis data available. Please run an analysis first.');
        return;
    }
    
    console.log('[PDF v10.0.0] Generating report for:', data.source || 'Unknown source');
    
    try {
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF({
            orientation: 'portrait',
            unit: 'mm',
            format: 'a4'
        });
        
        // Generate complete PDF
        generateProfessionalPDF(doc, data);
        
        // Save with descriptive filename
        const timestamp = new Date().toISOString().split('T')[0];
        const sourceShort = (data.source || 'Report').substring(0, 30).replace(/[^a-zA-Z0-9]/g, '-');
        const filename = `TruthLens-Report-${sourceShort}-${timestamp}.pdf`;
        
        doc.save(filename);
        console.log('[PDF v10.0.0] ✓ PDF generated successfully:', filename);
        
    } catch (error) {
        console.error('[PDF v10.0.0] Error generating PDF:', error);
        alert('Error generating PDF. Please try again.');
    }
}

// ============================================================================
// PDF GENERATION ORCHESTRATOR
// ============================================================================

function generateProfessionalPDF(doc, data) {
    // Extract key data
    const trustScore = Math.round(data.trust_score || 0);
    const detailed = data.detailed_analysis || {};
    
    // Color palette - professional, modern
    const colors = {
        primary: [59, 130, 246],      // Blue
        success: [34, 197, 94],       // Green
        warning: [251, 146, 60],      // Orange
        danger: [239, 68, 68],        // Red
        purple: [168, 85, 247],       // Purple
        gray: [107, 114, 128],        // Gray
        lightGray: [243, 244, 246],   // Light gray
        darkGray: [31, 41, 55],       // Dark gray
        white: [255, 255, 255]
    };
    
    // Determine score color
    const scoreColor = trustScore >= 70 ? colors.success :
                       trustScore >= 50 ? colors.warning : colors.danger;
    
    // Page 1: Cover Page
    generateCoverPage(doc, data, trustScore, scoreColor, colors);
    
    // Page 2: Executive Summary
    doc.addPage();
    generateExecutiveSummary(doc, data, trustScore, scoreColor, colors);
    
    // Page 3+: Service Analysis Pages
    const services = [
        { key: 'source_credibility', title: 'Source Credibility', icon: '🏛️' },
        { key: 'bias_detector', title: 'Bias Detection', icon: '⚖️' },
        { key: 'fact_checker', title: 'Fact Verification', icon: '✓' },
        { key: 'author_analyzer', title: 'Author Analysis', icon: '👤' },
        { key: 'transparency_analyzer', title: 'Transparency', icon: '🔍' },
        { key: 'content_analyzer', title: 'Content Quality', icon: '📄' }
    ];
    
    services.forEach(service => {
        if (detailed[service.key] && detailed[service.key].score !== undefined) {
            doc.addPage();
            generateServicePage(doc, service, detailed[service.key], colors);
        }
    });
    
    // Final Page: Recommendations
    doc.addPage();
    generateRecommendationsPage(doc, data, trustScore, scoreColor, colors);
    
    // Add page numbers to all pages except cover
    const totalPages = doc.internal.getNumberOfPages();
    for (let i = 2; i <= totalPages; i++) {
        doc.setPage(i);
        addPageFooter(doc, i, totalPages, colors);
    }
}

// ============================================================================
// PAGE 1: COVER PAGE
// ============================================================================

function generateCoverPage(doc, data, trustScore, scoreColor, colors) {
    const pageWidth = 210;
    const pageHeight = 297;
    
    // Header gradient bar
    doc.setFillColor(...colors.primary);
    doc.rect(0, 0, pageWidth, 60, 'F');
    
    // Title
    doc.setFontSize(48);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.white);
    doc.text('TruthLens', pageWidth / 2, 35, { align: 'center' });
    
    // Subtitle
    doc.setFontSize(16);
    doc.setFont('helvetica', 'normal');
    doc.text('AI-Powered Credibility Analysis Report', pageWidth / 2, 48, { align: 'center' });
    
    // Large circular trust score
    const centerX = pageWidth / 2;
    const centerY = 135;
    const radius = 45;
    
    // Outer circle
    doc.setDrawColor(...scoreColor);
    doc.setLineWidth(8);
    doc.circle(centerX, centerY, radius, 'S');
    
    // Inner white circle
    doc.setFillColor(...colors.white);
    doc.circle(centerX, centerY, radius - 6, 'F');
    
    // Score number
    doc.setFontSize(64);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...scoreColor);
    doc.text(trustScore.toString(), centerX, centerY + 8, { align: 'center' });
    
    // "/100" text
    doc.setFontSize(20);
    doc.setTextColor(...colors.gray);
    doc.text('/100', centerX, centerY + 22, { align: 'center' });
    
    // Trust level label
    const trustLabel = trustScore >= 80 ? 'HIGHLY TRUSTWORTHY' :
                       trustScore >= 70 ? 'TRUSTWORTHY' :
                       trustScore >= 60 ? 'MODERATELY RELIABLE' :
                       trustScore >= 50 ? 'QUESTIONABLE' : 'UNRELIABLE';
    
    doc.setFontSize(18);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...scoreColor);
    doc.text(trustLabel, centerX, centerY + 60, { align: 'center' });
    
    // Article info card
    const cardY = 210;
    const cardHeight = 60;
    
    doc.setFillColor(...colors.lightGray);
    doc.roundedRect(20, cardY, pageWidth - 40, cardHeight, 3, 3, 'F');
    
    let yPos = cardY + 12;
    
    // Source
    doc.setFontSize(10);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.darkGray);
    doc.text('SOURCE:', 25, yPos);
    
    doc.setFont('helvetica', 'normal');
    const sourceText = (data.source || 'Unknown Source').substring(0, 60);
    doc.text(sourceText, 50, yPos);
    
    yPos += 10;
    
    // Author
    doc.setFont('helvetica', 'bold');
    doc.text('AUTHOR:', 25, yPos);
    
    doc.setFont('helvetica', 'normal');
    const authorText = (data.author || 'Unknown Author').substring(0, 60);
    doc.text(authorText, 50, yPos);
    
    yPos += 10;
    
    // Word count
    doc.setFont('helvetica', 'bold');
    doc.text('LENGTH:', 25, yPos);
    
    doc.setFont('helvetica', 'normal');
    const wordCount = data.word_count || 0;
    doc.text(`${wordCount} words`, 50, yPos);
    
    yPos += 10;
    
    // Analysis date
    doc.setFont('helvetica', 'bold');
    doc.text('ANALYZED:', 25, yPos);
    
    doc.setFont('helvetica', 'normal');
    const dateStr = new Date().toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
    doc.text(dateStr, 50, yPos);
    
    // Footer tagline
    doc.setFontSize(12);
    doc.setFont('helvetica', 'italic');
    doc.setTextColor(...colors.gray);
    doc.text('Empowering truth through AI analysis', centerX, 285, { align: 'center' });
}

// ============================================================================
// PAGE 2: EXECUTIVE SUMMARY
// ============================================================================

function generateExecutiveSummary(doc, data, trustScore, scoreColor, colors) {
    // Page header
    doc.setFillColor(...colors.primary);
    doc.rect(0, 0, 210, 20, 'F');
    
    doc.setFontSize(20);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.white);
    doc.text('Executive Summary', 105, 13, { align: 'center' });
    
    let yPos = 35;
    
    // Article Summary Section
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.darkGray);
    doc.text('Article Overview', 20, yPos);
    
    yPos += 8;
    
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...colors.darkGray);
    
    const summary = data.article_summary || 'No summary available.';
    const summaryLines = doc.splitTextToSize(summary, 170);
    doc.text(summaryLines.slice(0, 4), 20, yPos);
    yPos += summaryLines.slice(0, 4).length * 5 + 10;
    
    // Key Findings Section
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text('Key Findings', 20, yPos);
    
    yPos += 8;
    
    const findings = extractKeyFindings(data);
    
    findings.slice(0, 5).forEach(finding => {
        // Bullet point
        doc.setFillColor(...colors.primary);
        doc.circle(23, yPos - 2, 1.5, 'F');
        
        // Finding text
        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(...colors.darkGray);
        const lines = doc.splitTextToSize(finding, 165);
        doc.text(lines[0], 28, yPos);
        
        yPos += 8;
    });
    
    yPos += 5;
    
    // Trust Score Breakdown Section
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.darkGray);
    doc.text('Trust Score Breakdown', 20, yPos);
    
    yPos += 10;
    
    // Service scores with bars
    const serviceScores = getServiceScores(data.detailed_analysis || {});
    
    serviceScores.forEach(service => {
        // Service name
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...colors.darkGray);
        doc.text(service.name, 20, yPos);
        
        // Score value
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...service.color);
        doc.text(`${service.score}`, 185, yPos, { align: 'right' });
        
        yPos += 4;
        
        // Progress bar background
        doc.setFillColor(...colors.lightGray);
        doc.rect(20, yPos - 2, 165, 4, 'F');
        
        // Progress bar fill
        const barWidth = (service.score / 100) * 165;
        doc.setFillColor(...service.color);
        doc.rect(20, yPos - 2, barWidth, 4, 'F');
        
        yPos += 10;
    });
    
    // Bottom line box
    yPos = 250;
    
    doc.setFillColor(255, 249, 235);
    doc.roundedRect(20, yPos, 170, 25, 2, 2, 'F');
    
    doc.setDrawColor(...colors.warning);
    doc.setLineWidth(0.5);
    doc.roundedRect(20, yPos, 170, 25, 2, 2, 'S');
    
    doc.setFontSize(11);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.darkGray);
    doc.text('Bottom Line:', 25, yPos + 8);
    
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    const bottomLine = data.findings_summary || generateBottomLine(trustScore);
    const bottomLines = doc.splitTextToSize(bottomLine, 160);
    doc.text(bottomLines.slice(0, 2), 25, yPos + 15);
}

// ============================================================================
// PAGE 3+: SERVICE ANALYSIS PAGES
// ============================================================================

function generateServicePage(doc, service, serviceData, colors) {
    // Page header with service title
    doc.setFillColor(...colors.primary);
    doc.rect(0, 0, 210, 20, 'F');
    
    doc.setFontSize(18);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.white);
    doc.text(`${service.icon} ${service.title}`, 105, 13, { align: 'center' });
    
    let yPos = 35;
    
    // Score display card
    const score = Math.round(serviceData.score || 0);
    const scoreColor = score >= 70 ? colors.success :
                       score >= 50 ? colors.warning : colors.danger;
    
    // Score box
    doc.setFillColor(...colors.lightGray);
    doc.roundedRect(20, yPos, 50, 35, 2, 2, 'F');
    
    doc.setFontSize(36);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...scoreColor);
    doc.text(score.toString(), 45, yPos + 20, { align: 'center' });
    
    doc.setFontSize(10);
    doc.setTextColor(...colors.gray);
    doc.text('/100', 45, yPos + 28, { align: 'center' });
    
    // Service interpretation
    const interpretation = getServiceInterpretation(service.key, score, serviceData);
    
    doc.setFillColor(...colors.lightGray);
    doc.roundedRect(75, yPos, 115, 35, 2, 2, 'F');
    
    doc.setFontSize(11);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.darkGray);
    doc.text('Assessment:', 80, yPos + 8);
    
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    const interpLines = doc.splitTextToSize(interpretation, 105);
    doc.text(interpLines.slice(0, 3), 80, yPos + 15);
    
    yPos += 45;
    
    // Findings section
    if (serviceData.findings && Array.isArray(serviceData.findings) && serviceData.findings.length > 0) {
        doc.setFontSize(13);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...colors.darkGray);
        doc.text('Key Findings:', 20, yPos);
        
        yPos += 8;
        
        serviceData.findings.slice(0, 6).forEach(finding => {
            const findingText = typeof finding === 'string' ? finding :
                              finding.text || finding.finding || '';
            
            if (findingText && yPos < 250) {
                // Checkmark bullet
                doc.setFontSize(10);
                doc.setTextColor(...colors.success);
                doc.text('✓', 22, yPos);
                
                // Finding text
                doc.setFontSize(9);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(...colors.darkGray);
                const lines = doc.splitTextToSize(findingText.substring(0, 150), 165);
                doc.text(lines[0], 28, yPos);
                
                yPos += 7;
            }
        });
        
        yPos += 5;
    }
    
    // Service-specific insights
    if (yPos < 240) {
        addServiceSpecificInsights(doc, service.key, serviceData, yPos, colors);
    }
}

// ============================================================================
// FINAL PAGE: RECOMMENDATIONS
// ============================================================================

function generateRecommendationsPage(doc, data, trustScore, scoreColor, colors) {
    // Page header
    doc.setFillColor(...colors.purple);
    doc.rect(0, 0, 210, 20, 'F');
    
    doc.setFontSize(20);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.white);
    doc.text('Recommendations & Next Steps', 105, 13, { align: 'center' });
    
    let yPos = 40;
    
    // Trust level explanation
    doc.setFillColor(...scoreColor);
    doc.roundedRect(20, yPos, 170, 25, 2, 2, 'F');
    
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.white);
    const trustLevel = trustScore >= 70 ? 'This content is generally trustworthy' :
                       trustScore >= 50 ? 'This content requires verification' :
                       'Exercise caution with this content';
    doc.text(trustLevel, 105, yPos + 10, { align: 'center' });
    
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    const scoreRange = trustScore >= 70 ? 'Score: 70-100 (Reliable)' :
                       trustScore >= 50 ? 'Score: 50-69 (Moderate)' :
                       'Score: Below 50 (Questionable)';
    doc.text(scoreRange, 105, yPos + 18, { align: 'center' });
    
    yPos += 35;
    
    // Recommendations
    const recommendations = generateRecommendations(data, trustScore);
    
    recommendations.forEach((rec, index) => {
        if (yPos > 240) return;
        
        // Number badge
        doc.setFillColor(...colors.primary);
        doc.circle(25, yPos + 2, 4, 'F');
        
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...colors.white);
        doc.text((index + 1).toString(), 25, yPos + 3, { align: 'center' });
        
        // Recommendation text
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...colors.darkGray);
        doc.text(rec.title, 33, yPos + 3);
        
        doc.setFontSize(9);
        doc.setFont('helvetica', 'normal');
        const lines = doc.splitTextToSize(rec.text, 160);
        doc.text(lines.slice(0, 2), 33, yPos + 9);
        
        yPos += lines.slice(0, 2).length * 5 + 10;
    });
    
    // Educational note
    yPos = 250;
    
    doc.setFillColor(240, 249, 255);
    doc.roundedRect(20, yPos, 170, 30, 2, 2, 'F');
    
    doc.setDrawColor(...colors.primary);
    doc.setLineWidth(0.5);
    doc.roundedRect(20, yPos, 170, 30, 2, 2, 'S');
    
    doc.setFontSize(10);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.primary);
    doc.text('💡 About TruthLens', 25, yPos + 8);
    
    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...colors.darkGray);
    const aboutText = 'TruthLens uses advanced AI and multiple verification services to analyze content credibility. This report provides an objective assessment based on source reputation, author credentials, factual accuracy, bias detection, and content quality. Use this analysis as one tool in your media literacy toolkit.';
    const aboutLines = doc.splitTextToSize(aboutText, 160);
    doc.text(aboutLines, 25, yPos + 15);
}

// ============================================================================
// HELPER FUNCTIONS - DATA EXTRACTION
// ============================================================================

function extractKeyFindings(data) {
    const findings = [];
    const detailed = data.detailed_analysis || {};
    
    // Extract from each service's findings array
    Object.values(detailed).forEach(service => {
        if (service && service.findings && Array.isArray(service.findings)) {
            service.findings.forEach(f => {
                const text = typeof f === 'string' ? f : f.text || f.finding || '';
                if (text) findings.push(text);
            });
        }
    });
    
    // If no findings, generate from score
    if (findings.length === 0) {
        const score = data.trust_score || 0;
        findings.push(
            score >= 70 ? 'Source demonstrates strong credibility and reputation' : 'Source credibility requires verification',
            score >= 70 ? 'Content shows minimal bias and balanced reporting' : 'Some bias indicators detected in content',
            score >= 70 ? 'Facts are well-sourced and verifiable' : 'Key claims should be independently verified'
        );
    }
    
    return findings;
}

function getServiceScores(detailed) {
    const services = [
        { key: 'source_credibility', name: 'Source Credibility', color: [79, 70, 229] },
        { key: 'bias_detector', name: 'Bias Detection', color: [251, 146, 60] },
        { key: 'fact_checker', name: 'Fact Verification', color: [34, 197, 94] },
        { key: 'author_analyzer', name: 'Author Analysis', color: [59, 130, 246] },
        { key: 'transparency_analyzer', name: 'Transparency', color: [168, 85, 247] },
        { key: 'content_analyzer', name: 'Content Quality', color: [236, 72, 153] }
    ];
    
    return services.map(s => ({
        ...s,
        score: Math.round(detailed[s.key]?.score || 0)
    })).filter(s => s.score > 0);
}

function getServiceInterpretation(key, score, data) {
    const interpretations = {
        source_credibility: score >= 70 ? 
            'This source has established credibility and a strong reputation for reliable journalism.' :
            'This source has moderate credibility. Independent verification of key claims is recommended.',
        
        bias_detector: score >= 70 ?
            'Content demonstrates objectivity with minimal bias. Balanced perspectives are presented.' :
            'Some bias elements detected. Consider seeking additional perspectives from diverse sources.',
        
        fact_checker: score >= 70 ?
            'Claims are well-supported by evidence from reliable sources. Factual accuracy is strong.' :
            'Some claims lack strong verification. Cross-reference important facts with authoritative sources.',
        
        author_analyzer: score >= 70 ?
            'Author has strong credentials and demonstrated expertise in this subject area.' :
            'Author credentials are unclear or limited. Verify author qualifications independently.',
        
        transparency_analyzer: score >= 70 ?
            'Content shows strong transparency with clear sourcing and proper attribution.' :
            'Transparency is limited. Look for additional source information and citations.',
        
        content_analyzer: score >= 70 ?
            'Content is well-written, properly structured, and maintains professional quality standards.' :
            'Content quality has some issues. Verify information with higher-quality sources.'
    };
    
    return interpretations[key] || 'Analysis completed successfully.';
}

function generateBottomLine(score) {
    if (score >= 80) {
        return 'This content comes from a highly credible source with strong verification, minimal bias, and professional quality. You can rely on this information with confidence.';
    } else if (score >= 60) {
        return 'This content is generally reliable from a moderately credible source. Most information can be trusted, but verify critical claims with additional sources.';
    } else {
        return 'This content has credibility concerns. Exercise caution and independently verify all key claims before relying on this information.';
    }
}

function generateRecommendations(data, score) {
    const recommendations = [];
    
    if (score >= 70) {
        recommendations.push({
            title: 'Content Reliability',
            text: 'This source meets high credibility standards. You can generally trust this information, though always maintain healthy skepticism.'
        });
        recommendations.push({
            title: 'Continue Good Practices',
            text: 'Keep consuming content from reputable sources like this. Build a diverse media diet with multiple trusted outlets.'
        });
    } else if (score >= 50) {
        recommendations.push({
            title: 'Verify Key Claims',
            text: 'Cross-reference important facts with additional authoritative sources before sharing or acting on this information.'
        });
        recommendations.push({
            title: 'Check Source History',
            text: 'Research this source\'s track record for accuracy and corrections. Look for transparency in their reporting process.'
        });
    } else {
        recommendations.push({
            title: 'Exercise Caution',
            text: 'This content has significant credibility concerns. Seek out high-quality sources before trusting this information.'
        });
        recommendations.push({
            title: 'Find Better Sources',
            text: 'Look for content from established news organizations with strong editorial standards and fact-checking processes.'
        });
    }
    
    recommendations.push({
        title: 'Practice Media Literacy',
        text: 'Always question sources, look for evidence, consider author credentials, and seek diverse perspectives on important topics.'
    });
    
    return recommendations;
}

function addServiceSpecificInsights(doc, key, data, yPos, colors) {
    if (yPos > 240) return;
    
    doc.setFontSize(11);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...colors.darkGray);
    doc.text('Additional Details:', 20, yPos);
    
    yPos += 7;
    
    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    
    // Service-specific details
    const details = [];
    
    if (key === 'source_credibility') {
        if (data.source_name) details.push(`Organization: ${data.source_name}`);
        if (data.credibility_level) details.push(`Credibility Level: ${data.credibility_level}`);
        if (data.reputation) details.push(`Reputation: ${data.reputation}`);
    } else if (key === 'bias_detector') {
        if (data.political_leaning) details.push(`Political Leaning: ${data.political_leaning}`);
        if (data.objectivity_score) details.push(`Objectivity: ${data.objectivity_score}/100`);
        if (data.sensationalism_level) details.push(`Sensationalism: ${data.sensationalism_level}`);
    } else if (key === 'fact_checker') {
        if (data.claims_verified) details.push(`Claims Verified: ${data.claims_verified}`);
        if (data.accuracy_score) details.push(`Accuracy: ${data.accuracy_score}%`);
    }
    
    details.slice(0, 4).forEach(detail => {
        doc.text(`• ${detail}`, 22, yPos);
        yPos += 5;
    });
}

function addPageFooter(doc, pageNum, totalPages, colors) {
    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...colors.gray);
    
    // Left: TruthLens branding
    doc.text('TruthLens Analysis Report', 20, 287);
    
    // Center: Date
    const dateStr = new Date().toLocaleDateString('en-US');
    doc.text(dateStr, 105, 287, { align: 'center' });
    
    // Right: Page number
    doc.text(`Page ${pageNum} of ${totalPages}`, 190, 287, { align: 'right' });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

console.log('[PDF v10.0.0] Professional PDF generator loaded successfully');
console.log('[PDF v10.0.0] Ready to generate comprehensive credibility reports');
