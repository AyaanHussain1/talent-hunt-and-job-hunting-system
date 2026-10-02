import os
import json
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, date
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
from sqlalchemy import cast, Text, func
from dotenv import load_dotenv

# Import functions from modules
from github_extractor_script import fetch_and_clean_github_data, save_to_database
from resume_parser import resume_parser, extract_resume_data, save_resume_to_database, generate_ats_report
from portfolio_analyzer import analyze_portfolio, save_portfolio_to_database
from resume_schema import CandidateCreate, ResumeData, Education, Project, Experience
from database import get_db, Candidate, GitHubProfile, GitHubRepo, Resume, PortfolioScore, PortfolioAudit, ATSReport, Job, JobMatch
from portfolio_site_auditor import audit_portfolio_site, PortfolioAuditError

load_dotenv("token.env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create PostgreSQL tables from SQLAlchemy models if they don't exist.

    Startup fails if the database schema cannot be initialized, so the API
    never accepts requests against a missing schema.
    """
    from database import init_db
    init_db()
    print("PostgreSQL tables verified/created.")
    yield


app = FastAPI(
    title="AI Talent Discovery & Job Placement Platform",
    description="Startup API Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """Lightweight health check that does not require a database connection."""
    return {"status": "ok"}


class JobPayload(BaseModel):
    title: str
    company: str
    job_type: str
    required_skills: list[str]
    description: str | None = None
    location: str | None = None


class PortfolioLinkPayload(BaseModel):
    portfolio_url: str


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
    """Decode JSON columns returned by PostgreSQL into native Python values."""
    if not row:
        return row
    for field in fields:
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except json.JSONDecodeError:
                pass
    return row


def coerce_json_list(value):
    """Return a JSONB column value as a Python list.

    PostgreSQL (psycopg2) returns JSONB natively as list/dict, while older
    rows written through ``json.dumps`` come back as strings — accept both.
    """
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []

# CANDIDATE ENDPOINTS

@app.post("/candidates/", tags=["Candidates"])
def create_candidate(body: CandidateCreate):
    """Create a new candidate record."""
    with get_db() as db:
        full_name = body.full_name.strip()
        email = body.email.strip() if body.email and body.email.strip() else None
        if email:
            existing = db.query(Candidate).filter(
                func.lower(func.trim(Candidate.email)) == email.lower()
            ).first()
        else:
            existing = db.query(Candidate).filter(
                func.lower(func.trim(Candidate.full_name)) == full_name.lower(),
                Candidate.email.is_(None),
            ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Candidate already exists (ID #{existing.id}).",
            )

        try:
            candidate = Candidate(full_name=full_name, email=email, created_at=datetime.now())
            db.add(candidate)
            db.flush()
            return {"candidate_id": candidate.id, "full_name": full_name}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))

@app.get("/candidates/", tags=["Candidates"])
def list_candidates():
    """List all candidates with their basic info."""
    with get_db() as db:
        candidates = db.query(Candidate).order_by(Candidate.id.desc()).all()
        return sanitize_data([
            {"id": c.id, "full_name": c.full_name, "email": c.email, "created_at": c.created_at}
            for c in candidates
        ])

@app.get("/candidates/{candidate_id}", tags=["Candidates"])
def get_candidate(candidate_id: int):
    """Get a single candidate's full profile from all data sources."""
    with get_db() as db:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found.")

        github = db.query(GitHubProfile).filter(GitHubProfile.candidate_id == candidate_id).order_by(GitHubProfile.last_fetched_at.desc()).first()

        resume = db.query(Resume).filter(Resume.candidate_id == candidate_id).first()

        portfolio = db.query(PortfolioScore).filter(PortfolioScore.candidate_id == candidate_id).first()

        result = {
            "candidate": {
                "id": candidate.id,
                "full_name": candidate.full_name,
                "email": candidate.email,
                "created_at": candidate.created_at
            },
            "github": None,
            "resume": None,
            "portfolio": None,
            "portfolio_audit": None,
        }

        if github:
            result["github"] = {
                "id": github.id,
                "candidate_id": github.candidate_id,
                "github_id": github.github_id,
                "github_username": github.github_username,
                "bio": github.bio,
                "company": github.company,
                "location": github.location,
                "public_repos": github.public_repos,
                "followers": github.followers,
                "account_created_at": github.account_created_at,
                "last_fetched_at": github.last_fetched_at
            }

        if resume:
            result["resume"] = {
                "full_name": resume.full_name,
                "email": resume.email,
                "phone": resume.phone,
                "location": resume.location,
                "github_url": resume.github_url,
                "linkedin_url": resume.linkedin_url,
                "skills": resume.skills,
                "education": resume.education,
                "projects": resume.projects,
                "experience": resume.experience,
                "certifications": resume.certifications
            }
            decode_json_fields(result["resume"], ["skills", "education", "projects", "experience", "certifications"])

        if portfolio:
            result["portfolio"] = {
                "id": portfolio.id,
                "candidate_id": portfolio.candidate_id,
                "portfolio_score": portfolio.portfolio_score,
                "total_repos": portfolio.total_repos,
                "live_projects_count": portfolio.live_projects_count,
                "primary_languages": portfolio.primary_languages,
                "strengths": portfolio.strengths,
                "weaknesses": portfolio.weaknesses,
                "calculated_at": portfolio.calculated_at
            }
            decode_json_fields(result["portfolio"], ["primary_languages", "strengths", "weaknesses"])

        audit = db.query(PortfolioAudit).filter(PortfolioAudit.candidate_id == candidate_id).first()
        if audit:
            result["portfolio_audit"] = {
                "id": audit.id,
                "candidate_id": audit.candidate_id,
                "portfolio_url": audit.portfolio_url,
                "overall_score": audit.overall_score,
                "category_scores": _portfolio_audit_categories(audit.checks),
                "checks": audit.checks,
                "strengths": audit.strengths,
                "weaknesses": audit.weaknesses,
                "analyzed_at": audit.analyzed_at,
            }
            decode_json_fields(result["portfolio_audit"], ["checks", "strengths", "weaknesses", "category_scores"])

        return sanitize_data(result)

# GITHUB ENDPOINTS

@app.post("/candidates/{candidate_id}/github", tags=["GitHub"])
def extract_github(candidate_id: int, github_username: str):
    """Fetch GitHub profile/repos, clean data, and save to DB."""
    try:
        cleaned_data = fetch_and_clean_github_data(github_username)
        if not cleaned_data.get("profile"):
            raise HTTPException(status_code=400, detail="Could not fetch GitHub data. Check username.")

        save_to_database(cleaned_data, candidate_id=candidate_id)
        return {
            "message": "GitHub data saved successfully.",
            "repos_saved": len(cleaned_data.get("repos", [])),
            "profile": cleaned_data.get("profile")
        }
    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 502
        if status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="GitHub rejected the configured token. Verify Github_Token in token.env.",
            ) from e
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with status {status_code}.",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# RESUME & ATS ENDPOINTS

