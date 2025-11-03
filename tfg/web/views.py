from django.shortcuts import render
from django.http import HttpResponse

def inicio(request):
    conjunto = {
        'nombre': 'Conjunto 1',
        'fecha': '25-10-2025'
    }
    return render(request, 'inicio.html', {'conjunto': conjunto})
