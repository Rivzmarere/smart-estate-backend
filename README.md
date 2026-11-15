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
