from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import connection, DatabaseError
from django.http import HttpResponse, JsonResponse
from django.utils.text import slugify
from django.contrib.auth.hashers import make_password, check_password
from .models import Dataset, Usuario
from .parsers.property_extraction_strategy import (
    CSVExtractionStrategy,
    JSONExtractionStrategy,
    RDFXMLExtractionStrategy,
    RDFTurtleExtractionStrategy
)
import json
import base64
import re
import os
import uuid
import io
import requests
from google import genai
from .services.ckan_service import CkanClient

INFERENCIA_CAMPOS = [
    {
        'id': 'titulo',
        'nombre': 'Título',
        'descripcion': 'Nombre representativo que resuma el contenido del dataset.',
    },
    {
        'id': 'descripcion',
        'nombre': 'Descripción',
        'descripcion': 'Texto breve que explique qué contiene y para qué sirve.',
    },
    {
        'id': 'tema',
        'nombre': 'Tema',
        'descripcion': 'Categoría principal o materia a la que pertenecen los datos.',
    },
    {
        'id': 'palabras_clave',
        'nombre': 'Palabras clave',
        'descripcion': 'Términos que facilitan la búsqueda y el etiquetado.',
    },
    {
        'id': 'extension_temporal',
        'nombre': 'Extensión temporal',
        'descripcion': 'Periodo de tiempo cubierto por la información.',
    },
    {
        'id': 'extension_espacial',
        'nombre': 'Extensión espacial',
        'descripcion': 'Área geográfica a la que aplica el dataset.',
    },
]


def login_view(request):
    """Vista de login que valida correo y contraseña."""
    if request.method == 'POST':
        correo = request.POST.get('correo', '').strip()
        contrasena = request.POST.get('contrasena', '').strip()
        
        if not correo or not contrasena:
            return render(request, 'login.html', {
                'error': 'Por favor completa todos los campos.'
            })
        
        try:
            # Buscar usuario por correo
            usuario = Usuario.objects.filter(correo=correo).first()
            
            if usuario and check_password(contrasena, usuario.contrasena):
                # Login exitoso: guardar user_id en sesión
                request.session['user_id'] = usuario.id_usuario
                request.session['user_name'] = usuario.nombre
                return redirect('inicio')
            else:
                return render(request, 'login.html', {
                    'error': 'Correo o contraseña incorrectos.'
                })
        except Exception as e:
            return render(request, 'login.html', {
                'error': f'Error al iniciar sesión: {str(e)}'
            })
    
    # GET request
    return render(request, 'login.html')


def register_view(request):
    """Vista de registro que crea un nuevo usuario."""
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        correo = request.POST.get('correo', '').strip()
        contrasena = request.POST.get('contrasena', '').strip()
        confirmar_contrasena = request.POST.get('confirmar_contrasena', '').strip()
        token_ckan = request.POST.get('token_ckan', '').strip() or None  # None si está vacío
        
        # Validaciones
        if not nombre or not correo or not contrasena or not confirmar_contrasena:
            return render(request, 'register.html', {
                'error': 'Por favor completa todos los campos.',
                'nombre': nombre,
                'correo': correo,
                'token_ckan': token_ckan
            })
        
        if contrasena != confirmar_contrasena:
            return render(request, 'register.html', {
                'error': 'Las contraseñas no coinciden.',
                'nombre': nombre,
                'correo': correo,
                'token_ckan': token_ckan
            })
        
        # Verificar si el correo ya existe
        if Usuario.objects.filter(correo=correo).exists():
            return render(request, 'register.html', {
                'error': 'Este correo ya está registrado.',
                'nombre': nombre,
                'token_ckan': token_ckan
            })
        
        try:
            # Crear usuario con contraseña hasheada
            with connection.cursor() as cursor:
                contrasena_hash = make_password(contrasena)
                cursor.execute(
                    """
                    INSERT INTO usuario (nombre, correo, contrasena, token_ckan)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id_usuario
                    """,
                    [nombre, correo, contrasena_hash, token_ckan]
                )
                row = cursor.fetchone()
                user_id = row[0] if row else None
            
            if user_id:
                # Iniciar sesión automáticamente
                request.session['user_id'] = user_id
                request.session['user_name'] = nombre
                return redirect('inicio')
            else:
                return render(request, 'register.html', {
                    'error': 'Error al crear el usuario.',
                    'nombre': nombre,
                    'correo': correo
                })
        except DatabaseError as e:
            return render(request, 'register.html', {
                'error': f'Error en la base de datos: {str(e)}',
                'nombre': nombre,
                'correo': correo
            })
    
    # GET request
    return render(request, 'register.html')


def logout_view(request):
    """Vista de logout que limpia la sesión."""
    request.session.flush()
    return redirect('login')


