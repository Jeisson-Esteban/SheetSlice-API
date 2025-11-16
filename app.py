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

if __name__ == "__main__":
    # Render y otros servicios de PaaS usan la variable de entorno PORT
    port = int(os.environ.get("PORT", 8080))
    # host='0.0.0.0' es crucial para que la app sea accesible desde fuera del contenedor
    app.run(host="0.0.0.0", port=port)