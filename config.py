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
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # One-to-many relationship (User -> Resumes)
    resumes = relationship("Resume", back_populates="user", cascade="all, delete")

# Resumes table
class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    original_resume_path = Column(String(255), nullable=False)
    generation_count = Column(Integer, default=0)

    # Relationship back to user
    user = relationship("User", back_populates="resumes")
    # One-to-many relationship (Resume -> ResumeVersions)
    versions = relationship("ResumeVersion", back_populates="resume", cascade="all, delete")

# Resume Versions table
class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    optimized_resume_path = Column(String(255), nullable=False)
    job_description = Column(String(1000), nullable=True)  # Optional: store the job description or ID
    version_number = Column(Integer, nullable=False)

    # Relationship back to resume
    resume = relationship("Resume", back_populates="versions")

# Create all tables
Base.metadata.create_all(engine)

print("✅ Database schema with resume_versions created successfully!")
