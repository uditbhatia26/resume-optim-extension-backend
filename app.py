# app.py
from flask import Flask, request, jsonify, send_file
from langchain_groq import ChatGroq
from langchain_community.document_loaders import WebBaseLoader, PyMuPDFLoader
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
    CompatibilityAnalysisModel,
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

# LLM (single global instance)
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

# -----------------------
# Utilities
# -----------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_write_file(path: str, content: str) -> None:
    """Write file atomically (simple approach)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def is_within_uploads(filename: str) -> bool:
    """Prevent path traversal by ensuring the resolved path is inside the uploads folder."""
    uploads_dir = pathlib.Path(app.config["UPLOAD_FOLDER"]).resolve()
    target_path = (uploads_dir / filename).resolve()
    return uploads_dir in target_path.parents or uploads_dir == target_path.parent

def extract_resume(file_path: str) -> str:
    """
    Extract resume data from PDF/DOCX using LLM -> YAML conversion.
    Returns YAML string.
    """
    try:
        # Use PyMuPDF loader for PDFs; if file is not PDF, loader may still read raw text.
        loader = PyMuPDFLoader(file_path=file_path)
        docs = loader.load()
        # `docs` may be a list of Document objects; convert to text if needed
        # We'll provide the page_content of the first document (consistent with previous code)
        resume_text = docs[0].page_content if docs else ""

        # Build prompt using the strict system prompt from config
        prompt = ChatPromptTemplate(
            [
                ("system", resume_to_yaml_system_prompt),
                ("human", "{resume_text}")
            ]
        )

        chain = prompt | llm
        # Provide the resume text explicitly to avoid brittle f-strings
        response = chain.invoke({"resume_text": resume_text})
        yaml_str = response.content.strip()

        # Quick sanity check: ensure we received something that looks like YAML (contains newline + colon)
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

        # Extract resume -> YAML string
        try:
            yaml_data = extract_resume(upload_path)
        except Exception as e:
            # cleanup original uploaded file
            if os.path.exists(upload_path):
                os.remove(upload_path)
            return jsonify({"error": f"Resume extraction failed: {str(e)}"}), 500

        # Save YAML to file
        yaml_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{uuid.uuid4()}_resume.yaml")
        try:
            safe_write_file(yaml_file_path, yaml_data)
        except Exception as e:
            # cleanup both files
            if os.path.exists(upload_path):
                os.remove(upload_path)
            return jsonify({"error": f"Failed to save resume YAML: {str(e)}"}), 500

        # Now that YAML saved, delete original upload to avoid storage bloat
        try:
            if os.path.exists(upload_path):
                os.remove(upload_path)
        except Exception:
            # non-fatal, continue
            pass

        # Create DB record
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
    # try:
    #     resume = db.query(Resume).filter_by(id=resume_id, user_id=user_id).first()
    #     if not resume:
    #         return jsonify({"error": "Resume not found"}), 404

    #     try:
    #         with open(resume.original_resume_path, "r", encoding="utf-8") as f:
    #             resume_data = yaml.safe_load(f)
    #     except Exception as e:
    #         return jsonify({"error": f"Failed to load resume YAML: {str(e)}"}), 500

        # Build analysis prompt (explicit)
    #     system_text = (
    #         "You are a career assistant. Given a resume (YAML) and a job description, "
    #         "provide a match score (0-100) indicating how well the resume fits the job. "
    #         "Return only the number (integer)."
    #     )
    #     human_text = (
    #         "Resume (YAML):\n"
    #         f"{yaml.dump(resume_data, default_flow_style=False, allow_unicode=True)}\n\n"
    #         "Job Description:\n"
    #         f"{job_description}\n\n"
    #         "Instructions: Output ONLY the integer score between 0 and 100 (no extra text)."
    #     )

    #     prompt = ChatPromptTemplate.from_messages([
    #         ("system", system_text),
    #         ("human", human_text),
    #     ])
    #     chain = prompt | llm

    #     # Invoke
    #     response = chain.invoke({})
    #     raw = response.content.strip()

    #     # Extract integer robustly (first integer 0-100)
    #     # Accept formats like "85", "Match Score: 85", "85/100"
    #     match = re.search(r"(\b100\b|\b\d{1,2}\b)", raw)
    #     if not match:
    #         return jsonify({"error": f"LLM returned unparseable score: {raw}"}), 500

    #     try:
    #         score = int(match.group(1))
    #     except Exception:
    #         return jsonify({"error": f"Failed to parse score: {raw}"}), 500

    #     # Clamp to 0-100
    #     score = max(0, min(100, score))

    #     return jsonify({
    #         "resume_id": resume_id,
    #         "job_description": job_description,
    #         "match_score": score
    #     })

    # except Exception as e:
    #     return jsonify({"error": f"Analysis failed: {str(e)}"}), 500
    # finally:
    #     db.close()

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

        # Load original resume YAML
        try:
            with open(resume.original_resume_path, "r", encoding="utf-8") as f:
                original_resume = yaml.safe_load(f)
        except Exception as e:
            return jsonify({"error": f"Failed to load resume YAML: {str(e)}"}), 500

        addons = user.addons if getattr(user, "addons", None) else {}

        # Build the system/human prompts
        system_prompt = (
            "You are an expert resume optimizer. "
            "Given a resume (YAML), a job description, and optional user addons, "
            "return an optimized resume in YAML that matches the ResumeModel schema exactly. "
            "Do NOT include any commentary — output only YAML. "
            "If user addons contain projects/PORs/certifications that better match the job, include them."
        )

        human_prompt = (
            "Original Resume (YAML):\n"
            f"{yaml.dump(original_resume, default_flow_style=False, allow_unicode=True)}\n\n"
            "Job Description:\n"
            f"{job_description}\n\n"
            "User Addons (JSON):\n"
            f"{json.dumps(addons, indent=2)}\n\n"
            "Additional Info (JSON):\n"
            f"{json.dumps(additional_info, indent=2)}\n\n"
            "Return ONLY the optimized resume YAML that conforms to the schema: "
            "personal_info, experience, education, skills, projects, certifications, extracurriculars."
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_prompt)
        ])
        chain = prompt | llm

        # Invoke LLM
        response = chain.invoke({})
        optimized_yaml_str = response.content.strip()

        # Validate YAML -> dict
        try:
            optimized_resume_dict = yaml.safe_load(optimized_yaml_str)
            if not isinstance(optimized_resume_dict, dict):
                raise ValueError("Optimized YAML is not a mapping")
        except Exception as e:
            return jsonify({"error": f"LLM did not return valid YAML: {str(e)}", "llm_output": optimized_yaml_str}), 500

        # Validate against Pydantic ResumeModel
        try:
            validated = ResumeModel(**optimized_resume_dict)
            # Use validated.dict() if you want normalized representation
            optimized_resume_normalized = validated.dict()
        except ValidationError as ve:
            # If validation fails, return the errors and the raw YAML for debugging
            return jsonify({
                "error": "Optimized resume did not match ResumeModel schema",
                "validation_errors": ve.errors(),
                "llm_output": optimized_yaml_str
            }), 400

        # Save optimized YAML file (only after successful validation)
        optimized_file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            f"optimized_{resume.id}_{uuid.uuid4()}.yaml"
        )
        try:
            safe_write_file(optimized_file_path, optimized_yaml_str)
        except Exception as e:
            return jsonify({"error": f"Failed to save optimized YAML file: {str(e)}"}), 500

        # Increment counters and create ResumeVersion atomically
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
# Generate Resume (PDF/DOCX)
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

        # Load optimized YAML
        try:
            with open(version.optimized_resume_path, "r", encoding="utf-8") as f:
                resume_data = yaml.safe_load(f)
        except Exception as e:
            return jsonify({"error": f"Failed to load optimized YAML: {str(e)}"}), 500

        # Generate document
        filename = f"optimized_resume_{version_id[:8]}.{format_type}"
        output_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        try:
            cv_generator = McKinseyCVGenerator(config=resume_data, output_filename=output_path)
            cv_generator.build()
            cv_generator.save()
        except Exception as e:
            return jsonify({"error": f"Resume generation failed: {str(e)}"}), 500

        # Increment counters (user + resume) and record new version entry pointing to generated file
        resume = version.resume
        resume.generation_count = (resume.generation_count or 0) + 1
        user = db.query(User).filter_by(id=user_id).first()
        user.generated_count = (user.generated_count or 0) + 1

        new_version = ResumeVersion(
            resume_id=resume.id,
            optimized_resume_path=output_path,
            job_description=(version.job_description[:1000] if version.job_description else None),
            version_number=resume.generation_count
        )
        db.add(new_version)
        db.commit()
        db.refresh(new_version)

        return jsonify({
            "message": "Resume generated successfully",
            "download_url": f"/download/{filename}",
            "filename": filename,
            "version_id": new_version.id,
            "version_number": resume.generation_count
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500
    finally:
        db.close()

# -----------------------
# Get all resumes for a user
# -----------------------
@app.route("/api/user-resumes/<user_id>", methods=["GET"])
def get_user_resumes(user_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        resumes_list = []
        for resume in user.resumes:
            versions = db.query(ResumeVersion).filter_by(resume_id=resume.id).all()
            versions_data = [
                {
                    "version_id": v.id,
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

        return jsonify({
            "user_id": user_id,
            "resumes": resumes_list
        })
    finally:
        db.close()

# -----------------------
# Download file (safe)
# -----------------------
@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    # Ensure filename is safe and within uploads folder
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
