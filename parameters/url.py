from django.urls import include, path

urlpatterns = [
    # path('admin/', admin.site.urls),
    path('parameters/', include('parameters.urls.url_complaint_category')),
    path('parameters/', include('parameters.urls.url_complaint_status')),
    path('parameters/', include('parameters.urls.url_gender')),
    path('parameters/', include('parameters.urls.url_home_status')),
    path('parameters/', include('parameters.urls.url_nationality')),
    path('parameters/', include('parameters.urls.url_provider_category')),
    path('parameters/', include('parameters.urls.url_provider_status')),
    path('parameters/', include('parameters.urls.url_stand_status')),
    path('parameters/', include('parameters.urls.url_transport_type')),
    path('parameters/', include('parameters.urls.url_user_type')),
    path('parameters/', include('parameters.urls.url_visit_status')),
]