def perfil_usuario(request):
    """Vista de perfil de usuario para ver y editar información."""
    # Verificar autenticación
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    # Obtener datos del usuario
    try:
        usuario = Usuario.objects.get(id_usuario=user_id)
    except Usuario.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        token_ckan = request.POST.get('token_ckan', '').strip() or None
        contrasena_actual = request.POST.get('contrasena_actual', '').strip()
        nueva_contrasena = request.POST.get('nueva_contrasena', '').strip()
        confirmar_nueva_contrasena = request.POST.get('confirmar_nueva_contrasena', '').strip()
        
        # Validar nombre
        if not nombre:
            return render(request, 'usuario.html', {
                'usuario': usuario,
                'error': 'El nombre no puede estar vacío.'
            })
        
        # Si se intenta cambiar contraseña
        cambiar_contrasena = nueva_contrasena or confirmar_nueva_contrasena
        
        if cambiar_contrasena:
            # Validar que se proporcionó la contraseña actual
            if not contrasena_actual:
                return render(request, 'usuario.html', {
                    'usuario': usuario,
                    'error': 'Debes introducir tu contraseña actual para cambiarla.'
                })
            
            # Verificar contraseña actual
            if not check_password(contrasena_actual, usuario.contrasena):
                return render(request, 'usuario.html', {
                    'usuario': usuario,
                    'error': 'La contraseña actual es incorrecta.'
                })
            
            # Verificar que las nuevas contraseñas coincidan
            if nueva_contrasena != confirmar_nueva_contrasena:
                return render(request, 'usuario.html', {
                    'usuario': usuario,
                    'error': 'Las nuevas contraseñas no coinciden.'
                })
            
            # Actualizar con nueva contraseña
            try:
                with connection.cursor() as cursor:
                    contrasena_hash = make_password(nueva_contrasena)
                    cursor.execute(
                        """
                        UPDATE usuario 
                        SET nombre = %s, token_ckan = %s, contrasena = %s
                        WHERE id_usuario = %s
                        """,
                        [nombre, token_ckan, contrasena_hash, user_id]
                    )
            except DatabaseError as e:
                return render(request, 'usuario.html', {
                    'usuario': usuario,
                    'error': f'Error al actualizar: {str(e)}'
                })
        else:
            # Actualizar solo nombre y token (sin cambiar contraseña)
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE usuario 
                        SET nombre = %s, token_ckan = %s
                        WHERE id_usuario = %s
                        """,
                        [nombre, token_ckan, user_id]
                    )
            except DatabaseError as e:
                return render(request, 'usuario.html', {
                    'usuario': usuario,
                    'error': f'Error al actualizar: {str(e)}'
                })
        
        # Actualizar sesión si cambió el nombre
        request.session['user_name'] = nombre
        
        # Redirigir a inicio con mensaje de éxito
        return redirect('inicio')
    
    # GET request
    return render(request, 'usuario.html', {'usuario': usuario})


@require_POST
def eliminar_cuenta(request):
    """Vista para eliminar cuenta de usuario y todos sus datos."""
    # Verificar autenticación
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    # Obtener contraseña de confirmación
    contrasena_confirmacion = request.POST.get('contrasena_confirmacion', '').strip()
    
    if not contrasena_confirmacion:
        # Volver a perfil con error
        try:
            usuario = Usuario.objects.get(id_usuario=user_id)
            return render(request, 'usuario.html', {
                'usuario': usuario,
                'error': 'Debes introducir tu contraseña para eliminar la cuenta.'
            })
        except Usuario.DoesNotExist:
            return redirect('login')
    
    # Verificar contraseña
    try:
        usuario = Usuario.objects.get(id_usuario=user_id)
        if not check_password(contrasena_confirmacion, usuario.contrasena):
            return render(request, 'usuario.html', {
                'usuario': usuario,
                'error': 'Contraseña incorrecta. No se puede eliminar la cuenta.'
            })
    except Usuario.DoesNotExist:
        return redirect('login')
    
    # Eliminar usuario y todos sus datos
    try:
        with connection.cursor() as cursor:
            # 1. Obtener todos los datasets del usuario
            cursor.execute(
                "SELECT id_dataset FROM dataset WHERE id_usuario = %s",
                [user_id]
            )
            datasets = cursor.fetchall()
            dataset_ids = [row[0] for row in datasets]
            
            # 2. Eliminar ficheros de esos datasets
            if dataset_ids:
                placeholders = ','.join(['%s'] * len(dataset_ids))
                cursor.execute(
                    f"DELETE FROM fichero WHERE id_dataset IN ({placeholders})",
                    dataset_ids
                )
            
            # 3. Eliminar datasets del usuario
            cursor.execute(
                "DELETE FROM dataset WHERE id_usuario = %s",
                [user_id]
            )
            
            # 4. Eliminar usuario
            cursor.execute(
                "DELETE FROM usuario WHERE id_usuario = %s",
                [user_id]
            )
    except DatabaseError as e:
        # En caso de error, volver con mensaje
        return render(request, 'usuario.html', {
            'usuario': usuario,
            'error': f'Error al eliminar la cuenta: {str(e)}'
        })
    
    # Limpiar sesión y redirigir a login
    request.session.flush()
    return redirect('login')


def inicio(request):
    # Verificar autenticación
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    # Obtener nombre de usuario para mostrarlo
    user_name = request.session.get('user_name', 'Usuario')
    
    # Filtrar conjuntos por el usuario autenticado
    conjuntos = Dataset.objects.filter(id_usuario=user_id)
    return render(request, 'inicio.html', {
        'conjuntos': conjuntos,
        'user_name': user_name
    })


@require_POST
def dataset_delete(request, pk):
    """Eliminar un Dataset por su PK y redirigir a la página de inicio.

    Usamos POST para evitar borrados por GET y `get_object_or_404` para
    manejar el caso en que no exista.
    """
    dataset = get_object_or_404(Dataset, pk=pk)
    
    # Verificar si se solicitó borrar de CKAN
    delete_ckan = request.POST.get('delete_ckan') == 'true'
    
    # Si se solicitó borrar de CKAN y el dataset tiene identificador
    if delete_ckan and dataset.identificador:
        user_id = request.session.get('user_id')
        if user_id:
            try:
                ckan = CkanClient(user_id)
                ckan.delete_dataset(dataset.identificador)
            except Exception as e:
                # En un entorno real, usar logging. Por ahora imprimimos en consola
                print(f"Error borrando dataset {dataset.identificador} de CKAN: {e}")
    
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM fichero WHERE id_dataset = %s", [dataset.pk])
        cursor.execute("DELETE FROM dataset WHERE id_dataset = %s", [dataset.pk])

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

        try:
            with connection.cursor() as cursor:
                def nz(val):
                    v = (val or '').strip()
                    return v if v != '' else None

                identificador = None
                titulo = nz(request.POST.get('titulo'))
                descripcion = nz(request.POST.get('descripcion'))
                dcat_type = nz(request.POST.get('dcat_type'))
                idioma = nz(request.POST.get('idioma'))
                tema = nz(request.POST.get('tema'))
                palabras_clave = nz(request.POST.get('palabras_clave'))
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
                        palabras_clave, extension_temporal, extension_espacial, url_descarga, issued, modificado,
                        publisher_name, url_acceso, formato, licencia, derechos, descripcion_distribucion, url_metadatos, contenido_metadatos
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_dataset, fecha_creacion;
                    """,
                    [
                        request.session.get('user_id', 1), name, identificador, titulo, descripcion, dcat_type, idioma, tema,
                        palabras_clave, extension_temporal, extension_espacial, url_descarga, issued, modificado,
                        publisher_name, url_acceso, formato, licencia, derechos, descripcion_distribucion, url_metadatos, contenido_metadatos
                    ]
                )
                row = cursor.fetchone()
                id_dataset = row[0] if row else None
                
                # Procesar archivos si existen
                if id_dataset:
                    dataset_files_data = request.POST.get('dataset_files_data', '')
                    if dataset_files_data:
                        try:
                            files_data = json.loads(dataset_files_data)
                            formato_seleccionado = formato or ''
                            
                            for file_info in files_data:
                                # Extraer el contenido base64 (remover el prefijo data:...;base64,)
                                content_original = file_info.get('content', '')
                                if not content_original:
                                    continue
                                
                                # Extraer solo la parte base64 (sin el prefijo data:...;base64,)
                                match = re.search(r'base64,(.+)', content_original)
                                if match:
                                    content_base64 = match.group(1)
                                else:
                                    content_base64 = content_original
                                
                                # Decodificar base64 y manejar archivos binarios
                                try:
                                    # Decodificar base64 a bytes para verificar si es binario
                                    file_bytes = base64.b64decode(content_base64)
                                    
                                    # Verificar si el archivo contiene caracteres NUL (es binario)
                                    if b'\x00' in file_bytes:
                                        # Es un archivo binario, mantenerlo en base64
                                        file_content = content_base64
                                    else:
                                        # Intentar decodificar como texto
                                        try:
                                            file_content = file_bytes.decode('utf-8')
                                        except UnicodeDecodeError:
                                            # Si no es UTF-8, intentar con latin-1
                                            file_content = file_bytes.decode('latin-1')
                                except Exception:
                                    continue
                                
                                # Determinar tipo_formato
                                file_name = file_info.get('name', '').lower()
                                file_type = file_info.get('type', '').lower()
                                
                                tipo_formato = None
                                if formato_seleccionado:
                                    tipo_formato = formato_seleccionado.upper()
                                elif file_name.endswith('.csv') or 'csv' in file_type:
                                    tipo_formato = 'CSV'
                                elif file_name.endswith('.json') or 'json' in file_type:
                                    tipo_formato = 'JSON'
                                elif file_name.endswith('.ttl') or 'turtle' in file_type:
                                    tipo_formato = 'RDF-TURTLE'
                                elif file_name.endswith('.xml') or file_name.endswith('.rdf') or 'xml' in file_type or 'rdf' in file_type:
                                    tipo_formato = 'RDF-XML'
                                
                                # Si no se pudo determinar, usar el formato seleccionado o CSV por defecto
                                if not tipo_formato:
                                    tipo_formato = formato_seleccionado.upper() if formato_seleccionado else 'CSV'
                                
                                # Validar que el tipo_formato sea válido
                                if tipo_formato not in ['CSV', 'RDF-XML', 'RDF-TURTLE', 'JSON']:
                                    tipo_formato = 'CSV'
                                
                                # Insertar en la tabla FICHERO
                                cursor.execute(
                                    """
                                    INSERT INTO fichero (
                                        id_dataset, tipo_formato, url_datos, contenido, nombre_archivo
                                    )
                                    VALUES (%s, %s, %s, %s, %s)
                                    """,
                                    [
                                        id_dataset,
                                        tipo_formato,
                                        None,
                                        file_content,
                                        file_info.get('name', '')
                                    ]
                                )
                        except (json.JSONDecodeError, Exception):
                            pass
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
            # Redirigir a inicio.html como solicitó el usuario
            return redirect('inicio')
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


