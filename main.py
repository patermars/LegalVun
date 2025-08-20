import google.generativeai as genai
import pdfplumber
import json
import re
from flask import Flask, request, jsonify, render_template, send_from_directory
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import tempfile
from typing import Dict, List, Any
import api_key

# 🔑 Configure with your Gemini API key
genai.configure(api_key=api_key.api_key)

# Load model
model = genai.GenerativeModel("gemini-1.5-flash")

app = Flask(__name__)
CORS(app)  # Enable CORS for web frontend

class LegalDocumentAnalyzer:
    def __init__(self):
        self.risk_patterns = {
            'unilateral_changes': r'(modify|change|alter).*terms.*without.*notice',
            'broad_license': r'perpetual|irrevocable|unlimited.*license',
            'no_warranty': r'as is.*without.*warrant',
            'liability_waiver': r'not liable|disclaim.*liability',
            'auto_renewal': r'automatic.*renew|auto.*renew',
            'data_collection': r'collect.*data|gather.*information',
            'termination_rights': r'terminate.*at.*discretion|suspend.*account'
        }
    
    def extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text content from PDF file"""
        text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            raise Exception(f"Error extracting PDF text: {str(e)}")
        
        return text.strip()
    
    def split_into_clauses(self, text: str) -> List[Dict[str, Any]]:
        """Split document text into individual clauses with position tracking"""
        # Split by common clause separators
        clauses = re.split(r'\n\s*\d+\.|(?:\n\s*[A-Z]\.)|(?:\n\s*\([a-z]\))', text)
        
        # Clean and filter clauses with position tracking
        cleaned_clauses = []
        current_position = 0
        
        for clause in clauses:
            clause = clause.strip()
            if len(clause) > 50:  # Only keep substantial clauses
                # Find the actual position in original text
                start_pos = text.find(clause, current_position)
                if start_pos != -1:
                    cleaned_clauses.append({
                        'text': clause,
                        'start_position': start_pos,
                        'end_position': start_pos + len(clause)
                    })
                    current_position = start_pos + len(clause)
        
        # If we don't get good clause separation, split by paragraphs
        if len(cleaned_clauses) < 3:
            paragraphs = text.split('\n\n')
            cleaned_clauses = []
            current_position = 0
            
            for p in paragraphs:
                p = p.strip()
                if len(p) > 50:
                    start_pos = text.find(p, current_position)
                    if start_pos != -1:
                        cleaned_clauses.append({
                            'text': p,
                            'start_position': start_pos,
                            'end_position': start_pos + len(p)
                        })
                        current_position = start_pos + len(p)
    
        return cleaned_clauses[:20]  # Limit to first 20 clauses for efficiency
    
    def analyze_single_clause(self, clause: str) -> Dict[str, Any]:
        """Analyze a single clause for potential risks"""
        prompt = f"""
        You are a legal expert specializing in consumer protection. Analyze this legal clause for potential exploitation against users.

        Clause: "{clause}"

        Please provide your analysis in the following JSON format:
        {{
            "simplified": "Plain English explanation of what this clause means (max 100 words)",
            "risk_level": "safe|caution|exploitable",
            "risk_score": 1-10,
            "exploitation_potential": "Detailed explanation of how this could be used against a user (max 150 words)",
            "real_world_impact": "Concrete, specific example of potential negative outcomes (max 80 words)",
            "fairer_alternative": "Suggested rewrite that would be more balanced (max 100 words)",
            "key_concerns": ["concern1", "concern2", "concern3"]
        }}

        Scoring Guide:
        - 1-3: Safe - Standard legal language, balanced terms
        - 4-6: Caution - Some concerning elements but not severely problematic
        - 7-10: Exploitable - Heavily favors company, potential for abuse

        Focus specifically on:
        - Unilateral rights granted to the company
        - Vague or ambiguous language that could be interpreted broadly
        - Complete waiver of user rights or protections
        - Hidden obligations, fees, or automatic renewals
        - Unreasonable restrictions on user actions
        - Dispute resolution limitations or forced arbitration
        - Data usage and privacy concerns
        - Termination clauses and account suspension rights

        Be concise but thorough in your analysis.
        """
        
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Try to parse JSON response
            try:
                # Extract JSON from response if it's wrapped in markdown or other text
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    analysis = json.loads(json_str)
                else:
                    # If no JSON found, try parsing the whole response
                    analysis = json.loads(response_text)
                
                # Validate required fields
                required_fields = ['simplified', 'risk_level', 'risk_score', 'exploitation_potential', 'fairer_alternative']
                for field in required_fields:
                    if field not in analysis:
                        analysis[field] = "Analysis not available"
                
                # Ensure risk_score is a number
                if not isinstance(analysis.get('risk_score'), (int, float)):
                    analysis['risk_score'] = 5
                
                # Ensure key_concerns is a list
                if not isinstance(analysis.get('key_concerns'), list):
                    analysis['key_concerns'] = ["General concerns identified"]
                
                return analysis
                
            except (json.JSONDecodeError, AttributeError) as json_error:
                print(f"JSON parsing error: {json_error}")
                print(f"Response text: {response_text}")
                return self._create_fallback_analysis(clause, f"JSON parsing failed: {str(json_error)}")
            
        except Exception as e:
            print(f"Error in AI analysis: {str(e)}")
            return self._create_fallback_analysis(clause, str(e))
    
    def _create_fallback_analysis(self, clause: str, error_info: str) -> Dict[str, Any]:
        """Create a basic analysis when AI fails"""
        risk_level = "caution"
        risk_score = 5
        
        # Basic pattern matching for risk assessment
        clause_lower = clause.lower()
        if any(pattern in clause_lower for pattern in ['without notice', 'at any time', 'sole discretion']):
            risk_level = "exploitable"
            risk_score = 8
        elif any(pattern in clause_lower for pattern in ['may', 'reserves the right', 'as is']):
            risk_level = "caution"
            risk_score = 6
        
        return {
            "simplified": "This clause contains legal language that may favor the company over users.",
            "risk_level": risk_level,
            "risk_score": risk_score,
            "exploitation_potential": "This clause could potentially be used in ways that disadvantage users.",
            "real_world_impact": "Users may face unexpected changes or limitations to their service.",
            "fairer_alternative": "A more balanced version would include user protections and clearer terms.",
            "key_concerns": ["Vague language", "Potential user disadvantage"]
        }
    
    def calculate_overall_scores(self, clause_analyses: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate overall document scores based on clause analyses"""
        if not clause_analyses:
            return {"overall": 5.0, "clarity": 5.0, "balance": 5.0, "enforceability": 5.0}
        
        risk_scores = [analysis.get('risk_score', 5) for analysis in clause_analyses]
        avg_risk = sum(risk_scores) / len(risk_scores)
        
        # Calculate specific metrics
        exploitable_count = sum(1 for analysis in clause_analyses if analysis.get('risk_level') == 'exploitable')
        caution_count = sum(1 for analysis in clause_analyses if analysis.get('risk_level') == 'caution')
        
        # Overall score (inverted - lower risk = higher score)
        overall_score = max(1.0, 10.0 - avg_risk)
        
        # Clarity score (based on vague language detection)
        vague_terms = sum(1 for analysis in clause_analyses if 'vague' in str(analysis.get('key_concerns', [])).lower())
        clarity_score = max(1.0, 10.0 - (vague_terms * 2))
        
        # Balance score (based on unilateral rights)
        balance_score = max(1.0, 10.0 - (exploitable_count * 1.5))
        
        # Enforceability score
        enforceability_score = max(1.0, overall_score - (caution_count * 0.5))
        
        return {
            "overall": round(overall_score, 1),
            "clarity": round(clarity_score, 1),
            "balance": round(balance_score, 1),
            "enforceability": round(enforceability_score, 1)
        }
    
    def analyze_document(self, file_path: str) -> Dict[str, Any]:
        """Main method to analyze entire document"""
        try:
            # Extract text from PDF
            full_text = self.extract_text_from_pdf(file_path)
            
            if not full_text.strip():
                raise Exception("No text could be extracted from the PDF")
            
            # Split into clauses with position tracking
            clause_objects = self.split_into_clauses(full_text)
            
            if not clause_objects:
                raise Exception("No analyzable clauses found in the document")
            
            # Analyze each clause
            clause_analyses = []
            for i, clause_obj in enumerate(clause_objects[:10]):  # Limit to first 10 for demo
                print(f"Analyzing clause {i+1}/{min(len(clause_objects), 10)}...")
                analysis = self.analyze_single_clause(clause_obj['text'])
                analysis['original'] = clause_obj['text']
                analysis['clause_number'] = i + 1
                analysis['start_position'] = clause_obj['start_position']
                analysis['end_position'] = clause_obj['end_position']
                clause_analyses.append(analysis)
            
            # Calculate overall scores
            scores = self.calculate_overall_scores(clause_analyses)
            
            # Prepare results
            results = {
                "document_info": {
                    "total_clauses": len(clause_objects),
                    "analyzed_clauses": len(clause_analyses),
                    "text_length": len(full_text),
                    "extracted_text": full_text,  # Include full text for frontend highlighting
                    "filename": os.path.basename(file_path) if hasattr(os.path, 'basename') else "document.pdf"
                },
                "scores": scores,
                "clause_analyses": clause_analyses,
                "summary": {
                    "high_risk_clauses": len([c for c in clause_analyses if c.get('risk_level') == 'exploitable']),
                    "medium_risk_clauses": len([c for c in clause_analyses if c.get('risk_level') == 'caution']),
                    "safe_clauses": len([c for c in clause_analyses if c.get('risk_level') == 'safe']),
                    "avg_risk_score": round(sum(c.get('risk_score', 5) for c in clause_analyses) / len(clause_analyses), 1)
                }
            }
            
            return results
            
        except Exception as e:
            raise Exception(f"Error analyzing document: {str(e)}")

