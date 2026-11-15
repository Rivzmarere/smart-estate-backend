"""Tell residents when the estate changes the status of their repair."""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from sms.sender import send_sms
from whatsapp.notifications import notify

from .models import Complain

logger = logging.getLogger(__name__)


def send_status_update(complaint):
    status = complaint.compalint_status.name
    category = complaint.complaint_category.name
    text = f"🔧 Update on your repair *{complaint.complain_code}* ({category}): it is now *{status}*."
    if complaint.assigned_to and status.lower() not in {"resolved", "closed", "done", "completed"}:
        name = complaint.assigned_to.get_full_name() or complaint.assigned_to.username
        text += f"\nHandled by: {name}."
    if notify(complaint.resident_phone_number, text, settings.WHATSAPP_TEMPLATE_REPAIR_UPDATE, [complaint.complain_code, category, status]):
        return True
    return send_sms(complaint.resident_phone_number, f"Smart Estate: your repair {complaint.complain_code} ({category}) is now {status}.")


@receiver(pre_save, sender=Complain)
def remember_old_status(sender, instance, **kwargs):
    if instance.pk:
        instance._old_status_id = Complain.objects.filter(pk=instance.pk).values_list("compalint_status_id", flat=True).first()


@receiver(post_save, sender=Complain)
def status_changed(sender, instance, created, **kwargs):
    if created or getattr(instance, "_old_status_id", None) in (None, instance.compalint_status_id):
        return
    if kwargs.get("raw"):
        return

    def send():
        try:
            send_status_update(Complain.objects.select_related("compalint_status", "complaint_category", "assigned_to").get(pk=instance.pk))
        except Exception:
            logger.exception("Could not send repair update for complaint %s", instance.pk)

    transaction.on_commit(send)
