from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import connection, DatabaseError
from .models import Dataset


def inicio(request):
    conjuntos = Dataset.objects.all()
    for conjunto in conjuntos:
        print(conjunto.name)
    return render(request, 'inicio.html', {'conjuntos': conjuntos})


@require_POST
def dataset_delete(request, pk):
    """Eliminar un Dataset por su PK y redirigir a la página de inicio.

    Usamos POST para evitar borrados por GET y `get_object_or_404` para
    manejar el caso en que no exista.
    """
    dataset = get_object_or_404(Dataset, pk=pk)
    dataset.delete()
    return redirect('inicio')


def crear_conjunto(request):
    """Muestra el formulario y procesa el POST para crear un nuevo conjunto.

    Se inserta directamente usando un cursor SQL para permitir que la BD
    genere automáticamente `id_dataset` y `created_at` (si la tabla tiene
    defaults en el lado del servidor). Usamos `INSERT ... RETURNING` para
    obtener los valores generados si es necesario.
    """
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        next_page = request.POST.get('next', '')
        if not name:
            # Si venimos desde metadatos, mostramos el error en esa plantilla
            if next_page == 'metadatos':
                return render(request, 'metadatos.html', {
                    'error': 'El nombre no puede estar vacío.',
                    'name': name,
                })
            return render(request, 'crear_conjunto.html', {
                'error': 'El nombre no puede estar vacío.',
                'name': name,
            })

        # Procesar inserción en la base de datos
        try:
            with connection.cursor() as cursor:
                # Ajusta el nombre de la tabla/columnas si tu esquema es distinto.
                cursor.execute(
                    "INSERT INTO dataset (name) VALUES (%s) RETURNING id_dataset, created_at;",
                    [name]
                )
                row = cursor.fetchone()
                # row será (id_dataset, created_at) si el RETURNING tuvo éxito.
        except DatabaseError as e:
            # Devolver mensaje en plantilla para depuración
            err_msg = str(e)
            if next_page == 'metadatos':
                return render(request, 'metadatos.html', {
                    'error': f'Error al guardar en la base de datos: {err_msg}',
                    'name': name,
                })
            return render(request, 'crear_conjunto.html', {
                'error': f'Error al guardar en la base de datos: {err_msg}',
                'name': name,
            })

        # Insert OK
        if next_page == 'metadatos':
            # Volvemos a la plantilla de metadatos y mostramos notificación de éxito
            return render(request, 'metadatos.html', {
                'success': 'Dataset guardado correctamente.',
                'name': name,
            })
    # GET
    return render(request, 'crear_conjunto.html')

def metadatos(request):
    """Muestra el formulario para ingresar metadatos de un conjunto de datos."""
    # Si se recibe ?name=... desde crear_conjunto, lo pasamos al template
    name = request.GET.get('name', '') if request.method == 'GET' else ''
    return render(request, 'metadatos.html', {'name': name})


def visualizar(request, pk):
    """Muestra la página de visualización para un conjunto concreto."""
    conjunto = get_object_or_404(Dataset, pk=pk)
    context = {
        'conjunto': conjunto,
        # Placeholders por si más adelante añadimos propiedades/extracto desde BD
        'propiedades': request.GET.get('propiedades', ''),
        'extracto': request.GET.get('extracto', ''),
    }
    return render(request, 'visualizar.html', context)