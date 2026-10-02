import os
import json
from datetime import datetime
from dotenv import load_dotenv
from resume_schema import PortfolioScore
from database import get_db, GitHubProfile, GitHubRepo, Resume, PortfolioScore as PortfolioScoreModel, Candidate

load_dotenv("token.env")

def analyze_portfolio(candidate_id: int) -> PortfolioScore:
    """
    Fetches GitHub repos and resume projects for a candidate from PostgreSQL,
    calculates a portfolio score (0-100), and extracts strengths/weaknesses.
    """

    with get_db() as db:
        repo_rows = db.query(GitHubRepo).join(
            GitHubProfile, GitHubRepo.github_profile_id == GitHubProfile.id
        ).filter(
            GitHubProfile.candidate_id == candidate_id
        ).all()
        repos = [
            {
                "name": repo.name,
                "is_fork": repo.is_fork,
                "description": repo.description,
                "homepage_url": repo.homepage_url,
                "license_key": repo.license_key,
                "size_kb": repo.size_kb,
                "primary_language": repo.primary_language,
                "stargazers_count": repo.stargazers_count,
                "forks_count": repo.forks_count,
            }
            for repo in repo_rows
        ]

        resume_row = db.query(Resume.projects).filter(Resume.candidate_id == candidate_id).first()

        resume_projects = []
        if resume_row is not None and resume_row[0]:
            raw_projects = resume_row[0]
            resume_projects = json.loads(raw_projects) if isinstance(raw_projects, str) else raw_projects
    if not repos:
        return PortfolioScore(candidate_id=candidate_id, portfolio_score=0.0,
            total_repos=0, live_projects_count=0, primary_languages=[],
            strengths=[], weaknesses=["No GitHub repositories found."]
            )

    strengths = []
    weaknesses = []
    score = 0

    non_forks = [r for r in repos if not r["is_fork"]]
    total_non_forks = len(non_forks)

    # repo scores
    if total_non_forks >= 15:
        score += 15
    elif total_non_forks >= 8:
        score += 10
    elif total_non_forks >= 2:
        score += 5
    else:
        weaknesses.append("low number of original repositories")

    live_projects = 0

    for repo in non_forks:
        if repo["description"]:
            score += 1
        if repo["homepage_url"]:
            score += 2
            live_projects += 1
        if repo["license_key"]:
            score += 1
        if repo["size_kb"] and repo["size_kb"] > 100:
            score += 1

    if live_projects > 0:
        strengths.append(f"Has {live_projects} deployed projects with live URLs.")

    # Tech scores Reading primary_language column from github_repos table
    languages = list(set(r["primary_language"] for r in repos if r["primary_language"]))
    score += min(len(languages) * 5, 25)

    if len(languages) >= 3:
        strengths.append(f"Multi-language exposure: {', '.join(languages)}")

    # Community Engagement
    total_stars = sum(r["stargazers_count"] or 0 for r in repos)
    total_forks = sum(r["forks_count"] or 0 for r in repos)
    score += min((total_stars * 3) + (total_forks * 3), 15)

    if total_stars > 0:
        strengths.append(f"Earned {total_stars} stars across repositories.")

    # Resume Alignment (Max 20 Points)
    if resume_projects:
        repo_names = [r["name"].lower() for r in repos]
        matched_count = 0

        for proj in resume_projects:
            proj_name = proj.get("title", "").lower()
            if any(name in proj_name or proj_name in name for name in repo_names):
                matched_count += 1

        alignment_points = (matched_count / len(resume_projects)) * 20
        score += alignment_points

        if matched_count > 0:
            strengths.append(f"Verified {matched_count} projects between Resume and GitHub.")
    else:
        weaknesses.append("No projects found on resume to match with GitHub.")

    final_score = round(min(score, 100.0), 2)

    return PortfolioScore(
        candidate_id=candidate_id,
        portfolio_score=final_score,
        total_repos=total_non_forks,
        live_projects_count=live_projects,
        primary_languages=languages,
        strengths=strengths,
        weaknesses=weaknesses
    )

def save_portfolio_to_database(portfolio_data: PortfolioScore):
    
    "Saves or updates the calculated portfolio score into PostgreSQL."
    
    with get_db() as db:
        try:
            existing = db.query(PortfolioScoreModel).filter(
                PortfolioScoreModel.candidate_id == portfolio_data.candidate_id
            ).first()
            
            now = datetime.now()
            
            if existing:
                existing.portfolio_score = portfolio_data.portfolio_score
                existing.total_repos = portfolio_data.total_repos
                existing.live_projects_count = portfolio_data.live_projects_count
                existing.primary_languages = json.dumps(portfolio_data.primary_languages)
                existing.strengths = json.dumps(portfolio_data.strengths)
                existing.weaknesses = json.dumps(portfolio_data.weaknesses)
                existing.calculated_at = now
            else:
                new_score = PortfolioScoreModel(
                    candidate_id=portfolio_data.candidate_id,
                    portfolio_score=portfolio_data.portfolio_score,
                    total_repos=portfolio_data.total_repos,
                    live_projects_count=portfolio_data.live_projects_count,
                    primary_languages=json.dumps(portfolio_data.primary_languages),
                    strengths=json.dumps(portfolio_data.strengths),
                    weaknesses=json.dumps(portfolio_data.weaknesses),
                    calculated_at=now,
                )
                db.add(new_score)
            
            db.commit()
            print(f"Portfolio score successfully saved for candidate_id={portfolio_data.candidate_id}.")
            
        except Exception as e:
            db.rollback()
            print(f"Error saving portfolio score to database: {e}")
            raise

if __name__ == "__main__":
    # Manual local test only. Do not query the database when FastAPI imports this module.
    candidate = 1
    score_result = analyze_portfolio(candidate)
    save_portfolio_to_database(score_result)