@app.post("/candidates/{candidate_id}/resume", tags=["Resume"])
def upload_resume(candidate_id: int, file: UploadFile = File(...)):
    """Upload PDF, parse skills/projects with LLM, and store in DB."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".pdf",
            prefix=f"resume_{candidate_id}_",
            dir=tempfile.gettempdir(),
            delete=False,
        ) as f:
            temp_path = f.name
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@app.get("/candidates/{candidate_id}/ats", tags=["Resume"])
def get_ats_report(candidate_id: int):
    """Generate ATS score and improvement analysis."""
    with get_db() as db:
        resume_row = db.query(Resume).filter(Resume.candidate_id == candidate_id).first()
        if not resume_row:
            raise HTTPException(status_code=404, detail="No resume found for this candidate.")

        resume_data = ResumeData(
            full_name=resume_row.full_name,
            email=resume_row.email,
            phone=resume_row.phone,
            location=resume_row.location,
            github_url=resume_row.github_url,
            linkedin_url=resume_row.linkedin_url,
            skills=coerce_json_list(resume_row.skills),
            education=[Education(**e) for e in coerce_json_list(resume_row.education)],
            projects=[Project(**p) for p in coerce_json_list(resume_row.projects)],
            experience=[Experience(**e) for e in coerce_json_list(resume_row.experience)],
            certifications=coerce_json_list(resume_row.certifications),
        )
        report = generate_ats_report(resume_data, resume_row.raw_text)
        return report.model_dump()

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
    with get_db() as db:
        row = db.query(PortfolioScore).filter(PortfolioScore.candidate_id == candidate_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="No portfolio score found. Run POST first.")
        
        result = {
            "id": row.id,
            "candidate_id": row.candidate_id,
            "portfolio_score": row.portfolio_score,
            "total_repos": row.total_repos,
            "live_projects_count": row.live_projects_count,
            "primary_languages": row.primary_languages,
            "strengths": row.strengths,
            "weaknesses": row.weaknesses,
            "calculated_at": row.calculated_at
        }
        decode_json_fields(result, ["primary_languages", "strengths", "weaknesses"])
        return sanitize_data(result)


def _portfolio_audit_categories(checks):
    categories = {}
    if isinstance(checks, str):
        try:
            checks = json.loads(checks)
        except json.JSONDecodeError:
            checks = []
    for check in checks or []:
        category = check.get("category")
        if not category:
            continue
        summary = categories.setdefault(category, {"score": 0, "max_score": 0})
        summary["score"] += check.get("points", 0)
        summary["max_score"] += check.get("max_points", 0)
    return categories


@app.post("/candidates/{candidate_id}/portfolio-site", tags=["Portfolio"])
def audit_candidate_portfolio(candidate_id: int, body: PortfolioLinkPayload):
    """Audit and save the candidate's public portfolio website."""
    with get_db() as db:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        candidate_name = candidate.full_name
        candidate_email = candidate.email

    try:
        result = audit_portfolio_site(body.portfolio_url, candidate_name, candidate_email)
    except PortfolioAuditError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    with get_db() as db:
        audit = db.query(PortfolioAudit).filter(PortfolioAudit.candidate_id == candidate_id).first()
        if audit is None:
            audit = PortfolioAudit(candidate_id=candidate_id)
            db.add(audit)
        audit.portfolio_url = result["portfolio_url"]
        audit.overall_score = result["overall_score"]
        audit.checks = result["checks"]
        audit.strengths = result["strengths"]
        audit.weaknesses = result["weaknesses"]
        db.flush()
        result["candidate_id"] = candidate_id
        result["category_scores"] = _portfolio_audit_categories(result["checks"])
        result["analyzed_at"] = audit.analyzed_at
        return sanitize_data(result)

