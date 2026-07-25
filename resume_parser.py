import pdfplumber
import os 
import json 
import instructor
from openai import OpenAI
from dotenv import load_dotenv
from resume_schema import ResumeData,AtsReport,Experience
import mysql.connector
from datetime import datetime
import re
load_dotenv("token.env")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

api_key = os.environ.get("Api_key")

 
# instructor wraps the normal OpenAI client so that when we
# ask for a specific Pydantic model as response_model, we get back a
# validated instance of that model directly - not raw JSON text.

client = instructor.from_openai(OpenAI(api_key=api_key))

filename = "rs.pdf"

# use this function for raw text and use second one because the details in raw text 
# is unknown like whats the name etc so llm have knowledge so we i used llm function to structure this according to schema
 
def resume_parser(filename):
    text = ""
    links = []

    try:

        # safety first that file exists or not
        if not os.path.exists(filename):
            print(f"{filename} does not exists")
            return {"text" : "", "links": ""}
        
        # safety first that file is empty or not
        if os.path.getsize(filename) == 0:
            print(f"File '{filename}' is empty!")
            return {"text": "", "links": []}
        

        with pdfplumber.open(filename) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
                
                if page.hyperlinks:
                    for link in page.hyperlinks:
                        if link.get("uri"):
                            links.append(link["uri"])

        
        return {
            "text": text,
            "links": list(set(links))
        }
    
    except Exception as e:
        print(f"parser failed {e}")
        return {"text": "", "links": []}


def extract_resume_data(raw_text :str) -> ResumeData:
    
    """
    Takes raw resume text (from pdfplumber) and returns a validated
    ResumeData object using an LLM. this function only deals with text in, structured data out. """
     
    response  = client.chat.completions.create(model="gpt-4o-mini",response_model=ResumeData,messages=[{ "role": "system",
            "content": (
                "You are a resume parser. Extract structured information "
                "from the resume text provided. Only use information that "
                "is actually present in the text - do not invent details."
                "Only include formal certifications with an issuing body or platform — exclude general statements or summaries"
            )},
            {"role":"user","content":raw_text}])
    
    return response

def save_resume_to_database(candidate_id:int,resume_data:ResumeData,raw_text:str):
    """
    Saves a candidate's parsed resume data to MySQL.
 
    Because 'resumes' has a UNIQUE constraint on candidate_id, this uses
    INSERT ... ON DUPLICATE KEY UPDATE - MySQL automatically inserts a new
    row if this candidate has no resume yet, or updates their existing row
    if they do. This replaces the older resume with the newest one.
    """
 
    # education and projects are lists of Pydantic objects - convert each
    # one to a plain dict first (.model_dump()), then the whole list to a
    # JSON string, since MySQL's JSON column type needs a JSON string, not
    # raw Python objects.
    education_json = json.dumps([edu.model_dump() for edu in resume_data.education or []])
    projects_json = json.dumps([proj.model_dump() for proj in resume_data.projects or []])
    skills_json = json.dumps(resume_data.skills or [])
    certifications_json = json.dumps(resume_data.certifications or [])
    experience_json = json.dumps([exp.model_dump() for exp in resume_data.experience or []])

    connection = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = connection.cursor()
    try:

        cursor.execute("Select id from candidates where id = %s",(candidate_id,))
        candidate = cursor.fetchone()
        
        if candidate is None:
            print(f"Candidate with ID {candidate_id} does not exist.")
            return False

        
        cursor.execute("""
            INSERT INTO resumes
                (candidate_id, full_name, email, phone, location, github_url,
                 linkedin_url, skills, certifications, education, projects,
                 raw_text, uploaded_at, parsed_at,experience)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
            ON DUPLICATE KEY UPDATE
                full_name = VALUES(full_name),
                email = VALUES(email),
                phone = VALUES(phone),
                location = VALUES(location),
                github_url = VALUES(github_url),
                linkedin_url = VALUES(linkedin_url),
                skills = VALUES(skills),
                certifications = VALUES(certifications),
                education = VALUES(education),
                projects = VALUES(projects),
                raw_text = VALUES(raw_text),
                parsed_at = VALUES(parsed_at),
                experience = VALUES(experience)
            """,
            (
                candidate_id,
                resume_data.full_name,
                resume_data.email,
                resume_data.phone,
                resume_data.location,
                resume_data.github_url,
                resume_data.linkedin_url,
                skills_json,
                certifications_json,
                education_json,
                projects_json,
                raw_text,
                datetime.now(),
                datetime.now(),
                experience_json
            )
        )

        connection.commit()
        print(f"Resume saved for candidate_id={candidate_id}.")

    except mysql.connector.Error as e:
        connection.rollback()
        print(f"Something went wrong, nothing was saved: {e}")
        raise
 
    finally:
        cursor.close()
        connection.close()

