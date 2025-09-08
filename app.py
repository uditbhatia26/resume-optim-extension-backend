from flask import Flask, request, jsonify, send_file
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import User, Resume, ResumeVersion, resume_to_yaml_system_prompt
from generate_cv import McKinseyCVGenerator
from werkzeug.utils import secure_filename
import os
import uuid
import yaml
import json

app = Flask(__name__)
load_dotenv()

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# Load API keys from .env
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

# -------------------------------
# Utility functions
# -------------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_resume(file_path):
    """Extract resume data from PDF using LLM → YAML conversion"""
    try:
        # Load PDF text
        loader = PyMuPDFLoader(file_path=file_path)
        resume_pdf = loader.load()

        # Initialize LLM
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

        # Create prompt with your strict system instructions
        prompt = ChatPromptTemplate(
            [
                ("system", resume_to_yaml_system_prompt),
                ("human", "{resume}")
            ]
        )

        demo_chain = prompt | llm

        # Invoke chain
        response = demo_chain.invoke(input={"resume": resume_pdf}).content

        # Return raw YAML string (don’t dump again)
        return response  

    except Exception as e:
        raise ValueError(f"Failed to extract resume: {str(e)}")

# -------------------------------
# Routes
# -------------------------------

@app.route("/")
def home():
    return "Everything Working"

@app.route("/api/db/health", methods=["GET"])
def db_health():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            return jsonify({"database": "ok", "result": int(result)}), 200
    except Exception as e:
        return jsonify({"database": "error", "detail": str(e)}), 500

# Upload Resume
@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    file = request.files.get('file')
    user_id = request.form.get('user_id')
    
    if not file or file.filename == '':
        return jsonify({"error": "No file provided"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    db = SessionLocal()
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # Extract resume → YAML string
    yaml_data = extract_resume(file_path)

    # Save raw YAML string to file
    yaml_file_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        f"{uuid.uuid4()}_resume.yaml"
    )
    with open(yaml_file_path, "w+", encoding="utf-8") as file:
        file.write(yaml_data)

    new_resume = Resume(
        user_id=user_id,
        original_resume_path=yaml_file_path,  # now points to YAML file
        generation_count=0
    )
    db.add(new_resume)
    db.commit()
    db.refresh(new_resume)
    db.close()

    return jsonify({
        "message": "Resume uploaded successfully",
        "resume_id": new_resume.id,
        "resume_data": yaml_data  # return YAML string
    })

# Optimize Resume
@app.route("/api/optimize-resume", methods=["POST"])
def optimize_resume():
    data = request.get_json()
    user_id = data.get("user_id")
    resume_id = data.get("resume_id")
    job_description = data.get("job_description")
    additional_info = data.get("additional_info", {})

    if not user_id or not resume_id or not job_description:
        return jsonify({"error": "Missing required fields"}), 400

    db = SessionLocal()
    resume = db.query(Resume).filter_by(id=resume_id, user_id=user_id).first()
    if not resume:
        db.close()
        return jsonify({"error": "Resume not found"}), 404

    # Placeholder: fetch original resume YAML
    with open(resume.original_resume_path, "r") as f:
        original_resume = yaml.safe_load(f)

    # TODO: Replace with actual LLM optimization
    optimized_resume = original_resume  # placeholder

    # Increment generation count
    resume.generation_count += 1

    # Save optimized resume file
    optimized_file_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        f"optimized_{uuid.uuid4()}.yaml"
    )
    with open(optimized_file_path, "w") as f:
        yaml.dump(optimized_resume, f, default_flow_style=False)

    # Save to ResumeVersion
    new_version = ResumeVersion(
        resume_id=resume.id,
        optimized_resume_path=optimized_file_path,
        job_description=job_description,
        version_number=resume.generation_count
    )
    db.add(new_version)
    db.commit()
    db.close()

    return jsonify({
        "message": "Resume optimized successfully",
        "version_number": resume.generation_count,
        "optimized_resume": optimized_resume
    })

# Generate Resume (PDF/DOCX)
@app.route("/api/generate-resume", methods=["POST"])
def generate_resume():
    data = request.get_json()
    user_id = data.get("user_id")
    version_id = data.get("version_id")
    format_type = data.get("format", "docx")

    db = SessionLocal()
    version = db.query(ResumeVersion).filter_by(id=version_id).first()
    if not version or version.resume.user_id != user_id:
        db.close()
        return jsonify({"error": "Resume version not found"}), 404

    with open(version.optimized_resume_path, "r") as f:
        resume_data = yaml.safe_load(f)

    filename = f"optimized_resume_{version_id[:8]}.{format_type}"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    cv_generator = McKinseyCVGenerator(config=resume_data, output_filename=output_path)
    cv_generator.build()
    cv_generator.save()
    db.close()

    return jsonify({
        "message": "Resume generated successfully",
        "download_url": f"/download/{filename}",
        "filename": filename
    })

# Get all resumes for a user
@app.route("/api/user-resumes/<user_id>", methods=["GET"])
def get_user_resumes(user_id):
    db = SessionLocal()
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    resumes_list = []
    for resume in user.resumes:
        versions = db.query(ResumeVersion).filter_by(resume_id=resume.id).all()
        versions_data = [
            {
                "version_number": v.version_number,
                "optimized_resume_path": v.optimized_resume_path,
                "job_description": v.job_description
            } for v in versions
        ]
        resumes_list.append({
            "resume_id": resume.id,
            "original_resume_path": resume.original_resume_path,
            "generation_count": resume.generation_count,
            "versions": versions_data
        })
    db.close()
    return jsonify({
        "user_id": user_id,
        "resumes": resumes_list
    })

# Download file
@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

if __name__ == "__main__":
    app.run(debug=True)
