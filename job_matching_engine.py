import os
import json
import math
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from resume_schema import JobMatch, JobMatchingResult
from database import get_db, Candidate, Resume, Job, JobMatch as JobMatchModel

load_dotenv("token.env")

def _embed_texts(texts: list[str]) -> list[list[float]]:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("Api_key")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY or Api_key to enable job matching.")

    response = OpenAI(api_key=api_key).embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    embeddings = [
        item.embedding
        for item in sorted(response.data, key=lambda item: item.index)
    ]
    if len(embeddings) != len(texts):
        raise RuntimeError("The embeddings API returned an incomplete response.")
    return embeddings


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding vectors must have the same dimensions.")

    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot_product / (left_norm * right_norm)

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
    with get_db() as db:
        try:
            candidate_row = db.query(Candidate.full_name).filter(Candidate.id == candidate_id).first()

            if candidate_row is None:
                raise ValueError(f"Candidate with id={candidate_id} not found.")

            candidate_name = candidate_row[0] or f"Candidate {candidate_id}"

            resume_row = db.query(Resume.skills).filter(Resume.candidate_id == candidate_id).first()

            if resume_row is None or not resume_row[0]:
                raise ValueError(f"No resume found for candidate_id={candidate_id}. Upload a resume first.")

            raw_skills = resume_row[0]
            candidate_skills = json.loads(raw_skills) if isinstance(raw_skills, str) else raw_skills
            candidate_skills_text = ", ".join(candidate_skills)

            jobs = db.query(Job).all()

            if not jobs:
                raise ValueError("No jobs found in database. Add job postings first.")

            job_documents = []
            for job in jobs:
                req_skills_list = json.loads(job.required_skills) if isinstance(job.required_skills, str) else job.required_skills
                content = f"Job Title: {job.title}. Required Skills: {', '.join(req_skills_list)}"
                job_documents.append((job, req_skills_list, content))

            # Semantic scores come from OpenAI embeddings. If that call fails
            # (missing key, quota, network) fall back to exact skill overlap
            # instead of failing the whole request.
            try:
                embeddings = _embed_texts(
                    [f"Candidate Profile Skills: {candidate_skills_text}"]
                    + [content for _, _, content in job_documents]
                )
                candidate_embedding = embeddings[0]
                results_with_scores = [
                    (job, required_skills, _cosine_similarity(candidate_embedding, embedding))
                    for (job, required_skills, _), embedding in zip(job_documents, embeddings[1:])
                ]
            except Exception as embed_err:
                print(f"Embeddings unavailable, using exact skill match only: {embed_err}")
                results_with_scores = [(job, required_skills, None) for job, required_skills, _ in job_documents]

            matches = []
            for job, required_skills, similarity_score in results_with_scores:
                result = calculate_match(candidate_skills, required_skills, semantic_score=similarity_score)

                matches.append(
                    JobMatch(
                        candidate_id=candidate_id,
                        job_id=job.id,
                        job_title=job.title,
                        company=job.company,
                        job_type=job.job_type,
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

        except Exception as e:
            raise

def save_matches_to_database(matching_result: JobMatchingResult):
    with get_db() as db:
        try:
            for match in matching_result.matches:
                existing = db.query(JobMatchModel).filter(
                    JobMatchModel.candidate_id == match.candidate_id,
                    JobMatchModel.job_id == match.job_id
                ).first()

                if existing:
                    existing.match_score = match.match_score
                    existing.matched_skills = json.dumps(match.matched_skills)
                    existing.missing_skills = json.dumps(match.missing_skills)
                    existing.calculated_at = datetime.now()
                else:
                    new_match = JobMatchModel(
                        candidate_id=match.candidate_id,
                        job_id=match.job_id,
                        match_score=match.match_score,
                        matched_skills=json.dumps(match.matched_skills),
                        missing_skills=json.dumps(match.missing_skills),
                        calculated_at=datetime.now(),
                    )
                    db.add(new_match)

            db.commit()
        except Exception as e:
            db.rollback()
            raise

# Prevent execution on import when running via FastAPI
if __name__ == "__main__":
    cid = 1
    res = match_candidate_to_jobs(cid)
    save_matches_to_database(res)
    print(f"Match evaluation complete for candidate_id={cid}")
