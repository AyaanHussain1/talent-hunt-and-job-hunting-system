import os
import requests
import json
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values

TOKEN_ENV_PATH = Path(__file__).resolve().with_name("token.env")


def _get_github_token():
    """Read the current GitHub token, including UTF-8-BOM encoded env files."""
    values = dotenv_values(TOKEN_ENV_PATH, encoding="utf-8-sig")
    token = values.get("Github_Token") or os.environ.get("Github_Token")
    return token.strip() if token else None

from database import get_db, GitHubProfile, GitHubRepo, Candidate

def fetch_and_clean_github_data(username):

    """
    Fetches a GitHub profile + repo list, and returns them cleaned and
    ready to insert into the database.It does jonot touch the database -
    this function only deals with GitHub and data cleaning.
    """

    token = _get_github_token()

    headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
    }
    if not token:
        headers.pop("Authorization", None)

    profile_response = requests.get(f"https://api.github.com/users/{username}", headers=headers)
    profile_response.raise_for_status()
    profile_raw = profile_response.json()

    # GitHub only returns 30 repos per request by default. applying Loop on
    # pages (100 per page) until a page comes back empty, so
    # candidates with more than 30 repos are not silently missing data.
    repos_raw = []
    page = 1
    while True:
        repos_response = requests.get(
            f"https://api.github.com/users/{username}/repos",
            headers=headers,
            params={"per_page": 100, "page": page}
        )
        repos_response.raise_for_status()
        page_data = repos_response.json()

        if not page_data:  # empty list means there are no more pages
            break

        repos_raw.extend(page_data)
        page += 1

    if not isinstance(repos_raw, list) or len(repos_raw) == 0:
        return {"profile": {}, "repos": []}

    # to match my github_profile table
    profile_data = {
        "github_id": profile_raw.get("id"),
        "github_username": profile_raw.get("login"),
        "bio": profile_raw.get("bio").strip() if profile_raw.get("bio") else None,
        "company": profile_raw.get("company").strip() if profile_raw.get("company") else None,
        "location": profile_raw.get("location").strip() if profile_raw.get("location") else None,
        "public_repos": profile_raw.get("public_repos", 0),
        "followers": profile_raw.get("followers", 0),
        "account_created_at": (datetime.fromisoformat(profile_raw["created_at"]) if profile_raw.get("created_at") else None),
        "last_fetched_at": datetime.now()
    }

    clean_repos = []
    for repo in repos_raw:

        # skip forked repos and the special profile-readme repo
        if (repo["fork"] is not True) and (repo["name"] != username):
            if repo["description"] is not None:
                repo["description"] = repo["description"].strip()

            # for license
            repo["license"] = repo["license"].get("key") if repo["license"] else None

            # for home page
            if repo["homepage"] in ("null", "", None):
                repo["homepage"] = None

            # created at , updated at , pushed at
            for key in ["created_at", "updated_at", "pushed_at"]:
                value = repo.get(key)
                repo[key] = datetime.fromisoformat(value) if value not in (None, "", "null") else None

            # for topics
            if "topics" in repo:
                repo["topics"] = json.dumps(repo["topics"])  # because it is a list and sql troubles with list so convert in to json

            db_repo_row = {
                "github_repo_id": repo.get("id"),
                "name": repo.get("name"),
                "description": repo.get("description"),
                "primary_language": repo.get("language"),
                "is_fork": repo.get("fork"),
                "stargazers_count": repo.get("stargazers_count", 0),
                "forks_count": repo.get("forks_count", 0),
                "open_issues_count": repo.get("open_issues_count", 0),
                "size_kb": repo.get("size", 0),
                "license_key": repo.get("license"),
                "homepage_url": repo.get("homepage"),
                "topics": repo.get("topics"),
                "repo_created_at": repo["created_at"],
                "repo_updated_at": repo["updated_at"],
                "repo_pushed_at": repo["pushed_at"],
                "fetched_at": datetime.now()
            }
            clean_repos.append(db_repo_row)

    return {"profile": profile_data, "repos": clean_repos}


