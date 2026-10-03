"""PostgreSQL + SQLAlchemy database layer.

All project code talks to the database through this module (engine,
``get_db()`` session helper, and the ORM models below). No raw MySQL or
driver-specific code exists anywhere else in the project.

Connection resolution order:
  1. ``DATABASE_URL`` env var (e.g. ``postgresql://user:pass@host:5432/db``).
     Railway-style ``postgres://...`` URLs are normalized automatically.
  2. ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASSWORD`` / ``DB_NAME``
     (``DB_HOST`` may also be given as ``host:port``).
  3. Local development default: ``postgresql://postgres:postgres@localhost:5432/talent_hunt``.

Tables are created from these models via :func:`init_db` (also called
automatically on FastAPI startup, and manually with ``python database.py``).
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, JSON, ForeignKey, Enum, UniqueConstraint, Index
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.pool import NullPool
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from dotenv import load_dotenv

load_dotenv("token.env")
load_dotenv(".env")


def _normalize_database_url(url: str) -> str:
    """Make a PostgreSQL URL acceptable to SQLAlchemy/psycopg2.

    - ``postgres://`` (Railway, Heroku, ...) -> ``postgresql://``
    - bare ``postgresql://`` stays untouched (uses psycopg2, per requirements)
    - explicit ``postgresql+psycopg2://`` / ``postgresql+psycopg://`` drivers kept
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Newer SQLAlchemy defaults bare "postgresql://" to the psycopg v3 driver,
    # but requirements.txt installs psycopg2 -> pin the driver explicitly.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _build_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url and url.strip():
        return _normalize_database_url(url)

    host = os.environ.get("DB_HOST", "localhost").strip() or "localhost"
    port = (os.environ.get("DB_PORT", "") or "").strip()
    if not port and ":" in host:  # allow DB_HOST="host:1234"
        host, _, port = host.partition(":")
    port = port or "5432"

    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    name = os.environ.get("DB_NAME")
    if all([user, password, name]):
        return _normalize_database_url(f"postgresql://{user}:{password}@{host}:{port}/{name}")
    return _normalize_database_url("postgresql://postgres:postgres@localhost:5432/talent_hunt")


DATABASE_URL = _build_database_url()

connect_args = {"connect_timeout": 10}
sslmode = (os.environ.get("DB_SSLMODE", "") or "").strip()
if not sslmode and "sslmode=" not in DATABASE_URL and "neon.tech" in DATABASE_URL:
    sslmode = "require"  # Neon only accepts TLS connections
if sslmode:
    connect_args["sslmode"] = sslmode

# On Vercel every request may run in a fresh serverless instance, so a
# client-side pool only leaks idle connections. Open a connection per session
# and let Neon's pooler (the "-pooler" host, PgBouncer) do the pooling.
ON_VERCEL = bool(os.environ.get("VERCEL"))

if ON_VERCEL:
    engine = create_engine(DATABASE_URL, poolclass=NullPool, connect_args=connect_args)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=connect_args,
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    github_profiles = relationship("GitHubProfile", back_populates="candidate", cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    portfolio_scores = relationship("PortfolioScore", back_populates="candidate", cascade="all, delete-orphan")
    portfolio_audit = relationship("PortfolioAudit", back_populates="candidate", cascade="all, delete-orphan", uselist=False)
    ats_reports = relationship("ATSReport", back_populates="candidate", cascade="all, delete-orphan")
    final_scores = relationship("CandidateFinalScore", back_populates="candidate", cascade="all, delete-orphan")
    job_matches = relationship("JobMatch", back_populates="candidate", cascade="all, delete-orphan")


class GitHubProfile(Base):
    __tablename__ = "github_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    github_id = Column(String(50), nullable=False)
    github_username = Column(String(100), nullable=False, unique=True)
    bio = Column(Text, nullable=True)
    company = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    public_repos = Column(Integer, default=0, nullable=False)
    followers = Column(Integer, default=0, nullable=False)
    account_created_at = Column(DateTime, nullable=True)
    last_fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="github_profiles")
    repos = relationship("GitHubRepo", back_populates="profile", cascade="all, delete-orphan")


