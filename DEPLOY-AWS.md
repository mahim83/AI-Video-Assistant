# Deploying on AWS (free plan)

This guide puts the app on a small AWS server paid for by AWS's free-plan
credits, with a free domain from DuckDNS. Follow the steps in order.

```text
Users ──HTTPS──> yourname.duckdns.org ──> AWS server (t3.small, Mumbai)
                                              ├── Caddy  (HTTPS certificate)
                                              └── App    (Streamlit + Chroma, data on the server's disk)
```

## What it costs

| Item | Paid from your AWS credits |
|---|---|
| Server `t3.small` (2 vCPU, 2 GB RAM), Mumbai | ~$16/month |
| Disk, 25 GB | ~$2.50/month |
| Fixed public IP address (Elastic IP) | ~$3.60/month |
| **Total** | **~$22/month** |

- AWS gives **$100 when you sign up**, plus up to **$100 more** for trying some AWS services. The Billing console lists them; launching an EC2 server and creating a budget are typical examples.
- $100 lasts about 4.5 months; $200 covers the free plan's full **6 months**.
- **On the free plan AWS can't charge your card.** When the credits or the 6 months run out, you either upgrade to a paid plan or the account closes. See [step 15](#15-before-the-free-plan-ends) and plan your move well before then.

API costs (OpenAI, Deepgram, Sarvam) are separate and not covered by AWS credits.

## 1. Create the AWS account

1. Go to https://aws.amazon.com and click **Create an AWS account**.
2. Enter your email and an account name, then verify the email.
3. Choose the **Free plan**, not the Paid plan.
4. Contact information: choose **Personal**, country **India**, and your address as registered with your bank.
5. Payment: your **SBI RuPay debit card**, or **UPI AutoPay**. AWS charges ₹2 to verify and refunds it. You may be sent to SBI's page for an OTP. Online transactions must be enabled on the card (YONO → Manage Debit Card).
6. Verify your phone number with the SMS or call code.
7. Support plan: **Basic (free)**.
8. Wait for the "account is ready" email, then sign in at https://console.aws.amazon.com as **Root user**.

## 2. Protect the account

Anyone with your AWS password could use your credits, so add a second factor:

1. Click your account name (top right) → **Security credentials**.
2. **Multi-factor authentication (MFA)** → **Assign MFA device** → **Authenticator app**.
3. Scan the code with Google Authenticator or Microsoft Authenticator and enter two codes in a row.

## 3. Choose the Mumbai region

In the top-right corner of the console, next to your account name, choose
**Asia Pacific (Mumbai) ap-south-1**. Everything below must be created in this
region. If something "disappears" later, check this setting first.

## 4. Launch the server

Search for **EC2** at the top → **Launch instance**.

| Setting | Value |
|---|---|
| Name | `ai-video-assistant` |
| Application and OS image | **Ubuntu**, **Ubuntu Server 24.04 LTS**, architecture **64-bit (x86)** |
| Instance type | **t3.small** |
| Key pair | **Create new key pair** → name `ai-video-key`, type RSA, format **.pem** → it downloads. Keep this file safe; you need it to copy backups. |
| Network settings → Firewall | **Create security group**, then tick: **Allow SSH traffic from: My IP**, **Allow HTTPS traffic from the internet**, **Allow HTTP traffic from the internet** |
| Configure storage | **25** GiB, type **gp3** |
| Advanced details → **Credit specification** | **Standard** |

The last setting matters: by default, `t3` servers can burst above their
included CPU and bill the extra. With *Standard*, the server just slows down
for a while instead, so busy days can't eat your credits.

Click **Launch instance**.

## 5. Give the server a fixed address

A server's public IP changes whenever it's stopped and started. An Elastic IP stays the same.

1. EC2 left menu → **Network & Security → Elastic IPs** → **Allocate Elastic IP address** → **Allocate**.
2. Select the new address → **Actions → Associate Elastic IP address** → Instance: `ai-video-assistant` → **Associate**.
3. Write the address down, for example `13.234.56.78`.

### 5b. Keep containers away from the metadata service

AWS servers answer questions about themselves at a special internal address.
Containers don't need it, and blocking them is cheap defence against
server-side request tricks:

EC2 → **Instances** → select the server → **Actions → Instance settings →
Modify instance metadata options**:
- **IMDSv2:** Required
- **Metadata response hop limit:** **1**

Click **Save**. The server itself still works normally. Don't attach an IAM
role to this server; the app needs no AWS permissions.

