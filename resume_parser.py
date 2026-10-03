import pdfplumber
import os
import json
import instructor
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from resume_schema import ResumeData, AtsReport, Experience, Project
from database import get_db, Resume, Candidate
from datetime import datetime
import re

load_dotenv("token.env")

api_key = os.environ.get("Api_key")

_client = None


def _get_client():
    """Create the OpenAI/instructor client on first use, not at import time."""
    global _client
    if _client is None:
        key = os.environ.get("Api_key") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OpenAI key missing: set the Api_key environment variable.")
        _client = instructor.from_openai(OpenAI(api_key=key))
    return _client

filename = "rs.pdf"

# use this function for raw text and use second one because the details in raw text 
# is unknown like whats the name etc so llm have knowledge so we i used llm function to structure this according to schema
 
def resume_parser(filename):
    text = ""
    links = []

    try:

        # safety first that file exists or not
        if not os.path.exists(filename):
            print(f"{filename} does not exists")
            return {"text" : "", "links": ""}
        
        # safety first that file is empty or not
        if os.path.getsize(filename) == 0:
            print(f"File '{filename}' is empty!")
            return {"text": "", "links": []}
        

        with pdfplumber.open(filename) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
                
                if page.hyperlinks:
                    for link in page.hyperlinks:
                        if link.get("uri"):
                            links.append(link["uri"])

        
        return {
            "text": text,
            "links": list(set(links))
        }
    
    except Exception as e:
        print(f"parser failed {e}")
        return {"text": "", "links": []}


SYSTEM_PROMPT = (
    "You are a resume parser. Extract structured information from the resume text. "
    "Only use information that is actually present in the text - do not invent details.\n\n"
    "PROJECTS (important): extract EVERY project the candidate lists. A project is any named "
    "piece of work they built, even if it appears under a heading such as 'Projects', 'Academic "
    "Projects', 'Personal Projects', 'Key Projects', 'Selected Work', 'Portfolio' or "
    "'Capstone', or is listed inside Experience, Internship or Education sections, or is only a "
    "title followed by bullet points. For each project return: title; tech_stack (technologies "
    "named in that project's text; use an empty list if none are named); description (1-2 "
    "sentences summarising its bullets; use an empty string if none). Do not skip a project "
    "because it lacks a tech stack or description. If the resume truly has no projects, "
    "return an empty list.\n\n"
    "CERTIFICATIONS: only include formal certifications with an issuing body or platform - "
    "exclude general statements or summaries."
)

PROJECT_ONLY_PROMPT = (
    "Find every project in this resume text and return them. A project is any named piece of "
    "work the candidate built, under any heading (Projects, Academic Projects, Personal "
    "Projects, Portfolio, etc.), or inside Experience/Internship/Education sections, or a title "
    "followed by bullet points. For each: title, tech_stack (only technologies named in the "
    "text, else empty list), description (1-2 sentence summary, else empty string). "
    "Do not invent anything. Return an empty list only if there are truly no projects."
)


class _ProjectList(BaseModel):
    projects: list[Project] = []


