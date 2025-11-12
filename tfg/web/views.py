from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import connection, DatabaseError
from django.http import HttpResponse
from django.utils.text import slugify
from .models import Dataset


def inicio(request):
    # Filtramos por el usuario 1 según lo solicitado
    conjuntos = Dataset.objects.filter(id_usuario=1)
    for conjunto in conjuntos:
        print(conjunto.nombre)
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
                # Insertamos respetando el esquema de db.sql.
                # Si el POST viene desde metadatos, intentamos guardar también los campos.
                def nz(val):
                    v = (val or '').strip()
                    return v if v != '' else None

                identificador = nz(request.POST.get('identificador'))
                titulo = nz(request.POST.get('titulo'))
                descripcion = nz(request.POST.get('descripcion'))
                dcat_type = nz(request.POST.get('dcat_type'))
                idioma = nz(request.POST.get('idioma'))
                tema = nz(request.POST.get('tema'))
                extension_temporal = nz(request.POST.get('extension_temporal'))
                extension_espacial = nz(request.POST.get('extension_espacial'))
                url_descarga = nz(request.POST.get('url_descarga'))
                issued = nz(request.POST.get('issued'))
                modificado = nz(request.POST.get('modificado'))
                publisher_name = nz(request.POST.get('publisher_name'))
                url_acceso = nz(request.POST.get('url_acceso'))
                formato = nz(request.POST.get('formato'))
                licencia = nz(request.POST.get('licencia'))
                derechos = nz(request.POST.get('derechos'))
                descripcion_distribucion = nz(request.POST.get('descripcion_distribucion'))
                url_metadatos = nz(request.POST.get('url_metadatos'))
                contenido_metadatos = nz(request.POST.get('metadata_content'))

                cursor.execute(
                    """
                    INSERT INTO dataset (
                        id_usuario, nombre, identificador, titulo, descripcion, dcat_type, idioma, tema,
                        extension_temporal, extension_espacial, url_descarga, issued, modificado,
                        publisher_name, url_acceso, formato, licencia, derechos, descripcion_distribucion, url_metadatos, contenido_metadatos
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_dataset, fecha_creacion;
                    """,
                    [
                        1, name, identificador, titulo, descripcion, dcat_type, idioma, tema,
                        extension_temporal, extension_espacial, url_descarga, issued, modificado,
                        publisher_name, url_acceso, formato, licencia, derechos, descripcion_distribucion, url_metadatos, contenido_metadatos
                    ]
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
    formato = request.GET.get('formato', '') if request.method == 'GET' else ''
    metadata_url = request.GET.get('metadata_url', '') if request.method == 'GET' else ''
    return render(request, 'metadatos.html', {
        'name': name,
        'formato': formato,
        'metadata_url': metadata_url
    })


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


def editar_metadatos(request, pk):
    """Muestra el formulario de edición de metadatos y procesa las actualizaciones."""
    dataset = get_object_or_404(Dataset, pk=pk)
    
    if request.method == 'POST':
        # Procesar actualización
        try:
            with connection.cursor() as cursor:
                def nz(val):
                    v = (val or '').strip()
                    return v if v != '' else None

                identificador = nz(request.POST.get('identificador'))
                titulo = nz(request.POST.get('titulo'))
                descripcion = nz(request.POST.get('descripcion'))
                dcat_type = nz(request.POST.get('dcat_type'))
                idioma = nz(request.POST.get('idioma'))
                tema = nz(request.POST.get('tema'))
                extension_temporal = nz(request.POST.get('extension_temporal'))
                extension_espacial = nz(request.POST.get('extension_espacial'))
                url_descarga = nz(request.POST.get('url_descarga'))
                issued = nz(request.POST.get('issued'))
                modificado = nz(request.POST.get('modificado'))
                publisher_name = nz(request.POST.get('publisher_name'))
                url_acceso = nz(request.POST.get('url_acceso'))
                formato = nz(request.POST.get('formato'))
                licencia = nz(request.POST.get('licencia'))
                derechos = nz(request.POST.get('derechos'))
                descripcion_distribucion = nz(request.POST.get('descripcion_distribucion'))
                url_metadatos = nz(request.POST.get('url_metadatos'))
                contenido_metadatos = nz(request.POST.get('metadata_content'))

                cursor.execute(
                    """
                    UPDATE dataset SET
                        identificador = %s, titulo = %s, descripcion = %s, dcat_type = %s, idioma = %s,
                        tema = %s, extension_temporal = %s, extension_espacial = %s, url_descarga = %s,
                        issued = %s, modificado = %s, publisher_name = %s, url_acceso = %s,
                        formato = %s, licencia = %s, derechos = %s, descripcion_distribucion = %s,
                        url_metadatos = %s, contenido_metadatos = %s
                    WHERE id_dataset = %s
                    """,
                    [
                        identificador, titulo, descripcion, dcat_type, idioma,
                        tema, extension_temporal, extension_espacial, url_descarga,
                        issued, modificado, publisher_name, url_acceso,
                        formato, licencia, derechos, descripcion_distribucion,
                        url_metadatos, contenido_metadatos, pk
                    ]
                )
                
            dataset_data = _get_dataset_data(pk)
            return render(request, 'editar_metadatos.html', {
                'success': 'Metadatos actualizados correctamente.',
                'dataset': dataset,
                **dataset_data
            })
        except DatabaseError as e:
            dataset_data = _get_dataset_data(pk)
            return render(request, 'editar_metadatos.html', {
                'error': f'Error al actualizar en la base de datos: {str(e)}',
                'dataset': dataset,
                **dataset_data
            })
    
    # GET - Cargar datos existentes
    dataset_data = _get_dataset_data(pk)
    context = {'dataset': dataset, **dataset_data}
    return render(request, 'editar_metadatos.html', context)


def _get_dataset_data(pk):
    """Obtiene todos los datos del dataset desde la BD."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT identificador, titulo, descripcion, dcat_type, idioma, tema,
                   extension_temporal, extension_espacial, url_descarga, issued, modificado,
                   publisher_name, url_acceso, formato, licencia, derechos,
                   descripcion_distribucion, url_metadatos, contenido_metadatos
            FROM dataset
            WHERE id_dataset = %s
            """,
            [pk]
        )
        row = cursor.fetchone()
        if row:
            return {
                'identificador': row[0] or '',
                'titulo': row[1] or '',
                'descripcion': row[2] or '',
                'dcat_type': row[3] or '',
                'idioma': row[4] or '',
                'tema': row[5] or '',
                'extension_temporal': row[6] or '',
                'extension_espacial': row[7] or '',
                'url_descarga': row[8] or '',
                'issued': row[9].strftime('%Y-%m-%d') if row[9] else '',
                'modificado': row[10].strftime('%Y-%m-%d') if row[10] else '',
                'publisher_name': row[11] or '',
                'url_acceso': row[12] or '',
                'formato': row[13] or '',
                'licencia': row[14] or '',
                'derechos': row[15] or '',
                'descripcion_distribucion': row[16] or '',
                'url_metadatos': row[17] or '',
                'contenido_metadatos': row[18] or '',
            }
    return {}


