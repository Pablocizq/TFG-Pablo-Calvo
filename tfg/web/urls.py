from django.urls import path
from . import views

urlpatterns = [
    path('inicio/', views.inicio, name='inicio'),
    path('dataset/<int:pk>/delete/', views.dataset_delete, name='dataset_delete'),
    path('dataset/<int:pk>/', views.visualizar, name='visualizar'),
    path('dataset/<int:pk>/editar/', views.editar_metadatos, name='editar_metadatos'),
    path('crear-conjunto/', views.crear_conjunto, name='crear_conjunto'),
    path('metadatos/', views.metadatos, name='metadatos'),
    path('metadatos/turtle/', views.generar_turtle, name='generar_turtle'),
    path('inferir/', views.inferir, name='inferir'),
    path('api/extract-properties/', views.extract_properties_api, name='extract_properties_api'),
]
