from flask import Flask, request, send_file, jsonify
import pandas as pd
import io
import zipfile
import os

app = Flask(__name__)

# Definimos una constante para el tamaño de lote por defecto
DEFAULT_CHUNK_SIZE = 5000

@app.route('/split-file', methods=['POST'])
def split_file():
    # --- MEJORA 1: Validación robusta de chunk_size ---
    try:
        chunk_size_str = request.args.get('chunk_size', str(DEFAULT_CHUNK_SIZE))
        chunk_size = int(chunk_size_str)
        if chunk_size <= 0:
            return jsonify({'error': 'El tamaño del lote (chunk_size) debe ser un entero positivo.'}), 400
    except ValueError:
        return jsonify({'error': 'El tamaño del lote (chunk_size) debe ser un número entero válido.'}), 400

    # Verificar que se haya enviado un archivo
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'El archivo enviado está vacío o no tiene nombre.'}), 400

    filename = file.filename.lower()
    file_extension = os.path.splitext(filename)[1]

    if file_extension not in ['.xlsx', '.csv']:
        return jsonify({'error': 'Formato no soportado. Usa .xlsx o .csv'}), 400

    # Crear un buffer en memoria para almacenar el ZIP
    zip_buffer = io.BytesIO()

    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # --- MEJORA 2: Procesamiento en trozos para CSV grandes ---
            
            # --- NUEVA FUNCIONALIDAD: Añadir archivo de muestra con encabezados y primeras 3 líneas ---
            sample_filename = "sample_data.csv"
            sample_buffer = io.BytesIO()

            if file_extension == '.csv':
                # Asegurarse de que el stream esté al principio para leer el sample
                file.stream.seek(0)
                # Leer la primera línea (encabezados) y hasta 3 líneas de datos
                lines = []
                for _ in range(4): # Leer encabezado + 3 líneas de datos
                    line = file.stream.readline()
                    if not line:
                        break
                    lines.append(line.decode('utf-8'))
                
                sample_buffer.write("".join(lines).encode('utf-8'))
                # Resetear el stream para que pandas pueda leerlo desde el principio
                file.stream.seek(0)

            elif file_extension == '.xlsx':
                # Leer las primeras 4 filas (encabezado + 3 líneas de datos)
                sample_df = pd.read_excel(file.stream, nrows=4)
                sample_df.to_csv(sample_buffer, index=False, encoding='utf-8')
                # Resetear el stream para que pandas pueda leer el archivo completo
                file.stream.seek(0)
            
            zipf.writestr(sample_filename, sample_buffer.getvalue())
            # --- FIN NUEVA FUNCIONALIDAD ---

            if file_extension == '.csv':
                # Usamos un iterador para no cargar todo el archivo en memoria
                csv_iterator = pd.read_csv(file, chunksize=chunk_size)
                for i, chunk_df in enumerate(csv_iterator):
                    chunk_buffer = io.BytesIO()
                    # --- MEJORA 3: El formato de salida coincide con el de entrada ---
                    chunk_df.to_csv(chunk_buffer, index=False)
                    chunk_filename = f"part_{i+1}.csv"
                    zipf.writestr(chunk_filename, chunk_buffer.getvalue())
            
            elif file_extension == '.xlsx':
                # Para XLSX, la lectura por trozos es más compleja, mantenemos la carga completa
                # pero el resto del código está preparado para manejarlo.
                df = pd.read_excel(file)
                for i, start in enumerate(range(0, len(df), chunk_size)):
                    chunk = df.iloc[start:start + chunk_size]
                    chunk_buffer = io.BytesIO()
                    # --- MEJORA: Convertir los lotes de XLSX a CSV para reducir tamaño y mejorar rendimiento ---
                    chunk_filename = f"part_{i+1}.csv"
                    chunk.to_csv(chunk_buffer, index=False, encoding='utf-8') # Usamos to_csv en lugar de to_excel
                    zipf.writestr(chunk_filename, chunk_buffer.getvalue())

    except Exception as e:
        # Captura errores durante el procesamiento del archivo (ej. archivo corrupto)
        app.logger.error(f"Error procesando el archivo: {e}")
        return jsonify({'error': f'Ocurrió un error al procesar el archivo: {str(e)}'}), 500

    zip_buffer.seek(0)

    # Enviar el ZIP resultante como respuesta binaria
    return send_file(
        zip_buffer,
        mimetype='application/zip', # Correcto
        as_attachment=True,
        download_name='lotes_divididos.zip'
    )