class GitHubRepo(Base):
    __tablename__ = "github_repos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    github_profile_id = Column(Integer, ForeignKey("github_profiles.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    github_repo_id = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    primary_language = Column(String(100), nullable=True)
    is_fork = Column(Boolean, default=False, nullable=False)
    stargazers_count = Column(Integer, default=0, nullable=False)
    forks_count = Column(Integer, default=0, nullable=False)
    open_issues_count = Column(Integer, default=0, nullable=False)
    size_kb = Column(Integer, default=0, nullable=False)
    license_key = Column(String(50), nullable=True)
    homepage_url = Column(String(500), nullable=True)
    topics = Column(JSONB, nullable=True)
    repo_created_at = Column(DateTime, nullable=True)
    repo_updated_at = Column(DateTime, nullable=True)
    repo_pushed_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    profile = relationship("GitHubProfile", back_populates="repos")

    __table_args__ = (
        UniqueConstraint("github_profile_id", "github_repo_id", name="uq_profile_repo"),
        Index("idx_github_repos_profile_id", "github_profile_id"),
    )


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False, unique=True)
    full_name = Column(String(200), nullable=True)
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)
    github_url = Column(String(500), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    skills = Column(JSONB, nullable=True)
    certifications = Column(JSONB, nullable=True)
    education = Column(JSONB, nullable=True)
    projects = Column(JSONB, nullable=True)
    experience = Column(JSONB, nullable=True)
    raw_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    parsed_at = Column(DateTime, nullable=True)

    candidate = relationship("Candidate", back_populates="resumes")


class PortfolioScore(Base):
    __tablename__ = "portfolio_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, unique=True)
    portfolio_score = Column(Float, nullable=False)
    total_repos = Column(Integer, default=0, nullable=False)
    live_projects_count = Column(Integer, default=0, nullable=False)
    primary_languages = Column(JSONB, nullable=True)
    strengths = Column(JSONB, nullable=True)
    weaknesses = Column(JSONB, nullable=True)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="portfolio_scores")


class PortfolioAudit(Base):
    __tablename__ = "portfolio_audits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, unique=True)
    portfolio_url = Column(String(1000), nullable=False)
    overall_score = Column(Integer, nullable=False)
    checks = Column(JSONB, nullable=False)
    strengths = Column(JSONB, nullable=False)
    weaknesses = Column(JSONB, nullable=False)
    analyzed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="portfolio_audit")


class ATSReport(Base):
    __tablename__ = "ats_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, unique=True)
    overall_score = Column(Integer, nullable=False)
    contact_score = Column(Integer, nullable=True)
    summary_score = Column(Integer, nullable=True)
    skills_score = Column(Integer, nullable=True)
    experience_score = Column(Integer, nullable=True)
    education_score = Column(Integer, nullable=True)
    projects_score = Column(Integer, nullable=True)
    certifications_score = Column(Integer, nullable=True)
    formatting_score = Column(Integer, nullable=True)
    strengths = Column(JSONB, nullable=True)
    weaknesses = Column(JSONB, nullable=True)
    missing_sections = Column(JSONB, nullable=True)
    keyword_matches = Column(JSONB, nullable=True)
    missing_keywords = Column(JSONB, nullable=True)
    suggestions = Column(JSONB, nullable=True)
    hiring_recommendation = Column(String(50), nullable=True)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="ats_reports")


class CandidateFinalScore(Base):
    __tablename__ = "candidate_final_scores"
    candidate_id = Column(Integer, ForeignKey("candidates.id", onupdate="CASCADE", ondelete="CASCADE"), primary_key=True)
    portfolio_quality = Column(Float, nullable=True)
    project_experience = Column(Float, nullable=True)
    engineering_readiness = Column(Float, nullable=True)
    communication = Column(Float, nullable=True)
    leadership = Column(Float, nullable=True)
    hiring_confidence = Column(Float, nullable=True)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="final_scores")


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    job_type = Column(Enum("Full-Time", "Remote", "Freelance", "Client", "Internal", "Startup", name="job_type_enum"), nullable=False)
    required_skills = Column(JSONB, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    posted_ad = Column(DateTime, default=datetime.utcnow, nullable=False)

    matches = relationship("JobMatch", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_jobs_title_company", "title", "company"),
    )


class JobMatch(Base):
    __tablename__ = "job_matches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    match_score = Column(Float, nullable=False)
    matched_skills = Column(JSONB, nullable=False)
    missing_skills = Column(JSONB, nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="job_matches")
    job = relationship("Job", back_populates="matches")

    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job"),
        Index("idx_job_matches_candidate_id", "candidate_id"),
        Index("idx_job_matches_job_id", "job_id"),
    )


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Create all tables from the models (no-op if they already exist)."""
    Base.metadata.create_all(bind=engine, checkfirst=True)


def drop_db():
    Base.metadata.drop_all(bind=engine, checkfirst=True)


def _masked_url() -> str:
    try:
        from sqlalchemy.engine import make_url
        u = make_url(DATABASE_URL)
        return f"{u.drivername}://{u.username or '?'}:***@{u.host or 'localhost'}:{u.port or '5432'}/{u.database}"
    except Exception:
        return "postgresql://*** (unparsable URL)"


if __name__ == "__main__":
    print(f"Connecting to {_masked_url()} ...")
    init_db()
    print("OK: all tables are present.")