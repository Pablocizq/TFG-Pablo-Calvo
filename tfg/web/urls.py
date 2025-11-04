from django.urls import path
from . import views

urlpatterns = [
    path('inicio/', views.inicio, name='inicio'),
    path('dataset/<int:pk>/delete/', views.dataset_delete, name='dataset_delete'),
    path('crear-conjunto/', views.crear_conjunto, name='crear_conjunto'),
]
