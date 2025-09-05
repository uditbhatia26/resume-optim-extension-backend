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