from django.urls import path

from .views import CheckImport, Imports, SaveImport, Template, UndoImport

urlpatterns = [
    path("imports", Imports.as_view()),
    path("imports/template", Template.as_view()),
    path("imports/check", CheckImport.as_view()),
    path("imports/run", SaveImport.as_view()),
    path("imports/<int:id>/undo", UndoImport.as_view()),
]