def inferir(request):
    """Interfaz para seleccionar columnas y lanzar la inferencia de metadatos."""
    query_params = request.GET.urlencode()
    return render(request, 'inferir.html', {
        'campos_inferencia': INFERENCIA_CAMPOS,
        'query_params': query_params,
    })


def visualizar(request, pk):
    """Muestra la página de visualización para un conjunto concreto."""
    conjunto = get_object_or_404(Dataset, pk=pk)
    
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id_fichero, tipo_formato, nombre_archivo, contenido
            FROM fichero
            WHERE id_dataset = %s
            ORDER BY id_fichero
            """,
            [pk]
        )
        ficheros = cursor.fetchall()
    
    ficheros_list = []
    for f in ficheros:
        ficheros_list.append({
            'id': f[0],
            'tipo_formato': f[1],
            'nombre_archivo': f[2],
            'contenido': f[3]
        })
    
    fichero_index = int(request.GET.get('fichero', 0))
    if fichero_index < 0:
        fichero_index = 0
    if fichero_index >= len(ficheros_list):
        fichero_index = max(0, len(ficheros_list) - 1)
    
    propiedades_lista = []
    extracto = 'No hay extractos para mostrar'
    fichero_actual = None
    csv_data = None  # Store CSV data here
    
    if ficheros_list and fichero_index < len(ficheros_list):
        fichero_actual = ficheros_list[fichero_index]
        contenido = fichero_actual['contenido']
        tipo_formato = fichero_actual['tipo_formato']
        nombre_archivo = fichero_actual['nombre_archivo'] or ''
        
        # Detect actual format from filename extension (more reliable than tipo_formato)
        actual_format = tipo_formato  # Default to DB value
        nombre_lower = nombre_archivo.lower()
        if nombre_lower.endswith('.csv'):
            actual_format = 'CSV'
        elif nombre_lower.endswith('.json'):
            actual_format = 'JSON'
        elif nombre_lower.endswith('.ttl'):
            actual_format = 'RDF-TURTLE'
        elif nombre_lower.endswith('.xml') or nombre_lower.endswith('.rdf'):
            actual_format = 'RDF-XML'
        
        if contenido:
            if _es_base64(contenido):
                propiedades_lista = ['Archivo binario codificado en base64']
                extracto = "Este archivo está codificado en base64. No se puede mostrar como texto."
            else:
                strategy = _get_extraction_strategy_by_format(actual_format)
                
                if strategy:
                    try:
                        properties = strategy.extract_properties(contenido)
                        propiedades_lista = [prop.name for prop in properties]
                    except Exception as e:
                        print(f"Error extracting properties: {e}")
                        propiedades_lista = [f'Error al extraer propiedades: {str(e)}']
                else:
                    propiedades_lista = [f'Formato no soportado: {actual_format}']
                
                # Logic for CSV Table Visualization
                if actual_format and actual_format.upper() == 'CSV':
                    try:
                        import csv
                        from io import StringIO
                        
                        # Use StringIO to treat string as file
                        f = StringIO(contenido)
                        
                        # Attempt to detect delimiter
                        try:
                            sample = contenido[:1024]
                            sniffer = csv.Sniffer()
                            dialect = sniffer.sniff(sample, delimiters=',;\t|')
                            delimiter = dialect.delimiter
                        except csv.Error:
                            # Fallback manual detection
                            delimiters = [',', ';', '\t', '|']
                            counts = {d: contenido.count(d) for d in delimiters}
                            delimiter = max(counts, key=counts.get) if counts else ','
                            
                        # Read CSV
                        reader = csv.reader(f, delimiter=delimiter)
                        
                        # Extract headers and rows (limit to 20 rows)
                        headers = next(reader, [])
                        rows = []
                        for i, row in enumerate(reader):
                            if i >= 20:
                                break
                            rows.append(row)
                            
                        csv_data = {
                            'headers': headers,
                            'rows': rows,
                            'delimiter': delimiter
                        }

                    except Exception as e:
                        pass  # Silently fail, csv_data will remain None
                        csv_data = None  # Ensure csv_data is None on error
                else:
                    # Not a CSV file - ensure csv_data remains None
                    csv_data = None
                
                # Format JSON for better readability
                if actual_format and actual_format.upper() == 'JSON':
                    try:
                        # Try to parse and pretty-print the JSON
                        json_obj = json.loads(contenido)
                        extracto = json.dumps(json_obj, indent=2, ensure_ascii=False)
                        # Limit to first 2000 chars after formatting
                        if len(extracto) > 2000:
                            extracto = extracto[:2000] + '\n... (contenido truncado)'
                    except (json.JSONDecodeError, Exception):
                        extracto = contenido[:2000] + ('...' if len(contenido) > 2000 else '')
                else:
                    extracto = contenido[:2000] + ('...' if len(contenido) > 2000 else '')
    
    prev_index = fichero_index - 1 if fichero_index > 0 else None
    next_index = fichero_index + 1 if fichero_index < len(ficheros_list) - 1 else None
    current_num = fichero_index + 1
    
    context = {
        'conjunto': conjunto,
        'ficheros': ficheros_list,
        'fichero_actual': fichero_actual,
        'fichero_index': fichero_index,
        'prev_index': prev_index,
        'next_index': next_index,
        'current_num': current_num,
        'total_ficheros': len(ficheros_list),
        'propiedades_lista': propiedades_lista,
        'extracto': extracto,
    }
    
    # Add CSV context if available
    if csv_data:
        context['csv_context'] = csv_data
    
    return render(request, 'visualizar.html', context)


def _get_extraction_strategy_by_format(tipo_formato: str):
    """Get appropriate extraction strategy based on format type."""
    if tipo_formato == 'CSV':
        return CSVExtractionStrategy()
    elif tipo_formato == 'JSON':
        return JSONExtractionStrategy()
    elif tipo_formato == 'RDF-XML':
        return RDFXMLExtractionStrategy()
    elif tipo_formato == 'RDF-TURTLE':
        return RDFTurtleExtractionStrategy()
    return None


def _es_base64(s):
    """Verifica si una cadena es base64 válido."""
    try:
        if isinstance(s, str) and len(s) > 0:
            # Intentar decodificar
            base64.b64decode(s, validate=True)
            # Verificar que no sea texto normal (base64 tiene caracteres específicos)
            import string
            base64_chars = string.ascii_letters + string.digits + '+/='
            if all(c in base64_chars or c.isspace() for c in s[:100]):
                return True
    except:
        pass
    return False


def _procesar_csv(contenido):
    """Procesa un archivo CSV y extrae propiedades y extracto."""
    lineas = contenido.split('\n')
    if not lineas:
        return 'No hay datos CSV', 'Archivo CSV vacío'
    
    # Primera línea como encabezados
    headers = [h.strip().strip('"') for h in lineas[0].split(',')]
    
    # Propiedades: número de columnas, número de filas
    num_filas = len([l for l in lineas if l.strip()])
    propiedades = f"Columnas: {len(headers)}\nFilas: {num_filas - 1}\n\nColumnas:\n"
    propiedades += '\n'.join([f"  - {h}" for h in headers])
    
    # Extracto: primeras 10 líneas
    extracto = '\n'.join(lineas[:10])
    if len(lineas) > 10:
        extracto += f"\n\n... ({len(lineas) - 10} líneas más)"
    
    return propiedades, extracto


def _procesar_json(contenido):
    """Procesa un archivo JSON y extrae propiedades y extracto."""
    try:
        data = json.loads(contenido)
        
        if isinstance(data, dict):
            # Propiedades: claves del objeto
            propiedades = f"Tipo: Objeto JSON\nClaves: {len(data)}\n\nPropiedades:\n"
            propiedades += '\n'.join([f"  - {k}: {type(v).__name__}" for k, v in list(data.items())[:20]])
            if len(data) > 20:
                propiedades += f"\n  ... ({len(data) - 20} propiedades más)"
            
            # Extracto: JSON formateado (primeros 50 caracteres de cada valor)
            extracto = json.dumps(data, indent=2, ensure_ascii=False)
            if len(extracto) > 2000:
                extracto = extracto[:2000] + '\n... (contenido truncado)'
        elif isinstance(data, list):
            propiedades = f"Tipo: Array JSON\nElementos: {len(data)}\n"
            if data and isinstance(data[0], dict):
                propiedades += f"\nPropiedades del primer elemento:\n"
                propiedades += '\n'.join([f"  - {k}: {type(v).__name__}" for k, v in list(data[0].items())[:10]])
            
            extracto = json.dumps(data[:5], indent=2, ensure_ascii=False)
            if len(data) > 5:
                extracto += f"\n... ({len(data) - 5} elementos más)"
        else:
            propiedades = f"Tipo: {type(data).__name__}"
            extracto = str(data)
        
        return propiedades, extracto
    except json.JSONDecodeError:
        return 'Error: JSON inválido', contenido[:1000]


def _procesar_rdf(contenido, tipo_formato):
    """Procesa un archivo RDF y extrae propiedades y extracto."""
    import re
    
    if tipo_formato == 'RDF-TURTLE':
        lineas = contenido.split('\n')
        propiedades_list = [f"Tipo: {tipo_formato}", f"Líneas totales: {len(lineas)}"]
        
        # Extraer prefijos
        prefixes = {}
        prefix_pattern = r'@prefix\s+(\w+):\s+<([^>]+)>'
        for match in re.finditer(prefix_pattern, contenido):
            prefixes[match.group(1)] = match.group(2)
        
        if prefixes:
            propiedades_list.append(f"\nPrefijos ({len(prefixes)}):")
            for prefix, uri in list(prefixes.items())[:10]:
                propiedades_list.append(f"  {prefix}: <{uri}>")
            if len(prefixes) > 10:
                propiedades_list.append(f"  ... ({len(prefixes) - 10} prefijos más)")
        
        # Extraer recursos (sujetos) - mejorado
        # En Turtle, los sujetos aparecen al inicio de las líneas o después de punto
        sujetos = set()
        # Patrón para sujetos al inicio de línea o después de punto
        sujeto_pattern = r'(?:^|\.\s*)(<[^>]+>|[\w]+:[\w-]+|_:[\w]+)'
        for match in re.finditer(sujeto_pattern, contenido, re.MULTILINE):
            sujeto = match.group(1)
            if not sujeto.startswith('@') and 'base64' not in sujeto.lower():
                sujetos.add(sujeto)
        
        if sujetos:
            propiedades_list.append(f"\nRecursos únicos encontrados: {len(sujetos)}")
            for sujeto in list(sujetos)[:10]:
                propiedades_list.append(f"  - {sujeto}")
            if len(sujetos) > 10:
                propiedades_list.append(f"  ... ({len(sujetos) - 10} recursos más)")
        
        # Extraer propiedades comunes (predicados)
        propiedades_comunes = {
            'dct:title': [],
            'dct:description': [],
            'dct:identifier': [],
            'dct:type': [],
            'dct:language': [],
            'dcat:theme': [],
            'dct:issued': [],
            'dct:modified': [],
            'dct:publisher': [],
            'dct:format': [],
            'dct:license': [],
            'dcat:downloadURL': [],
            'dcat:accessURL': [],
        }
        
        for prop in propiedades_comunes.keys():
            # Buscar triples con este predicado en Turtle
            # Formato: predicado "valor" o predicado 'valor'
            patterns = [
                rf'{re.escape(prop)}\s+["\']([^"\']+)["\']',  # Literales con comillas
                rf'{re.escape(prop)}\s+<([^>]+)>',  # URIs
                rf'{re.escape(prop)}\s+([\w]+:[\w-]+)',  # Prefijos
            ]
            matches = []
            for pattern in patterns:
                matches.extend(re.findall(pattern, contenido))
            if matches:
                propiedades_comunes[prop] = matches[:3]  # Primeros 3 valores
        
        propiedades_encontradas = {k: v for k, v in propiedades_comunes.items() if v}
        if propiedades_encontradas:
            propiedades_list.append(f"\nPropiedades principales encontradas ({len(propiedades_encontradas)}):")
            for prop, valores in list(propiedades_encontradas.items())[:15]:
                valores_str = ', '.join(valores) if len(valores) == 1 else f"{valores[0]} (+{len(valores)-1} más)"
                propiedades_list.append(f"  {prop}: {valores_str}")
        
        # Contar triples aproximados (líneas con predicado)
        triples_count = len(re.findall(r'\s+\w+:\w+\s+', contenido))
        if triples_count > 0:
            propiedades_list.append(f"\nTriples aproximados: {triples_count}")
        
        propiedades = '\n'.join(propiedades_list)
        extracto = contenido[:2000]
        if len(contenido) > 2000:
            extracto += '\n... (contenido truncado)'
    
    elif tipo_formato == 'RDF-XML':
        propiedades_list = [f"Tipo: {tipo_formato}"]
        
        # Extraer namespaces
        namespaces = {}
        ns_pattern = r'xmlns(?::(\w+))?="([^"]+)"'
        for match in re.finditer(ns_pattern, contenido):
            prefix = match.group(1) or 'default'
            uri = match.group(2)
            namespaces[prefix] = uri
        
        if namespaces:
            propiedades_list.append(f"\nNamespaces ({len(namespaces)}):")
            for prefix, uri in list(namespaces.items())[:10]:
                propiedades_list.append(f"  {prefix}: {uri}")
            if len(namespaces) > 10:
                propiedades_list.append(f"  ... ({len(namespaces) - 10} namespaces más)")
        
        # Extraer elementos principales
        # Buscar elementos RDF:Description o elementos con rdf:about
        descriptions = re.findall(r'<rdf:Description[^>]*rdf:about=["\']([^"\']+)["\'][^>]*>', contenido)
        if descriptions:
            propiedades_list.append(f"\nRecursos descritos: {len(descriptions)}")
            for desc in descriptions[:5]:
                propiedades_list.append(f"  - {desc}")
            if len(descriptions) > 5:
                propiedades_list.append(f"  ... ({len(descriptions) - 5} recursos más)")
        
        # Extraer propiedades comunes de elementos
        propiedades_comunes = {
            'dct:title': [],
            'dct:description': [],
            'dct:identifier': [],
            'dct:type': [],
            'dct:language': [],
            'dcat:theme': [],
            'dct:issued': [],
            'dct:modified': [],
            'dct:publisher': [],
            'dct:format': [],
            'dct:license': [],
            'dcat:downloadURL': [],
            'dcat:accessURL': [],
        }
        
        for prop in propiedades_comunes.keys():
            # Buscar elementos con este nombre en XML
            # Puede ser con namespace o sin él
            patterns = [
                rf'<{re.escape(prop)}[^>]*>([^<]+)</{re.escape(prop)}>',  # Con namespace completo
                rf'<{prop.split(":")[-1]}[^>]*>([^<]+)</{prop.split(":")[-1]}>',  # Sin namespace
                rf'<[^>]*{re.escape(prop)}[^>]*>([^<]+)</[^>]*>',  # Variación
            ]
            matches = []
            for pattern in patterns:
                matches.extend(re.findall(pattern, contenido))
            if matches:
                propiedades_comunes[prop] = [m.strip() for m in matches[:3] if m.strip()]
        
        propiedades_encontradas = {k: v for k, v in propiedades_comunes.items() if v}
        if propiedades_encontradas:
            propiedades_list.append(f"\nPropiedades principales encontradas ({len(propiedades_encontradas)}):")
            for prop, valores in list(propiedades_encontradas.items())[:15]:
                valores_str = ', '.join(valores) if len(valores) == 1 else f"{valores[0]} (+{len(valores)-1} más)"
                propiedades_list.append(f"  {prop}: {valores_str}")
        
        # Contar elementos XML
        elementos = re.findall(r'<[^/>]+>', contenido)
        propiedades_list.append(f"\nElementos XML totales: {len(elementos)}")
        
        # Buscar tipos de recursos (rdf:type)
        tipos = re.findall(r'rdf:type\s+rdf:resource=["\']([^"\']+)["\']', contenido)
        if tipos:
            tipos_unicos = list(set(tipos))
            propiedades_list.append(f"\nTipos de recursos encontrados ({len(tipos_unicos)}):")
            for tipo in tipos_unicos[:10]:
                propiedades_list.append(f"  - {tipo}")
            if len(tipos_unicos) > 10:
                propiedades_list.append(f"  ... ({len(tipos_unicos) - 10} tipos más)")
        
        propiedades = '\n'.join(propiedades_list)
        extracto = contenido[:2000]
        if len(contenido) > 2000:
            extracto += '\n... (contenido truncado)'
    
    else:
        propiedades = f"Tipo: {tipo_formato}"
        extracto = contenido[:2000] if len(contenido) > 2000 else contenido
    
    return propiedades, extracto


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
                palabras_clave = nz(request.POST.get('palabras_clave'))
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
                        tema = %s, palabras_clave = %s, extension_temporal = %s, extension_espacial = %s, url_descarga = %s,
                        issued = %s, modificado = %s, publisher_name = %s, url_acceso = %s,
                        formato = %s, licencia = %s, derechos = %s, descripcion_distribucion = %s,
                        url_metadatos = %s, contenido_metadatos = %s
                    WHERE id_dataset = %s
                    """,
                    [
                        identificador, titulo, descripcion, dcat_type, idioma,
                        tema, palabras_clave, extension_temporal, extension_espacial, url_descarga,
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
            SELECT identificador, titulo, descripcion, dcat_type, idioma, tema, palabras_clave,
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
                'palabras_clave': row[6] or '',
                'extension_temporal': row[7] or '',
                'extension_espacial': row[8] or '',
                'url_descarga': row[9] or '',
                'issued': row[10].strftime('%Y-%m-%d') if row[10] else '',
                'modificado': row[11].strftime('%Y-%m-%d') if row[11] else '',
                'publisher_name': row[12] or '',
                'url_acceso': row[13] or '',
                'formato': row[14] or '',
                'licencia': row[15] or '',
                'derechos': row[16] or '',
                'descripcion_distribucion': row[17] or '',
                'url_metadatos': row[18] or '',
                'contenido_metadatos': row[19] or '',
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
        'palabras_clave': request.POST.get('palabras_clave', '').strip(),
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
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n\n"
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
    if fields['palabras_clave']:
        keywords = [k.strip() for k in fields['palabras_clave'].split(',') if k.strip()]
        if keywords:
            kw_lines = []
            for i, kw in enumerate(keywords):
                prefix = 'dcat:keyword ' if i == 0 else '             '
                suffix = ' ,' if i < len(keywords) - 1 else ''
                kw_lines.append(f'{prefix}"{_escape_literal(kw)}"@es{suffix}')
            statements.append(kw_lines)
    temp_ext = fields['extension_temporal']
    if temp_ext and ' / ' in temp_ext:
        parts = temp_ext.split(' / ')
        if len(parts) == 2:
            start, end = parts
            statements.append([
                'dct:temporal [',
                '        a dct:PeriodOfTime ;',
                f'        dcat:startDate "{start}"^^xsd:date ;',
                f'        dcat:endDate   "{end}"^^xsd:date',
                '    ]'
            ])
    else:
        add_literal('dct:temporal', temp_ext)
    if fields['extension_espacial']:
        statements.append([
            'dct:spatial [',
            '        a dct:Location ;',
            f'        skos:prefLabel "{_escape_literal(fields["extension_espacial"])}"@es',
            '    ]'
        ])
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


def extract_properties_api(request):
    """API endpoint to extract properties with type detection from uploaded files."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        files = data.get('files', [])
        
        if not files:
            return JsonResponse({'error': 'No files provided'}, status=400)
        
        all_properties = {}
        
        for file_info in files:
            content = file_info.get('content', '')
            file_type = file_info.get('type', '').lower()
            file_name = file_info.get('name', '').lower()
            
            try:
                content_text = _decode_file_content(content)
            except Exception as e:
                continue
            
            strategy = _get_extraction_strategy(file_type, file_name)
            
            if strategy:
                properties = strategy.extract_properties(content_text)
                
                for prop in properties:
                    prop_dict = prop.to_dict()
                    if prop_dict['name'] not in all_properties:
                        all_properties[prop_dict['name']] = prop_dict
        
        grouped = {
            'text': [],
            'numeric': [],
            'date': [],
            'coordinates': [],
            'boolean': []
        }
        
        for prop_name, prop_data in all_properties.items():
            prop_type = prop_data['type']
            if prop_type in grouped:
                grouped[prop_type].append(prop_name)
        
        auto_assignments = {
            'titulo': grouped['text'][:3],
            'descripcion': grouped['text'][:3],
            'tema': grouped['text'][:3],
            'palabras_clave': grouped['text'][:5],
            'extension_temporal': grouped['date'],
            'extension_espacial': grouped['coordinates']
        }
        
        return JsonResponse({
            'properties': list(all_properties.values()),
            'grouped': grouped,
            'auto_assignments': auto_assignments
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _decode_file_content(data_url: str) -> str:
    if not data_url:
        return ''
    
    base64_index = data_url.find('base64,')
    if base64_index == -1:
        return ''
    
    base64_str = data_url[base64_index + 7:]
    try:
        binary = base64.b64decode(base64_str)
        return binary.decode('utf-8', errors='ignore')
    except Exception:
        return ''


def _get_extraction_strategy(file_type: str, file_name: str):
    if 'turtle' in file_type or file_name.endswith('.ttl') or file_name.endswith('.turtle'):
        return RDFTurtleExtractionStrategy()
    
    elif 'json' in file_type or file_name.endswith('.json'):
        return JSONExtractionStrategy()
    
    elif 'xml' in file_type or 'rdf' in file_type or file_name.endswith('.xml') or file_name.endswith('.rdf'):
        return RDFXMLExtractionStrategy()
    
    elif 'csv' in file_type or file_name.endswith('.csv'):
        return CSVExtractionStrategy()
    
    return JSONExtractionStrategy()


def generate_title_with_ai(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        files = data.get('files', [])
        custom_prompt = data.get('custom_prompt', None)
        ai_model = data.get('ai_model', 'gemini-2.5-flash-lite')
        
        # Validar modelo permitido
        ALLOWED_AI_MODELS = ['gemini-2.5-flash-lite', 'gemini-2.5-flash']
        if ai_model not in ALLOWED_AI_MODELS:
            return JsonResponse({'error': f'Modelo no permitido: {ai_model}'}, status=400)
        
        if not files:
            return JsonResponse({'error': 'No se proporcionaron archivos'}, status=400)
        
        file_content = _decode_file_content(files[0].get('content', ''))
        if not file_content:
            return JsonResponse({'error': 'No se pudo decodificar el contenido del archivo'}, status=400)
        
        # Limitar contenido a primeros 1500 caracteres (reducido para evitar exceder límites de API)
        file_content_truncated = file_content[:1500]
        
        # Si hay un prompt personalizado, usarlo y reemplazar {file_content}
        if custom_prompt and custom_prompt.strip():
            prompt = custom_prompt.replace('{file_content}', file_content_truncated)
        else:
            # Prompt por defecto
            prompt = f'''Analiza el siguiente contenido de datos y genera un título descriptivo y conciso (máximo 20 palabras) que resuma de qué trata este conjunto de datos.

Responde SOLO con el título, sin explicaciones adicionales, sin comillas, sin puntos finales.

Contenido del archivo:
{file_content_truncated}'''
        
        api_key = os.getenv('API_KEY')
        if not api_key:
            return JsonResponse({'error': 'API_KEY no configurada en variables de entorno'}, status=500)
        
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=ai_model,
                contents=prompt
            )
            
            generated_title = response.text.strip()
            generated_title = generated_title.strip('"\'')
            
            return JsonResponse({
                'title': generated_title,
                'success': True
            })
        except Exception as ge:
            return JsonResponse({'error': f'Error al llamar a Gemini: {str(ge)}'}, status=500)
        
    except json.JSONDecodeError as je:
        return JsonResponse({'error': f'Error al parsear datos JSON: {str(je)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error inesperado: {str(e)}'}, status=500)


def generate_metadata_with_ai(request):
    """API endpoint to generate any metadata field using AI."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        files = data.get('files', [])
        field_id = data.get('field_id', '')
        custom_prompt = data.get('custom_prompt', None)
        ai_model = data.get('ai_model', 'gemini-2.5-flash-lite')
        
        # Validar modelo permitido
        ALLOWED_AI_MODELS = ['gemini-2.5-flash-lite', 'gemini-2.5-flash']
        if ai_model not in ALLOWED_AI_MODELS:
            return JsonResponse({'error': f'Modelo no permitido: {ai_model}'}, status=400)
        
        if not files:
            return JsonResponse({'error': 'No se proporcionaron archivos'}, status=400)
        
        if not field_id:
            return JsonResponse({'error': 'No se proporcionÃ³ field_id'}, status=400)
        
        file_content = _decode_file_content(files[0].get('content', ''))
        if not file_content:
            return JsonResponse({'error': 'No se pudo decodificar el contenido del archivo'}, status=400)
        
        # Limitar contenido a primeros 1500 caracteres
        file_content_truncated = file_content[:1500]
        
        # Prompts por defecto para cada campo
        DEFAULT_PROMPTS = {
            'titulo': '''Analiza el siguiente contenido de datos y genera un tÃ­tulo descriptivo y conciso (mÃ¡ximo 20 palabras) que resuma de quÃ© trata este conjunto de datos.

Responde SOLO con el tÃ­tulo, sin explicaciones adicionales, sin comillas, sin puntos finales.

Contenido del archivo:
{file_content}''',
            
            'descripcion': '''Analiza el siguiente contenido de datos y genera una descripciÃ³n detallada (60 palabras) que explique de quÃ© trata este conjunto de datos.

Responde SOLO con la descripciÃ³n, sin comillas ni puntos finales.

Contenido del archivo:
{file_content}''',
            
            'tema': '''Analiza el siguiente contenido de datos y selecciona EXACTAMENTE UNO de estos temas que mejor lo describa. Tambien te dejo las definiciones de los temas para ayudarte.

1. Agricultura, pesca, silvicultura y alimentaciÃ³n: tema de un conjunto de datos que abarca los ámbitos de la agricultura, relacionada con el cultivo de plantas y el ganado; la pesca, que se centra en la recolección de peces salvajes o de piscifactoría; la silvicultura, que comprende la gestión y conservación de los bosques y de las superficies forestales arboladas; y los alimentos, que incluyen las sustancias que proporcionan apoyo nutricional a los organismos
2. EconomÃ­a y finanzas: tema de un conjunto de datos que abarca los ámbitos de la actividad económica, que comprende la producción, la distribución, el comercio y el consumo de bienes y servicios, y la actividad financiera, centrada en la gestión del dinero a nivel particular, empresarial o gubernamental.
3. EducaciÃ³n, cultura y deportes: tema de un conjunto de datos que abarca los ámbitos de la educación, que facilita el aprendizaje y la adquisición de conocimientos, capacidades, valores, creencias y hábitos; la cultura, que incluye el comportamiento social, las normas, el conocimiento, las creencias, las artes, las leyes, las costumbres, las capacidades y los hábitos de las sociedades humanas; y el deporte, que comprende las actividades físicas o los juegos de competición que mejoran la aptitud física y las capacidades, y con las que los participantes disfrutan y los espectadores se entretienen.
4. EnergÃ­a: tema de un conjunto de datos que abarca el ámbito de la energía, definida como la propiedad cuantitativa necesaria para efectuar trabajos sobre objetos o para aumentar la temperatura de estos, y como un elemento vital para los organismos vivos y para el funcionamiento de la civilización humana.
5. Medio ambiente: tema de un conjunto de datos que abarca el ámbito del medio ambiente, definido como la interacción entre el conjunto de las especies vivas, el clima, las condiciones meteorológicas y los recursos naturales que inciden sobre la supervivencia humana y la actividad económica.
6. Gobierno y sector pÃºblico: tema de un conjunto de datos que abarca los ámbitos de la Administración pública, que es el sistema o grupo de personas que rigen una comunidad organizada —normalmente un Estado—, y el sector público, definido como el segmento de la economía en el que participan los servicios y empresas públicos, que pueden ser gestionados por las autoridades centrales, regionales o locales.
7. Salud: tema de un conjunto de datos que abarca el ámbito de la salud, que comprende las enfermedades, los tratamientos, los servicios de atención sanitaria y las políticas sanitarias.
8. Asuntos internacionales: tema de un conjunto de datos que abarca el ámbito de las cuestiones internacionales, que tiene que ver con temas o problemas significativos, objeto de debate o diálogo, que afectan a participantes de al menos dos países distintos.
9. Justicia, sistema judicial y seguridad pÃºblica: tema de un conjunto de datos que abarca los ámbitos de la justicia, que se entiende como la equidad procesal en la aplicación del Derecho; el sistema jurídico, que comprende diversos marcos, entre ellos el Derecho civil, consuetudinario, positivo o religioso; y la seguridad pública, que denota la responsabilidad gubernamental de proteger a las personas, las organizaciones y las instituciones contra las amenazas que afectan a su bienestar y a la prosperidad de la comunidad.
10. Regiones y ciudades: tema de un conjunto de datos que abarca los ámbitos de las regiones, definidas como unidades geográficas políticas —por ejemplo, los Estados soberanos, las zonas administrativas subnacionales y las agrupaciones multinacionales—, y las ciudades, que se caracterizan como grandes asentamientos humanos.
11. PoblaciÃ³n y sociedad: tema de un conjunto de datos que abarca los ámbitos de la población, que se refiere al número total de personas que residen en los distintos niveles geográficos —desde las ciudades hasta la escala mundial—, y la sociedad, que denota un colectivo de personas que participan en una interacción social continua dentro de un territorio común, a menudo con arreglo a las mismas normas políticas y culturales.
12. Ciencia y tecnologÃ­a: tema de un conjunto de datos que abarca los ámbitos de la ciencia, que es la búsqueda sistemática del conocimiento a través de explicaciones y predicciones verificables en las disciplinas naturales, sociales y formales, y la tecnología, que comprende las técnicas, capacidades, métodos y procesos colectivos utilizados para producir bienes, prestar servicios o alcanzar objetivos, como la investigación científica.
13. Transportes: tema de un conjunto de datos que abarca el ámbito del transporte, que comprende el desplazamiento de personas, animales y mercancías de un lugar a otro mediante diversos modos de transporte; por ejemplo, el transporte aéreo, terrestre (por ferrocarril y por carretera), por vías navegables, por cable, por tubería o espacial.

Responde SOLO con el nombre del tema seleccionado (ej: "Medio ambiente"), sin explicaciones adicionales.

Contenido del archivo:
{file_content}''',
            
            'palabras_clave': '''Analiza el siguiente contenido de datos y genera entre 3 y 5 palabras clave relevantes que describan el contenido.

Responde SOLO con las palabras clave separadas por comas, sin numeraciÃ³n ni explicaciones.

Contenido del archivo:
{file_content}''',
            
            'extension_temporal': '''Analiza el siguiente contenido de datos e identifica el perÃ­odo temporal cubierto por la informaciÃ³n.

El unico formato valido es el siguiente: "dd-mm-aaaa / dd-mm-aaaa"
Siendo dd el dia, mm el mes y aaaa el año.

Responde SOLO con el perÃ­odo temporal, sin explicaciones adicionales.

Contenido del archivo:
{file_content}''',
            
            'extension_espacial': '''Analiza el siguiente contenido de datos e identifica la zona geogrÃ¡fica cubierta por la informaciÃ³n.

Formatos vÃ¡lidos: "EspaÃ±a", "Europa", "Madrid", "Global", "AmÃ©rica Latina", etc.

Responde SOLO con la ubicaciÃ³n geogrÃ¡fica, sin explicaciones adicionales.

Contenido del archivo:
{file_content}'''
        }
        
        # Si hay un prompt personalizado, usarlo; sino usar el por defecto
        if custom_prompt and custom_prompt.strip():
            prompt = custom_prompt.replace('{file_content}', file_content_truncated)
        else:
            default_prompt = DEFAULT_PROMPTS.get(field_id, DEFAULT_PROMPTS['titulo'])
            prompt = default_prompt.replace('{file_content}', file_content_truncated)
        
        api_key = os.getenv('API_KEY')
        if not api_key:
            return JsonResponse({'error': 'API_KEY no configurada en variables de entorno'}, status=500)
        
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=ai_model,
                contents=prompt
            )
            
            generated_value = response.text.strip()
            generated_value = generated_value.strip('"\'')
            
            return JsonResponse({
                'value': generated_value,
                'field_id': field_id,
                'success': True
            })
        except Exception as ge:
            return JsonResponse({'error': f'Error al llamar a Gemini: {str(ge)}'}, status=500)
        
    except json.JSONDecodeError as je:
        return JsonResponse({'error': f'Error al parsear datos JSON: {str(je)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error inesperado: {str(e)}'}, status=500)



