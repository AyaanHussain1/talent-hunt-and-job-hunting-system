import os
import json
import shutil
from datetime import datetime, date
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import mysql.connector

# Import functions from modules
from github_extractor_script import fetch_and_clean_github_data, save_to_database
from resume_parser import resume_parser, extract_resume_data, save_resume_to_database, generate_ats_report
from portfolio_analyzer import analyze_portfolio, save_portfolio_to_database
from job_matching_engine import match_candidate_to_jobs, save_matches_to_database
from resume_schema import CandidateCreate, ResumeData, Education, Project, Experience

load_dotenv("token.env")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

app = FastAPI(
    title="AI Talent Discovery & Job Placement Platform",
    description="Startup API Backend",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """Lightweight Railway health check that does not require a database connection."""
    return {"status": "ok"}


class JobPayload(BaseModel):
    title: str
    company: str
    job_type: str
    required_skills: list[str]
    description: str | None = None
    location: str | None = None

def get_db():
    return mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )

def sanitize_data(data):
    """Recursively convert datetime/date objects into ISO strings for clean JSON serialization."""
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, dict):
        return {
            k: (v.isoformat() if isinstance(v, (datetime, date)) else sanitize_data(v))
            for k, v in data.items()
        }
    return data


def decode_json_fields(row, fields):
    """Decode JSON columns returned by MySQL into native Python values."""
    if not row:
        return row
    for field in fields:
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except json.JSONDecodeError:
                pass
    return row

# CANDIDATE ENDPOINTS

@app.post("/candidates/", tags=["Candidates"])
def create_candidate(body: CandidateCreate):
    """Create a new candidate record."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO candidates (full_name, email, created_at) VALUES (%s, %s, NOW())",
            (body.full_name, body.email)
        )
        db.commit()
        return {"candidate_id": cursor.lastrowid, "full_name": body.full_name}
    except mysql.connector.Error as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        db.close()

@app.get("/candidates/", tags=["Candidates"])
def list_candidates():
    """List all candidates with their basic info."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, full_name, email, created_at FROM candidates ORDER BY id DESC")
        rows = cursor.fetchall()
        return sanitize_data(rows)
    finally:
        cursor.close()
        db.close()

@app.get("/candidates/{candidate_id}", tags=["Candidates"])
def get_candidate(candidate_id: int):
    """Get a single candidate's full profile from all data sources."""
    db = get_db()
    # Buffered results prevent unread rows from one profile query blocking the
    # remaining resume and portfolio queries when duplicate legacy rows exist.
    cursor = db.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute("SELECT * FROM candidates WHERE id = %s", (candidate_id,))
        candidate = cursor.fetchone()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found.")

        cursor.execute("SELECT * FROM github_profiles WHERE candidate_id = %s ORDER BY last_fetched_at DESC LIMIT 1", (candidate_id,))
        github = cursor.fetchone()

        cursor.execute(
            "SELECT full_name, email, phone, location, github_url, linkedin_url, skills, education, projects, experience, certifications "
            "FROM resumes WHERE candidate_id = %s",
            (candidate_id,)
        )
        resume = cursor.fetchone()
        decode_json_fields(resume, ["skills", "education", "projects", "experience", "certifications"])

        cursor.execute("SELECT * FROM portfolio_scores WHERE candidate_id = %s", (candidate_id,))
        portfolio = cursor.fetchone()
        decode_json_fields(portfolio, ["primary_languages", "strengths", "weaknesses"])

        return sanitize_data({
            "candidate": candidate,
            "github": github,
            "resume": resume,
            "portfolio": portfolio
        })
    finally:
        cursor.close()
        db.close()

# GITHUB ENDPOINTS