def _escape_literal(value: str) -> str:
    """Escapa caracteres especiales para usarlos en literales Turtle."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


@require_POST
def generar_turtle(request):
    """Genera un archivo Turtle con los metadatos proporcionados."""
    fields = {
        'name': request.POST.get('name', '').strip(),
        'identificador': request.POST.get('identificador', '').strip(),
        'titulo': request.POST.get('titulo', '').strip(),
        'descripcion': request.POST.get('descripcion', '').strip(),
        'dcat_type': request.POST.get('dcat_type', '').strip(),
        'idioma': request.POST.get('idioma', '').strip(),
        'tema': request.POST.get('tema', '').strip(),
        'extension_temporal': request.POST.get('extension_temporal', '').strip(),
        'extension_espacial': request.POST.get('extension_espacial', '').strip(),
        'url_descarga': request.POST.get('url_descarga', '').strip(),
        'issued': request.POST.get('issued', '').strip(),
        'modificado': request.POST.get('modificado', '').strip(),
        'publisher_name': request.POST.get('publisher_name', '').strip(),
        'url_acceso': request.POST.get('url_acceso', '').strip(),
        'formato': request.POST.get('formato', '').strip(),
        'licencia': request.POST.get('licencia', '').strip(),
        'derechos': request.POST.get('derechos', '').strip(),
        'descripcion_distribucion': request.POST.get('descripcion_distribucion', '').strip(),
        'url_metadatos': request.POST.get('url_metadatos', '').strip(),
    }

    dataset_identifier = fields['identificador'] or fields['name'] or 'dataset'
    slug = slugify(dataset_identifier) or 'dataset'
    dataset_uri = f"<urn:dataset:{slug}>"

    prefixes = (
        "@prefix dct: <http://purl.org/dc/terms/> .\n"
        "@prefix dcat: <http://www.w3.org/ns/dcat#> .\n"
        "@prefix foaf: <http://xmlns.com/foaf/0.1/> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n"
    )

    statements = []

    def add_literal(predicate, value, lang=None, datatype=None):
        if not value:
            return
        literal = _escape_literal(value)
        if datatype:
            statements.append([f'{predicate} "{literal}"^^{datatype}'])
        elif lang:
            statements.append([f'{predicate} "{literal}"@{lang}'])
        else:
            statements.append([f'{predicate} "{literal}"'])

    def add_uri(predicate, value):
        if not value:
            return
        statements.append([f'{predicate} <{value}>'])

    add_literal('dct:identifier', fields['identificador'])
    add_literal('dct:title', fields['titulo'], lang='es')
    add_literal('dct:description', fields['descripcion'], lang='es')
    add_literal('dct:type', fields['dcat_type'])
    add_literal('dct:language', fields['idioma'])
    add_literal('dcat:theme', fields['tema'])
    add_literal('dct:temporal', fields['extension_temporal'])
    add_literal('dct:spatial', fields['extension_espacial'])
    add_literal('dct:issued', fields['issued'], datatype='xsd:date')
    add_literal('dct:modified', fields['modificado'], datatype='xsd:date')
    add_literal('dct:format', fields['formato'])
    add_literal('dct:license', fields['licencia'])
    add_literal('dct:rights', fields['derechos'])
    add_uri('dcat:landingPage', fields['url_metadatos'])
    add_uri('dcat:downloadURL', fields['url_descarga'])
    add_uri('dcat:accessURL', fields['url_acceso'])

    if fields['publisher_name']:
        statements.append([
            'dct:publisher [',
            f'        foaf:name "{_escape_literal(fields["publisher_name"])}"@es',
            '    ]'
        ])

    distribution_parts = []
    if fields['descripcion_distribucion']:
        distribution_parts.append(f'dct:description "{_escape_literal(fields["descripcion_distribucion"])}"@es')
    if fields['url_descarga']:
        distribution_parts.append(f'dcat:downloadURL <{fields["url_descarga"]}>')
    if fields['url_acceso']:
        distribution_parts.append(f'dcat:accessURL <{fields["url_acceso"]}>')
    if fields['formato']:
        distribution_parts.append(f'dct:format "{_escape_literal(fields["formato"])}"')

    if distribution_parts:
        statements.append(
            ['dcat:distribution ['] +
            [f'        {part}' for part in distribution_parts] +
            ['    ]']
        )

    lines = [prefixes, f"{dataset_uri} a dcat:Dataset"]
    if statements:
        lines[-1] += " ;"
        for idx, stmt_lines in enumerate(statements):
            terminator = " ;" if idx < len(statements) - 1 else " ."
            for line_idx, content in enumerate(stmt_lines):
                if line_idx == len(stmt_lines) - 1:
                    lines.append(f"    {content}{terminator}")
                else:
                    lines.append(f"    {content}")
    else:
        lines[-1] += " ."

    turtle_content = "\n".join(lines) + "\n"
    filename = f"metadatos_{slug}.ttl"
    response = HttpResponse(turtle_content, content_type="text/turtle; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response