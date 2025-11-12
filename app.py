from flask import Flask, request, Response
import pandas as pd
import io
import zipfile
import os
import json

app = Flask(__name__)
DEFAULT_CHUNK_SIZE = 5000

@app.route('/split-file', methods=['POST'])
def split_file():
    # Validación chunk_size
    try:
        chunk_size = int(request.args.get('chunk_size', str(DEFAULT_CHUNK_SIZE)))
        if chunk_size <= 0:
            return {"error": "chunk_size debe ser positivo"}, 400
    except ValueError:
        return {"error": "chunk_size inválido"}, 400

    if 'file' not in request.files:
        return {"error": "No file"}, 400

    file = request.files['file']
    if not file or file.filename == '':
        return {"error": "Archivo vacío"}, 400

    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in ['.csv', '.xlsx']:
        return {"error": "Solo .csv o .xlsx"}, 400

    # === 1. GENERAR METADATA (solo 3 filas) ===
    file.seek(0)
    try:
        if ext == '.csv':
            sample_df = pd.read_csv(file, nrows=3)
        else:
            sample_df = pd.read_excel(file, nrows=3)
        file.seek(0)  # reset para procesar después
    except Exception as e:
        return {"error": f"Error leyendo muestra: {e}"}, 500

    metadata = {
        "columns": list(sample_df.columns),
        "dtypes": {col: str(dtype) for col, dtype in sample_df.dtypes.items()},
        "sample_rows": sample_df.head(3).to_dict(orient='records')
    }
    metadata_json_str = json.dumps(metadata, ensure_ascii=False)
    metadata_bytes = metadata_json_str.encode('utf-8')

    # === 2. GENERAR ZIP (con chunks) ===
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Incluimos metadata también dentro del ZIP (opcional, pero útil)
            zipf.writestr('metadata.json', metadata_bytes)

            if ext == '.csv':
                for i, chunk in enumerate(pd.read_csv(file, chunksize=chunk_size)):
                    buf = io.BytesIO()
                    chunk.to_csv(buf, index=False)
                    zipf.writestr(f"part_{i+1:04d}.csv", buf.getvalue())
            else:
                df = pd.read_excel(file)
                for i, start in enumerate(range(0, len(df), chunk_size)):
                    chunk = df.iloc[start:start + chunk_size]
                    buf = io.BytesIO()
                    chunk.to_csv(buf, index=False, encoding='utf-8')
                    zipf.writestr(f"part_{i+1:04d}.csv", buf.getvalue())
    except Exception as e:
        return {"error": f"Error procesando: {e}"}, 500

    zip_buffer.seek(0)
    zip_data = zip_buffer.getvalue()

    # === 3. RESPUESTA MULTIPART (JSON + ZIP en una sola petición) ===
    boundary = "----FLASKBOUNDARY123"
    parts = []

    # Parte 1: JSON
    parts.append(f"--{boundary}")
    parts.append("Content-Type: application/json")
    parts.append("Content-Disposition: attachment; filename=\"metadata.json\"")
    parts.append("")
    parts.append(metadata_json_str)

    # Parte 2: ZIP
    parts.append(f"--{boundary}")
    parts.append("Content-Type: application/zip")
    parts.append("Content-Disposition: attachment; filename=\"lotes_divididos.zip\"")
    parts.append("")
    parts.append("{ZIP_BINARY_DATA}")  # placeholder

    parts.append(f"--{boundary}--")
    body_prefix = "\r\n".join(parts).encode('utf-8')
    body_prefix = body_prefix.replace(b"{ZIP_BINARY_DATA}", b"")  # quitamos placeholder

    def generate():
        yield body_prefix
        yield zip_data
        yield f"\r\n--{boundary}--".encode('utf-8')

    response = Response(generate(), mimetype=f'multipart/mixed; boundary={boundary}')
    response.headers['Content-Disposition'] = 'attachment; filename="resultado_completo.dat"'
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)