@app.post("/candidates/{candidate_id}/github", tags=["GitHub"])
def extract_github(candidate_id: int, github_username: str):
    """Fetch GitHub profile/repos, clean data, and save to DB."""
    try:
        cleaned_data = fetch_and_clean_github_data(github_username)
        if not cleaned_data.get("profile"):
            raise HTTPException(status_code=400, detail="Could not fetch GitHub data. Check username.")

        cleaned_data["profile"]["candidate_id"] = candidate_id
        save_to_database(cleaned_data)
        return {
            "message": "GitHub data saved successfully.",
            "repos_saved": len(cleaned_data.get("repos", [])),
            "profile": cleaned_data.get("profile")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# RESUME & ATS ENDPOINTS

@app.post("/candidates/{candidate_id}/resume", tags=["Resume"])
def upload_resume(candidate_id: int, file: UploadFile = File(...)):
    """Upload PDF, parse skills/projects with LLM, and store in DB."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    temp_path = f"temp_resume_{candidate_id}.pdf"
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        raw_result = resume_parser(temp_path)
        if not raw_result.get("text"):
            raise HTTPException(status_code=400, detail="Could not extract text from PDF.")

        resume_data = extract_resume_data(raw_result["text"])
        save_resume_to_database(candidate_id, resume_data, raw_result["text"])

        return {
            "message": "Resume parsed and saved successfully.",
            "candidate_id": candidate_id,
            "skills_found": len(resume_data.skills),
            "projects_found": len(resume_data.projects),
            "education_found": len(resume_data.education),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.get("/candidates/{candidate_id}/ats", tags=["Resume"])
def get_ats_report(candidate_id: int):
    """Generate ATS score and improvement analysis."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT raw_text, full_name, email, phone, location, github_url, linkedin_url, skills, education, projects, experience, certifications FROM resumes WHERE candidate_id = %s", (candidate_id,))
        resume_row = cursor.fetchone()
        if not resume_row:
            raise HTTPException(status_code=404, detail="No resume found for this candidate.")

        resume_data = ResumeData(
            full_name=resume_row["full_name"],
            email=resume_row["email"],
            phone=resume_row["phone"],
            location=resume_row["location"],
            github_url=resume_row["github_url"],
            linkedin_url=resume_row["linkedin_url"],
            skills=json.loads(resume_row["skills"]) if resume_row["skills"] else [],
            education=[Education(**e) for e in (json.loads(resume_row["education"]) if resume_row["education"] else [])],
            projects=[Project(**p) for p in (json.loads(resume_row["projects"]) if resume_row["projects"] else [])],
            experience=[Experience(**e) for e in (json.loads(resume_row["experience"]) if resume_row["experience"] else [])],
            certifications=json.loads(resume_row["certifications"]) if resume_row["certifications"] else [],
        )
        report = generate_ats_report(resume_data, resume_row["raw_text"])
        return report.model_dump()
    finally:
        cursor.close()
        db.close()

# PORTFOLIO ENDPOINTS

@app.post("/candidates/{candidate_id}/portfolio", tags=["Portfolio"])
def calculate_portfolio(candidate_id: int):
    try:
        result = analyze_portfolio(candidate_id)
        save_portfolio_to_database(result)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/candidates/{candidate_id}/portfolio", tags=["Portfolio"])
def get_portfolio(candidate_id: int):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM portfolio_scores WHERE candidate_id = %s", (candidate_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No portfolio score found. Run POST first.")
        decode_json_fields(row, ["primary_languages", "strengths", "weaknesses"])
        return sanitize_data(row)
    finally:
        cursor.close()
        db.close()

# JOB MATCHING ENDPOINTS

@app.post("/candidates/{candidate_id}/match", tags=["Job Matching"])
def run_job_matching(candidate_id: int):
    """Run vector + keyword match and save scores into MySQL."""
    try:
        result = match_candidate_to_jobs(candidate_id)
        save_matches_to_database(result)
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/candidates/{candidate_id}/matches", tags=["Job Matching"])
def get_matches(candidate_id: int):
    """Get saved matches for candidate, parsed correctly."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT jm.*, j.title, j.company, j.job_type, j.location
            FROM job_matches jm
            JOIN jobs j ON jm.job_id = j.id
            WHERE jm.candidate_id = %s
            ORDER BY jm.match_score DESC
            """,
            (candidate_id,)
        )
        rows = cursor.fetchall()
        for row in rows:
            if isinstance(row.get("matched_skills"), str):
                row["matched_skills"] = json.loads(row["matched_skills"])
            if isinstance(row.get("missing_skills"), str):
                row["missing_skills"] = json.loads(row["missing_skills"])
        return sanitize_data(rows)
    finally:
        cursor.close()
        db.close()

