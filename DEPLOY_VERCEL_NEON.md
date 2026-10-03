# Deploy to Vercel + Neon (frontend and backend in one repo)

Layout: `public/` = frontend (served by Vercel's CDN at `/`), `fast_api_backend.py` = FastAPI API (one Vercel Function).
Same domain for both, so the frontend calls the API with no CORS or URL setup.

## 0. Rotate your keys first
The OpenAI key and GitHub token that were in `token.env` have been shared in chat/archives. Revoke and recreate both:
- OpenAI: platform.openai.com -> API keys -> delete old, create new
- GitHub: Settings -> Developer settings -> Personal access tokens -> delete old, create new
Use the NEW values below. Never commit `token.env` (it is in `.gitignore`).

## 1. Neon (database)
1. neon.tech -> New Project -> create it.
2. Click **Connect**, tick **Connection pooling**, copy the string. It looks like
   `postgresql://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require`
   (the host must contain `-pooler`).
3. Tables are created automatically on the first request. Optional: paste `git_data.sql` into Neon's SQL Editor to add the sample jobs.

## 2. GitHub
Copy these files over your existing repo folder (token.env is intentionally not included), then:
```
git add -A
git commit -m "Vercel + Neon deployment"
git push
```

## 3. Vercel
1. vercel.com -> Add New -> Project -> import the repo.
2. Framework Preset: FastAPI (auto-detected) or Other. Leave Build/Output/Install commands empty.
3. Settings -> Environment Variables (names are case-sensitive), for Production + Preview:
   | Name | Value |
   | --- | --- |
   | `DATABASE_URL` | the Neon pooled string from step 1 |
   | `Api_key` | your NEW OpenAI key |
   | `Github_Token` | your NEW GitHub token |
4. Deploy.

## 4. Verify (replace with your domain)
- `https://YOUR-APP.vercel.app/` -> the UI loads
- `/health` -> `{"status":"ok"}` (does not touch the DB)
- `/jobs/` -> `[]` or your jobs (this proves the Neon connection)
- `/docs` -> FastAPI docs

## Troubleshooting
| Symptom | Cause / fix |
| --- | --- |
| `/health` ok but `/jobs/` is 500 | `DATABASE_URL` missing/wrong. Check Vercel logs for "database init failed". Redeploy after fixing env vars |
| Resume upload fails with 413 | Vercel's request body limit is ~4.5 MB. Use a smaller PDF |
| Resume parse 500 "OpenAI key missing" | `Api_key` env var not set (or typo in the name) |
| GitHub analyze returns 401 | `Github_Token` invalid/expired |
| Matching shows lower scores | OpenAI embeddings failed, so it used exact skill match only (check `Api_key`/quota) |
| Changed an env var, nothing changed | Env vars apply to new deployments only. Redeploy |

Local run: put values in `token.env` (see `.env.example`), then `uvicorn fast_api_backend:app --reload` -> http://127.0.0.1:8000