## 6. Get a free domain (DuckDNS)

1. Go to https://www.duckdns.org and sign in, for example with your Google account.
2. Type a subdomain, for example `mahim-video`, and click **add domain**. Your address is now `mahim-video.duckdns.org`.
3. In the **current ip** box next to it, enter the **Elastic IP** from step 5 and click **update ip**.

> Google sign-in should accept a DuckDNS address, but this isn't guaranteed. If
> Google rejects the redirect URI in step 9, buy a cheap domain (`.xyz` or
> `.in`, ₹100–800/year, payable by UPI at Indian registrars), point an `A`
> record at the Elastic IP, and use that domain instead.

## 7. Connect to the server and prepare it

You connect from **PowerShell on your laptop** with the key file from step 4.
Windows 10 and 11 include `ssh`. Move `ai-video-key.pem` to a folder of its own,
for example `C:\Users\mahim\aws`, then:

```powershell
cd C:\Users\mahim\aws
# Once: let only you read the key, or ssh refuses it as "unprotected".
icacls ai-video-key.pem /inheritance:r /grant:r "$($env:USERNAME):R"

ssh -i ai-video-key.pem ubuntu@13.234.56.78      # your Elastic IP from step 5
```

Type `yes` when asked about the fingerprint. The prompt changes to
`ubuntu@ip-...`: you're now typing on the server. Paste these commands
(right-click pastes in PowerShell):

```bash
# 4 GB of swap: the server has 2 GB of RAM, and swap keeps it from running out.
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```

Then type `exit` and **connect again with the same `ssh` command**, so the
Docker permission applies. Check with:

```bash
docker run --rm hello-world     # should print "Hello from Docker!"
free -h                         # Swap should show 4.0Gi
```

## 8. Get the code onto the server

```bash
git clone https://github.com/mahim83/AI-Video-Assistant.git
cd AI-Video-Assistant
```

