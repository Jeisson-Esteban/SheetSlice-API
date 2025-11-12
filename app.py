from flask import Flask, request, send_file, jsonify
import pandas as pd
import io
import zipfile
import os

app = Flask(__name__)

# Definimos una constante para el tamaño de lote por defecto
DEFAULT_CHUNK_SIZE = 5000

@app.route('/file-preview', methods=['POST'])
def file_preview():
    """
    Endpoint para previsualizar las cabeceras y las primeras 3 filas de un archivo.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'El archivo enviado está vacío o no tiene nombre.'}), 400

    filename = file.filename.lower()
    file_extension = os.path.splitext(filename)[1]

    if file_extension not in ['.xlsx', '.csv']:
        return jsonify({'error': 'Formato no soportado. Usa .xlsx o .csv'}), 400

    try:
        if file_extension == '.csv':
            df_preview = pd.read_csv(file, nrows=3)
        elif file_extension == '.xlsx':
            df_preview = pd.read_excel(file, nrows=3)

        headers = df_preview.columns.tolist()
        data_preview = df_preview.to_dict(orient='records')

        return jsonify({'headers': headers, 'data_preview': data_preview})
    except Exception as e:
        app.logger.error(f"Error previsualizando el archivo: {e}")
        return jsonify({'error': f'Ocurrió un error al previsualizar el archivo: {str(e)}'}), 500

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
        # --- NUEVA FUNCIONALIDAD: Generar la vista previa ---
        # Para generar la vista previa, necesitamos poder leer el inicio del archivo.
        # Como request.files['file'] es un stream, si lo leemos, el cursor se mueve.
        # Lo leemos en memoria para poder "rebobinarlo" y usarlo varias veces.
        file_stream = io.BytesIO(file.read())
        file.close() # Cerramos el archivo original

        # Generamos el DataFrame de la vista previa (primeras 3 filas)
        if file_extension == '.csv':
            df_preview = pd.read_csv(file_stream, nrows=3)
        elif file_extension == '.xlsx':
            df_preview = pd.read_excel(file_stream, nrows=3)
        
        # Preparamos el JSON de la vista previa
        preview_data = {'headers': df_preview.columns.tolist(), 'data_preview': df_preview.to_dict(orient='records')}
        preview_json_str = pd.io.json.dumps(preview_data, indent=2)

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # --- MEJORA 2: Procesamiento en trozos para CSV grandes ---
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
                # Rebobinamos el stream para leer el archivo completo para la división
                file_stream.seek(0)
                df = pd.read_excel(file_stream)
                for i, start in enumerate(range(0, len(df), chunk_size)):
                    chunk = df.iloc[start:start + chunk_size]
                    chunk_buffer = io.BytesIO()
                    # --- MEJORA: Convertir los lotes de XLSX a CSV para reducir tamaño y mejorar rendimiento ---
                    chunk_filename = f"part_{i+1}.csv"
                    chunk.to_csv(chunk_buffer, index=False, encoding='utf-8') # Usamos to_csv en lugar de to_excel
                    zipf.writestr(chunk_filename, chunk_buffer.getvalue())
            
            # Añadimos el archivo de vista previa al ZIP
            zipf.writestr("_preview.json", preview_json_str)

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

if __name__ == "__main__":
    # Render y otros servicios de PaaS usan la variable de entorno PORT
    port = int(os.environ.get("PORT", 8080))
    # host='0.0.0.0' es crucial para que la app sea accesible desde fuera del contenedor
    app.run(host="0.0.0.0", port=port)