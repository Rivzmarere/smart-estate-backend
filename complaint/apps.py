from django.apps import AppConfig


class ComplaintConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'complaint'

    def ready(self):
        from . import notifications  # noqa: F401  (connects the status-change signal)
