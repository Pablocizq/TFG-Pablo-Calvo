from django.urls import path
from . import views

urlpatterns = [
    path('inicio/', views.inicio, name='inicio'),
    path('dataset/<int:pk>/delete/', views.dataset_delete, name='dataset_delete'),
    path('dataset/<int:pk>/', views.visualizar, name='visualizar'),
    path('dataset/<int:pk>/editar/', views.editar_metadatos, name='editar_metadatos'),
    path('crear-conjunto/', views.crear_conjunto, name='crear_conjunto'),
    path('metadatos/', views.metadatos, name='metadatos'),
]
