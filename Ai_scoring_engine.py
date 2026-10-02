import os
from datetime import datetime
from dotenv import load_dotenv
from resume_schema import CandidateFinalScores
from database import get_db, PortfolioScore as PortfolioScoreModel, ATSReport, CandidateFinalScore as CandidateFinalScoreModel

load_dotenv("token.env")


def calculate_scores(candidate_id: int) -> CandidateFinalScores | None:
    """
    Fetches portfolio and ATS metrics, calculates the 6 AI scores,
    and returns a validated CandidateFinalScores Pydantic object.
    """
    with get_db() as db:
        try:
            # Fetch portfolio score
            portfolio = db.query(PortfolioScoreModel.portfolio_score).filter(
                PortfolioScoreModel.candidate_id == candidate_id
            ).first()

            # Fetch ATS report scores
            ats = db.query(
                ATSReport.experience_score,
                ATSReport.projects_score,
                ATSReport.skills_score,
                ATSReport.contact_score,
                ATSReport.summary_score,
                ATSReport.formatting_score
            ).filter(ATSReport.candidate_id == candidate_id).first()

            if not portfolio or not ats:
                print(f"Data missing for candidate_id={candidate_id}")
                return None

            # Formulas
            portfolio_quality = float(portfolio[0])
            project_experience = min((ats[0] + ats[1]) * 2.5, 100.0)
            engineering_readiness = min(ats[2] * 5.0, 100.0)
            communication = min((ats[3] + ats[4] + ats[5]) * 3.0, 100.0)
            leadership = min((portfolio_quality * 0.5) + (ats[0] * 1.5), 100.0)

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

        except Exception as e:
            print(f"Error calculating scores: {e}")
            raise


def save_final_scores_to_database(scores: CandidateFinalScores):
    """
    Saves or updates CandidateFinalScores in PostgreSQL.
    """
    if not scores:
        return

    with get_db() as db:
        try:
            existing = db.query(CandidateFinalScoreModel).filter(
                CandidateFinalScoreModel.candidate_id == scores.candidate_id
            ).first()

            if existing:
                existing.portfolio_quality = scores.portfolio_quality
                existing.project_experience = scores.project_experience
                existing.engineering_readiness = scores.engineering_readiness
                existing.communication = scores.communication
                existing.leadership = scores.leadership
                existing.hiring_confidence = scores.hiring_confidence
                existing.calculated_at = datetime.now()
            else:
                new_scores = CandidateFinalScoreModel(
                    candidate_id=scores.candidate_id,
                    portfolio_quality=scores.portfolio_quality,
                    project_experience=scores.project_experience,
                    engineering_readiness=scores.engineering_readiness,
                    communication=scores.communication,
                    leadership=scores.leadership,
                    hiring_confidence=scores.hiring_confidence,
                    calculated_at=datetime.now(),
                )
                db.add(new_scores)

            db.commit()
            print(f"Scores successfully saved for candidate_id={scores.candidate_id}")

        except Exception as e:
            db.rollback()
            print(f"Error saving candidate scores: {e}")
            raise



test_id = 2
scores = calculate_scores(test_id)
save_final_scores_to_database(scores)