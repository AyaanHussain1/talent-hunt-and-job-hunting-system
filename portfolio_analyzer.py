import os
import json
import mysql.connector
from dotenv import load_dotenv
from resume_schema import PortfolioScore

load_dotenv("token.env")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

def analyze_portfolio(candidate_id : int) -> PortfolioScore:
    """
    Fetches GitHub repos and resume projects for a candidate from MySQL,
    calculates a portfolio score (0-100), and extracts strengths/weaknesses.
    """

    connection = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = connection.cursor(dictionary=True) # we can easily read through keys thats why dict is true

    try:

        cursor.execute(
            """
            SELECT gr.* 
            FROM github_repos gr
            JOIN github_profiles gp ON gr.github_profile_id = gp.id
            WHERE gp.candidate_id = %s
            """,
            (candidate_id,)
        )

        repos = cursor.fetchall()

        cursor.execute("Select projects from resumes where candidate_id = %s",(candidate_id,))
        resume_row = cursor.fetchone()

        resume_projects = []
        if resume_row is not None and resume_row["projects"]:
            raw_projects = resume_row["projects"]
            resume_projects = json.loads(raw_projects) if isinstance(raw_projects, str) else raw_projects

        # Now handling candidates with no github repo
        if not repos:
            return PortfolioScore(candidate_id=candidate_id,portfolio_score=0.0,
                total_repos=0,live_projects_count=0,primary_languages=[],
                strengths=[],weaknesses=["No GitHub repositories found."]
                )
        
        strengths = []
        weaknesses = []
        score = 0

        non_forks = [r for r in repos if not r.get("is_fork")]
        total_non_forks = len(non_forks)

        # repo scores
        if total_non_forks >=15:
            score +=15
        elif total_non_forks >=8:
            score +=10
        elif total_non_forks >=2:
            score +=5
        else:
            weaknesses.append("low number of original repositories")
        
        live_projects = 0
        
        for repo in non_forks:
            
            if repo.get("description"):
                    score += 1
            if repo.get("homepage_url"):
                score += 2
                live_projects += 1
            if repo.get("license_key"):
                score += 1
            if repo.get("size_kb", 0) > 100:
                score += 1
        
        if live_projects > 0:
            strengths.append(f"Has {live_projects} deployed projects with live URLs.")

        # Tech scores Reading primary_language column from github_repos table
        languages = list(set([r["primary_language"] for r in repos if r.get("primary_language")]))
        score += min(len(languages) * 5, 25)  # multiplying because 1 language is refer to 5 point and 2 lang is 10

        if len(languages) >= 3:
            strengths.append(f"Multi-language exposure: {', '.join(languages)}")

        # Community Engagement
        total_stars = sum(r.get("stargazers_count",0) for r in repos)
        total_forks = sum(r.get("forks_count",0) for r in repos)
        score += min((total_stars * 3) + (total_forks * 3),15)  # sam logic 1 star is 3 points and 1 fork is 3

        if total_stars > 0:
                strengths.append(f"Earned {total_stars} stars across repositories.")

        # Resume Alignment (Max 20 Points)
        if resume_projects:
            repo_names = [r["name"].lower() for r in repos]
            matched_count = 0

            for proj in resume_projects:

                proj_name = proj.get("title","").lower()
                if any(name in proj_name or proj_name in name for name in repo_names):
                    matched_count +=1

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
    finally:
        cursor.close()
        connection.close()

def save_portfolio_to_database(portfolio_data: PortfolioScore):
    
    "Saves or updates the calculated portfolio score into MySQL."
    
    connection = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    cursor = connection.cursor()

    try:
        query = """
            INSERT INTO portfolio_scores (candidate_id, portfolio_score, total_repos, live_projects_count,
                primary_languages, strengths, weaknesses, calculated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                portfolio_score = VALUES(portfolio_score),
                total_repos = VALUES(total_repos),
                live_projects_count = VALUES(live_projects_count),
                primary_languages = VALUES(primary_languages),
                strengths = VALUES(strengths),
                weaknesses = VALUES(weaknesses),
                calculated_at = NOW()
        """

        cursor.execute(
            query,
            (
                portfolio_data.candidate_id,
                portfolio_data.portfolio_score,
                portfolio_data.total_repos,
                portfolio_data.live_projects_count,
                json.dumps(portfolio_data.primary_languages),
                json.dumps(portfolio_data.strengths),
                json.dumps(portfolio_data.weaknesses),
            )
        )

        connection.commit()
        print(f"Portfolio score successfully saved for candidate_id={portfolio_data.candidate_id}.")

    except mysql.connector.Error as e:
        connection.rollback()
        print(f"Error saving portfolio score to database: {e}")
        raise

    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    # Manual local test only. Do not query the database when FastAPI imports this module.
    candidate = 1
    score_result = analyze_portfolio(candidate)
    save_portfolio_to_database(score_result)