def extract_resume_data(raw_text: str) -> ResumeData:
    """
    Takes raw resume text (from pdfplumber) and returns a validated
    ResumeData object using an LLM. This function only deals with text in,
    structured data out.
    """
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=ResumeData,
        temperature=0,
        max_retries=2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
    )

    # Safety net: the big one-shot extraction sometimes returns no projects even
    # when the resume has them. Ask again with a prompt that ONLY looks for projects.
    if not response.projects:
        try:
            extra = client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=_ProjectList,
                temperature=0,
                max_retries=2,
                messages=[
                    {"role": "system", "content": PROJECT_ONLY_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
            )
            response.projects = extra.projects
        except Exception as exc:
            print(f"Project-only extraction failed: {exc}")

    return response


def save_resume_to_database(candidate_id: int, resume_data: ResumeData, raw_text: str):
    """
    Saves a candidate's parsed resume data to PostgreSQL using SQLAlchemy.

    Because 'resumes' has a UNIQUE constraint on candidate_id, this uses
    INSERT ... ON CONFLICT DO UPDATE - PostgreSQL automatically inserts a new
    row if this candidate has no resume yet, or updates their existing row
    if they do. This replaces the older resume with the newest one.
    """

    education_json = json.dumps([edu.model_dump() for edu in resume_data.education or []])
    projects_json = json.dumps([proj.model_dump() for proj in resume_data.projects or []])
    skills_json = json.dumps(resume_data.skills or [])
    certifications_json = json.dumps(resume_data.certifications or [])
    experience_json = json.dumps([exp.model_dump() for exp in resume_data.experience or []])

    with get_db() as db:
        try:
            candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            if candidate is None:
                print(f"Candidate with ID {candidate_id} does not exist.")
                return False

            existing_resume = db.query(Resume).filter(Resume.candidate_id == candidate_id).first()
            now = datetime.now()

            if existing_resume:
                existing_resume.full_name = resume_data.full_name
                existing_resume.email = resume_data.email
                existing_resume.phone = resume_data.phone
                existing_resume.location = resume_data.location
                existing_resume.github_url = resume_data.github_url
                existing_resume.linkedin_url = resume_data.linkedin_url
                existing_resume.skills = skills_json
                existing_resume.certifications = certifications_json
                existing_resume.education = education_json
                existing_resume.projects = projects_json
                existing_resume.experience = experience_json
                existing_resume.raw_text = raw_text
                existing_resume.parsed_at = now
            else:
                new_resume = Resume(
                    candidate_id=candidate_id,
                    full_name=resume_data.full_name,
                    email=resume_data.email,
                    phone=resume_data.phone,
                    location=resume_data.location,
                    github_url=resume_data.github_url,
                    linkedin_url=resume_data.linkedin_url,
                    skills=skills_json,
                    certifications=certifications_json,
                    education=education_json,
                    projects=projects_json,
                    experience=experience_json,
                    raw_text=raw_text,
                    uploaded_at=now,
                    parsed_at=now,
                )
                db.add(new_resume)

            db.commit()
            print(f"Resume saved for candidate_id={candidate_id}.")

        except Exception as e:
            db.rollback()
            print(f"Something went wrong, nothing was saved: {e}")
            raise

def generate_ats_report(resume_data,raw_text):
    raw_text = raw_text or ""
    score = 0

    strengths = []
    weaknesses = []
    suggestions = []
    missing_sections = []

    keyword_matches = []
    missing_keywords = []

    # Contact Information
    contact_Score = 0 

    if resume_data.full_name:
        contact_Score += 3
    else:
        suggestions.append("Add your full name.")

    if resume_data.email:
        contact_Score +=4
    else:
        suggestions.append("Email missing.")
    
    if resume_data.phone:
        contact_Score += 3
    else:
        weaknesses.append("Phone number missing")

    if resume_data.linkedin_url:
        contact_Score += 2
        strengths.append("LinkedIn profile available")
    else:
        suggestions.append("Add LinkedIn profile.")

    if resume_data.github_url:
        contact_Score += 2
        strengths.append("GitHub profile available")
    else:
        suggestions.append("Add GitHub profile.")

    if resume_data.location:
        contact_Score += 1

    # Professional Summary
    summary_score = 0
    if "summary" in raw_text.lower():
        summary_score +=10
        strengths.append("Professional summary found")
    
    else:

        missing_sections.append("Professional Summary")

        suggestions.append("Add a professional summary.")

    # Skills
    skills_score = 0
    skill_count = len(resume_data.skills)


    if skill_count >= 15:
        skills_score = 20

    elif skill_count >= 10:
        skills_score = 17

    elif skill_count >= 7:
        skills_score = 14

    elif skill_count >= 4:
        skills_score = 10

    else:

        skills_score = 5

        weaknesses.append("Very few technical skills")

        suggestions.append("Add more relevant technical skills.")
     
    
    # Education
    education_score = 10 if resume_data.education else 0

    if not resume_data.education:

        missing_sections.append("Education")

    # Projects
    project_count = len(resume_data.projects)

    if project_count >= 3:

        projects_score = 10

    elif project_count == 2:

        projects_score = 8

    elif project_count == 1:

        projects_score = 5

    else:

        projects_score = 0

        missing_sections.append("Projects")
        suggestions.append("Add 2-3 good projects.")
    
    # Certifications
    if not resume_data.certifications:
        certifications_score = 0
    else:
        cert_count = len(resume_data.certifications)

        if cert_count >= 3:
            certifications_score = 5

        elif cert_count >= 1:
            certifications_score = 3

        else:
            certifications_score = 0
            suggestions.append("Consider adding certifications.")

    # Experience and achievements
    experience_score = 0

    if not resume_data.experience:

        weaknesses.append("No work experience section found.")
        missing_sections.append("Experience")
        suggestions.append("Add internships, freelance work or professional experience.")

    else:

        strengths.append("Work experience section found.")

        # Base score for having experience
        experience_score += 10

        for exp in resume_data.experience:

          
            # Company Name
            if exp.company:
                experience_score += 2

            # Job Title
            if exp.job_title:
                experience_score += 2

            # Employment Dates
            if exp.start_date and (exp.end_date or exp.currently_working):
                experience_score += 4

            # Description
            if exp.description and len(exp.description.split()) >= 20:
                experience_score += 4

            # Technologies Used
            if exp.technologies:
                experience_score += 3

            # Achievements
            if exp.achievements:

                experience_score += 5
                achievement_text = " ".join(exp.achievements)

                if re.search(r"\d+[%+]?", achievement_text):
                    experience_score += 5
                else:
                    suggestions.append(
                        "Include measurable achievements in your work experience (e.g'Improved performance by 30%')"
                    )

    # Maximum 30 points
    experience_score = min(experience_score, 30)

    # Formatting
    formatting_score = 10

    words = len(raw_text.split())

    if words < 250:

        formatting_score -= 2

        suggestions.append("Resume is too short.")

    if raw_text.count("\n") < 15:

        formatting_score -= 2

    if len(raw_text) > 6000:

        formatting_score -= 2

        suggestions.append("Resume is too long.")


    # Keywords
    ats_keywords = [
        "Python",
        "SQL",
        "Git",
        "Docker",
        "AWS",
        "FastAPI",
        "Machine Learning",
        "REST API",
        "CI/CD",
        "Linux"
    ]    

    for keyword in ats_keywords:

        if keyword.lower() in raw_text.lower():

            keyword_matches.append(keyword)

        else:

            missing_keywords.append(keyword)


    # Normalize each rubric section into weighted points whose maxima sum to 100.
    category_maxima = {
        "contact_score": 15,
        "summary_score": 10,
        "skills_score": 18,
        "experience_score": 27,
        "education_score": 9,
        "projects_score": 9,
        "certifications_score": 4,
        "formatting_score": 8,
    }
    raw_maxima = {
        "contact_score": 15,
        "summary_score": 10,
        "skills_score": 20,
        "experience_score": 30,
        "education_score": 10,
        "projects_score": 10,
        "certifications_score": 5,
        "formatting_score": 10,
    }
    raw_scores = {
        "contact_score": contact_Score,
        "summary_score": summary_score,
        "skills_score": skills_score,
        "experience_score": experience_score,
        "education_score": education_score,
        "projects_score": projects_score,
        "certifications_score": certifications_score,
        "formatting_score": formatting_score,
    }
    weighted_scores = {
        name: round(min(value, raw_maxima[name]) * category_maxima[name] / raw_maxima[name])
        for name, value in raw_scores.items()
    }
    score = sum(weighted_scores.values())

    # Recommendation
    if score >= 90:

        recommendation = "Excellent"

    elif score >= 75:

        recommendation = "Strong"

    elif score >= 60:

        recommendation = "Needs Improvement"

    else:

        recommendation = "Poor"


    return AtsReport(

        overall_score=score,
        category_maxima=category_maxima,
        contact_score=weighted_scores["contact_score"],
        summary_score=weighted_scores["summary_score"],
        skills_score=weighted_scores["skills_score"],
        experience_score=weighted_scores["experience_score"],
        education_score=weighted_scores["education_score"],
        projects_score=weighted_scores["projects_score"],
        certifications_score=weighted_scores["certifications_score"],
        formatting_score=weighted_scores["formatting_score"],
        strengths=strengths,
        weaknesses=weaknesses,
        missing_sections=missing_sections,
        keyword_matches=keyword_matches,
        missing_keywords=missing_keywords,
        suggestions=suggestions,
        hiring_recommendation=recommendation
    )

def save_ats_report_to_database(candidate_id: int, ats_report):
    from database import ATSReport

    with get_db() as db:
        try:
            existing_report = db.query(ATSReport).filter(ATSReport.candidate_id == candidate_id).first()
            now = datetime.now()

            if existing_report:
                existing_report.overall_score = ats_report.overall_score
                existing_report.contact_score = ats_report.contact_score
                existing_report.summary_score = ats_report.summary_score
                existing_report.skills_score = ats_report.skills_score
                existing_report.experience_score = ats_report.experience_score
                existing_report.education_score = ats_report.education_score
                existing_report.projects_score = ats_report.projects_score
                existing_report.certifications_score = ats_report.certifications_score
                existing_report.formatting_score = ats_report.formatting_score
                existing_report.strengths = json.dumps(ats_report.strengths)
                existing_report.weaknesses = json.dumps(ats_report.weaknesses)
                existing_report.missing_sections = json.dumps(ats_report.missing_sections)
                existing_report.keyword_matches = json.dumps(ats_report.keyword_matches)
                existing_report.missing_keywords = json.dumps(ats_report.missing_keywords)
                existing_report.suggestions = json.dumps(ats_report.suggestions)
                existing_report.hiring_recommendation = ats_report.hiring_recommendation
                existing_report.calculated_at = now
            else:
                new_report = ATSReport(
                    candidate_id=candidate_id,
                    overall_score=ats_report.overall_score,
                    contact_score=ats_report.contact_score,
                    summary_score=ats_report.summary_score,
                    skills_score=ats_report.skills_score,
                    experience_score=ats_report.experience_score,
                    education_score=ats_report.education_score,
                    projects_score=ats_report.projects_score,
                    certifications_score=ats_report.certifications_score,
                    formatting_score=ats_report.formatting_score,
                    strengths=json.dumps(ats_report.strengths),
                    weaknesses=json.dumps(ats_report.weaknesses),
                    missing_sections=json.dumps(ats_report.missing_sections),
                    keyword_matches=json.dumps(ats_report.keyword_matches),
                    missing_keywords=json.dumps(ats_report.missing_keywords),
                    suggestions=json.dumps(ats_report.suggestions),
                    hiring_recommendation=ats_report.hiring_recommendation,
                    calculated_at=now,
                )
                db.add(new_report)

            db.commit()
            print(f"ATS Report saved for candidate_id={candidate_id}.")

        except Exception as e:
            db.rollback()
            print(f"Error saving ATS report: {e}")
            raise

if __name__ == "__main__":
    # Manual local test only. Keep this out of module import so FastAPI can start.
    result = resume_parser(filename)
    resume_data = extract_resume_data(result["text"])
    ats_report = generate_ats_report(resume_data, result["text"])
    save_resume_to_database(candidate_id=1, resume_data=resume_data, raw_text=result["text"])
    save_ats_report_to_database(candidate_id=1, ats_report=ats_report)