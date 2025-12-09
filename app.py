from flask import Flask, request, send_file, jsonify
import pandas as pd
import io
import zipfile
import os

app = Flask(__name__)

# Constante para el tamaño de lote por defecto si no se especifica.
DEFAULT_CHUNK_SIZE = 5000

@app.route('/split-file', methods=['POST'])
def split_file():
    # 1. Validación del parámetro 'chunk_size' de la URL.
    try:
        chunk_size_str = request.args.get('chunk_size', str(DEFAULT_CHUNK_SIZE))
        chunk_size = int(chunk_size_str)
        if chunk_size <= 0:
            return jsonify({'error': 'El tamaño del lote (chunk_size) debe ser un entero positivo.'}), 400
    except ValueError:
        return jsonify({'error': 'El tamaño del lote (chunk_size) debe ser un número entero válido.'}), 400

    # 2. Validación del archivo de entrada.
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'El archivo enviado está vacío o no tiene nombre.'}), 400

    filename = file.filename.lower()
    file_extension = os.path.splitext(filename)[1]

    if file_extension not in ['.xlsx', '.csv']:
        return jsonify({'error': 'Formato no soportado. Usa .xlsx o .csv'}), 400

    # 3. Creación de un archivo ZIP en memoria para no escribir en disco.
    zip_buffer = io.BytesIO()

    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 4. Creación de un archivo de muestra (sample) para una rápida visualización.
            # Este archivo contiene los encabezados y las primeras 3 filas de datos.
            sample_filename = "sample_data.csv"
            sample_buffer = io.BytesIO()

            if file_extension == '.csv':
                # Para CSV, leemos las primeras líneas directamente del stream.
                file.stream.seek(0)
                lines = []
                for _ in range(4): # Leer encabezado + 3 líneas de datos
                    line = file.stream.readline()
                    if not line:
                        break
                    lines.append(line.decode('utf-8'))
                
                sample_buffer.write("".join(lines).encode('utf-8'))
                # Es crucial resetear el stream para que pandas pueda leer el archivo completo después.
                file.stream.seek(0)

            elif file_extension == '.xlsx':
                # Para XLSX, usamos pandas para leer solo las primeras filas.
                sample_df = pd.read_excel(file.stream, nrows=4)
                sample_df.to_csv(sample_buffer, index=False, encoding='utf-8')
                # Reseteamos el stream para el procesamiento posterior.
                file.stream.seek(0)
            
            # Añadimos el archivo de muestra al ZIP.
            zipf.writestr(sample_filename, sample_buffer.getvalue())

            # 5. Procesamiento y división del archivo principal en lotes.
            if file_extension == '.csv':
                # Para CSV, procesamos el archivo en trozos (chunks) para no agotar la memoria.
                csv_iterator = pd.read_csv(file, chunksize=chunk_size)
                for i, chunk_df in enumerate(csv_iterator):
                    chunk_buffer = io.BytesIO()
                    # Cada trozo se guarda como un archivo CSV individual.
                    chunk_df.to_csv(chunk_buffer, index=False)
                    chunk_filename = f"part_{i+1}.csv"
                    zipf.writestr(chunk_filename, chunk_buffer.getvalue())
            
            elif file_extension == '.xlsx':
                # Para XLSX, pandas no soporta `chunksize` de forma nativa y eficiente.
                # Por tanto, cargamos el archivo completo en memoria y lo dividimos con iloc.
                # NOTA: Esto puede consumir mucha memoria para archivos XLSX muy grandes.
                df = pd.read_excel(file)
                for i, start in enumerate(range(0, len(df), chunk_size)):
                    chunk = df.iloc[start:start + chunk_size]
                    chunk_buffer = io.BytesIO()
                    # Convertimos cada lote a formato CSV para estandarizar la salida,
                    # reducir el tamaño del archivo y mejorar la compatibilidad.
                    chunk_filename = f"part_{i+1}.csv"
                    chunk.to_csv(chunk_buffer, index=False, encoding='utf-8')
                    zipf.writestr(chunk_filename, chunk_buffer.getvalue())

    except Exception as e:
        # Captura errores durante el procesamiento del archivo (ej. archivo corrupto)
        app.logger.error(f"Error procesando el archivo: {e}")
        return jsonify({'error': f'Ocurrió un error al procesar el archivo: {str(e)}'}), 500

    zip_buffer.seek(0)

    # 6. Envío del archivo ZIP como respuesta.
    return send_file(
        zip_buffer,
        mimetype='application/zip',
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

    # 2. Validar la extensión del archivo (solo CSV soportado)
    filename = file.filename.lower()
    file_extension = os.path.splitext(filename)[1]

    if file_extension != '.csv':
        return jsonify({'error': 'Formato no soportado. Usa .csv'}), 400

    try:
        # 3. Leer el contenido completo del archivo.
        # Se usa 'utf-8-sig' para manejar correctamente el BOM (Byte Order Mark)
        # que algunos editores (como Excel) añaden al guardar como CSV.
        file.stream.seek(0)
        csv_content = file.read().decode('utf-8-sig')

        if not csv_content.strip():
            return jsonify({'error': 'El archivo CSV está vacío.'}), 400

        # 4. Extraer la primera línea (encabezados).
        header_line = csv_content.splitlines()[0].strip()
        
        # 5. Formatear los encabezados como un string de literales separados por comas.
        headers = [h.strip() for h in header_line.split(',')]
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
    # 1. Validación del archivo de entrada.
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

        # Función auxiliar para limpiar cada fila del DataFrame.
        # Elimina claves cuyo valor es un string vacío y quita espacios en blanco.
        def clean_row_dict(row_dict):
            return {k: v.strip() for k, v in row_dict.items() if str(v).strip() != ''}

        # Función auxiliar para leer bytes de un CSV y convertirlo a una lista de diccionarios limpios.
        def read_csv_to_clean_json(csv_bytes):
            # `dtype=str` y `keep_default_na=False` evitan que pandas infiera tipos
            # y trate valores como 'NA' o '' como NaN, preservando los datos originales.
            df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)
            df = df.fillna('')
            raw_rows = df.to_dict(orient='records')
            return [clean_row_dict(row) for row in raw_rows]

        # 2. Lógica de procesamiento según la extensión del archivo.
        if file_extension == '.csv':
            # Caso 1: Un solo CSV → devuelve array plano como muestras.json
            data = read_csv_to_clean_json(file_bytes)
            return jsonify(data)

        else:  # .zip
            # Caso 2: Un archivo ZIP → devuelve un objeto donde cada clave es el nombre
            # de un archivo CSV dentro del ZIP, y su valor es el array de objetos JSON.
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

@app.route('/health', methods=['GET'])
def health_check():
    """
    Endpoint de health check para mantener la aplicación activa.
    Puede ser llamado por servicios externos como cron-job.org para
    prevenir que el servicio de hosting ponga la aplicación en modo 'sleep'.
    """
    return jsonify({'status': 'ok', 'message': 'La aplicación está activa.'}), 200

if __name__ == "__main__":
    # El puerto se obtiene de la variable de entorno PORT, común en servicios de PaaS como Render.
    port = int(os.environ.get("PORT", 8080))
    # `host='0.0.0.0'` hace que el servidor sea accesible desde fuera del contenedor/máquina.
    app.run(host="0.0.0.0", port=port)