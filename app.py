from flask import Flask, request, jsonify
from pydantic import Field, BaseModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os
import yaml
import json
from werkzeug.utils import secure_filename
from generate_cv import McKinseyCVGenerator
import tempfile
import uuid

app = Flask(__name__)
load_dotenv()

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Define structured output schemas
class ScraperModel(BaseModel):
    job_description: str = Field(description="Extracted job description")
    skills: list[str] = Field(description="Skills extracted for the job")

class ResumeModel(BaseModel):
    personal_info: dict = Field(description="Personal information")
    experience: list = Field(description="Work experience")
    education: list = Field(description="Education details")
    skills: dict = Field(description="Skills organized by categories")
    projects: list = Field(description="Projects")
    certifications: list = Field(description="Certifications")
    extracurriculars: list = Field(description="Extracurricular activities")

class CompatibilityAnalysisModel(BaseModel):
    match_score: float = Field(description="Resume match score (0-100)")
    strengths: list[str] = Field(description="Matching strengths")
    missing_skills: list[str] = Field(description="Missing skills")
    recommendations: list[str] = Field(description="Improvement recommendations")

# In-memory storage for demo purposes
# TODO: Replace with proper database (SQLite/PostgreSQL)
# Consider using SQLAlchemy with SQLite for development or PostgreSQL for production
# You'll need to create tables for users, resumes, and resume_versions
user_data = {}
resume_versions = {}

# Load API keys from .env
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

# Utility functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_resume(file_path):
    """
    Extract resume data from uploaded file
    TODO: Implement proper resume parsing for different file formats
    - PDF parsing using PyPDF2 or pdfplumber
    - DOCX parsing using python-docx
    - Text file parsing
    
    For now, returns a sample structure that matches the ResumeModel schema.
    You need to implement actual file parsing logic here.
    """
    # TODO: Implement actual file parsing
    # This is a placeholder that returns sample data
    # You should replace this with actual parsing logic based on file type
    
    file_extension = file_path.split('.')[-1].lower()
    
    if file_extension == 'pdf':
        # TODO: Use PyPDF2 or pdfplumber to extract text from PDF
        # Then use LLM to parse the extracted text into structured data
        pass
    elif file_extension in ['docx', 'doc']:
        # TODO: Use python-docx to extract text from Word documents
        # Then use LLM to parse the extracted text into structured data
        pass
    
    # Placeholder return - replace with actual parsed data
    return {
        'personal_info': {
            'name': 'Sample Name',
            'email': 'sample@email.com',
            'phone': '+1234567890'
        },
        'experience': [],
        'education': [],
        'skills': {'categories': []},
        'projects': [],
        'certifications': [],
        'extracurriculars': []
    }

def resume_to_yaml(resume_data):
    """
    Convert extracted resume data to YAML format
    TODO: Implement proper YAML conversion with validation
    
    This function should validate the resume data structure and convert it to YAML.
    You might want to add validation to ensure all required fields are present.
    """
    # TODO: Add validation logic here
    # Ensure the resume_data matches the expected ResumeModel schema
    
    try:
        # Convert to YAML string
        yaml_string = yaml.dump(resume_data, default_flow_style=False, allow_unicode=True)
        return yaml_string
    except Exception as e:
        # TODO: Handle conversion errors appropriately
        raise ValueError(f"Failed to convert resume data to YAML: {str(e)}")


@app.route("/")
def home():
    return "Everything Working"

