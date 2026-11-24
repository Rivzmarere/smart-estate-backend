from django.urls import path

from .views import (
    AccountStatement, Accounts, ExchangeRates, GenerateLevies, Invoices, PaynowResult, Payments, ReversePayment, VoidInvoice,
)

urlpatterns = [
    path("levies/rates", ExchangeRates.as_view()),
    path("levies/invoices", Invoices.as_view()),
    path("levies/invoices/generate", GenerateLevies.as_view()),
    path("levies/invoices/<int:id>/void", VoidInvoice.as_view()),
    path("levies/accounts", Accounts.as_view()),
    path("levies/accounts/<int:home_id>", AccountStatement.as_view()),
    path("levies/payments", Payments.as_view()),
    path("levies/payments/<int:id>/reverse", ReversePayment.as_view()),
    path("paynow/result/<int:payment_id>", PaynowResult.as_view()),
]
