import os
import mysql.connector
from dotenv import load_dotenv
from resume_schema import CandidateFinalScores

load_dotenv("token.env")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")


def calculate_scores(candidate_id: int) -> CandidateFinalScores | None:
    """
    Fetches portfolio and ATS metrics, calculates the 6 AI scores,
    and returns a validated CandidateFinalScores Pydantic object.
    """
    connection = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch portfolio score
        cursor.execute(
            "SELECT portfolio_score FROM portfolio_scores WHERE candidate_id = %s", 
            (candidate_id,)
        )
        portfolio = cursor.fetchone()

        # Fetch ATS report scores
        cursor.execute(
            """
            SELECT experience_score, projects_score, skills_score, 
                   contact_score, summary_score, formatting_score 
            FROM ats_reports WHERE candidate_id = %s
            """, 
            (candidate_id,)
        )
        ats = cursor.fetchone()

        if not portfolio or not ats:
            print(f"Data missing for candidate_id={candidate_id}")
            return None

        # Formulas
        portfolio_quality = float(portfolio["portfolio_score"])
        project_experience = min((ats["experience_score"] + ats["projects_score"]) * 2.5, 100.0)
        engineering_readiness = min(ats["skills_score"] * 5.0, 100.0)
        communication = min((ats["contact_score"] + ats["summary_score"] + ats["formatting_score"]) * 3.0, 100.0)
        leadership = min((portfolio_quality * 0.5) + (ats["experience_score"] * 1.5), 100.0)

        # Dividing in to different impact sections like 0 percent impact of this and that ...
        hiring_confidence = (
            (engineering_readiness * 0.30) +
            (portfolio_quality * 0.25) +
            (project_experience * 0.20) +
            (communication * 0.15) +
            (leadership * 0.10)
        )

        return CandidateFinalScores(
            candidate_id=candidate_id,
            portfolio_quality=round(portfolio_quality, 1),
            project_experience=round(project_experience, 1),
            engineering_readiness=round(engineering_readiness, 1),
            communication=round(communication, 1),
            leadership=round(leadership, 1),
            hiring_confidence=round(hiring_confidence, 1)
        )

    finally:
        cursor.close()
        connection.close()


def save_final_scores_to_database(scores: CandidateFinalScores):
    """
    Saves or updates CandidateFinalScores in MySQL.
    """
    if not scores:
        return

    connection = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    cursor = connection.cursor()

    try:
        query = """
            INSERT INTO candidate_final_scores (
                candidate_id, portfolio_quality, project_experience, 
                engineering_readiness, communication, leadership, hiring_confidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                portfolio_quality = VALUES(portfolio_quality),
                project_experience = VALUES(project_experience),
                engineering_readiness = VALUES(engineering_readiness),
                communication = VALUES(communication),
                leadership = VALUES(leadership),
                hiring_confidence = VALUES(hiring_confidence)
        """
        
        cursor.execute(query, (
            scores.candidate_id, 
            scores.portfolio_quality, 
            scores.project_experience,
            scores.engineering_readiness, 
            scores.communication, 
            scores.leadership, 
            scores.hiring_confidence
        ))
        
        connection.commit()
        print(f"Scores successfully saved for candidate_id={scores.candidate_id}")

    except mysql.connector.Error as e:
        connection.rollback()
        print(f"Error saving candidate scores: {e}")
        raise

    finally:
        cursor.close()
        connection.close()



test_id = 2
scores = calculate_scores(test_id)
save_final_scores_to_database(scores)