def ckan_proxies(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Authenticate user
    user_id = request.session.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
        action = data.get('action')
        ckan = CkanClient(user_id=user_id)
        
        if action == 'get_organizations':
            response = ckan.get_user_organizations()
            return JsonResponse(response)
            
        elif action == 'create_organization':
            name = data.get('name')
            description = data.get('description')
            if not name:
                return JsonResponse({'error': 'Name is required'}, status=400)
            response = ckan.create_organization(name, description)
            return JsonResponse(response)

        elif action == 'delete_organization':
            org_id = data.get('id')
            if not org_id:
                return JsonResponse({'error': 'Org ID is required'}, status=400)
            response = ckan.delete_organization(org_id)
            return JsonResponse(response)
            
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def publish_to_ckan(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Authenticate user
    user_id = request.session.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'Authentication required'}, status=401)
        
    try:
        
        ckan = CkanClient(user_id=user_id)
        
        local_id = request.POST.get('id_dataset')
        ckan_id = request.POST.get('identificador')

        is_local_update = bool(local_id)
        is_ckan_update = bool(ckan_id)
        
        files_list = []
        files_json = request.POST.get('dataset_files_data')
        if files_json:
            try:
                files_list = json.loads(files_json)
            except:
                pass

        title = request.POST.get('titulo')
        
        if not title and files_list:
            first_file_name = files_list[0].get('name', '')
            if first_file_name:
                title = first_file_name.rsplit('.', 1)[0]
        
        desc_parts = [
            request.POST.get('descripcion', ''),
            request.POST.get('tema', ''),
            request.POST.get('extension_temporal', ''),
            request.POST.get('extension_espacial', '')
        ]
        description = ' . '.join([p for p in desc_parts if p])
        
        tags_input = request.POST.get('palabras_clave', '')
        tags = [{'name': t.strip()} for t in tags_input.split(',') if t.strip()]
        
        license_id = request.POST.get('licencia', 'cc-by')
        
        organization_id = request.POST.get('organization_id')
        
        if not organization_id and not is_ckan_update:
             return JsonResponse({'error': 'Organization ID is required for new datasets'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("SELECT nombre, correo FROM usuario WHERE id_usuario = %s", [user_id])
            user_row = cursor.fetchone()
            author_name = user_row[0] if user_row else ''
            author_email = user_row[1] if user_row else ''
            
        metadata = {
            'title': title or 'Nuevo Dataset',
            'notes': description,
            'tags': tags,
            'license_id': license_id,
            'author': author_name,
            'author_email': author_email,
            'maintainer': author_name,
            'maintainer_email': author_email,
            'private': True 
        }
        
        if is_ckan_update:
            ckan_resp = ckan.update_dataset(ckan_id, metadata, organization_id)
        else:
            slug = slugify(title) if title else 'dataset'
            if not slug: 
                slug = 'dataset'
            metadata['name'] = f"{slug}-{str(uuid.uuid4())[:8]}"
            
            ckan_resp = ckan.create_dataset(metadata, organization_id)
            
        ckan_dataset_id = ckan_resp['result']['id']
        
        for file_info in files_list:
            content_original = file_info.get('content', '')
            if not content_original: continue
            
            if 'base64,' in content_original:
                _, b64_data = content_original.split('base64,')
            else:
                b64_data = content_original
            
            try:
                file_bytes = base64.b64decode(b64_data)
                file_obj = io.BytesIO(file_bytes)
                filename = file_info.get('name', 'resource')
                file_fmt = file_info.get('type', '')
                
                ckan.resource_create(ckan_dataset_id, file_obj, filename, file_fmt)
            except Exception:
                continue
        
        with connection.cursor() as cursor:
            def nz(val): return (val or '').strip() or None
            
            identificador = ckan_dataset_id
            name = request.POST.get('name') or title
            
            db_values = [
                user_id, name, identificador, title, nz(request.POST.get('descripcion')), 
                nz(request.POST.get('dcat_type')), nz(request.POST.get('idioma')), nz(request.POST.get('tema')),
                nz(request.POST.get('palabras_clave')), nz(request.POST.get('extension_temporal')), 
                nz(request.POST.get('extension_espacial')), nz(request.POST.get('url_descarga')),
                nz(request.POST.get('issued')), nz(request.POST.get('modificado')),
                nz(request.POST.get('publisher_name')), nz(request.POST.get('url_acceso')),
                nz(request.POST.get('formato')), nz(request.POST.get('licencia')),
                nz(request.POST.get('derechos')), nz(request.POST.get('descripcion_distribucion')),
                nz(request.POST.get('url_metadatos')), nz(request.POST.get('metadata_content'))
            ]
            
            if is_local_update:
                cursor.execute(
                    """
                    UPDATE dataset SET
                        nombre=%s, identificador=%s, titulo=%s, descripcion=%s, dcat_type=%s, idioma=%s, 
                        tema=%s, palabras_clave=%s, extension_temporal=%s, extension_espacial=%s, url_descarga=%s, 
                        issued=%s, modificado=%s, publisher_name=%s, url_acceso=%s, 
                        formato=%s, licencia=%s, derechos=%s, descripcion_distribucion=%s, 
                        url_metadatos=%s, contenido_metadatos=%s
                    WHERE id_dataset = %s
                    """,
                    db_values[1:] + [local_id]
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO dataset (
                        id_usuario, nombre, identificador, titulo, descripcion, dcat_type, idioma, tema,
                        palabras_clave, extension_temporal, extension_espacial, url_descarga, issued, modificado,
                        publisher_name, url_acceso, formato, licencia, derechos, descripcion_distribucion, url_metadatos, contenido_metadatos,
                        fecha_creacion
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id_dataset
                    """,
                    db_values
                )
                row = cursor.fetchone()
                local_id = row[0] if row else None
                
        if local_id and files_list:
            for file_info in files_list:
                content_original = file_info.get('content', '')
                if not content_original:
                    continue
                
                if 'base64,' in content_original:
                        _, content_base64 = content_original.split('base64,')
                else:
                        content_base64 = content_original
                
                try:
                    file_bytes = base64.b64decode(content_base64)
                    if b'\x00' in file_bytes:
                        file_content = content_base64
                    else:
                        try:
                            file_content = file_bytes.decode('utf-8')
                        except UnicodeDecodeError:
                            file_content = file_bytes.decode('latin-1')
                except Exception:
                    continue

                file_name = file_info.get('name', '').lower()
                file_type = file_info.get('type', '').lower()
                formato_seleccionado = request.POST.get('formato', '')
                
                tipo_formato = None
                if formato_seleccionado:
                    tipo_formato = formato_seleccionado.upper()
                elif file_name.endswith('.csv') or 'csv' in file_type:
                    tipo_formato = 'CSV'
                elif file_name.endswith('.json') or 'json' in file_type:
                    tipo_formato = 'JSON'
                elif file_name.endswith('.ttl') or 'turtle' in file_type:
                    tipo_formato = 'RDF-TURTLE'
                elif file_name.endswith('.xml') or file_name.endswith('.rdf') or 'xml' in file_type or 'rdf' in file_type:
                    tipo_formato = 'RDF-XML'
                
                if not tipo_formato:
                    tipo_formato = formato_seleccionado.upper() if formato_seleccionado else 'CSV'
                
                if tipo_formato not in ['CSV', 'RDF-XML', 'RDF-TURTLE', 'JSON']:
                    tipo_formato = 'CSV'

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO fichero (
                            id_dataset, tipo_formato, url_datos, contenido, nombre_archivo
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        [
                            local_id,
                            tipo_formato,
                            None,
                            file_content,
                            file_info.get('name', '')
                        ]
                    )

        return JsonResponse({'success': True, 'dataset_id': local_id, 'ckan_id': ckan_dataset_id})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
