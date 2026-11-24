# Deploying AI Video Assistant

This guide puts the app on a Linux server (VPS) with Docker. Visitors sign in
with Google, and only people you invite get in. Caddy provides HTTPS
automatically.

> **Deploying on AWS's free plan?** Follow [DEPLOY-AWS.md](DEPLOY-AWS.md)
> instead: it covers the whole AWS setup from account creation, with a free
> domain. Come back here for [Operating](#operating) and the
> [Security model](#security-model).

```text
Internet ──HTTPS──> Caddy (ports 80/443) ──> app container (Streamlit, port 8501, internal only)
                                                 │
                                                 └── ./data on the server's disk
                                                       users/<id>/meetings, vector_db, work
                                                       app.db (users, quotas, audit log)
```

## What you need

- A VPS running Ubuntu 22.04 or 24.04 with **4 GB RAM**, 2 vCPUs and 40 GB of disk or more. The embedding and reranker models need about 1.5 GB of RAM.
- A domain or subdomain, such as `video.example.com`.
- API keys for OpenAI and Deepgram (plus Sarvam if you want Hinglish).
- A Google account to create the sign-in client.

## 1. Point the domain at the server

At your DNS provider, add an `A` record for `video.example.com` with the
server's IP address. Caddy can only get a certificate once this record resolves.

## 2. Prepare the server

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # log out and back in afterwards

# Firewall: SSH and web only. Port 8501 stays closed; only Caddy reaches the app.
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

## 3. Create the Google sign-in client

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project, for example "AI Video Assistant".
2. Go to **APIs & Services → OAuth consent screen**.
   - User type: **External**.
   - Fill in the app name, a support email and the developer contact.
   - Scopes: leave the defaults. The app only needs `openid`, `email` and `profile`.
   - **Publish the app** (Publishing status → *In production*). Apps that only use these basic scopes don't need Google's review. In *Testing* status, only accounts listed as test users can sign in.
3. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
   - Application type: **Web application**.
   - Authorized redirect URIs: `https://video.example.com/oauth2callback`.
   - Copy the **client ID** and **client secret**.

Google only confirms who someone is. Who may use the app is decided by the
app (step 6): by default anyone with a verified email can sign up, and you
can revoke anyone.

## 4. Configure the app

```bash
git clone <your repository URL> ai-video-assistant
cd ai-video-assistant

cp .env.example .env
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
chmod 600 .env .streamlit/secrets.toml

# The container runs as user 10001: it must be able to read the sign-in
# secrets and write the data folder.
sudo chown 10001:10001 .streamlit/secrets.toml
mkdir -p data && sudo chown 10001:10001 data
```

Edit **`.env`**:

| Setting | Value |
|---|---|
| `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `SARVAM_API_KEY` | Your keys. |
| `ADMIN_EMAILS` | Your Google account email. Admins can invite and remove users. |
| `DOMAIN` | `video.example.com` |
| `AUTH_MODE` | Leave as is. `docker-compose.yml` forces `oidc` on the server. |

Edit **`.streamlit/secrets.toml`**:

- `redirect_uri`: `https://video.example.com/oauth2callback`, exactly as registered in step 3.
- `cookie_secret`: generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `client_id` and `client_secret` from step 3.

## 5. Start it

```bash
docker compose up -d --build
docker compose logs -f app      # Ctrl+C to stop following
```

The first build takes several minutes because it downloads PyTorch and the
models. Then open `https://video.example.com`. You should see **Sign in with
Google**, and after signing in with your admin account, the app.

## 6. Manage people

With the default `SIGNUP_MODE=open`, anyone with a verified Google account or
email can sign up and use the app straight away, as a regular user with the
daily limits. With email set up (SMTP settings), you get an email for each new
registration, so you can check it. Set `SIGNUP_MODE=invite` to let in only the
people you add.

In the sidebar, choose **Admin**:

- **Invite a user**: enter their email and choose a role. They can sign in right away.
- **Users**: everyone with access, by name and email: how they sign in (Google, email or both), when they joined and last signed in, how many meetings they have, and their usage today and in total.
- **Manage a user**: pick anyone, whether they signed up with Google or email or were invited, by name. Change their role between user and admin; **Revoke access**, which takes effect at their next click and stops that email signing up again (their meetings stay on disk); or **Delete** them with all their meetings and data, optionally blocking the email too. Users set in `ADMIN_EMAILS` or `ALLOWED_EMAILS`, and your own account, are changed in `.env` instead.
- **Revoked emails**: everyone revoked, with **Restore** to let them back in as a regular user.
- **Users and today's usage** and the **Audit log** show who did what. The log records actions (sign-in, processed, opened, deleted), never questions or transcripts.

## 7. Bring over your existing meetings (optional)

Copy the old `outputs/` folder from your computer to the server, next to
`docker-compose.yml`, then run:

```bash
docker compose run --rm -v "$PWD/outputs:/app/outputs:ro" app \
    python -m scripts.migrate_legacy --email you@gmail.com
```

The meetings are copied into your account. Each search index is rebuilt the
first time you open the meeting.

## 8. Back up `data/`

Everything users create lives in `./data`. Schedule the backup script nightly:

```bash
chmod +x deploy/backup.sh
sudo crontab -e
# add:
15 3 * * * /home/<you>/ai-video-assistant/deploy/backup.sh >> /var/log/ai-video-backup.log 2>&1
```

It writes `backups/data-<date>.tar.gz` and keeps 14 days of them. To keep a copy
off the server, which you should, install [rclone](https://rclone.org/), set up an
encrypted remote (rclone's `crypt` type, since backups contain every user's
transcripts) on top of a
remote such as Backblaze B2, Cloudflare R2 or S3, and add
`RCLONE_REMOTE=b2:your-bucket/ai-video` before the command in the crontab line.

Each meeting takes about 0.5 MB per hour of video, because audio is deleted
after transcription. Disk use grows slowly, and new videos pause automatically
when free space drops below `MIN_FREE_DISK_GB`.

## 9. Set spending limits with the providers

The app's quotas cap what each user can do, but set hard limits where the
money is too, in case of a bug or a leaked key:

- **OpenAI**: Settings → Limits → set a monthly budget and an alert.
- **Deepgram** and **Sarvam**: check your balance and usage alerts in their consoles.

## Updating

```bash
git pull
docker compose up -d --build
```

## Operating

| Task | How |
|---|---|
| See logs | `docker compose logs -f app` |
| A user reports "Something went wrong (ref a1b2c3)" | `docker compose logs app \| grep a1b2c3` shows the full error. |
| Change limits | Edit `.env` (see the limits block in `.env.example`), then `docker compose up -d`. |
| Rotate an API key | Update `.env`, then `docker compose up -d`. |
| Sign everyone out | Change `cookie_secret` in `secrets.toml`, then `docker compose restart app`. |
| Delete a user's data | Revoke access in Admin, then remove `data/users/<id>/`. The id is the first 16 hex characters of the SHA-256 of their lowercase email: `python3 -c "import hashlib; print(hashlib.sha256(b'them@gmail.com').hexdigest()[:16])"` |

## Security model

| Layer | What it does |
|---|---|
| HTTPS | Caddy gets and renews certificates and sends security headers. The app port isn't exposed. |
| Authentication | Google sign-in (OIDC) through Streamlit's `st.login`. Emails must be verified by Google. |
| Authorization | Invite-only list (`ADMIN_EMAILS`, `ALLOWED_EMAILS`, plus users added in Admin), checked on every interaction. Roles: `admin` and `user`. Admin actions are checked server-side, not only hidden in the UI. |
| Data isolation | Each user's meetings and search indexes live in their own folder. Meeting names are validated so no request can reach outside it. |
| Upload gate | Streamlit's upload endpoint accepts files from any page session. `server.py` puts a gate in front of it (`core/upload_gate.py`): an upload needs a valid sign-in cookie for an invited user, with one upload at a time per user and a few per 10 minutes. Anonymous visitors can't fill the server's memory. |
| Input guardrails | YouTube links only, checked by host and by restricting yt-dlp to its YouTube extractor, so no server paths or internal addresses. Uploads are checked by type and size (100 MB) and decoded with the format forced, audio decoders only, and plain file access only. Length cap before download. Question length cap. Every processing attempt counts toward a daily limit, failed ones included. |
| Spend guardrails | Per-user daily limits on videos, audio minutes and questions, a per-minute question limit, at most `MAX_CONCURRENT_JOBS` videos at once, one per user, and a cap on answer length. |
| LLM guardrails | Answers only about the video and declines unrelated requests. The transcript is marked as untrusted data inside delimiters it can't close, in the chat and the summary prompts. Every markdown image in answers and summaries is turned into a plain link, and the CSP stops the browser from loading images from other sites. |
| Identity | Two ways to sign in. **Google**: the login cookie needs a strong `cookie_secret` (the app refuses to start with the example or a short one), and each email is bound to the Google account that first used it. **Email and password** (`core/local_auth.py`, needs SMTP): an account exists only after a 6-digit code sent to the address is entered; passwords are stored only as salted scrypt hashes; five wrong passwords lock the account for 15 minutes; errors don't reveal which emails have accounts; code emails are rate-limited; "forgot password" resets by code and signs out other devices. The session is an HttpOnly, SameSite=Lax cookie set by `server.py` and checked server-side, so sign-out ends it everywhere it's used. Cookies get the Secure flag at Caddy. |
| Errors and logs | Users see friendly messages with a reference; details stay in the server log. Transcripts and questions are not logged. |
| Fail-safes | `AUTH_MODE=off` is refused unless the app listens on localhost. New videos pause when the disk is nearly full. Audio is deleted after every job. |

## Known limitations

- **YouTube often blocks downloads from cloud servers** ("Sign in to confirm you're not a bot"). Updating yt-dlp (bump it in `requirements-prod.txt` and rebuild) sometimes helps. Mounting cookies from a throwaway YouTube account via `YTDLP_COOKIES` helps more, but that account can get flagged. File upload always works. Downloading YouTube content may also conflict with YouTube's Terms of Service, so check this for your use.
- **One server.** The app keeps state on local disk and in memory, so it runs as one container. That's fine for an invited group. Hundreds of users would need a database-backed design.
- **Whisper is off on the server** (`ENABLE_WHISPER=false`): it would occupy the CPU for minutes per video and slow everyone down.
