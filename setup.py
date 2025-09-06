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
    optimized_resume_path = Column(String(255))
    generation_count = Column(Integer, default=0)

    # Relationship back to user
    user = relationship("User", back_populates="resumes")

# Create all tables
Base.metadata.create_all(engine)

print("✅ Database schema created successfully!")