@app.route('/extract-headers', methods=['POST'])
def extract_headers():
    # 1. Verificar que se haya enviado un archivo
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'El archivo enviado está vacío o no tiene nombre.'}), 400

    # 2. Validar la extensión del archivo
    filename = file.filename.lower()
    file_extension = os.path.splitext(filename)[1]

    if file_extension != '.csv':
        return jsonify({'error': 'Formato no soportado. Usa .csv'}), 400

    try:
        # 3. Leer el contenido completo del archivo una sola vez
        # Usamos 'utf-8-sig' para manejar el BOM (Byte Order Mark)
        file.stream.seek(0)
        csv_content = file.read().decode('utf-8-sig')

        if not csv_content.strip():
            return jsonify({'error': 'El archivo CSV está vacío.'}), 400

        # 4. Extraer la primera línea (encabezados) del contenido
        header_line = csv_content.splitlines()[0].strip()
        
        # 5. Procesar los encabezados para darles el formato solicitado
        headers = [h.strip() for h in header_line.split(',')]
        # Formatear cada encabezado entre comillas simples y unirlos en un solo string
        formatted_headers = ", ".join([f"'{h}'" for h in headers])

        # 6. Crear y enviar la respuesta JSON completa
        response_data = {
            "input_column_literals": formatted_headers,
            "CSV_content_file": csv_content
        }
        return jsonify(response_data)

    except Exception as e:
        app.logger.error(f"Error extrayendo encabezados: {e}")
        return jsonify({'error': f'Ocurrió un error al procesar el archivo: {str(e)}'}), 500

@app.route('/extractjson', methods=['POST'])
def extractjson():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'El archivo enviado está vacío o no tiene nombre.'}), 400

    filename = file.filename.lower()
    file_extension = os.path.splitext(filename)[1]

    if file_extension not in ['.csv', '.zip']:
        return jsonify({'error': 'Formato no soportado. Usa .csv o .zip'}), 400

    try:
        file.stream.seek(0)
        file_bytes = file.stream.read()

        # Función para limpiar cada fila: elimina campos vacíos y limpia espacios
        def clean_row_dict(row_dict):
            return {k: v.strip() for k, v in row_dict.items() if str(v).strip() != ''}

        # Leer CSV y convertir a lista de dicts limpios
        def read_csv_to_clean_json(csv_bytes):
            df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)
            df = df.fillna('')
            raw_rows = df.to_dict(orient='records')
            return [clean_row_dict(row) for row in raw_rows]

        if file_extension == '.csv':
            # Caso 1: Un solo CSV → devuelve array plano como muestras.json
            data = read_csv_to_clean_json(file_bytes)
            return jsonify(data)

        else:  # .zip
            # Caso 2: ZIP → objeto con nombre de archivo como clave
            result = {}
            with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zipf:
                csv_files = [
                    f for f in zipf.namelist()
                    if f.lower().endswith('.csv') and not f.startswith('__MACOSX/')
                ]

                if not csv_files:
                    return jsonify({'error': 'No se encontraron archivos CSV dentro del ZIP.'}), 400

                for csv_name in csv_files:
                    with zipf.open(csv_name) as csv_file:
                        csv_content = csv_file.read()
                        result[csv_name] = read_csv_to_clean_json(csv_content)

            return jsonify(result)

    except Exception as e:
        app.logger.error(f"Error en /extractjson: {e}")
        return jsonify({'error': f'Error procesando el archivo: {str(e)}'}), 500

