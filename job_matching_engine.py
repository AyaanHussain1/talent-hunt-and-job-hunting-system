import os
import json
import mysql.connector
from dotenv import load_dotenv
from resume_schema import JobMatch, JobMatchingResult
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

load_dotenv("token.env")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

# Load the model only when a matching request is made.  Creating it at import
# time blocks FastAPI startup and can trigger a model download.
embeddings = None


def get_embeddings():
    global embeddings
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return embeddings

def calculate_match(candidate_skills: list[str], required_skills: list[str], semantic_score: float = None) -> dict:
    candidate_skill_set = set(s.lower() for s in candidate_skills)
    required_skill_set = set(s.lower() for s in required_skills)

    matched = [s for s in required_skills if s.lower() in candidate_skill_set]
    missing = [s for s in required_skills if s.lower() not in candidate_skill_set]

    if len(required_skill_set) == 0:
        exact_score = 0.0
    else:
        exact_score = (len(matched) / len(required_skill_set)) * 100.0

    if semantic_score is not None:
        semantic_pct = max(0.0, min(100.0, semantic_score * 100.0))
        final_score = round((exact_score * 0.5) + (semantic_pct * 0.5), 2)
    else:
        final_score = round(exact_score, 2)

    return {
        "match_score": final_score,
        "matched_skills": matched,
        "missing_skills": missing
    }

def match_candidate_to_jobs(candidate_id: int) -> JobMatchingResult:
    connection = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = connection.cursor(dictionary=True)
    
    try: 
        cursor.execute("SELECT full_name FROM candidates WHERE id = %s", (candidate_id,))
        candidate_row = cursor.fetchone()

        if candidate_row is None:
            raise ValueError(f"Candidate with id={candidate_id} not found.")

        candidate_name = candidate_row["full_name"] or f"Candidate {candidate_id}"

        cursor.execute("SELECT skills FROM resumes WHERE candidate_id = %s", (candidate_id,))
        resume_row = cursor.fetchone()

        if resume_row is None or not resume_row["skills"]:
            raise ValueError(f"No resume found for candidate_id={candidate_id}. Upload a resume first.")

        raw_skills = resume_row["skills"]
        candidate_skills = json.loads(raw_skills) if isinstance(raw_skills, str) else raw_skills
        candidate_skills_text = ", ".join(candidate_skills)

        cursor.execute("SELECT id, title, company, job_type, required_skills FROM jobs")
        jobs = cursor.fetchall()

        if not jobs:
            raise ValueError("No jobs found in database. Add job postings first.")

        documents = []
        for job in jobs:
            req_skills_list = json.loads(job["required_skills"]) if isinstance(job["required_skills"], str) else job["required_skills"]
            content = f"Job Title: {job['title']}. Required Skills: {', '.join(req_skills_list)}"
            
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "job_id": job["id"],
                        "title": job["title"],
                        "company": job["company"],
                        "job_type": job["job_type"],
                        "required_skills": json.dumps(req_skills_list)
                    }
                )
            )

        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=get_embeddings()
        )

        results_with_scores = vectorstore.similarity_search_with_relevance_scores(
            query=f"Candidate Profile Skills: {candidate_skills_text}",
            k=len(jobs)
        )

        matches = []
        for doc, similarity_score in results_with_scores:
            meta = doc.metadata
            required_skills = json.loads(meta["required_skills"])
            
            result = calculate_match(candidate_skills, required_skills, semantic_score=similarity_score)

            matches.append(
                JobMatch(
                    candidate_id=candidate_id,
                    job_id=meta["job_id"],
                    job_title=meta["title"],
                    company=meta["company"],
                    job_type=meta["job_type"],
                    match_score=result["match_score"],
                    matched_skills=result["matched_skills"],
                    missing_skills=result["missing_skills"]
                )
            )

        matches.sort(key=lambda x: x.match_score, reverse=True)

        return JobMatchingResult(
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            total_jobs_evaluated=len(jobs),
            matches=matches
        )

    finally:
        cursor.close()
        connection.close()

def save_matches_to_database(matching_result: JobMatchingResult):
    connection = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    cursor = connection.cursor()
    try:
        for match in matching_result.matches:
            cursor.execute(
                """
                INSERT INTO job_matches
                    (candidate_id, job_id, match_score, matched_skills, missing_skills, calculated_at)
                VALUES (%s, %s, %s, %s, %s, NOW()) 
                ON DUPLICATE KEY UPDATE
                    match_score = VALUES(match_score),
                    matched_skills = VALUES(matched_skills),
                    missing_skills = VALUES(missing_skills),
                    calculated_at = NOW()
                """, (
                    match.candidate_id,
                    match.job_id,
                    match.match_score,
                    json.dumps(match.matched_skills),
                    json.dumps(match.missing_skills),
                )
            )

        connection.commit()
    except mysql.connector.Error as e:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

# Prevent execution on import when running via FastAPI
if __name__ == "__main__":
    cid = 1
    res = match_candidate_to_jobs(cid)
    save_matches_to_database(res)
    print(f"Match evaluation complete for candidate_id={cid}")
