from pydantic import BaseModel
from typing import Optional

class Education(BaseModel):
    institution: str
    degree: str
    start_year: Optional[str] = None
    end_year: Optional[str] = None
    gpa_or_percentage: Optional[str] = None

class Project(BaseModel):
    title: str
    tech_stack: list[str]
    description: str

class Experience(BaseModel):
    company: str
    job_title: str
    employment_type: str | None
    start_date: str
    end_date: str | None
    currently_working: bool
    description: str
    technologies: list[str]
    achievements: list[str]

class ResumeData(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    skills: list[str] = []
    education: list[Education] = [] 
    projects: list[Project] = []
    certifications: Optional[list[str]] = None
    experience: list[Experience] = []

class AtsReport(BaseModel):
    overall_score : int
    contact_score: int
    summary_score: int
    skills_score: int
    experience_score: int
    education_score: int
    projects_score: int
    certifications_score: int
    formatting_score: int

    strengths : list[str]
    weaknesses : list[str]
    missing_sections : list[str]
    
    keyword_matches: list[str]
    missing_keywords: list[str]
    suggestions: list[str]
    
    hiring_recommendation: str

class PortfolioScore(BaseModel):
    candidate_id : int
    portfolio_score : float
    total_repos : int
    live_projects_count : int
    primary_languages : list[str]
    strengths: list[str]
    weaknesses: list[str]

from pydantic import BaseModel, Field

class CandidateFinalScores(BaseModel):
    candidate_id: int
    portfolio_quality: float = Field(description="Score out of 100 based on GitHub quality")
    project_experience: float = Field(description="Score out of 100 based on resume and repos")
    engineering_readiness: float = Field(description="Technical skill strength")
    communication: float = Field(description="Formatting, summary, and contact score")
    leadership: float = Field(description="Keyword matches and open-source impact")
    hiring_confidence: float = Field(description="Overall aggregated confidence score")

# job matching engine 
class JobMatch(BaseModel):
    candidate_id : int
    job_id : int
    job_title : str
    company : str
    job_type : str
    match_score : float  # 0.0 - 100.0 percentage
    matched_skills : list[str] # skills the candidate has that the job needs 
    missing_skills : list[str] # skills the job needs that the candidate lacks

class JobMatchingResult(BaseModel):
    candidate_id: int
    candidate_name: str
    total_jobs_evaluated: int
    matches: list[JobMatch]

class CandidateCreate(BaseModel):
    full_name: str
    email: str | None = None