@app.route('/normalize-and-generate-sql', methods=['POST'])
def normalize_and_generate_sql():
    # --- 1. Validación de Entradas (CSV y Diccionario en form-data) ---
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo CSV (file)'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'El archivo enviado está vacío o no tiene nombre.'}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'El archivo de datos debe ser un .csv'}), 400

    try:
        # Leer el diccionario del campo de formulario
        dictionary_str = request.form.get('dictionary')
        if not dictionary_str:
            return jsonify({'error': 'Falta el campo "dictionary" en el form-data.'}), 400
        dictionary_rows = pd.read_json(dictionary_str, orient='records').to_dict('records')

        # --- 2. Extracción de datos del CSV (Lógica de extractjson) ---
        file.stream.seek(0)
        # Usamos dtype=str y keep_default_na=False para leer todo como texto
        df = pd.read_csv(file.stream, dtype=str, keep_default_na=False)
        raw_data_items = df.to_dict(orient='records')

    except Exception as e:
        return jsonify({'error': f'Error al procesar las entradas: {str(e)}'}), 400

    try:
        # --- 2. Normalización (Lógica del primer JS) ---

        # Construir el mapa de búsqueda (lookup map)
        lookup_map = {}
        for row in dictionary_rows:
            standard_key = row.get('valor_estandarizado')
            origin_keys_str = row.get('nombre_columna_origen')
            if not standard_key or not origin_keys_str:
                continue
            
            for variation in origin_keys_str.split('|'):
                cleaned_variation = variation.strip()
                if cleaned_variation:
                    lookup_map[cleaned_variation] = standard_key

        # Normalizar los datos
        normalized_items = []
        for raw_item in raw_data_items:
            normalized_json = {}
            for raw_key, raw_value in raw_item.items():
                cleaned_input_key = raw_key.strip()
                standard_key = lookup_map.get(cleaned_input_key)
                if standard_key:
                    normalized_json[standard_key] = raw_value
            if normalized_json:
                normalized_items.append(normalized_json)

        # --- 3. Generación de SQL (Lógica del segundo JS) ---

        if not normalized_items:
            return jsonify({'error': "No se generaron datos normalizados para procesar."}), 400

        # Definiciones y constantes para el formateo SQL
        conflict_keys = ['Sales_Order', 'EAN_UPC_Code']
        headers = list(normalized_items[0].keys())

        numeric_zero_columns = {'Stock_Qty', 'Order_Qty', 'RetailPrice'}
        zero_if_empty_columns = {'Rejected_Quantity', 'Confirmed_QTY', 'Ordered_QTY'}
        date_columns = {'Launch_Date', 'Planned_Delivery_Date', 'Rejected_Dt', 'SO_Cr_Date', 'RetailDate'}

        def format_for_sql(value, header):
            trimmed_value = str(value).strip() if value is not None else ""

            if trimmed_value == "":
                if header in zero_if_empty_columns:
                    return '0'
                return 'NULL'

            is_special_null = trimmed_value.upper() in ("NULL", "*UNK*", "#N/A")
            if is_special_null:
                return 'NULL'

            if trimmed_value == "0" and header not in numeric_zero_columns and header not in zero_if_empty_columns:
                return 'NULL'

            if header in date_columns:
                try:
                    # Asume formato DD.MM.YYYY
                    parts = trimmed_value.split('.')
                    if len(parts) == 3 and len(parts[2]) == 4:
                        yyyy_mm_dd = f"{parts[2]}-{parts[1]}-{parts[0]}"
                        return f"'{yyyy_mm_dd}'"
                    return 'NULL' # Formato de fecha no esperado
                except Exception:
                    return 'NULL'

            # Escapar comillas simples y envolver en comillas
            escaped_value = trimmed_value.replace("'", "''")
            return f"'{escaped_value}'"

        # (BLOQUE 1) Crear lista de columnas SQL
        sql_column_list = ", ".join([f'"{h}"' for h in headers])

        # (BLOQUE 2) Crear string de valores (con deduplicación)
        value_rows = []
        seen_keys = set()

        for item in normalized_items:
            # Crear clave compuesta para deduplicación
            composite_key_parts = [str(item.get(k, '')) for k in conflict_keys]
            composite_key = "|".join(composite_key_parts)

            if composite_key in seen_keys:
                continue
            seen_keys.add(composite_key)

            # Mapear valores en el mismo orden que los encabezados
            value_list = [format_for_sql(item.get(h), h) for h in headers]
            value_rows.append(f"({', '.join(value_list)})")
        
        sql_values_string = ',\n'.join(value_rows)

        # (BLOQUE 3) Crear string de actualización para ON CONFLICT
        sql_update_set = ',\n    '.join([
            f'"{h}" = EXCLUDED."{h}"' for h in headers if h not in conflict_keys
        ])

        # --- 4. Devolver el resultado ---
        return jsonify({
            'sql_column_list': sql_column_list,
            'sql_values_string': sql_values_string,
            'sql_update_set': sql_update_set
        })

    except Exception as e:
        app.logger.error(f"Error en /normalize-and-generate-sql: {e}")
        return jsonify({'error': f'Ocurrió un error inesperado: {str(e)}'}), 500

if __name__ == "__main__":
    # Render y otros servicios de PaaS usan la variable de entorno PORT
    port = int(os.environ.get("PORT", 8080))
    # host='0.0.0.0' es crucial para que la app sea accesible desde fuera del contenedor
    app.run(host="0.0.0.0", port=port)