# EMPLOYER & JOBS ENDPOINTS

@app.get("/jobs/", tags=["Jobs"])
def list_jobs():
    """List open jobs ordered by ID."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
        rows = cursor.fetchall()
        for row in rows:
            decode_json_fields(row, ["required_skills"])
        return sanitize_data(rows)
    finally:
        cursor.close()
        db.close()


@app.post("/jobs/", tags=["Jobs"])
def create_or_update_job(job: JobPayload):
    """Create a job or overwrite the row with the same title and company."""
    title, company = job.title.strip(), job.company.strip()
    skills = [skill.strip() for skill in job.required_skills if skill and skill.strip()]
    if not title or not company or not skills:
        raise HTTPException(status_code=400, detail="Title, company, and at least one required skill are required.")
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM jobs WHERE title = %s AND company = %s ORDER BY id DESC LIMIT 1", (title, company))
        existing = cursor.fetchone()
        values = (job.job_type, json.dumps(skills), job.description.strip() if job.description else None, job.location.strip() if job.location else None)
        if existing:
            cursor.execute(
                "UPDATE jobs SET job_type = %s, required_skills = %s, description = %s, location = %s, posted_ad = NOW() WHERE id = %s",
                (*values, existing["id"]),
            )
            job_id, action = existing["id"], "updated"
        else:
            cursor.execute(
                "INSERT INTO jobs (title, company, job_type, required_skills, description, location) VALUES (%s, %s, %s, %s, %s, %s)",
                (title, company, *values),
            )
            job_id, action = cursor.lastrowid, "created"
        db.commit()
        return {"message": f"Job {action} successfully.", "job_id": job_id, "action": action}
    except mysql.connector.Error as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        cursor.close()
        db.close()

@app.get("/employer/candidates", tags=["Employer"])
def search_candidates(skill: str | None = None):
    """Search candidates using standard SQL pattern matching."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        if skill and skill.strip():
            pattern = f"%{skill.strip().lower()}%"
            cursor.execute(
                """
                SELECT c.id, c.full_name, c.email, r.skills, r.location, ps.portfolio_score
                FROM candidates c
                LEFT JOIN resumes r ON c.id = r.candidate_id
                LEFT JOIN portfolio_scores ps ON c.id = ps.candidate_id
                WHERE LOWER(r.skills) LIKE %s
                ORDER BY ps.portfolio_score DESC
                """,
                (pattern,)
            )
        else:
            cursor.execute(
                """
                SELECT c.id, c.full_name, c.email, r.skills, r.location, ps.portfolio_score
                FROM candidates c
                LEFT JOIN resumes r ON c.id = r.candidate_id
                LEFT JOIN portfolio_scores ps ON c.id = ps.candidate_id
                ORDER BY ps.portfolio_score DESC
                """
            )
        rows = cursor.fetchall()
        return sanitize_data(rows)
    finally:
        cursor.close()
        db.close()

@app.get("/employer/jobs/{job_id}/candidates", tags=["Employer"])
def get_candidates_for_job(job_id: int):
    """Get candidate matches for a specific job position."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT c.id, c.full_name, c.email,
                   jm.match_score, jm.matched_skills, jm.missing_skills,
                   ps.portfolio_score
            FROM job_matches jm
            JOIN candidates c ON jm.candidate_id = c.id
            LEFT JOIN portfolio_scores ps ON c.id = ps.candidate_id
            WHERE jm.job_id = %s
            ORDER BY jm.match_score DESC
            """,
            (job_id,)
        )
        rows = cursor.fetchall()
        return sanitize_data(rows)
    finally:
        cursor.close()
        db.close()
