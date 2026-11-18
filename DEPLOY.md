# Deploying Smart Estate

One server runs everything with Docker Compose:

| Service | What it does |
| --- | --- |
| `web` | Caddy: HTTPS certificates, the back office, the resident portal, and the API proxy |
| `api` | Django + gunicorn (runs database migrations on start) |
| `db` | PostgreSQL 17 |
| `paynow-poller` | Checks Paynow every 2 minutes for payments whose result did not arrive |
| `rent-run` | Rental portfolios: bills each month's rent a week ahead and sends rent reminders (every 6 hours; nothing is billed or sent twice) |
| `backup` | Database dump and photo archive at start-up and every night |

Run a **staging** copy first (its own server or subdomains, Paynow in test
mode, WhatsApp test number), then production the same way.

## 1. Server

- Ubuntu 24.04, 2 vCPU, 4 GB RAM, 40 GB disk is plenty for the first estates.
- Close to Zimbabwe for speed: a Johannesburg or Cape Town region, or a
  Zimbabwean data centre.
- Open ports 22, 80 and 443 only.
- Install Docker: https://docs.docker.com/engine/install/ubuntu/

## 2. DNS

Create three `A` records pointing at the server's IP address, e.g.

```
api.myestate.co.zw        -> server IP
admin.myestate.co.zw      -> server IP
residents.myestate.co.zw  -> server IP
```

Certificates are issued automatically on first start once DNS resolves.

## 3. Code and settings

```bash
git clone -b phase-7 https://github.com/Rivzmarere/smart-estate-backend.git
git clone -b phase-7 https://github.com/Rivzmarere/smart-estate-frontend.git   # must sit next to the backend
cd smart-estate-backend
cp .env.example .env
nano .env
```

Until the work is merged into `main`, use the `phase-7` branch of **both**
repositories, as above: `main` does not have the estates, rentals, portal or
sandbox features yet.

In `.env` set at least the three domains, `ACME_EMAIL`, a new
`DJANGO_SECRET_KEY`, the database password (in both `POSTGRES_PASSWORD` and
`DATABASE_URL`), `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
`CSRF_TRUSTED_ORIGINS`, `PUBLIC_API_URL` and `RESIDENT_PORTAL_URL`.

Use a **new** secret key. An old development key exists in the git history,
so it must never be used on a server.

## 4. Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # all should be "running" / "healthy"
curl https://api.myestate.co.zw/health               # {"status": "ok"}
```

The first build takes several minutes (it builds both web apps).

## 5. Bringing over the existing data (SQLite)

Do this **before** creating any accounts on the server (step 6): the
import keeps the old record numbers, so it must go into an empty database.
Skip it for a brand-new estate.

On a computer with the old `db.sqlite3` and the backend code:

```bash
export DJANGO_DEBUG=True DATABASE_URL=sqlite:////full/path/to/db.sqlite3
.venv/bin/python manage.py migrate            # bring the old file up to date
.venv/bin/python manage.py data_check         # fix what it lists in the back office first
.venv/bin/python manage.py dumpdata --all --natural-foreign \
  --exclude contenttypes --exclude auth.permission --exclude admin.logentry \
  --exclude sessions --exclude whatsapp.messagelog --exclude sms.smslog \
  --indent 1 -o smart-estate-data.json
```

`smart-estate-data.json` contains residents' personal data: copy it to the
server over SSH only, and delete it when done. Then, on the server:

```bash
docker compose -f docker-compose.prod.yml cp smart-estate-data.json api:/tmp/data.json
docker compose -f docker-compose.prod.yml exec api python manage.py loaddata /tmp/data.json
docker compose -f docker-compose.prod.yml exec api rm /tmp/data.json
docker compose -f docker-compose.prod.yml exec api python manage.py data_check
```

Repair photos (if any) are in the old `media/` folder; copy them into the
`media` volume with `docker compose cp media/. api:/data/media/`.

## 6. First accounts

```bash
# A platform account (sees and creates estates). Give it no estate.
docker compose -f docker-compose.prod.yml exec api python manage.py createsuperuser
```

Log in at `https://admin.../` with it. On the **Estates** page rename the
first estate if needed, add estates, and create each estate's first
administrator. That administrator adds guards under **Users** and fills in
**Estate settings** (office phone, emergency numbers, Paynow).

**Managing agents and landlords:** on the Estates page, tab *Agents and
landlords*, create the customer and their login. They then add their own
estates and rental portfolios, properties, tenants and staff themselves.

### Demo data to look around or give to testers

