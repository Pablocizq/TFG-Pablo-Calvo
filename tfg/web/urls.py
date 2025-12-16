from django.urls import path
from . import views

urlpatterns = [
    path('inicio/', views.inicio, name='inicio'),
    path('dataset/<str:pk>/delete/', views.dataset_delete, name='dataset_delete'),
    path('dataset/<str:pk>/', views.visualizar, name='visualizar'),
    path('dataset/<str:pk>/editar/', views.editar_metadatos, name='editar_metadatos'),
    path('crear-conjunto/', views.crear_conjunto, name='crear_conjunto'),
    path('metadatos/', views.metadatos, name='metadatos'),
    path('metadatos/turtle/', views.generar_turtle, name='generar_turtle'),
    path('inferir/', views.inferir, name='inferir'),
    path('ckan/proxy/', views.ckan_proxies, name='ckan_proxies'),
    path('ckan/publish/', views.publish_to_ckan, name='publish_to_ckan'),
    path('api/extract-properties/', views.extract_properties_api, name='extract_properties_api'),
    path('api/generate-title/', views.generate_title_with_ai, name='generate_title_with_ai'),
    path('api/generate-metadata/', views.generate_metadata_with_ai, name='generate_metadata_with_ai'),
]
