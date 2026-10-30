# Operations — Upload and Admin Dashboard

*As of 2026-10-27. Exactly the steps that were actually executed during verification.*

## Deploying to a Server (Docker Compose)

Tested with these exact files (`deploy/`): on 2026-10-25 locally (Arm, Chrome test run, 208 MB video), on 2026-10-26 **on a real server** (Hetzner CPX12, x86, Ubuntu 26.04, Docker 29.9): build, startup, real Let's Encrypt certificate via Caddy, test uploads (new / identical / re-encoded copy / without audio / preview). The database and backend port are not reachable from the outside. **The admin dashboard** was tested locally on 2026-10-27 (Chrome, real database, a placeholder instead of Google) and is not yet deployed **on the server**; it remains closed there anyway until the domain and Google credentials are set up.

1. **Create server** (Hetzner Cloud Console): Ubuntu 24.04, location Nuremberg, type **CPX12** (1 vCPU, 2 GB RAM, 40 GB SSD; €11.49/month + €0.50 IPv4, net plus VAT). Measured on the running stack: all four containers combined ~0.35 GB RAM, frontend build peak ~0.35 GB, images ~2.7 GB on disk. The smaller CPX02 (1 GB, 20 GB) would be too tight, especially disk space; CPX22 (€19.49) is not needed. Scale later via server upgrade or an attached volume. Add SSH key. **Enable backups** (+20%) before real uploads arrive: the server holds the only copy of each upload until an admin registers it. Afterwards create swap once (buffer during image build, standard commands, untested on Hetzner):
   `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`
2. **Domain**: Point an A record to the server's IPv4.
   *Temporarily, while the project name is undecided:* free via duckdns.org (login with Google/GitHub, choose name, enter server IP) and set `DOMAIN=<name>.duckdns.org`. Do not use sslip.io/nip.io: neither is on the Public Suffix List and both share Let's Encrypt rate limits with all users worldwide; certificate issuance can fail. With the real domain: update `DOMAIN` in `.env`, run `docker compose up -d` — data is preserved, only the link changes (distribute newly to contributors). Untested on a production server.
3. **On the server:**
   ```bash
   curl -fsSL https://get.docker.com | sh
   git clone https://github.com/PSchmitz-Valckenberg/maqati3.git /opt/maqati3 && cd /opt/maqati3/deploy
   cat > .env <<EOF
   DOMAIN=archiv.example.org
   POSTGRES_PASSWORD=$(openssl rand -hex 24)
   UPLOAD_KEY=$(openssl rand -base64 24 | tr '+/' '-_' | tr -d '=')
   EOF
   docker compose up -d --build
   ```
   Caddy fetches the HTTPS certificate automatically as soon as the domain points to the server.
4. **Firewall** (Hetzner Console): allow only ports 22, 80, 443 inbound.
5. **Updating**: `git pull && docker compose up -d --build` — migrations run automatically on startup.

## Settings (Backend)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | set automatically by `deploy/compose.yml` |
| `UPLOAD_KEY` | yes | The secret key in the upload link. Without it the server will not start. Changing it invalidates all previous links. |
| `STAGING_DIR` | no | Directory where uploads reside until an admin registers them. Inside container: `/var/lib/maqati3/staging` on volume `staging`. |
| `MAX_UPLOAD_BYTES` | no | Default 2 GiB per file (Caddy permits up to 2 GB) |
| `FPCALC_PATH` | no | Default `fpcalc` (included in container image) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | for admin dashboard | Google OAuth client, see below |
| `PUBLIC_URL` | for admin dashboard | The site's own address, `https://<domain>`, without path |
| `SESSION_SECRET` | for admin dashboard | Signs the login cookie, min. 32 chars: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing it signs all admins out. |

The four admin variables belong together: **all or none**. None → the admin dashboard is closed (every endpoint returns 503). Partial configuration → the server refuses to start, reporting which value is missing.

## Without Docker (Local Development)

```bash
docker compose up -d --wait db   # database only, empty; port taken? DB_PORT=55432 ...
cd backend
export DATABASE_URL=postgresql://maqati3:devonly@127.0.0.1:5432/maqati3
uv run python -m maqati3 migrate && uv run python -m maqati3 seed
UPLOAD_KEY=dev STAGING_DIR=.staging uv run python -m maqati3 serve --port 8000
cd frontend && npm run dev   # proxies /api to :8000 (API_ORIGIN, baked in during build)
```

The database intentionally starts empty: `migrate` creates the schema, identical to server setup.
`STAGING_DIR` must be set locally; otherwise the first upload fails on the default path `/var/lib/maqati3/staging`.

Next.js request proxying caps uploads at **10 MB** — only in this development mode. On the server, `/api` is routed directly through Caddy to the backend (208 MB verified). Send large files locally directly to port 8000 or use the Docker stack.

Requires `fpcalc` and `ffmpeg` locally (`brew install chromaprint ffmpeg`).

## The Link for Contributors

```
https://<domain>/ar/upload#k=<UPLOAD_KEY>
```

(`/en/` and `/de/` for other languages respectively.) The key is placed behind `#` (fragment) and never reaches server access logs or HTTP referrers. Share only within the group.

## The Admin Dashboard

Address: `https://<domain>/de/admin` (also `/en/`, `/ar/`). Workflow and rationale: `CLAUDE.md`, "The Admin Workflow". In summary: admins log in via Google, review retained uploads with player, assign scholar, and **register** the video (creates library entry, attribution stays "not sure") or **discard** it. Every admin action is logged with the admin's email in the `admin_log` table.

### Setup (one-off, ~15 minutes, requires final domain)

Google binds the redirect URL strictly; setting it with a temporary DuckDNS address requires redoing configuration later.

1. <https://console.cloud.google.com> → select a project (from `docs/SETUP-GOOGLE.md` or a new one).
2. **APIs & Services → OAuth consent screen**: User Type *External*, fill in App name and support email. Scopes: only `openid`, `email`, `profile` (no sensitive scopes). While status is *Testing*, only explicitly listed **Test users** can sign in: add admin emails there.
3. **Credentials → Create Credentials → OAuth client ID**, Application type **Web application** (not "Desktop" like the Drive guide). *Authorized redirect URI*: `https://<domain>/api/v1/admin/auth/callback` — character for character.
4. Copy Client ID and Client Secret **only** into the server's `.env`:
   ```
   GOOGLE_CLIENT_ID=…
   GOOGLE_CLIENT_SECRET=…
   PUBLIC_URL=https://<domain>
   SESSION_SECRET=<generated random string>
   ```
   Then run `docker compose up -d`. Never post the secret to chats, repositories, or screenshots.
5. Add initial admins (the **Google email address** used to sign in):
   ```bash
   cd /opt/maqati3/deploy
   docker compose exec api python -m maqati3 admin add name@gmail.com --name Firstname
   docker compose exec api python -m maqati3 admin list
   docker compose exec api python -m maqati3 admin remove name@gmail.com   # takes effect immediately
   ```

Anyone not present on the admin list is rejected, even with a valid Google account; anyone removed is denied access starting with the next request.

### Without Dashboard: The Server Inbox

```bash
ssh root@<IP>                                      # optionally -i <key>
cd /opt/maqati3/deploy && docker compose exec api python -m maqati3 inbox
```

Lists submitted uploads with file path and sender, marking those that were retained **despite matching duplicates**. Registering and discarding can only be performed in the dashboard.