def generate_ats_report(resume_data,raw_text):
    score = 0

    strengths = []
    weaknesses = []
    suggestions = []
    missing_sections = []

    keyword_matches = []
    missing_keywords = []

    # Contact Information
    contact_Score = 0 

    if resume_data.full_name:
        contact_Score += 3
    else:
        suggestions.append("Add your full name.")

    if resume_data.email:
        contact_Score +=4
    else:
        suggestions.append("Email missing.")
    
    if resume_data.phone:
        contact_Score += 3
    else:
        weaknesses.append("Phone number missing")

    if resume_data.linkedin_url:
        contact_Score += 2
        strengths.append("LinkedIn profile available")
    else:
        suggestions.append("Add LinkedIn profile.")

    if resume_data.github_url:
        contact_Score += 2
        strengths.append("GitHub profile available")
    else:
        suggestions.append("Add GitHub profile.")

    if resume_data.location:
        contact_Score += 1

    # Professional Summary
    summary_score = 0
    if "summary" in raw_text.lower():
        summary_score +=10
        strengths.append("Professional summary found")
    
    else:

        missing_sections.append("Professional Summary")

        suggestions.append("Add a professional summary.")

    # Skills
    skills_score = 0
    skill_count = len(resume_data.skills)


    if skill_count >= 15:
        skills_score = 20

    elif skill_count >= 10:
        skills_score = 17

    elif skill_count >= 7:
        skills_score = 14

    elif skill_count >= 4:
        skills_score = 10

    else:

        skills_score = 5

        weaknesses.append("Very few technical skills")

        suggestions.append("Add more relevant technical skills.")
     
    
    # Education
    education_score = 10 if resume_data.education else 0

    if not resume_data.education:

        missing_sections.append("Education")

    # Projects
    project_count = len(resume_data.projects)

    if project_count >= 3:

        projects_score = 10

    elif project_count == 2:

        projects_score = 8

    elif project_count == 1:

        projects_score = 5

    else:

        projects_score = 0

        missing_sections.append("Projects")
        suggestions.append("Add 2-3 good projects.")
    
    # Certifications
    if not resume_data.certifications:
        certifications_score = 0
    else:
        cert_count = len(resume_data.certifications)

        if cert_count >= 3:
            certifications_score = 5

        elif cert_count >= 1:
            certifications_score = 3

        else:
            certifications_score = 0
            suggestions.append("Consider adding certifications.")

    # Experience and achievements
    experience_score = 0

    if not resume_data.experience:

        weaknesses.append("No work experience section found.")
        missing_sections.append("Experience")
        suggestions.append("Add internships, freelance work or professional experience.")

    else:

        strengths.append("Work experience section found.")

        # Base score for having experience
        experience_score += 10

        for exp in resume_data.experience:

          
            # Company Name
            if exp.company:
                experience_score += 2

            # Job Title
            if exp.job_title:
                experience_score += 2

            # Employment Dates
            if exp.start_date and (exp.end_date or exp.currently_working):
                experience_score += 4

            # Description
            if exp.description and len(exp.description.split()) >= 20:
                experience_score += 4

            # Technologies Used
            if exp.technologies:
                experience_score += 3

            # Achievements
            if exp.achievements:

                experience_score += 5
                achievement_text = " ".join(exp.achievements)

                if re.search(r"\d+[%+]?", achievement_text):
                    experience_score += 5
                else:
                    suggestions.append(
                        "Include measurable achievements in your work experience (e.g'Improved performance by 30%')"
                    )

    # Maximum 30 points
    experience_score = min(experience_score, 30)

    # Formatting
    formatting_score = 10

    words = len(raw_text.split())

    if words < 250:

        formatting_score -= 2

        suggestions.append("Resume is too short.")

    if raw_text.count("\n") < 15:

        formatting_score -= 2

    if len(raw_text) > 6000:

        formatting_score -= 2

        suggestions.append("Resume is too long.")


    # Keywords
    ats_keywords = [
        "Python",
        "SQL",
        "Git",
        "Docker",
        "AWS",
        "FastAPI",
        "Machine Learning",
        "REST API",
        "CI/CD",
        "Linux"
    ]    

    for keyword in ats_keywords:

        if keyword.lower() in raw_text.lower():

            keyword_matches.append(keyword)

        else:

            missing_keywords.append(keyword)


    # Final Score
    score = (
        contact_Score
        + summary_score
        + skills_score
        + education_score
        + experience_score
        + projects_score
        + certifications_score
        + formatting_score
    )

    score = min(score,100)

    # Recommendation
    if score >= 90:

        recommendation = "Excellent"

    elif score >= 75:

        recommendation = "Strong"

    elif score >= 60:

        recommendation = "Needs Improvement"

    else:

        recommendation = "Poor"


    return AtsReport(

        overall_score=score,
        contact_score=contact_Score,
        summary_score=summary_score,
        skills_score=skills_score,
        experience_score=experience_score,
        education_score=education_score,
        projects_score=projects_score,
        certifications_score=certifications_score,
        formatting_score=formatting_score,
        strengths=strengths,
        weaknesses=weaknesses,
        missing_sections=missing_sections,
        keyword_matches=keyword_matches,
        missing_keywords=missing_keywords,
        suggestions=suggestions,
        hiring_recommendation=recommendation
    )

