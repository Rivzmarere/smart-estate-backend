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

## Levies and payments

Levies are billed in US dollars, one invoice per home per month
(`POST /levies/invoices/generate`). Payments can be USD or ZiG; a ZiG payment
is converted at the rate recorded with it (`/levies/rates`), so balances are
always in USD. Money received pays off the oldest invoice first, and
"arrears" is what is still owed on invoices past their due date.

Residents pay from WhatsApp (*Pay levy*) with EcoCash or OneMoney through
Paynow. To switch this on:

1. In Paynow, create one integration per currency (USD, and ZiG if wanted)
   and set `PAYNOW_USD_INTEGRATION_ID` / `_KEY` (and `PAYNOW_ZWG_...`).
2. Set `PUBLIC_API_URL` to this API's public https address. Paynow posts
   results to `PUBLIC_API_URL/paynow/result/<payment id>`.
3. Set `PAYNOW_AUTH_EMAIL` (in Paynow test mode it must be the merchant's
   login email) and `PAYNOW_DRY_RUN=False`.
4. Run `python manage.py paynow_poll` every few minutes (the
   `paynow-poller` service in docker-compose does this), in case a result
   POST never arrives.

Paynow test mode numbers: 0771111111 succeeds, 0772222222 succeeds after a
delay, 0773333333 is cancelled by the user, 0774444444 has insufficient
balance.

## Gate walk-ins

When a visitor arrives without a code, the guard sends a walk-in request
from the gate screen. The resident gets WhatsApp buttons (Approve / Decline);
approving creates a visit the guard books in as usual. Without WhatsApp the
gate shows the resident's number, and the guard records the answer from
the call. Requests expire after 10 minutes.

## Repairs

Residents can send up to three photos with a repair report. Photos are kept
in `MEDIA_ROOT` (put it on a persistent volume) and only staff can open
them. When the estate changes a repair's status, the resident is told on
WhatsApp, or by SMS if WhatsApp is not possible.

## WhatsApp templates to submit to Meta

Messages to someone who has not written in the last 24 hours need approved
templates. Submit these (category "Utility") and put their names in `.env`:

| Setting | Body | Buttons |
| --- | --- | --- |
| `WHATSAPP_TEMPLATE_VISITOR_ARRIVED` | {{1}} arrived at the gate at {{2}} (code {{3}}). | none |
| `WHATSAPP_TEMPLATE_WALK_IN` | {{1}} is at the gate asking to visit you. Let them in? | Quick reply: Approve, Decline |
| `WHATSAPP_TEMPLATE_PAYMENT_RECEIPT` | Smart Estate receipt {{1}}: {{2}} received for {{3}}. Balance now {{4}}. | none |
| `WHATSAPP_TEMPLATE_REPAIR_UPDATE` | Your repair {{1}} ({{2}}) is now: {{3}}. | none |

## Several estates on one installation

Each estate's data is kept apart automatically: every estate-owned model
inherits `estates.models.EstateScoped`, whose default manager only returns
the *current estate's* rows, and new rows are stamped with that estate.
The current estate is:

- for staff: the estate on their account;
- for platform staff (a superuser with no estate): every estate, or the
  one named in the `X-Estate` header;
- for the resident portal: the `X-Estate` header or `?estate=<slug>`;
- with only one active estate: that estate (nothing to configure).

Code that runs outside a request (the WhatsApp webhook, Paynow callbacks,
management commands) works inside `estates.context.use_estate(estate)`.
Use `Model.all_estates` only where looking across estates is intended.

On first install the existing data is put in an estate named
`DEFAULT_ESTATE_NAME` (slug `DEFAULT_ESTATE_SLUG`). To add an estate, a
platform user (`python manage.py createsuperuser`, no estate) uses
`POST /estates` and then `POST /estates/<id>/admin` for its first
administrator. Each estate can have its own Paynow account (Estate
settings); otherwise the server-wide `PAYNOW_*` settings are used.

## Emergencies, service providers and the office inbox

- **Emergency**: residents tap *🚨 Emergency* or type *SOS*. The alert is
  SMSed to the estate's emergency numbers (Estate settings), shown on the
  gate screen, and the resident gets the national emergency numbers.
  Guards acknowledge and resolve it; the resident is told each time.
- **Service providers**: residents see the estate's active providers by
  category (names and phone numbers only).
- **Talk to the office**: the resident's messages go to the back-office
  Inbox until they type *menu*. Replies go out on WhatsApp; after 24 hours
  of silence from the resident that needs the
  `WHATSAPP_TEMPLATE_OFFICE_MESSAGE` template, otherwise the office is
  told to phone them.

## Residents' portal (sign-in) and household

Residents sign in to the portal with their mobile number and a 6-digit
code (WhatsApp if they wrote recently, otherwise SMS; only a hash is kept,
codes expire in 10 minutes, 5 tries). The token works only on `/resident/...`
endpoints and is tied to one estate.

A number can belong to a home as its **owner**, its **main resident**
(tenant or owner living there) or a **household member** (family, domestic
worker, co-tenant). What each may do is in `portal/access.py`:

| | Owner | Main resident | Member | Member (no bookings) |
| --- | --- | --- | --- | --- |
| Visitors, walk-ins | ✓ | ✓ | ✓ | |
| Repairs, emergency, office chat | ✓ | ✓ | ✓ | ✓ |
| Levy and payments | ✓ | ✓ | | |
| Add / remove household members | ✓ | ✓ | | |
| New tenant / tenant moving out | ✓ | | | |

The same rules apply on WhatsApp, USSD and the public booking form.
Household changes wait for the office (Back office > Inbox > Household)
when the estate's *household approval* setting is on (the default);
removing someone always takes effect at once.

## USSD (*xxx#)

Book a visitor, see visitors, levy balance and EcoCash payment, report a
fault, and emergency, on any phone. Get a USSD short code from the mobile
networks or an aggregator, set `USSD_SECRET`, and give the gateway
`https://API_DOMAIN/ussd/<USSD_SECRET>` as the callback. The endpoint takes
the common format (`sessionId`, `serviceCode`, `phoneNumber`, `text` with
answers joined by `*`; reply `CON ...` / `END ...`); a gateway with another
format needs a small adapter around `ussd.menu.handle()`.