@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    """
    Upload and process resume file
    Returns: YAML formatted resume data
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    user_id = request.form.get('user_id', str(uuid.uuid4()))
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            # Extract resume data
            resume_data = extract_resume(file_path)
            if not resume_data:
                return jsonify({"error": "Failed to extract resume data"}), 500
            
            # Convert to YAML
            yaml_data = resume_to_yaml(resume_data)
            if not yaml_data:
                return jsonify({"error": "Failed to convert resume to YAML"}), 500
            
            # Store user data
            user_data[user_id] = {
                'original_resume': yaml_data,
                'upload_date': str(uuid.uuid4()),  # TODO: Use proper datetime
                'file_path': file_path
            }
            
            # Clean up uploaded file
            os.remove(file_path)
            
            return jsonify({
                "message": "Resume uploaded and processed successfully",
                "user_id": user_id,
                "resume_data": yaml_data
            })
            
        except Exception as e:
            # Clean up file on error
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({"error": f"Processing failed: {str(e)}"}), 500
    
    return jsonify({"error": "Invalid file type"}), 400

@app.route("/api/job-description", methods=["POST"])
def extract_job_description():
    """
    Function to extract job description and skills required from a webpage

    Returns:
        job_description (str): The extracted job description
        skills_required (list(str)): The extracted skills 
    """
    data = request.get_json()
    url = data.get("url")
    
    if not url:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    try:
        loader = WebBaseLoader(url)
        docs = loader.load()
    except Exception as e:
        return jsonify({"error": f"Failed to load content from URL: {str(e)}"}), 500

    extraction_system_prompt = """
        You are a job listing parser. Carefully extract the **entire job description**. 
        Also extract the **required skills** explicitly mentioned in the text.
    """
    jd_extraction_prompt = ChatPromptTemplate.from_messages([
        ("system", extraction_system_prompt),
        ("human", "{docs}")
    ])

    llm = ChatGroq(model="llama-3.3-70b-versatile") 
    jd_extraction_chain = jd_extraction_prompt | llm.with_structured_output(ScraperModel)

    try:
        response = jd_extraction_chain.invoke({"docs": docs[0].page_content})
        return jsonify({
            "job_description": response.job_description,
            "skills": response.skills
        })
    except Exception as e:
        return jsonify({"error": f"LLM parsing failed: {str(e)}"}), 500
    
@app.route("/api/analyze-compatibility", methods=["POST"])
def analyze_compatibility():
    """
    Analyze compatibility between resume and job description
    Returns: Match score, strengths, missing skills, and recommendations
    """
    data = request.get_json()
    user_id = data.get("user_id")
    job_description = data.get("job_description")
    job_skills = data.get("skills", [])
    
    if not user_id or not job_description:
        return jsonify({"error": "Missing user_id or job_description"}), 400
    
    if user_id not in user_data:
        return jsonify({"error": "User not found. Please upload resume first."}), 404
    
    try:
        resume_data = user_data[user_id]['original_resume']
        
        # Create analysis prompt
        analysis_prompt = f"""
        Analyze the compatibility between this resume and job description.
        
        Resume Data:
        {yaml.dump(resume_data, default_flow_style=False)}
        
        Job Description:
        {job_description}
        
        Required Skills:
        {', '.join(job_skills)}
        
        Provide a detailed analysis including:
        1. Match score (0-100)
        2. Key strengths that match the job requirements
        3. Missing skills that should be added
        4. Specific recommendations for improvement
        """
        
        llm = ChatGroq(model="llama-3.3-70b-versatile")
        analysis_chain = llm.with_structured_output(CompatibilityAnalysisModel)
        
        response = analysis_chain.invoke(analysis_prompt)
        
        return jsonify({
            "match_score": response.match_score,
            "strengths": response.strengths,
            "missing_skills": response.missing_skills,
            "recommendations": response.recommendations
        })
        
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

@app.route("/api/optimize-resume", methods=["POST"])
def optimize_resume():
    """
    Optimize resume based on job description and additional information
    Returns: Optimized YAML resume data
    """
    data = request.get_json()
    user_id = data.get("user_id")
    job_description = data.get("job_description")
    job_skills = data.get("skills", [])
    additional_info = data.get("additional_info", {})
    
    if not user_id or not job_description:
        return jsonify({"error": "Missing user_id or job_description"}), 400
    
    if user_id not in user_data:
        return jsonify({"error": "User not found. Please upload resume first."}), 404
    
    try:
        original_resume = user_data[user_id]['original_resume']
        
        # Create optimization prompt
        optimization_prompt = f"""
        Optimize this resume for the given job description by:
        1. Highlighting relevant skills and experiences
        2. Adding missing skills from the job requirements
        3. Improving bullet points to match job needs
        4. Incorporating additional information provided
        
        Original Resume:
        {yaml.dump(original_resume, default_flow_style=False)}
        
        Job Description:
        {job_description}
        
        Required Skills:
        {', '.join(job_skills)}
        
        Additional Information:
        {json.dumps(additional_info, indent=2)}
        
        Return the optimized resume in the same YAML structure.
        """
        
        llm = ChatGroq(model="llama-3.3-70b-versatile")
        optimization_chain = llm.with_structured_output(ResumeModel)
        
        optimized_resume = optimization_chain.invoke(optimization_prompt)
        
        # Store optimized version
        version_id = str(uuid.uuid4())
        if user_id not in resume_versions:
            resume_versions[user_id] = {}
        resume_versions[user_id][version_id] = {
            'resume_data': optimized_resume.dict(),
            'job_description': job_description,
            'created_date': str(uuid.uuid4())  # TODO: Use proper datetime
        }
        
        return jsonify({
            "message": "Resume optimized successfully",
            "version_id": version_id,
            "optimized_resume": optimized_resume.dict()
        })
        
    except Exception as e:
        return jsonify({"error": f"Optimization failed: {str(e)}"}), 500

@app.route("/api/generate-resume", methods=["POST"])
def generate_resume():
    """
    Generate final resume document (PDF/DOCX) from optimized YAML data
    Returns: Download link for generated resume
    """
    data = request.get_json()
    user_id = data.get("user_id")
    version_id = data.get("version_id")
    format_type = data.get("format", "docx")  # docx or pdf
    
    if not user_id or not version_id:
        return jsonify({"error": "Missing user_id or version_id"}), 400
    
    if user_id not in resume_versions or version_id not in resume_versions[user_id]:
        return jsonify({"error": "Resume version not found"}), 404
    
    try:
        resume_data = resume_versions[user_id][version_id]['resume_data']
        
        # Generate filename
        filename = f"optimized_resume_{version_id[:8]}.{format_type}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Use McKinseyCVGenerator from generate_cv.py
        cv_generator = McKinseyCVGenerator(
            config=resume_data,
            output_filename=output_path
        )
        cv_generator.build()
        cv_generator.save()
        
        # TODO: Implement proper file serving and cleanup
        # For now, return the file path
        return jsonify({
            "message": "Resume generated successfully",
            "download_url": f"/download/{filename}",
            "filename": filename
        })
        
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500

@app.route("/api/user-resumes/<user_id>", methods=["GET"])
def get_user_resumes(user_id):
    """
    Get all resume versions for a user
    """
    if user_id not in user_data:
        return jsonify({"error": "User not found"}), 404
    
    versions = resume_versions.get(user_id, {})
    return jsonify({
        "user_id": user_id,
        "original_resume": user_data[user_id]['original_resume'],
        "versions": versions
    })

@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    """
    Download generated resume file
    TODO: Implement proper file serving with authentication
    """
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        # TODO: Use Flask's send_file for proper file serving
        return jsonify({"message": f"File {filename} ready for download"})
    else:
        return jsonify({"error": "File not found"}), 404

# Chrome Extension Integration Endpoints
@app.route("/api/extension/analyze", methods=["POST"])
def extension_analyze():
    """
    Chrome extension endpoint for quick compatibility analysis
    Combines job description extraction and compatibility analysis
    """
    data = request.get_json()
    url = data.get("url")
    user_id = data.get("user_id")
    
    if not url or not user_id:
        return jsonify({"error": "Missing url or user_id"}), 400
    
    if user_id not in user_data:
        return jsonify({"error": "User not found. Please upload resume first."}), 404
    
    try:
        # Extract job description from URL
        loader = WebBaseLoader(url)
        docs = loader.load()
        
        extraction_system_prompt = """
            You are a job listing parser. Carefully extract the **entire job description**. 
            Also extract the **required skills** explicitly mentioned in the text.
        """
        jd_extraction_prompt = ChatPromptTemplate.from_messages([
            ("system", extraction_system_prompt),
            ("human", "{docs}")
        ])
        
        llm = ChatGroq(model="llama-3.3-70b-versatile")
        jd_extraction_chain = jd_extraction_prompt | llm.with_structured_output(ScraperModel)
        
        job_data = jd_extraction_chain.invoke({"docs": docs[0].page_content})
        
        # Perform compatibility analysis
        resume_data = user_data[user_id]['original_resume']
        
        analysis_prompt = f"""
        Analyze the compatibility between this resume and job description.
        
        Resume Data:
        {yaml.dump(resume_data, default_flow_style=False)}
        
        Job Description:
        {job_data.job_description}
        
        Required Skills:
        {', '.join(job_data.skills)}
        
        Provide a detailed analysis including:
        1. Match score (0-100)
        2. Key strengths that match the job requirements
        3. Missing skills that should be added
        4. Specific recommendations for improvement
        """
        
        analysis_chain = llm.with_structured_output(CompatibilityAnalysisModel)
        analysis_result = analysis_chain.invoke(analysis_prompt)
        
        return jsonify({
            "job_description": job_data.job_description,
            "skills": job_data.skills,
            "match_score": analysis_result.match_score,
            "strengths": analysis_result.strengths,
            "missing_skills": analysis_result.missing_skills,
            "recommendations": analysis_result.recommendations
        })
        
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

@app.route("/api/extension/optimize", methods=["POST"])
def extension_optimize():
    """
    Chrome extension endpoint for quick resume optimization
    """
    data = request.get_json()
    user_id = data.get("user_id")
    job_description = data.get("job_description")
    job_skills = data.get("skills", [])
    
    if not user_id or not job_description:
        return jsonify({"error": "Missing user_id or job_description"}), 400
    
    if user_id not in user_data:
        return jsonify({"error": "User not found. Please upload resume first."}), 404
    
    try:
        original_resume = user_data[user_id]['original_resume']
        
        optimization_prompt = f"""
        Optimize this resume for the given job description by:
        1. Highlighting relevant skills and experiences
        2. Adding missing skills from the job requirements
        3. Improving bullet points to match job needs
        
        Original Resume:
        {yaml.dump(original_resume, default_flow_style=False)}
        
        Job Description:
        {job_description}
        
        Required Skills:
        {', '.join(job_skills)}
        
        Return the optimized resume in the same YAML structure.
        """
        
        llm = ChatGroq(model="llama-3.3-70b-versatile")
        optimization_chain = llm.with_structured_output(ResumeModel)
        
        optimized_resume = optimization_chain.invoke(optimization_prompt)
        
        # Store optimized version
        version_id = str(uuid.uuid4())
        if user_id not in resume_versions:
            resume_versions[user_id] = {}
        resume_versions[user_id][version_id] = {
            'resume_data': optimized_resume.dict(),
            'job_description': job_description,
            'created_date': str(uuid.uuid4())  # TODO: Use proper datetime
        }
        
        return jsonify({
            "message": "Resume optimized successfully",
            "version_id": version_id,
            "optimized_resume": optimized_resume.dict()
        })
        
    except Exception as e:
        return jsonify({"error": f"Optimization failed: {str(e)}"}), 500

@app.route("/api/extension/generate", methods=["POST"])
def extension_generate():
    """
    Chrome extension endpoint for quick resume generation
    """
    data = request.get_json()
    user_id = data.get("user_id")
    version_id = data.get("version_id")
    
    if not user_id or not version_id:
        return jsonify({"error": "Missing user_id or version_id"}), 400
    
    if user_id not in resume_versions or version_id not in resume_versions[user_id]:
        return jsonify({"error": "Resume version not found"}), 404
    
    try:
        resume_data = resume_versions[user_id][version_id]['resume_data']
        
        # Generate filename
        filename = f"optimized_resume_{version_id[:8]}.docx"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Use McKinseyCVGenerator from generate_cv.py
        cv_generator = McKinseyCVGenerator(
            config=resume_data,
            output_filename=output_path
        )
        cv_generator.build()
        cv_generator.save()
        
        return jsonify({
            "message": "Resume generated successfully",
            "download_url": f"/download/{filename}",
            "filename": filename
        })
        
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500


# Run Flask app
if __name__ == "__main__":
    app.run(debug=True)