def save_to_database(data, candidate_id=None):
    """
    Takes already cleaned profile + repo data and saves it to PostgreSQL using SQLAlchemy.
    It does NOT talk to GitHub - this function only deals with the database.

    Automatically finds or creates the matching candidate (no manual id
    typing). If this candidates GitHub data already exists, it UPDATES
    the existing profile row and DELETES their old repos before inserting
    the fresh ones - this prevents duplicate profiles and duplicate repos
    building up every time this script is re-run for the same person.
    Commits everything together, or rolls back if anything fails.
    """

    if not data["profile"]:
        print("No data to save")
        return

    profile_data = data["profile"]
    repos = data["repos"]

    with get_db() as db:
        try:
            if candidate_id is not None and not db.query(Candidate.id).filter(
                Candidate.id == candidate_id
            ).first():
                raise ValueError(f"Candidate with id={candidate_id} does not exist.")

            existing_profile = db.query(GitHubProfile).filter(
                GitHubProfile.github_username == profile_data["github_username"]
            ).first()

            if existing_profile:
                github_profile_id = existing_profile.id
                if candidate_id is None:
                    candidate_id = existing_profile.candidate_id
                else:
                    existing_profile.candidate_id = candidate_id

                existing_profile.bio = profile_data["bio"]
                existing_profile.company = profile_data["company"]
                existing_profile.location = profile_data["location"]
                existing_profile.public_repos = profile_data["public_repos"]
                existing_profile.followers = profile_data["followers"]
                existing_profile.account_created_at = profile_data["account_created_at"]
                existing_profile.last_fetched_at = profile_data["last_fetched_at"]

                db.query(GitHubRepo).filter(GitHubRepo.github_profile_id == github_profile_id).delete()

            else:
                if candidate_id is None:
                    candidate = Candidate(
                        full_name=profile_data["github_username"],
                        created_at=datetime.now()
                    )
                    db.add(candidate)
                    db.flush()
                    candidate_id = candidate.id

                new_profile = GitHubProfile(
                    candidate_id=candidate_id,
                    github_id=profile_data["github_id"],
                    github_username=profile_data["github_username"],
                    bio=profile_data["bio"],
                    company=profile_data["company"],
                    location=profile_data["location"],
                    public_repos=profile_data["public_repos"],
                    followers=profile_data["followers"],
                    account_created_at=profile_data["account_created_at"],
                    last_fetched_at=profile_data["last_fetched_at"],
                )
                db.add(new_profile)
                db.flush()
                github_profile_id = new_profile.id

            for repo in repos:
                db_repo = GitHubRepo(
                    github_profile_id=github_profile_id,
                    github_repo_id=repo["github_repo_id"],
                    name=repo["name"],
                    description=repo["description"],
                    primary_language=repo["primary_language"],
                    is_fork=repo["is_fork"],
                    stargazers_count=repo["stargazers_count"],
                    forks_count=repo["forks_count"],
                    open_issues_count=repo["open_issues_count"],
                    size_kb=repo["size_kb"],
                    license_key=repo["license_key"],
                    homepage_url=repo["homepage_url"],
                    topics=repo["topics"],
                    repo_created_at=repo["repo_created_at"],
                    repo_updated_at=repo["repo_updated_at"],
                    repo_pushed_at=repo["repo_pushed_at"],
                    fetched_at=repo["fetched_at"],
                )
                db.add(db_repo)

            db.commit()
            print(f"Saved candidate_id={candidate_id}, github_profile_id={github_profile_id}, "
                  f"{len(repos)} repos.")

        except Exception as e:
            db.rollback()
            print(f"Something went wrong, nothing was saved: {e}")
            raise


if __name__ == "__main__":
    cleaned_data = fetch_and_clean_github_data(username="AyaanHussain1")
    save_to_database(cleaned_data)