"""
URL configuration for smartEstateBackend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path

from .health import health
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from .health import health

urlpatterns = [
    path('health', health),
    # path('admin/', admin.site.urls),
    path('', include('estates.url')),
    path('', include('authentication.url')),
    path('', include('complaint.url')),
    path('', include('home.url')),
    path('', include('owner.url')),
    path('', include('provider.url')),
    path('', include('resident.url')),
    path('', include('stand.url')),
    path('', include('visit.url')),
    path('', include('whitelist.url')),
    path('', include('parameters.url')),
    path('', include('whatsapp.url')),
    path('', include('notice.url')),
    path('', include('reports.url')),
    path('', include('levy.url')),
    path('', include('gatepass.url')),
    path('', include('assist.url')),
    path('', include('portal.url')),
    path('', include('ussd.url')),
    path('', include('rentals.url')),
    path('', include('dashboard.url')),
    path('', include('imports.url')),
    path('', include('audit.url')),
]
