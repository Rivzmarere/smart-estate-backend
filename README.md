# Smart Estate backend

Django 5.2 LTS + Django REST Framework API for estate visitor management, residents, complaints and service providers.

## Run locally (quick, SQLite)

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
DJANGO_DEBUG=True .venv/bin/python manage.py migrate
DJANGO_DEBUG=True .venv/bin/python manage.py createsuperuser
DJANGO_DEBUG=True .venv/bin/python manage.py runserver
```

## Run with PostgreSQL (same as production)

```bash
cp .env.example .env   # then set a real DJANGO_SECRET_KEY and passwords
docker compose up -d --build
docker compose exec api python manage.py createsuperuser
```

## Tests

```bash
DJANGO_DEBUG=True .venv/bin/python manage.py test
```

## Access rules

| Who | Can do |
| --- | --- |
| Anyone (resident portal) | Book a visitor or log a complaint for their own stand (stand number + their phone), read lookup lists and the service-provider directory (no ID numbers) |
| Guard | Everything visitors and whitelist; read residents, owners, homes, stands |
| Admin | Everything, including creating users |

Users get the `Guard` role unless an admin sets `Admin`. Public booking is rate-limited to 20 requests per hour per IP; login to 10 per minute.

## Environment variables

See `.env.example`. With `DJANGO_DEBUG=False` the app refuses to start without `DJANGO_SECRET_KEY` and `DATABASE_URL`.

## WhatsApp bot

Residents message the estate's WhatsApp number to book visitors, see or cancel them, and report repairs.
They get a message when the guard books their visitor in. Only numbers registered on a home are served.

Try it locally without Meta (nothing is sent):

```bash
DJANGO_DEBUG=True .venv/bin/python manage.py whatsapp_chat 263772111111
```

Connect to Meta (test number works before business verification, for up to 5 recipient numbers):

1. developers.facebook.com → create an app of type **Business** → add **WhatsApp**.
2. WhatsApp → API setup: copy the **Phone number ID** and a **token**; add your phone as a test recipient.
3. App settings → Basic: copy the **App secret**.
4. Set `WHATSAPP_ENABLED=True`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, and any random `WHATSAPP_VERIFY_TOKEN` in `.env`.
5. WhatsApp → Configuration → Webhook: callback URL `https://<your-api-domain>/whatsapp/webhook`, the same verify token; subscribe to **messages**.
6. For arrival messages more than 24 hours after a resident last wrote, get a **utility** template approved
   (body: `{{1}} arrived at the gate at {{2}} (code {{3}})`) and set `WHATSAPP_TEMPLATE_VISITOR_ARRIVED` to its name.

The webhook needs a public HTTPS address. For local testing use a tunnel such as `cloudflared tunnel --url http://localhost:8000`.