The server can only get what's on GitHub, so commit and push your latest
changes first. If the repository is **private**, Git asks for a username and
password: enter your GitHub username, and as password a **personal access
token** (GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained → read-only access to this repository's Contents).

## 9. Create the Google sign-in client

1. Open https://console.cloud.google.com and create a project named `AI Video Assistant`.
2. **APIs & Services → OAuth consent screen**: User type **External**; fill in the app name and your email; leave the default scopes; then **Publish app** (status *In production*). Basic sign-in doesn't need Google's review.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**
   - Authorized redirect URIs: `https://mahim-video.duckdns.org/oauth2callback`, with your own subdomain
4. Copy the **client ID** and **client secret**.

## 10. Configure the app

In the server terminal, inside `AI-Video-Assistant`:

```bash
cp .env.example .env
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
chmod 600 .env .streamlit/secrets.toml
# The app container runs as user 10001: it must be able to read the sign-in
# secrets and write the data folder. Nobody else can read either.
sudo chown 10001:10001 .streamlit/secrets.toml
mkdir -p data && sudo chown 10001:10001 data
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # copy this: your cookie_secret
nano .env
```

In `.env`, fill in or change these lines. In nano, move with the arrow keys,
press **Ctrl+O** then **Enter** to save, and **Ctrl+X** to exit.

```bash
OPENAI_API_KEY=sk-...
DEEPGRAM_API_KEY=...
SARVAM_API_KEY=...                   # or leave as is if you don't need Hinglish
ADMIN_EMAILS=you@gmail.com           # your Google account
DOMAIN=mahim-video.duckdns.org

# Sized for a 2 GB server and a small budget:
APP_MEM_LIMIT=1600m
MAX_CONCURRENT_JOBS=1
MAX_VIDEO_MINUTES=60
VIDEOS_PER_DAY=3
AUDIO_MINUTES_PER_DAY=60
QUESTIONS_PER_DAY=100
```

Make sure each of these settings appears only once in the file. If a line
already exists, edit it, or delete the `#` at the start of the commented
version, instead of adding a second copy.

Then edit the sign-in settings:

```bash
nano .streamlit/secrets.toml
```

| Line | Value |
|---|---|
| `redirect_uri` | `https://mahim-video.duckdns.org/oauth2callback`, exactly as in step 9 |
| `cookie_secret` | the random string printed above |
| `client_id`, `client_secret` | from step 9 |

## 11. Start it

```bash
docker compose up -d --build
```

The first build takes **10–20 minutes** on this small server, because it
downloads PyTorch and the models. Follow it with:

```bash
docker compose logs -f app       # Ctrl+C stops following, not the app
```

When you see `You can now view your Streamlit app`, open
`https://mahim-video.duckdns.org`. Caddy gets the HTTPS certificate on the
first visit, which can take a few seconds. Sign in with your admin account.

## 12. Invite users

Sidebar → **Admin** → **Invite a user**: enter their Google account email.
They can sign in immediately. **Revoke access** takes effect at their next click.

## 13. Bring over your existing meetings (optional)

Open a **second** PowerShell window on your laptop (not the one connected to
the server):

```powershell
cd C:\Users\mahim\aws
scp -i ai-video-key.pem -r "C:\Users\mahim\Desktop\AI Video Assistant\outputs" ubuntu@mahim-video.duckdns.org:~/AI-Video-Assistant/
```

Then, in the server window:

```bash
cd ~/AI-Video-Assistant
docker compose run --rm -v "$PWD/outputs:/app/outputs:ro" app \
    python -m scripts.migrate_legacy --email you@gmail.com
```

## 14. Back up every night, and keep a copy on your laptop

On the server:

```bash
chmod +x ~/AI-Video-Assistant/deploy/backup.sh
sudo crontab -e      # choose nano if asked, then add this line at the bottom:
15 3 * * * /home/ubuntu/AI-Video-Assistant/deploy/backup.sh >> /var/log/ai-video-backup.log 2>&1
```

Backups on the server are lost along with the server, so **copy them to your
laptop every week or two**, from PowerShell on your laptop:

```powershell
cd C:\Users\mahim\aws
New-Item -ItemType Directory -Force C:\Users\mahim\Documents\ai-video-backups | Out-Null
scp -i ai-video-key.pem "ubuntu@mahim-video.duckdns.org:~/AI-Video-Assistant/backups/*.tar.gz" "C:\Users\mahim\Documents\ai-video-backups\"
```

## 15. Before the free plan ends

- Check your remaining credits monthly: **Billing and Cost Management → Credits**. AWS also emails you before the plan ends.
- **By month 5**, decide where the app goes next:
  - **Oracle Cloud Always Free**: permanently free, but needs a Visa or Mastercard card. SBI can issue one on your account.
  - **Upgrade AWS to the paid plan**: about ₹1,800/month for this server.
- Moving is the same Docker setup on the new server, plus your latest backup:
  copy the `.tar.gz` into the app folder there and run
  `tar -xzf data-<date>.tar.gz && mv data/app.db.backup data/app.db && sudo chown -R 10001:10001 data`
  before `docker compose up -d --build`. Update the DuckDNS IP, and the Google
  redirect URI if the domain changes.
- **Don't let the plan expire without a recent backup on your laptop.** When the account closes, the server and its disk are deleted.

## Updating the app later

Push your changes to GitHub, then on the server:

```bash
cd ~/AI-Video-Assistant
git pull
docker compose up -d --build
```

## Troubleshooting

| Problem | What to do |
|---|---|
| The site doesn't load at all | Check that the DuckDNS IP matches the Elastic IP; that the security group allows HTTP and HTTPS from anywhere; and that `docker compose ps` shows both containers *running*. |
| Certificate or HTTPS errors | `docker compose logs caddy`. Usually the domain doesn't point at the server yet. Fix DuckDNS, then `docker compose restart caddy`. |
| Google says `redirect_uri_mismatch` | The URI in Google Cloud and `redirect_uri` in `secrets.toml` must match exactly, including `https://` and `/oauth2callback`. |
| Google rejects the DuckDNS address | Use a cheap paid domain instead (see step 6). |
| App restarts or is very slow | `docker stats` shows memory use. Keep `MAX_CONCURRENT_JOBS=1`, and check that swap is on (`free -h`). |
| "Something went wrong (ref a1b2c3)" | `docker compose logs app \| grep a1b2c3` shows the full error. |
| YouTube downloads fail | YouTube often blocks cloud servers. Uploading the audio file always works. See [DEPLOY.md, Known limitations](DEPLOY.md#known-limitations). |
| `ssh` or `scp` hangs, then times out | SSH is allowed only from the IP you had in step 4, and home IPs change. EC2 → Security Groups → your group → Edit inbound rules → SSH → Source **My IP** → Save. |
| `ssh` says "UNPROTECTED PRIVATE KEY FILE" | Run the `icacls` command from step 7 again, in the folder with the key. |

For changing limits, rotating keys, signing everyone out or deleting a user's
data, see [DEPLOY.md, Operating](DEPLOY.md#operating).
