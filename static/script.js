let uploadedFile = null;
        let analysisResults = null;

        // File upload handling
        const uploadZone = document.querySelector('.upload-zone');
        const fileInput = document.getElementById('pdfInput');
        const filePreview = document.getElementById('filePreview');
        const analyzeBtn = document.getElementById('analyzeBtn');
        const loadingSpinner = document.getElementById('loadingSpinner');

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
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Analysis failed');
                }

                const results = await response.json();
                analysisResults = results;
                
                // Show report page instead of inline results
                showReportPage(results);

            } catch (error) {
                console.error('Analysis error:', error);
                
                // Show user-friendly error message
                if (error.message.includes('Failed to fetch')) {
                    alert('Could not connect to analysis server. Please make sure the Python backend is running.');
                } else {
                    alert(`Error analyzing document: ${error.message}`);
                }

            } finally {
                // Reset button state
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = '🔍 Analyze Document';
                loadingSpinner.style.display = 'none';
            }
        }

        function showReportPage(results) {
            // Hide main page and show report page
            document.getElementById('mainPage').style.display = 'none';
            document.getElementById('reportPage').style.display = 'block';
            
            // Update report subtitle
            document.getElementById('reportSubtitle').textContent = `Analysis of ${uploadedFile.name}`;
            
            // Update scores
            document.getElementById('mainScore').textContent = results.scores.overall.toFixed(1);
            document.getElementById('clarityScoreReport').textContent = results.scores.clarity.toFixed(1);
            document.getElementById('balanceScoreReport').textContent = results.scores.balance.toFixed(1);
            document.getElementById('enforceabilityScoreReport').textContent = results.scores.enforceability.toFixed(1);
            
            // Update summary stats
            document.getElementById('highRiskCount').textContent = results.summary.high_risk_clauses;
            document.getElementById('mediumRiskCount').textContent = results.summary.medium_risk_clauses;
            document.getElementById('safeCount').textContent = results.summary.safe_clauses;
            
            // Generate highlighted document
            generateHighlightedDocument(results);
            
            // Generate detailed findings
            generateDetailedFindings(results);
            
            // Scroll to top
            window.scrollTo(0, 0);
        }

        function generateHighlightedDocument(results) {
            const documentText = results.document_info.extracted_text || "Document text not available";
            const clauses = results.clause_analyses || [];
            
            let highlightedText = documentText;
            
            // Sort clauses by position (if available) to avoid overlapping replacements
            const sortedClauses = clauses.sort((a, b) => {
                return (b.start_position || 0) - (a.start_position || 0);
            });
            
            // Apply highlighting to each clause
            sortedClauses.forEach((clause, index) => {
                const riskClass = `risk-${clause.risk_level}`;
                const clauseId = `clause-${index}`;
                
                // Create highlighted span with tooltip
                const highlightedSpan = `<span class="highlighted-text ${riskClass}" 
                    data-clause-id="${clauseId}"
                    onmouseover="showTooltip(event, '${clauseId}')"
                    onmouseout="hideTooltip('${clauseId}')">
                    ${clause.original}
                    <div class="clause-tooltip" id="tooltip-${clauseId}">
                        <strong>Risk Level:</strong> ${clause.risk_level.toUpperCase()}<br>
                        <strong>Risk Score:</strong> ${clause.risk_score}/10<br>
                        <strong>Simplified:</strong> ${clause.simplified}<br>
                        <strong>Impact:</strong> ${clause.real_world_impact || 'See detailed analysis below'}
                    </div>
                </span>`;
                
                // Replace the original text with highlighted version
                highlightedText = highlightedText.replace(clause.original, highlightedSpan);
            });
            
            // Format the text with proper paragraphs
            highlightedText = highlightedText.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>');
            highlightedText = '<p>' + highlightedText + '</p>';
            
            document.getElementById('highlightedDocument').innerHTML = highlightedText;
        }

        function generateDetailedFindings(results) {
            const clauses = results.clause_analyses || [];
            
            const findingsHTML = clauses.map((clause, index) => {
                const riskClass = clause.risk_level === 'safe' ? 'safe' : 
                                clause.risk_level === 'caution' ? 'medium-risk' : 'high-risk';
                const riskEmoji = clause.risk_level === 'safe' ? '🟢' : 
                                clause.risk_level === 'caution' ? '🟡' : '🔴';
                
                return `
                    <div class="finding-item ${riskClass}">
                        <div class="finding-header">
                            <h3 class="finding-title">Clause ${index + 1}: ${clause.risk_level.charAt(0).toUpperCase() + clause.risk_level.slice(1)} Risk</h3>
                            <span class="risk-badge ${riskClass}">${riskEmoji} ${clause.risk_score}/10</span>
                        </div>
                        
                        <div class="finding-description">
                            <strong>Original Text:</strong><br>
                            "${clause.original}"
                        </div>
                        
                        <div class="finding-description">
                            <strong>Plain English:</strong><br>
                            ${clause.simplified}
                        </div>
                        
                        <div class="finding-impact">
                            <strong>⚠️ Potential Impact:</strong><br>
                            ${clause.exploitation_potential}
                            ${clause.real_world_impact ? `<br><strong>Real-world consequence:</strong> ${clause.real_world_impact}` : ''}
                        </div>
                        
                        <div class="finding-suggestion">
                            <strong>💡 Suggested Improvement:</strong><br>
                            ${clause.fairer_alternative}
                        </div>
                        
                        ${clause.key_concerns && clause.key_concerns.length > 0 ? `
                            <div style="margin-top: 15px;">
                                <strong>🎯 Key Concerns:</strong>
                                <div style="margin-top: 8px;">
                                    ${clause.key_concerns.map(concern => 
                                        `<span class="risk-badge ${riskClass}" style="margin: 2px 5px 2px 0; font-size: 0.75rem;">${concern}</span>`
                                    ).join('')}
                                </div>
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join('');
            
            document.getElementById('detailedFindings').innerHTML = findingsHTML;
        }

        function showTooltip(event, clauseId) {
            const tooltip = document.getElementById(`tooltip-${clauseId}`);
            if (tooltip) {
                tooltip.style.display = 'block';
                tooltip.style.left = '0px';
                tooltip.style.top = '100%';
            }
        }

        function hideTooltip(clauseId) {
            const tooltip = document.getElementById(`tooltip-${clauseId}`);
            if (tooltip) {
                tooltip.style.display = 'none';
            }
        }

        function showMainPage() {
            document.getElementById('reportPage').style.display = 'none';
            document.getElementById('mainPage').style.display = 'block';
            window.scrollTo(0, 0);
        }

        // Print report functionality
        function printReport() {
            window.print();
        }

        // Export report functionality (you can implement this later)
        function exportReport() {
            alert('Export functionality coming soon!');
        }