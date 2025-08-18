let uploadedFile = null;

// File upload handling
const uploadZone = document.querySelector('.upload-zone');
const fileInput = document.getElementById('pdfInput');
const filePreview = document.getElementById('filePreview');
const analyzeBtn = document.getElementById('analyzeBtn');
const loadingSpinner = document.getElementById('loadingSpinner');
const resultsSection = document.getElementById('resultsSection');

// Drag and drop functionality
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type === 'application/pdf') {
        handleFileUpload(files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

function handleFileUpload(file) {
    uploadedFile = file;
    
    // Show file preview
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB`;
    filePreview.style.display = 'block';
    
    // Show analyze button with animation
    analyzeBtn.classList.add('visible');
}

async function analyzeDocument() {
    if (!uploadedFile) {
        alert('Please upload a PDF file first.');
        return;
    }

    // Show loading state
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';
    loadingSpinner.style.display = 'block';

    try {
        // Prepare form data for API call
        const formData = new FormData();
        formData.append('pdf', uploadedFile);

        // Call the Python backend API
        const response = await fetch('http://localhost:5000/analyze', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Analysis failed');
        }

        const results = await response.json();
        
        // Convert backend format to frontend format
        const formattedResults = {
            overallScore: results.scores.overall,
            clarityScore: results.scores.clarity,
            balanceScore: results.scores.balance,
            enforceabilityScore: results.scores.enforceability,
            clauses: results.clause_analyses.map(analysis => ({
                original: analysis.original,
                simplified: analysis.simplified,
                risk: analysis.risk_level,
                exploitation: analysis.exploitation_potential,
                suggestion: analysis.fairer_alternative,
                riskScore: analysis.risk_score,
                keyConcerns: analysis.key_concerns || [],
                realWorldImpact: analysis.real_world_impact
            })),
            documentInfo: results.document_info,
            summary: results.summary
        };

        displayResults(formattedResults);

    } catch (error) {
        console.error('Analysis error:', error);
        
        // Show user-friendly error message
        if (error.message.includes('Failed to fetch')) {
            alert('Could not connect to analysis server. Please make sure the Python backend is running on http://localhost:5000');
        } else {
            alert(`Error analyzing document: ${error.message}`);
        }
        
        // Fallback to demo mode with mock data
        console.log('Falling back to demo mode...');
        const mockResults = {
            overallScore: 7.2,
            clarityScore: 6.5,
            balanceScore: 8.0,
            enforceabilityScore: 7.1,
            clauses: [
                {
                    original: "The Company reserves the right to modify these terms at any time without prior notice.",
                    simplified: "The company can change these rules whenever they want without telling you first.",
                    risk: "exploitable",
                    exploitation: "The company could change important terms like pricing, cancellation policies, or user rights without warning, potentially trapping users in unfavorable conditions.",
                    suggestion: "The Company will provide at least 30 days written notice before any material changes to these terms take effect.",
                    riskScore: 9,
                    keyConcerns: ["Unilateral changes", "No notice period"],
                    realWorldImpact: "Users could face sudden price increases or service changes"
                },
                {
                    original: "Users grant the Company a perpetual, irrevocable license to any content uploaded.",
                    simplified: "Anything you upload becomes theirs forever, and you can't take it back.",
                    risk: "exploitable", 
                    exploitation: "Your personal photos, documents, or creative work could be used by the company indefinitely, even after you delete your account.",
                    suggestion: "Users grant the Company a limited license to content uploaded, which terminates when the user deletes their account or removes the content.",
                    riskScore: 8,
                    keyConcerns: ["Perpetual license", "No user control"],
                    realWorldImpact: "Loss of intellectual property rights"
                },
                {
                    original: "The service is provided 'as is' without warranties of any kind.",
                    simplified: "If the service doesn't work properly, that's your problem, not theirs.",
                    risk: "caution",
                    exploitation: "If the service fails and causes you losses (data loss, business interruption), the company won't take responsibility.",
                    suggestion: "The Company provides reasonable efforts to maintain service availability and will address service issues in a timely manner.",
                    riskScore: 6,
                    keyConcerns: ["No warranties", "Limited liability"],
                    realWorldImpact: "No recourse for service failures"
                }
            ],
            summary: {
                high_risk_clauses: 2,
                medium_risk_clauses: 1,
                safe_clauses: 0
            }
        };

        displayResults(mockResults);

    } finally {
        // Reset button state
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = '🔍 Analyze Document';
        loadingSpinner.style.display = 'none';
    }
}

function displayResults(results) {
    // Update scores
    document.getElementById('overallScore').textContent = results.overallScore.toFixed(1);
    document.getElementById('clarityScore').textContent = results.clarityScore.toFixed(1);
    document.getElementById('balanceScore').textContent = results.balanceScore.toFixed(1);
    document.getElementById('enforceabilityScore').textContent = results.enforceabilityScore.toFixed(1);

    // Generate clause analysis HTML
    const analysisHTML = results.clauses.map((clause, index) => {
        const riskClass = `risk-${clause.risk}`;
        const riskEmoji = clause.risk === 'safe' ? '🟢' : clause.risk === 'caution' ? '🟡' : '🔴';
        const riskScore = clause.riskScore || 'N/A';
        
        return `
            <div class="clause-analysis">
                <h4>Clause ${index + 1} 
                    <span class="risk-badge ${riskClass}">${riskEmoji} ${clause.risk.toUpperCase()}</span>
                    <span style="font-size: 0.9rem; color: #666; margin-left: 10px;">Risk Score: ${riskScore}/10</span>
                </h4>
                
                <h5>📜 Original Text:</h5>
                <div class="original-text">${clause.original}</div>
                
                <h5>🔍 Simplified:</h5>
                <div class="simplified-text">${clause.simplified}</div>
                
                <h5>⚠️ Potential Exploitation:</h5>
                <div class="exploit-warning">${clause.exploitation}</div>
                
                ${clause.realWorldImpact ? `
                    <h5>💥 Real World Impact:</h5>
                    <div class="exploit-warning" style="background: #ffebee; border-color: #f44336;">
                        ${clause.realWorldImpact}
                    </div>
                ` : ''}
                
                <h5>🛠️ Suggested Fix:</h5>
                <div class="suggestion">${clause.suggestion}</div>
                
                ${clause.keyConcerns && clause.keyConcerns.length > 0 ? `
                    <h5>🎯 Key Concerns:</h5>
                    <div style="margin: 10px 0;">
                        ${clause.keyConcerns.map(concern => 
                            `<span class="risk-badge risk-caution" style="margin: 2px;">${concern}</span>`
                        ).join('')}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');

    // Add document summary if available
    let summaryHTML = '';
    if (results.summary) {
        summaryHTML = `
            <div style="background: #f8f9fa; border-radius: 12px; padding: 25px; margin: 25px 0;">
                <h3 style="color: #333; margin-bottom: 15px;">📊 Document Summary</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; text-align: center;">
                    <div>
                        <div style="font-size: 2rem; color: #dc3545; font-weight: bold;">${results.summary.high_risk_clauses || 0}</div>
                        <div style="color: #666;">🔴 High Risk</div>
                    </div>
                    <div>
                        <div style="font-size: 2rem; color: #ffc107; font-weight: bold;">${results.summary.medium_risk_clauses || 0}</div>
                        <div style="color: #666;">🟡 Medium Risk</div>
                    </div>
                    <div>
                        <div style="font-size: 2rem; color: #28a745; font-weight: bold;">${results.summary.safe_clauses || 0}</div>
                        <div style="color: #666;">🟢 Safe</div>
                    </div>
                </div>
            </div>
        `;
    }

    document.getElementById('analysisResults').innerHTML = summaryHTML + analysisHTML;
    resultsSection.style.display = 'block';

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}