from django.shortcuts import render
from django.http import HttpResponse

def inicio(request):
    return HttpResponse("¡Hola, mundo! Esta es mi primera página en Django.")
