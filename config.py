from pydantic import BaseModel, Field

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



from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.mysql import JSON
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ✅ Load MySQL credentials from environment variables
USERNAME = os.getenv("MYSQL_USERNAME")
PASSWORD = os.getenv("MYSQL_PASSWORD")
HOST = os.getenv("MYSQL_HOST")
PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DB_NAME")

# Create connection string
DATABASE_URL = f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"

# Create engine
engine = create_engine(DATABASE_URL, echo=True)  # echo=True prints SQL logs

# Base class for models
Base = declarative_base()
# Users table
class User(Base):
    __tablename__ = "users"   # required!

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    generated_count = Column(Integer, default=0)
    addons = Column(JSON, nullable=True)

    # 🔑 This relationship is MISSING in your code
    resumes = relationship("Resume", back_populates="user", cascade="all, delete")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    original_resume_path = Column(String(255), nullable=False)
    generation_count = Column(Integer, default=0)

    user = relationship("User", back_populates="resumes")
    versions = relationship("ResumeVersion", back_populates="resume", cascade="all, delete")


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    optimized_resume_path = Column(String(255), nullable=False)
    job_description = Column(String(1000), nullable=True)
    version_number = Column(Integer, nullable=False)

    resume = relationship("Resume", back_populates="versions")


# Create all tables
Base.metadata.create_all(engine)

print("✅ Database schema with resume_versions created successfully!")



resume_to_yaml_system_prompt = """
You are an expert resume-to-structured-data converter. Your task is to extract information from resumes (PDF format) and output it strictly in YAML format, without changing a single word.

Rules:

- Do not paraphrase, shorten, or rephrase. The YAML must contain the exact same text from the resume.
- Preserve original wording, spelling, capitalization, punctuation, and formatting exactly as it appears in the resume.
- Only restructure the resume content into the YAML schema — no edits, summaries, or interpretations.
- Normalize dates into the format Month YYYY  Month YYYY or Present.
- If a section is missing, output it as an empty list ([]).
- The output must be pure YAML only (no Markdown formatting, no explanations).

<YAML SCHEMA>

personal_info:
  name: 
  phone: 
  email: 
  location: 
  linkedin: 
  github: 

certifications:
  - 

skills:
  categories:
    - name: 
      items: []

experience:
  - company: 
    location: 
    dates: 
    title: 
    bullet_points:
      - 

education:
  - institution: 
    degree: 
    cgpa: 
    dates: 

extracurriculars:
  - organization: 
    position: 
    dates: 
    bullet_points:
      - 

projects:
  - name: 
    tech_stack: []
    bullet_points:
      - 

</YAML SCHEMA>


Example Conversion:

<example>

personal_info:
  name: Udit Bhatia
  phone: "+91 9717228929"
  email: bhatiaudit.work@gmail.com
  location: Delhi, India
  linkedin: https://linkedin.com/in/uditbhatia26
  github: https://github.com/uditbhatia26

certifications:
  - Supervised Machine Learning: Regression and Classification
  - Advanced Learning Algorithms
  - Unsupervised Learning and Recommender Systems
  - Generative AI with Large Language Models

skills:
  categories:
    - name: Programming Languages
      items: [Python, Java, C++, OOP]
    - name: AI/ML Skills
      items: [Machine Learning, Deep Learning, NLP]
    - name: Tools & Frameworks
      items: [Langchain, Streamlit, Ollama, CrewAI, Flask, Django, FastAPI, Zilliz, Git, TensorFlow, Numpy, Pandas, Scikit-Learn]

experience:
  - company: Supervity
    location: Remote
    dates: May 2025 - Present
    title: Product Development Intern
    bullet_points:
      - Developed components of AP Command Centre, an enterprise invoice automation platform powered by LLMs and OCR, achieving 90% faster invoice processing and zero data entry errors.
      - Designed and deployed scalable Django APIs for document upload, collection management, and deletion using Milvus (Zilliz), forming the backbone of a custom RAG system.
      - Implemented real-time Live & Hybrid Search by integrating vector search with DuckDuckGo, Serper, and Bing APIs.
      - Contributed to a Transcription API that converts voice notes and video audio into accurate text with more than 95% accuracy.

  - company: Octainfinity
    location: Remote
    dates: Jan 2025 - Feb 2025
    title: AI Intern
    bullet_points:
      - Built a job scraper using Botasaurus and automated the process with N8N, enabling real-time job data extraction.
      - Engineered an AI-driven job application pipeline using Botasaurus, N8N, and browser automation to streamline submissions and reduce manual effort.

education:
  - institution: Guru Gobind Singh Indraprastha University (MSIT)
    degree: BTech in Information Technology
    cgpa: 8.0
    dates: 2023 - 2027

extracurriculars:
  - organization: Google Developers Group (GDG)
    position: AIML Deputy Head
    dates: Sep 2024 - Present
    bullet_points:
      - Led a team of 15 members in the AIML department, providing guidance on impactful AI/ML projects.
      - Directed the Enva and Avensis technical festivals, organizing 5+ workshops and events focused on AI/ML.

projects:
  - name: Postify
    tech_stack: [Python, Langchain, Groq, Flask, N8N, CrewAI]
    bullet_points:
      - Created an AI-powered platform that automated 100+ LinkedIn posts based on trending news and personal experiences.
      - Integrated an LLM-based assistant that generated posts with 80% accuracy in style and context.
      - Built an editing interface with seamless auto-posting to LinkedIn.

  - name: NCERT Learning Assistant
    tech_stack: [Python, Langchain, Groq, Streamlit]
    bullet_points:
      - Architected a Retrieval-Augmented Generation system with FAISS indexing to enhance question-answering on NCERT queries, achieving 95% relevance.
      - Designed a dual-themed interface blending educational and magical motifs to engage students.
      - Deployed an intuitive Streamlit app that served 100+ students weekly with personalized Q&A support.


</example>
"""