# JOB MATCHING ENDPOINTS

@app.post("/candidates/{candidate_id}/match", tags=["Job Matching"])
def run_job_matching(candidate_id: int):
    """Run vector + keyword match and save scores into PostgreSQL."""
    try:
        from job_matching_engine import match_candidate_to_jobs, save_matches_to_database

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
    with get_db() as db:
        matches = db.query(JobMatch, Job).join(Job, JobMatch.job_id == Job.id).filter(
            JobMatch.candidate_id == candidate_id
        ).order_by(JobMatch.match_score.desc()).all()
        
        rows = []
        for match, job in matches:
            row = {
                "id": match.id,
                "candidate_id": match.candidate_id,
                "job_id": match.job_id,
                "match_score": match.match_score,
                "matched_skills": match.matched_skills,
                "missing_skills": match.missing_skills,
                "calculated_at": match.calculated_at,
                "title": job.title,
                "company": job.company,
                "job_type": job.job_type,
                "location": job.location
            }
            if isinstance(row.get("matched_skills"), str):
                row["matched_skills"] = json.loads(row["matched_skills"])
            if isinstance(row.get("missing_skills"), str):
                row["missing_skills"] = json.loads(row["missing_skills"])
            rows.append(row)
        
        return sanitize_data(rows)

# EMPLOYER & JOBS ENDPOINTS

@app.get("/jobs/", tags=["Jobs"])
def list_jobs():
    """List open jobs ordered by ID."""
    with get_db() as db:
        jobs = db.query(Job).order_by(Job.id.desc()).all()
        rows = []
        for job in jobs:
            row = {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "job_type": job.job_type,
                "required_skills": job.required_skills,
                "description": job.description,
                "location": job.location,
                "posted_ad": job.posted_ad
            }
            decode_json_fields(row, ["required_skills"])
            rows.append(row)
        
        return sanitize_data(rows)


# ---------------------------------------------------------------------------
# NOTE: the SPA static mount lives at the very END of this file. It must be
# registered after every API route, otherwise it shadows them.
# ---------------------------------------------------------------------------


