"""
Chat with the bot in the terminal, as if from a resident's WhatsApp number.
Nothing is sent to Meta.

    DJANGO_DEBUG=True python manage.py whatsapp_chat 263772111111

Type a message, or a number to tap that option in the last menu. Ctrl+D to quit.
"""

import itertools

from django.core.management.base import BaseCommand
from django.test import override_settings

from whatsapp import bot, client


def render(message):
    if message["type"] == "text":
        return message["text"]["body"], []
    if message["type"] == "template":
        return f"[template {message['template']['name']}]", []
    interactive = message["interactive"]
    lines, options = [interactive["body"]["text"]], []
    action = interactive["action"]
    items = [(b["reply"]["id"], b["reply"]["title"], None) for b in action.get("buttons", [])]
    for section in action.get("sections", []):
        items += [(r["id"], r["title"], r.get("description")) for r in section["rows"]]
    for number, (oid, title, desc) in enumerate(items, 1):
        lines.append(f"  {number}. {title}" + (f"  ({desc})" if desc else ""))
        options.append(oid)
    return "\n".join(lines), options


class Command(BaseCommand):
    help = "Chat with the Smart Estate WhatsApp bot locally (no messages are sent)."

    def add_arguments(self, parser):
        parser.add_argument("wa_id", help="Resident WhatsApp number, e.g. 263772111111")

    def handle(self, wa_id, **options):
        ids = itertools.count(1)
        options_shown = []
        with override_settings(WHATSAPP_ENABLED=True, WHATSAPP_DRY_RUN=True):
            self.stdout.write("Type a message (try 'hi'). Ctrl+D to quit.\n")
            while True:
                try:
                    typed = input("you> ").strip()
                except EOFError:
                    self.stdout.write("\n")
                    return
                if typed.isdigit() and options_shown and 1 <= int(typed) <= len(options_shown):
                    message = {"type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": options_shown[int(typed) - 1]}}}
                else:
                    message = {"type": "text", "text": {"body": typed}}
                message.update({"from": wa_id, "id": f"local.{next(ids)}"})
                start = len(client.OUTBOX)
                bot.handle_message(wa_id, message)
                for out in client.OUTBOX[start:]:
                    text, opts = render(out)
                    if opts:
                        options_shown = opts
                    self.stdout.write(self.style.SUCCESS("bot> ") + text.replace("\n", "\n     ") + "\n")