# Initialize analyzer
analyzer = LegalDocumentAnalyzer()

@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    """API endpoint to analyze uploaded PDF"""
    try:
        # Check if file was uploaded
        if 'pdf' not in request.files:
            return jsonify({"error": "No PDF file uploaded"}), 400
        
        file = request.files['pdf']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        
        try:
            # Analyze the document
            results = analyzer.analyze_document(temp_path)
            return jsonify(results)
        
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    except Exception as e:
        print(f"Error in analyze_pdf: {str(e)}")  # Add logging
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "Legal Document Analyzer"})

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

def analyze_local_file(file_path: str):
    """Standalone function to analyze local PDF file"""
    try:
        results = analyzer.analyze_document(file_path)
        
        print("\n" + "="*80)
        print("🦅 LEGALHAWK - DOCUMENT ANALYSIS RESULTS")
        print("="*80)
        
        # Print scores
        scores = results['scores']
        print(f"\n📊 OVERALL EXPLOITABILITY SCORE: {scores['overall']}/10")
        print(f"   📈 Clarity Score: {scores['clarity']}/10")
        print(f"   ⚖️  Balance Score: {scores['balance']}/10")
        print(f"   📋 Enforceability Score: {scores['enforceability']}/10")
        
        # Print summary
        summary = results['summary']
        print(f"\n📋 SUMMARY:")
        print(f"   🔴 High Risk Clauses: {summary['high_risk_clauses']}")
        print(f"   🟡 Medium Risk Clauses: {summary['medium_risk_clauses']}")
        print(f"   🟢 Safe Clauses: {summary['safe_clauses']}")
        print(f"   📊 Average Risk Score: {summary['avg_risk_score']}/10")
        
        # Print detailed clause analysis
        print(f"\n🔍 DETAILED CLAUSE ANALYSIS:")
        print("-" * 80)
        
        for i, analysis in enumerate(results['clause_analyses'], 1):
            risk_emoji = "🔴" if analysis['risk_level'] == 'exploitable' else "🟡" if analysis['risk_level'] == 'caution' else "🟢"
            
            print(f"\n{risk_emoji} CLAUSE {i} - {analysis['risk_level'].upper()} (Risk Score: {analysis['risk_score']}/10)")
            print(f"\n📜 Original:")
            print(f"   {analysis['original'][:200]}{'...' if len(analysis['original']) > 200 else ''}")
            
            print(f"\n🔍 Simplified:")
            print(f"   {analysis['simplified']}")
            
            print(f"\n⚠️ Exploitation Potential:")
            print(f"   {analysis['exploitation_potential']}")
            
            print(f"\n💡 Fairer Alternative:")
            print(f"   {analysis['fairer_alternative']}")
            
            if analysis.get('key_concerns'):
                print(f"\n🎯 Key Concerns: {', '.join(analysis['key_concerns'])}")
            
            print("-" * 80)
        
        return results
        
    except Exception as e:
        print(f"Error analyzing document: {str(e)}")
        return None

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Command line usage - analyze local file
        file_path = sys.argv[1]
        if os.path.exists(file_path):
            analyze_local_file(file_path)
        else:
            print(f"Error: File '{file_path}' not found.")
    else:
        # Web server mode
        print("🦅 Starting LegalHawk API Server...")
        print("📋 Upload PDFs to http://localhost:5000")
        print("💻 Open the HTML file in your browser to use the web interface")
        app.run(debug=True, host='0.0.0.0', port=5000)
