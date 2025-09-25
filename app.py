from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from langchain_groq import ChatGroq
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError
from config import (
    User,
    Resume,
    ResumeVersion,
    resume_to_yaml_system_prompt,
    ResumeModel,
)
from generate_cv import McKinseyCVGenerator
from werkzeug.utils import secure_filename
import os
import uuid
import yaml
import json
import re
import pathlib

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for extension

# -----------------------
# Config
# -----------------------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx", "doc"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# DB
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# LLM
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

# -----------------------
# Utilities
# -----------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def is_within_uploads(filename: str) -> bool:
    uploads_dir = pathlib.Path(app.config["UPLOAD_FOLDER"]).resolve()
    target_path = (uploads_dir / filename).resolve()
    return uploads_dir in target_path.parents or uploads_dir == target_path.parent

def extract_resume(file_path: str) -> str:
    try:
        loader = PyMuPDFLoader(file_path=file_path)
        docs = loader.load()
        resume_text = docs[0].page_content if docs else ""

        prompt = ChatPromptTemplate(
            [("system", resume_to_yaml_system_prompt), ("human", "{resume_text}")]
        )
        chain = prompt | llm
        response = chain.invoke({"resume_text": resume_text})
        yaml_str = response.content.strip()

        if not yaml_str or ":" not in yaml_str:
            raise ValueError("LLM returned unexpected format for resume extraction")
        return yaml_str
    except Exception as e:
        raise ValueError(f"Failed to extract resume: {str(e)}")

# -----------------------
# Routes
# -----------------------
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

