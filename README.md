# TalentAI: AI-Powered Talent Discovery & Job Matching

**Live demo:** https://talentai-teal.vercel.app/
**API docs:** https://talentai-teal.vercel.app/docs

TalentAI is a full-stack platform that helps candidates and employers find each other. It reads resumes with an LLM, analyses GitHub profiles and portfolio websites, scores how ready a candidate is, and matches candidates to jobs using both exact skill overlap and semantic similarity.

## Features

- **Resume parsing:** upload a PDF and an LLM extracts skills, projects, education, experience and certifications into structured data.
- **ATS report:** scores the resume across contact info, summary, skills, experience, education, projects, certifications and formatting. It lists strengths, weaknesses, missing sections, keyword matches and suggestions.
- **GitHub analyzer:** pulls a candidate's profile and repositories (languages, stars, forks, live demos) and stores them.
- **Portfolio scoring:** turns GitHub activity into a 0 to 100 portfolio score with strengths and weaknesses.
- **Portfolio website audit:** checks a candidate's public portfolio site for contact details, about section, projects, project detail, professional links and page basics.
- **Job matching:** blends exact skill overlap (50%) with OpenAI embedding similarity (50%). It shows matched and missing skills per job. If embeddings are unavailable, it falls back to exact skill matching.
- **Employer portal:** search candidates by skill and rank candidates for a specific job.
- **Job postings:** create and update job listings with required skills.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, FastAPI, Pydantic |
| Database | PostgreSQL on Neon, SQLAlchemy (psycopg2) |
| AI | OpenAI (`gpt-4o-mini` for parsing, `text-embedding-3-small` for matching), Instructor |
| PDF | pdfplumber |
| Frontend | Vanilla HTML, CSS and JavaScript (no build step) |
| Hosting | Vercel (frontend served from the CDN, backend as a serverless function) |

## Project Structure

```
├── fast_api_backend.py         # FastAPI app and all routes
├── database.py                 # SQLAlchemy models and engine (Neon-ready)
├── resume_parser.py            # PDF text extraction, LLM parsing, ATS report
├── resume_schema.py            # Pydantic schemas
├── github_extractor_script.py  # GitHub profile and repo ingestion
├── portfolio_analyzer.py       # GitHub-based portfolio score
├── portfolio_site_auditor.py   # Portfolio website audit
├── job_matching_engine.py      # Skill and embedding job matching
├── Ai_scoring_engine.py        # Final candidate score calculation
├── git_data.sql                # Manual PostgreSQL schema and seed jobs
├── public/                     # Frontend (index.html, app.js, styles.css)
├── vercel.json
├── pyproject.toml
└── requirements.txt
```

## Run Locally

```bash
git clone https://github.com/AyaanHussain1/talent-hunt-and-job-hunting-system.git
cd talent-hunt-and-job-hunting-system
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `token.env` file (never commit it):

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/talent_hunt
Api_key=your_openai_api_key
Github_Token=your_github_token
```

Start the app:

```bash
uvicorn fast_api_backend:app --reload
```

Open http://127.0.0.1:8000. Tables are created automatically on startup.

## Deploy to Vercel + Neon

1. Create a Neon project and copy the **pooled** connection string (the host contains `-pooler`).
2. Push this repo to GitHub and import it in Vercel. No build settings are needed.
3. Add these environment variables in Vercel:

   | Name | Value |
   | --- | --- |
   | `DATABASE_URL` | Neon pooled connection string |
   | `Api_key` | OpenAI API key |
   | `Github_Token` | GitHub personal access token |

4. Deploy, then check `/health`, `/jobs/` and `/docs`.

## API Overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST / GET | `/candidates/` | Create or list candidates |
| GET | `/candidates/{id}` | Full candidate profile |
| POST | `/candidates/{id}/resume` | Upload and parse a PDF resume |
| GET | `/candidates/{id}/ats` | ATS report |
| POST | `/candidates/{id}/github` | Fetch and save GitHub data |
| POST / GET | `/candidates/{id}/portfolio` | Calculate or get portfolio score |
| POST | `/candidates/{id}/portfolio-site` | Audit a portfolio website |
| POST / GET | `/candidates/{id}/match` and `/matches` | Run or read job matches |
| POST / GET | `/jobs/` | Create or list jobs |
| GET | `/employer/candidates` | Search candidates by skill |
| GET | `/employer/jobs/{id}/candidates` | Ranked candidates for a job |
| GET | `/health` | Health check |

## Limitations

- Resume uploads on Vercel are limited to about 4.5 MB per request.
- Resumes with complex layouts (multi-column, text inside images) may not extract cleanly.

## Author

Built by [Ayaan Hussain](https://github.com/AyaanHussain1).
