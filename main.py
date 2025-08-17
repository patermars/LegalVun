import google.generativeai as genai
import pdfplumber
import json
import re
from flask import Flask, request, jsonify, render_template
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
    
    def split_into_clauses(self, text: str) -> List[str]:
        """Split document text into individual clauses"""
        # Split by common clause separators
        clauses = re.split(r'\n\s*\d+\.|(?:\n\s*[A-Z]\.)|(?:\n\s*\([a-z]\))', text)
        
        # Clean and filter clauses
        cleaned_clauses = []
        for clause in clauses:
            clause = clause.strip()
            if len(clause) > 50:  # Only keep substantial clauses
                cleaned_clauses.append(clause)
        
        # If we don't get good clause separation, split by paragraphs
        if len(cleaned_clauses) < 3:
            paragraphs = text.split('\n\n')
            cleaned_clauses = [p.strip() for p in paragraphs if len(p.strip()) > 50]
        
        return cleaned_clauses[:20]  # Limit to first 20 clauses for efficiency
    
    def analyze_single_clause(self, clause: str) -> Dict[str, Any]:
        """Analyze a single legal clause using Gemini AI"""
        prompt = f"""
        You are a legal expert specializing in consumer protection. Analyze this legal clause for potential exploitation against users.

        Clause: "{clause}"

        Please provide your analysis in the following JSON format:
        {{
            "simplified": "Plain English explanation of what this clause means",
            "risk_level": "safe|caution|exploitable",
            "risk_score": 1-10,
            "exploitation_potential": "Detailed explanation of how this could be used against a user",
            "real_world_impact": "Concrete examples of potential negative outcomes",
            "fairer_alternative": "Suggested rewrite that would be more balanced",
            "key_concerns": ["list", "of", "specific", "issues"]
        }}

        Focus on:
        - Unilateral rights granted to the company
        - Vague or ambiguous language
        - Waiver of user rights
        - Hidden obligations or fees
        - Unreasonable restrictions
        - Dispute resolution limitations
        """
        
        try:
            response = model.generate_content(prompt)
            # Clean the response text to extract JSON
            response_text = response.text.strip()
            
            # Try to extract JSON from the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                return json.loads(json_text)
            else:
                # Fallback if JSON parsing fails
                return self._create_fallback_analysis(clause, response_text)
                
        except Exception as e:
            print(f"Error analyzing clause: {str(e)}")
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
            
            # Split into clauses
            clauses = self.split_into_clauses(full_text)
            
            if not clauses:
                raise Exception("No analyzable clauses found in the document")
            
            # Analyze each clause
            clause_analyses = []
            for i, clause in enumerate(clauses[:10]):  # Limit to first 10 for demo
                print(f"Analyzing clause {i+1}/{min(len(clauses), 10)}...")
                analysis = self.analyze_single_clause(clause)
                analysis['original'] = clause
                analysis['clause_number'] = i + 1
                clause_analyses.append(analysis)
            
            # Calculate overall scores
            scores = self.calculate_overall_scores(clause_analyses)
            
            # Prepare results
            results = {
                "document_info": {
                    "total_clauses": len(clauses),
                    "analyzed_clauses": len(clause_analyses),
                    "text_length": len(full_text)
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
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "Legal Document Analyzer"})

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')
    # """Basic info endpoint"""
    # return jsonify({
    #     "service": "Legal Document Analyzer API",
    #     "version": "1.0",
    #     "endpoints": {
    #         "/analyze": "POST - Upload PDF for analysis",
    #         "/health": "GET - Health check"
    #     }
    # })

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
        print("📋 Upload PDFs to http://localhost:5000/analyze")
        print("💻 Open the HTML file in your browser to use the web interface")
        app.run(debug=True, host='0.0.0.0', port=5000)
