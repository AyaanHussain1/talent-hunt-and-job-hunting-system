-- ============================================================================
-- TalentAI — PostgreSQL schema (SQLAlchemy models in database.py are
-- authoritative; the FastAPI app auto-creates these tables on startup via
-- init_db(). This file is the manual fallback: run it with
--   psql "$DATABASE_URL" -f git_data.sql
-- ============================================================================

-- Job type enum used by jobs.job_type
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_type_enum') THEN
        CREATE TYPE job_type_enum AS ENUM
            ('Full-Time', 'Remote', 'Freelance', 'Client', 'Internal', 'Startup');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS candidates (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS github_profiles (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    github_id VARCHAR(50) NOT NULL,
    github_username VARCHAR(100) NOT NULL UNIQUE,
    bio TEXT NULL,
    company VARCHAR(255) NULL,
    location VARCHAR(255) NULL,
    public_repos INTEGER NOT NULL DEFAULT 0,
    followers INTEGER NOT NULL DEFAULT 0,
    account_created_at TIMESTAMPTZ NULL,
    last_fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS github_repos (
    id SERIAL PRIMARY KEY,
    github_profile_id INTEGER NOT NULL REFERENCES github_profiles(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    github_repo_id VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    primary_language VARCHAR(100) NULL,
    is_fork BOOLEAN NOT NULL DEFAULT FALSE,
    stargazers_count INTEGER NOT NULL DEFAULT 0,
    forks_count INTEGER NOT NULL DEFAULT 0,
    open_issues_count INTEGER NOT NULL DEFAULT 0,
    size_kb INTEGER NOT NULL DEFAULT 0,
    license_key VARCHAR(50) NULL,
    homepage_url VARCHAR(500) NULL,
    topics JSONB NULL,
    repo_created_at TIMESTAMPTZ NULL,
    repo_updated_at TIMESTAMPTZ NULL,
    repo_pushed_at TIMESTAMPTZ NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_profile_repo UNIQUE (github_profile_id, github_repo_id)
);
CREATE INDEX IF NOT EXISTS idx_github_repos_profile_id ON github_repos (github_profile_id);

CREATE TABLE IF NOT EXISTS resumes (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL UNIQUE REFERENCES candidates(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    full_name VARCHAR(200) NULL,
    email VARCHAR(200) NULL,
    phone VARCHAR(50) NULL,
    location VARCHAR(200) NULL,
    github_url VARCHAR(500) NULL,
    linkedin_url VARCHAR(500) NULL,
    skills JSONB NULL,
    certifications JSONB NULL,
    education JSONB NULL,
    projects JSONB NULL,
    experience JSONB NULL,
    raw_text TEXT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parsed_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS portfolio_scores (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL UNIQUE REFERENCES candidates(id) ON DELETE CASCADE,
    portfolio_score DOUBLE PRECISION NOT NULL,
    total_repos INTEGER NOT NULL DEFAULT 0,
    live_projects_count INTEGER NOT NULL DEFAULT 0,
    primary_languages JSONB NULL,
    strengths JSONB NULL,
    weaknesses JSONB NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_audits (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL UNIQUE REFERENCES candidates(id) ON DELETE CASCADE,
    portfolio_url VARCHAR(1000) NOT NULL,
    overall_score INTEGER NOT NULL,
    checks JSONB NOT NULL,
    strengths JSONB NOT NULL,
    weaknesses JSONB NOT NULL,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ats_reports (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL UNIQUE REFERENCES candidates(id) ON DELETE CASCADE,
    overall_score INTEGER NOT NULL,
    contact_score INTEGER NULL,
    summary_score INTEGER NULL,
    skills_score INTEGER NULL,
    experience_score INTEGER NULL,
    education_score INTEGER NULL,
    projects_score INTEGER NULL,
    certifications_score INTEGER NULL,
    formatting_score INTEGER NULL,
    strengths JSONB NULL,
    weaknesses JSONB NULL,
    missing_sections JSONB NULL,
    keyword_matches JSONB NULL,
    missing_keywords JSONB NULL,
    suggestions JSONB NULL,
    hiring_recommendation VARCHAR(50) NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidate_final_scores (
    candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
    portfolio_quality DOUBLE PRECISION NULL,
    project_experience DOUBLE PRECISION NULL,
    engineering_readiness DOUBLE PRECISION NULL,
    communication DOUBLE PRECISION NULL,
    leadership DOUBLE PRECISION NULL,
    hiring_confidence DOUBLE PRECISION NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    job_type job_type_enum NOT NULL,
    required_skills JSONB NOT NULL,
    description TEXT NULL,
    location VARCHAR(255) NULL,
    posted_ad TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_title_company ON jobs (title, company);

CREATE TABLE IF NOT EXISTS job_matches (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    match_score DOUBLE PRECISION NOT NULL,
    matched_skills JSONB NOT NULL,
    missing_skills JSONB NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_candidate_job UNIQUE (candidate_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_job_matches_candidate_id ON job_matches (candidate_id);
CREATE INDEX IF NOT EXISTS idx_job_matches_job_id ON job_matches (job_id);

-- ----------------------------------------------------------------------------
-- Seed job postings (safe to re-run)
-- ----------------------------------------------------------------------------
INSERT INTO jobs (title, company, job_type, required_skills, description, location) VALUES
    ('Junior ML Engineer', 'TechCorp', 'Full-Time',
     '["Python", "Scikit-learn", "Pandas", "NumPy", "Machine Learning"]',
     'Build and deploy ML models.', 'Karachi'),
    ('Data Analyst', 'DataFlow', 'Remote',
     '["Python", "SQL", "Pandas", "Matplotlib", "Seaborn"]',
     'Analyze and visualize business data.', 'Remote'),
    ('AI Engineer Intern', 'AI Startup', 'Startup',
     '["Python", "Deep Learning", "RAG Pipelines", "Git"]',
     'Work on cutting-edge AI systems.', 'Karachi'),
    ('Backend Developer', 'WebCo', 'Full-Time',
     '["Python", "FastAPI", "SQL", "Docker", "REST API"]',
     'Build scalable APIs.', 'Remote')
ON CONFLICT DO NOTHING;
