import os 
import requests
import json 
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector

# for token loading use .env for safety 
load_dotenv("token.env",override=True) # it reads the .env file 

token = os.environ.get("Github_Token")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")
username = "AyaanHussain1"


def fetch_and_clean_github_data(username):

    """
    Fetches a GitHub profile + repo list, and returns them cleaned and
    ready to insert into the database.It does jonot touch the database -
    this function only deals with GitHub and data cleaning.
    """

    headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
    }

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


def save_to_database(data):

    """
    Takes already cleaned profile + repo data and saves it to MySQL.
    it does NOT talk to GitHub - this function only deals with the database.

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

    connection = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = connection.cursor()

    try:
        # check if this GitHub username was already saved before - and if
        # so, grab both its candidate_id AND its existing github_profiles
        # row id, since we need to update/reuse that same profile row
        # rather than creating a second one.
        cursor.execute(
            "select id, candidate_id from github_profiles where github_username = %s",
            (profile_data["github_username"],)
        )
        existing = cursor.fetchone()

        if existing is not None:
            github_profile_id, candidate_id = existing

            # update the existing profile row instead of inserting a
            # new one, so re-running this script does not create duplicates.
            cursor.execute(
                """
                UPDATE github_profiles
                SET bio = %s, company = %s, location = %s, public_repos = %s,
                    followers = %s, account_created_at = %s, last_fetched_at = %s
                WHERE id = %s
                """,
                (
                    profile_data["bio"],
                    profile_data["company"],
                    profile_data["location"],
                    profile_data["public_repos"],
                    profile_data["followers"],
                    profile_data["account_created_at"],
                    profile_data["last_fetched_at"],
                    github_profile_id,
                )
            )

            # FIX: delete this candidate's old repos before inserting the
            # fresh ones, so repos don't pile up as duplicates over time.
            cursor.execute(
                "delete from github_repos where github_profile_id = %s",
                (github_profile_id,)
            )

        else:
            # brand new candidate - create their record, then their profile
            cursor.execute(
                "insert into candidates (full_name, created_at) values (%s, %s)",
                (profile_data["github_username"], datetime.now())
            )
            candidate_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO github_profiles
                    (candidate_id, github_id, github_username, bio, company, location,
                     public_repos, followers, account_created_at, last_fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    candidate_id,
                    profile_data["github_id"],
                    profile_data["github_username"],
                    profile_data["bio"],
                    profile_data["company"],
                    profile_data["location"],
                    profile_data["public_repos"],
                    profile_data["followers"],
                    profile_data["account_created_at"],
                    profile_data["last_fetched_at"],
                )
            )
            github_profile_id = cursor.lastrowid

        # attach that id to every repo, then insert them all in one batch
        insert_query = """
            INSERT INTO github_repos
                (github_profile_id, github_repo_id, name, description, primary_language,
                 is_fork, stargazers_count, forks_count, open_issues_count, size_kb,
                 license_key, homepage_url, topics, repo_created_at, repo_updated_at,
                 repo_pushed_at, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        rows = [
            (
                github_profile_id, repo["github_repo_id"], repo["name"], repo["description"],
                repo["primary_language"], repo["is_fork"], repo["stargazers_count"],
                repo["forks_count"], repo["open_issues_count"], repo["size_kb"],
                repo["license_key"], repo["homepage_url"], repo["topics"],
                repo["repo_created_at"], repo["repo_updated_at"], repo["repo_pushed_at"],
                repo["fetched_at"],
            )
            for repo in repos
        ]
        cursor.executemany(insert_query, rows)

        connection.commit()
        print(f"Saved candidate_id={candidate_id}, github_profile_id={github_profile_id}, "
              f"{len(repos)} repos.")

    except Exception as e:
        connection.rollback()
        print(f"Something went wrong, nothing was saved: {e}")
        raise

    finally:
        cursor.close()
        connection.close()


# testing
cleaned_data = fetch_and_clean_github_data(username=username)
save_to_database(cleaned_data)