Sandbox estates hold sample data. Nothing in them is really sent (messages go
to an Outbox you can read) and EcoCash payments are simulated, so they are
safe on a live server.

```bash
# A managing agent with a gated estate and a rental portfolio, and one login for both
docker compose -f docker-compose.prod.yml exec api python manage.py sandbox agent "Demo Agents"
# Or one of each on its own
docker compose -f docker-compose.prod.yml exec api python manage.py sandbox create "Sandbox Estate"
docker compose -f docker-compose.prod.yml exec api python manage.py sandbox create "Sandbox Rentals" --kind rental
```

Each command prints the logins. The portal link for a sandbox is
`https://residents.../?estate=<its slug>`. The same can be done from the
Estates page (*New sandbox*).

## 7. Connect the outside services

- **WhatsApp** (Meta app dashboard > WhatsApp > Configuration): callback URL
  `https://api.../whatsapp/webhook`, verify token = `WHATSAPP_VERIFY_TOKEN`,
  subscribe to `messages`. Then set `WHATSAPP_ENABLED=True` and the template
  names, and restart (step 9).
- **Paynow**: nothing to configure on Paynow's side; the result URL is sent
  with each payment. Put the integration keys in `.env` (default) or in each
  estate's settings, set `PAYNOW_DRY_RUN=False`.
- **SMS**: `SMS_BACKEND` and its credentials.

## 8. Backups

Backups are written to the `backups` volume every night and kept for
`BACKUP_KEEP_DAYS`. **Also copy them off the server** (a server can be lost):

```bash
# e.g. nightly from another machine
rsync -az server:/var/lib/docker/volumes/smart-estate-backend_backups/_data/ ./smart-estate-backups/
```

Restore a database dump:

```bash
docker compose -f docker-compose.prod.yml cp db_2026-12-01_0200.dump db:/tmp/restore.dump
docker compose -f docker-compose.prod.yml exec db pg_restore -U smartestate -d smartestate --clean --if-exists /tmp/restore.dump
```

Try a restore on staging once, before you need it.

## 9. Updates

```bash
cd smart-estate-backend && git pull && cd ../smart-estate-frontend && git pull && cd ../smart-estate-backend   # same branch in both
docker compose -f docker-compose.prod.yml up -d --build
```

Migrations run automatically. Gate tablets pick up the new version the next
time they are online (the app is cached for offline use).

## 10. Monitoring

Point an uptime monitor (e.g. UptimeRobot, free) at `https://api.../health`.
It returns 200 when the API and database are working. Logs:

```bash
docker compose -f docker-compose.prod.yml logs -f api
```

## Appendix: sharing a server that already runs nginx

Used when the server already hosts other websites on ports 80 and 443 and is
too small for Docker (e.g. 1 CPU, 2 GB). nginx stays in charge; nothing else
on the server changes.

| Part | Where |
| --- | --- |
| Code | `/srv/smart-estate/backend` (branch `phase-7`), owned by the `smartestate` user |
| Settings | `/srv/smart-estate/backend.env` (readable only by `smartestate`) |
| Database | PostgreSQL on the server, database and user `smartestate` |
| API | `smart-estate-api` service: gunicorn on `127.0.0.1:8001` |
| Jobs | `smart-estate-paynow-poll`, `smart-estate-rent-run`, `smart-estate-backup` timers |
| Backups | `/srv/smart-estate/backups`, nightly at 02:00, 14 days kept |
| Web apps | `/var/www/smart-estate/admin` and `/var/www/smart-estate/portal` (built elsewhere, uploaded) |
| nginx | `/etc/nginx/sites-available/smart-estate-{api,admin,portal}`, certificates by certbot |
| Memory | 1 GB swap at `/swapfile` |

Update the API:

```bash
cd /srv/smart-estate/backend && sudo -u smartestate git pull
run() { sudo -u smartestate env $(sudo cat /srv/smart-estate/backend.env | xargs) /srv/smart-estate/venv/bin/python manage.py "$@"; }
sudo -u smartestate /srv/smart-estate/venv/bin/pip install -q -r requirements.txt
run migrate --noinput && run collectstatic --noinput
sudo systemctl restart smart-estate-api
```

Update the web apps: build them on a computer (in `smart-estate-frontend`,
set `https://api.<domain>/` in both `environment.prod.ts` files, run
`npx nx run-many -t build -p smart-estate-back-office smart-estate-front-office --configuration=production`,
then put the files back), upload `dist/apps/...` to the server and copy them
into `/var/www/smart-estate/admin` and `/var/www/smart-estate/portal`.

Logs: `journalctl -u smart-estate-api -f`.
