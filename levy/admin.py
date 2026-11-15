from django.contrib import admin

from .models import ExchangeRate, Invoice, Payment

admin.site.register(ExchangeRate)
admin.site.register(Invoice)
admin.site.register(Payment)
