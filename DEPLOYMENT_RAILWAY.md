# Deploying the FastAPI backend to Railway

This repository is configured to run the API with:

```text
uvicorn fast_api_backend:app --host 0.0.0.0 --port $PORT
```

## Railway setup

1. Push this project to a GitHub repository. Do not commit `token.env` or `github-token.txt`.
2. In Railway, select **New Project** → **Deploy from GitHub repo**, then select that repository.
3. Add a MySQL service to the same Railway project (or use an existing publicly reachable MySQL database).
4. Open the backend service's **Variables** tab and add the variables below. For a Railway MySQL service, use variable references such as `${{MySQL.MYSQLHOST}}`; replace `MySQL` with the actual service name.
5. Deploy. Railway reads `railway.toml`, builds from `requirements.txt`, and uses `/health` as its health check.

## Backend variables

| Variable | Value |
| --- | --- |
| `DB_HOST` | `${{MySQL.MYSQLHOST}}` |
| `DB_USER` | `${{MySQL.MYSQLUSER}}` |
| `DB_PASSWORD` | `${{MySQL.MYSQLPASSWORD}}` |
| `DB_NAME` | `${{MySQL.MYSQLDATABASE}}` |
| `Api_key` | Your OpenAI API key |
| `Github_Token` | A GitHub personal access token, if GitHub analysis is used |

The MySQL schema must be initialized before the API is used. `git_data.sql` contains the project's schema reference, but its SQL statements are currently commented out; copy the required `CREATE TABLE` statements into your Railway MySQL query editor (without the leading `--`) and run them.

## Verify

After Railway generates a public domain, open:

```text
https://YOUR-RAILWAY-DOMAIN/health
https://YOUR-RAILWAY-DOMAIN/docs
```

`/health` should return `{"status":"ok"}` and `/docs` opens the FastAPI documentation.
