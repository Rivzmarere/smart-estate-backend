from django.urls import path

from . import views

urlpatterns = [
    path("rentals/properties", views.Properties.as_view()),
    path("rentals/properties/<int:home_id>", views.PropertyDetail.as_view()),
    path("rentals/people", views.People.as_view()),
    path("rentals/leases", views.Leases.as_view()),
    path("rentals/leases/<int:id>", views.LeaseDetail.as_view()),
    path("rentals/leases/<int:id>/end", views.EndLease.as_view()),
    path("rentals/leases/<int:id>/payments", views.LeasePayments.as_view()),
    path("rentals/leases/<int:id>/document", views.LeaseDocument.as_view()),
    path("rentals/bill", views.BillRent.as_view()),
    path("rentals/expenses", views.Expenses.as_view()),
    path("rentals/expenses/<int:id>", views.ExpenseDetail.as_view()),
    path("rentals/statement", views.Statement.as_view()),
]