# -----------------------
# Upload Resume
# -----------------------
@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    file = request.files.get("file")
    user_id = request.form.get("user_id")

    if not file or file.filename == "":
        return jsonify({"error": "No file provided"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        filename = secure_filename(file.filename)
        upload_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{uuid.uuid4()}_{filename}")
        file.save(upload_path)

        try:
            yaml_data = extract_resume(upload_path)
        except Exception as e:
            if os.path.exists(upload_path):
                os.remove(upload_path)
            return jsonify({"error": f"Resume extraction failed: {str(e)}"}), 500

        yaml_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{uuid.uuid4()}_resume.yaml")
        try:
            safe_write_file(yaml_file_path, yaml_data)
        except Exception as e:
            if os.path.exists(upload_path):
                os.remove(upload_path)
            return jsonify({"error": f"Failed to save resume YAML: {str(e)}"}), 500

        if os.path.exists(upload_path):
            os.remove(upload_path)

        new_resume = Resume(
            user_id=user_id,
            original_resume_path=yaml_file_path,
            generation_count=0,
        )
        db.add(new_resume)
        db.commit()
        db.refresh(new_resume)

        return jsonify({
            "message": "Resume uploaded successfully",
            "resume_id": new_resume.id,
            "resume_data": yaml_data
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500
    finally:
        db.close()

# -----------------------
# Analyze Compatibility
# -----------------------
@app.route("/api/analyze-compatibility", methods=["POST"])
def analyze_compatibility():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    resume_id = data.get("resume_id")
    job_description = data.get("job_description")

    if not user_id or not resume_id or not job_description:
        return jsonify({"error": "Missing required fields"}), 400

    db = SessionLocal()
    try:
        resume = db.query(Resume).filter_by(id=resume_id, user_id=user_id).first()
        if not resume:
            return jsonify({"error": "Resume not found"}), 404

        with open(resume.original_resume_path, "r", encoding="utf-8") as f:
            resume_data = yaml.safe_load(f)

        system_text = (
            "You are a career assistant. Given a resume (YAML) and a job description, "
            "provide a match score (0-100) indicating how well the resume fits the job. "
            "Return only the number (integer)."
        )
        human_text = (
            "Resume (YAML):\n"
            f"{yaml.dump(resume_data)}\n\n"
            "Job Description:\n"
            f"{job_description}\n\n"
            "Instructions: Output ONLY the integer score between 0 and 100."
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            ("human", human_text),
        ])
        chain = prompt | llm
        response = chain.invoke({})
        raw = response.content.strip()

        match = re.search(r"(\b100\b|\b\d{1,2}\b)", raw)
        if not match:
            return jsonify({"error": f"LLM returned unparseable score: {raw}"}), 500

        score = int(match.group(1))
        score = max(0, min(100, score))

        return jsonify({
            "resume_id": resume_id,
            "job_description": job_description,
            "match_score": score
        })
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500
    finally:
        db.close()

# -----------------------
# Optimize Resume
# -----------------------
@app.route("/api/optimize-resume", methods=["POST"])
def optimize_resume():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    resume_id = data.get("resume_id")
    job_description = data.get("job_description")
    additional_info = data.get("additional_info", {})

    if not user_id or not resume_id or not job_description:
        return jsonify({"error": "Missing required fields"}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        resume = db.query(Resume).filter_by(id=resume_id, user_id=user_id).first()
        if not user or not resume:
            return jsonify({"error": "User or Resume not found"}), 404

        if (user.generated_count or 0) >= 3:
            return jsonify({"error": "Free limit reached. Please upgrade."}), 402

        with open(resume.original_resume_path, "r", encoding="utf-8") as f:
            original_resume = yaml.safe_load(f)

        addons = user.addons if getattr(user, "addons", None) else {}

        system_prompt = (
            "You are an expert resume optimizer. "
            "Given a resume (YAML), a job description, and optional user addons, "
            "return an optimized resume in YAML that matches the ResumeModel schema exactly. "
            "Do NOT include any commentary — output only YAML."
        )
        human_prompt = (
            f"Original Resume (YAML):\n{yaml.dump(original_resume)}\n\n"
            f"Job Description:\n{job_description}\n\n"
            f"User Addons (JSON):\n{json.dumps(addons, indent=2)}\n\n"
            f"Additional Info (JSON):\n{json.dumps(additional_info, indent=2)}"
        )

        response = llm.invoke([
            ("system", system_prompt),
            ("human", human_prompt)
        ])
        optimized_yaml_str = response.content.strip()


        try:
            optimized_resume_dict = yaml.safe_load(optimized_yaml_str)
            validated = ResumeModel(**optimized_resume_dict)
            optimized_resume_normalized = validated.dict()
        except Exception as e:
            return jsonify({"error": "Optimized resume invalid", "llm_output": optimized_yaml_str}), 400

        optimized_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"optimized_{resume.id}_{uuid.uuid4()}.yaml")
        safe_write_file(optimized_file_path, optimized_yaml_str)

        resume.generation_count = (resume.generation_count or 0) + 1
        user.generated_count = (user.generated_count or 0) + 1

        new_version = ResumeVersion(
            resume_id=resume.id,
            optimized_resume_path=optimized_file_path,
            job_description=(job_description[:1000] if job_description else None),
            version_number=resume.generation_count
        )
        db.add(new_version)
        db.commit()
        db.refresh(new_version)

        return jsonify({
            "message": "Resume optimized successfully",
            "resume_id": resume.id,
            "version_id": new_version.id,
            "version_number": resume.generation_count,
            "optimized_resume": optimized_resume_normalized
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Optimization failed: {str(e)}"}), 500
    finally:
        db.close()

# -----------------------
# Generate Resume
# -----------------------
@app.route("/api/generate-resume", methods=["POST"])
def generate_resume():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    version_id = data.get("version_id")
    format_type = data.get("format", "docx")

    if not user_id or not version_id:
        return jsonify({"error": "Missing required fields"}), 400

    db = SessionLocal()
    try:
        version = db.query(ResumeVersion).filter_by(id=version_id).first()
        if not version or not getattr(version, "resume", None) or version.resume.user_id != user_id:
            return jsonify({"error": "Resume version not found or access denied"}), 404

        with open(version.optimized_resume_path, "r", encoding="utf-8") as f:
            resume_data = yaml.safe_load(f)

        filename = f"optimized_resume_{version_id[:8]}.{format_type}"
        output_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        cv_generator = McKinseyCVGenerator(config=resume_data, output_filename=output_path)
        cv_generator.build()
        cv_generator.save()

        return jsonify({
            "message": "Resume generated successfully",
            "download_url": f"/download/{filename}",
            "filename": filename,
            "version_id": version.id,
            "version_number": version.version_number
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500
    finally:
        db.close()

# -----------------------
# Preview Resume
# -----------------------
@app.route("/api/preview-resume/<version_id>", methods=["GET"])
def preview_resume(version_id):
    db = SessionLocal()
    try:
        version = db.query(ResumeVersion).filter_by(id=version_id).first()
        if not version:
            return jsonify({"error": "Version not found"}), 404
        with open(version.optimized_resume_path, "r", encoding="utf-8") as f:
            resume_data = yaml.safe_load(f)
        html = f"<html><body><pre>{json.dumps(resume_data, indent=2)}</pre></body></html>"
        return html
    finally:
        db.close()

# -----------------------
# Recalculate Score
# -----------------------
@app.route("/api/recalculate-score/<version_id>", methods=["GET"])
def recalculate_score(version_id):
    db = SessionLocal()
    try:
        version = db.query(ResumeVersion).filter_by(id=version_id).first()
        if not version:
            return jsonify({"error": "Version not found"}), 404

        with open(version.optimized_resume_path, "r", encoding="utf-8") as f:
            resume_data = yaml.safe_load(f)

        system_text = (
            "Recalculate match score (0-100) for this resume and job description. "
            "Return ONLY an integer."
        )
        human_text = (
            f"Resume (YAML):\n{yaml.dump(resume_data)}\n\n"
            f"Job Description:\n{version.job_description}"
        )

        prompt = ChatPromptTemplate.from_messages([("system", system_text), ("human", human_text)])
        chain = prompt | llm
        response = chain.invoke({})
        raw = response.content.strip()

        match = re.search(r"(\b100\b|\b\d{1,2}\b)", raw)
        if not match:
            return jsonify({"error": f"LLM returned invalid score: {raw}"}), 500

        score = int(match.group(1))
        score = max(0, min(100, score))

        return jsonify({"version_id": version_id, "new_score": score})
    finally:
        db.close()

# -----------------------
# Download File
# -----------------------
@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Invalid filename"}), 400
    if not is_within_uploads(filename):
        return jsonify({"error": "Invalid filename or path traversal attempt"}), 400

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    app.run(debug=True)
