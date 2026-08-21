# Deploying MUN Chit System

This app is now deployment-ready: `Procfile`, `gunicorn`, and `whitenoise`
(for static files) are wired in, and `manage.py check --deploy` passes
clean under `config.settings.prod`. This guide gets it from "runs on my
machine" to "has a public URL," using **Railway** as the primary example
(simple, free-tier-friendly, native Postgres). Render and Fly.io work
almost identically — see the notes at the end.

## Why I can't do this step myself

I (Claude) am running in a private, temporary sandbox with no public IP
or persistent server — it disappears when this conversation ends, and
its network access is locked to package registries (PyPI, npm, GitHub),
not general web hosting. Going live also requires things only you can
do: creating a hosting account, agreeing to its billing terms, and
holding the production secrets. What I *can* do is make sure the app
itself is genuinely ready — which is what Phase 6 plus the changes below
accomplished — and walk you through the remaining steps precisely.

## 1. Push the code to GitHub

Railway deploys from a Git repository.

```bash
cd mun_chit_system
git init
git add .
git commit -m "Initial commit"
```

Create a new repository on GitHub, then:

```bash
git remote add origin https://github.com/<you>/mun-chit-system.git
git branch -M main
git push -u origin main
```

**Before pushing**, double check `.gitignore` excludes `.env`,
`__pycache__/`, `staticfiles/`, and `media/` — never commit real
secrets or the SQLite/Postgres data directory.

## 2. Create the Railway project

1. Sign up at [railway.app](https://railway.app) (GitHub login is fastest).
2. **New Project → Deploy from GitHub repo** → select your repo.
3. **New → Database → Add PostgreSQL** in the same project. Railway
   automatically injects a `DATABASE_URL` variable into your web
   service — `dj-database-url` (already in `requirements.txt`) reads it
   automatically once `config/settings/prod.py` is active.

## 3. Set environment variables

On your web service → **Variables** tab, add:

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Generate one — see below |
| `DJANGO_ALLOWED_HOSTS` | `your-app.up.railway.app` (Railway shows this after first deploy; add your custom domain later too) |
| `SECURE_SSL_REDIRECT` | `True` |

Generate a real secret key locally and paste the value in (never reuse
the one from `.env.example` or any value shown in this conversation):

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

`DATABASE_URL` is already set for you by the Postgres plugin — don't
add it manually.

## 4. Deploy

Railway detects the `Procfile` automatically:

```
release: python manage.py migrate --noinput
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3
```

The `release` line runs migrations automatically on every deploy. Push
to `main` (or click **Deploy** in the dashboard) and Railway builds and
starts the app. Watch the **Deployments** tab for build/runtime logs.

## 5. Create your first real superuser

Once deployed, open a shell against the live service (Railway dashboard
→ your service → **Settings → Shell**, or `railway run` via their CLI):

```bash
python manage.py createsuperuser
```

**Do not run `seed_demo_data` against this database** — it creates
accounts with the publicly-known password `DemoPass123!`. It already
refuses to run when `DEBUG=False`, which production correctly is; treat
that refusal as a safety feature, not an obstacle to work around.

## 6. Visit the site

Railway gives you a URL like `https://mun-chit-system-production.up.railway.app`.
Open it, sign in with the superuser you just created, and you're live.
Add a custom domain under **Settings → Domains** if you want one —
remember to add it to `DJANGO_ALLOWED_HOSTS` too.

## Alternative hosts

- **Render**: nearly identical flow — connect the GitHub repo, add a
  managed Postgres instance, set the same environment variables, and
  Render also reads the `Procfile`.
- **Fly.io**: more control, more setup — needs a `fly.toml` and
  `flyctl launch`, and you manage the Postgres volume yourself. Better
  if you outgrow Railway/Render's limits later, not a great starting
  point.
- **PythonAnywhere**: good free tier for a small always-on demo, but its
  WSGI config differs from the `Procfile` approach above — ask me for
  PythonAnywhere-specific steps if you go this route.

## After going live: things worth doing next

- Rotate the database password from the sandbox-only
  `dev_only_change_me_123` value if you ever export/import this
  database into the live one — don't carry dev credentials into
  production.
- Point `DEFAULT_FROM_EMAIL` / real SMTP credentials at a provider if
  you want password-reset emails to work (not yet built — see the
  README's "Future improvements" list).
- Set up automated backups on the Postgres instance (Railway/Render both
  offer this as a paid add-on).