def save_ats_report_to_database(candidate_id: int, ats_report):
    connection = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    cursor = connection.cursor()

    try:
        query = """
            INSERT INTO ats_reports (
                candidate_id, overall_score, contact_score, summary_score,
                skills_score, experience_score, education_score, projects_score,
                certifications_score, formatting_score, strengths, weaknesses,
                missing_sections, keyword_matches, missing_keywords,
                suggestions, hiring_recommendation, calculated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON DUPLICATE KEY UPDATE
                overall_score = VALUES(overall_score),
                contact_score = VALUES(contact_score),
                summary_score = VALUES(summary_score),
                skills_score = VALUES(skills_score),
                experience_score = VALUES(experience_score),
                education_score = VALUES(education_score),
                projects_score = VALUES(projects_score),
                certifications_score = VALUES(certifications_score),
                formatting_score = VALUES(formatting_score),
                strengths = VALUES(strengths),
                weaknesses = VALUES(weaknesses),
                missing_sections = VALUES(missing_sections),
                keyword_matches = VALUES(keyword_matches),
                missing_keywords = VALUES(missing_keywords),
                suggestions = VALUES(suggestions),
                hiring_recommendation = VALUES(hiring_recommendation),
                calculated_at = NOW()
        """

        values = (
            candidate_id,
            ats_report.overall_score,
            ats_report.contact_score,
            ats_report.summary_score,
            ats_report.skills_score,
            ats_report.experience_score,
            ats_report.education_score,
            ats_report.projects_score,
            ats_report.certifications_score,
            ats_report.formatting_score,
            json.dumps(ats_report.strengths),
            json.dumps(ats_report.weaknesses),
            json.dumps(ats_report.missing_sections),
            json.dumps(ats_report.keyword_matches),
            json.dumps(ats_report.missing_keywords),
            json.dumps(ats_report.suggestions),
            ats_report.hiring_recommendation
        )

        cursor.execute(query, values)
        connection.commit()
        print(f"ATS Report saved for candidate_id={candidate_id}.")

    except mysql.connector.Error as e:
        connection.rollback()
        print(f"Error saving ATS report: {e}")
        raise

    finally:
        cursor.close()
        connection.close()

result = resume_parser(filename)
resume_data = extract_resume_data(result["text"])
ats_report = generate_ats_report(resume_data,result["text"])
save_resume_to_database(candidate_id=1,resume_data=resume_data,raw_text=result["text"])
print(save_ats_report_to_database(candidate_id=1,ats_report=ats_report))