@app.post("/jobs/", tags=["Jobs"])
def create_or_update_job(job: JobPayload):
    """Create a job or overwrite the row with the same title and company."""
    title, company = job.title.strip(), job.company.strip()
    skills = [skill.strip() for skill in job.required_skills if skill and skill.strip()]
    if not title or not company or not skills:
        raise HTTPException(status_code=400, detail="Title, company, and at least one required skill are required.")
    
    with get_db() as db:
        try:
            existing = db.query(Job).filter(Job.title == title, Job.company == company).order_by(Job.id.desc()).first()
            skills_json = json.dumps(skills)
            description = job.description.strip() if job.description else None
            location = job.location.strip() if job.location else None
            
            if existing:
                existing.job_type = job.job_type
                existing.required_skills = skills_json
                existing.description = description
                existing.location = location
                existing.posted_ad = datetime.now()
                job_id, action = existing.id, "updated"
            else:
                new_job = Job(
                    title=title,
                    company=company,
                    job_type=job.job_type,
                    required_skills=skills_json,
                    description=description,
                    location=location,
                    posted_ad=datetime.now()
                )
                db.add(new_job)
                db.flush()
                job_id, action = new_job.id, "created"
            
            db.commit()
            return {"message": f"Job {action} successfully.", "job_id": job_id, "action": action}
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))

@app.get("/employer/candidates", tags=["Employer"])
def search_candidates(skill: str | None = None):
    """Search candidates using standard SQL pattern matching."""
    with get_db() as db:
        query = db.query(
            Candidate.id,
            Candidate.full_name,
            Candidate.email,
            Resume.skills,
            Resume.location,
            PortfolioScore.portfolio_score
        ).outerjoin(Resume, Candidate.id == Resume.candidate_id)\
         .outerjoin(PortfolioScore, Candidate.id == PortfolioScore.candidate_id)
        
        if skill and skill.strip():
            # Resume.skills is JSONB, which has no LIKE operator — cast to
            # text first so pattern matching works on PostgreSQL.
            pattern = f"%{skill.strip().lower()}%"
            query = query.filter(cast(Resume.skills, Text).ilike(pattern))
        
        query = query.order_by(PortfolioScore.portfolio_score.desc().nullslast())
        rows = query.all()
        
        results = []
        for row in rows:
            result = {
                "id": row.id,
                "full_name": row.full_name,
                "email": row.email,
                "skills": row.skills,
                "location": row.location,
                "portfolio_score": row.portfolio_score
            }
            if isinstance(result.get("skills"), str):
                try:
                    result["skills"] = json.loads(result["skills"])
                except json.JSONDecodeError:
                    pass
            results.append(result)
        
        return sanitize_data(results)

@app.get("/employer/jobs/{job_id}/candidates", tags=["Employer"])
def get_candidates_for_job(job_id: int):
    """Get candidate matches for a specific job position."""
    with get_db() as db:
        matches = db.query(JobMatch, Candidate, PortfolioScore).join(
            Candidate, JobMatch.candidate_id == Candidate.id
        ).outerjoin(
            PortfolioScore, Candidate.id == PortfolioScore.candidate_id
        ).filter(JobMatch.job_id == job_id).order_by(JobMatch.match_score.desc()).all()
        
        rows = []
        for match, candidate, portfolio in matches:
            row = {
                "id": candidate.id,
                "full_name": candidate.full_name,
                "email": candidate.email,
                "match_score": match.match_score,
                "matched_skills": match.matched_skills,
                "missing_skills": match.missing_skills,
                "portfolio_score": portfolio.portfolio_score if portfolio else None
            }
            if isinstance(row.get("matched_skills"), str):
                try:
                    row["matched_skills"] = json.loads(row["matched_skills"])
                except json.JSONDecodeError:
                    pass
            if isinstance(row.get("missing_skills"), str):
                try:
                    row["missing_skills"] = json.loads(row["missing_skills"])
                except json.JSONDecodeError:
                    pass
            rows.append(row)

        return sanitize_data(rows)


# ---------------------------------------------------------------------------
# Serve the vanilla HTML/CSS/JS frontend (replaces the old Streamlit app).
# Registered LAST on purpose: the "/" mount matches every path, so any API
# route defined after it would be shadowed. API routes above take
# precedence; anything else falls back to the SPA.
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

if FRONTEND_DIR.is_dir():
    @app.get("/", include_in_schema=False)
    def serve_spa_root():
        index = FRONTEND_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index), media_type="text/html")
        return {"status": "ok", "frontend": "missing"}

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
