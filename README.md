# SheetSlice API

Un microservicio web simple, construido con Python y Flask, diseñado para dividir archivos CSV y XLSX de gran tamaño en múltiples archivos `.csv` más pequeños.

## ✨ Características Principales

-   **División Inteligente de Archivos**: Procesa archivos `.csv` y `.xlsx` y los divide en lotes según un tamaño de fila especificado por el usuario.
-   **Optimización de Formato**: Convierte automáticamente los lotes de archivos `.xlsx` a formato `.csv`, reduciendo significativamente el tamaño final.
-   **Salida Comprimida**: Devuelve un único archivo `.zip` que contiene todas las partes generadas, listo para descargar y usar.
-   **Procesamiento Eficiente en Memoria**:
    -   Para archivos `.csv`, utiliza un sistema de lectura por trozos (`chunks`) para manejar archivos de gran tamaño sin agotar la memoria.
    -   Toda la operación de compresión se realiza en memoria para evitar escrituras innecesarias en disco.
-   **API Fácil de Usar**: Expone un único endpoint que se puede consumir a través de peticiones HTTP estándar.

## 🛠️ Tecnologías Utilizadas

-   **Backend**: Python
-   **Framework**: Flask
-   **Manipulación de Datos**: Pandas
-   **Servidor WSGI para Producción**: Gunicorn

## 🚀 Cómo Usarlo como API

Una vez que el servicio está en ejecución, puedes enviar una petición `POST` al endpoint `/split-file` con el archivo que deseas dividir.

**Endpoint**: `/split-file`
**Método**: `POST`

### Parámetros

-   **`chunk_size`** (parámetro en la URL, opcional): Un número entero que especifica cuántas filas tendrá cada archivo dividido. Si no se proporciona, el valor por defecto es `5000`.
-   **`file`** (en `form-data`): El archivo `.csv` o `.xlsx` que deseas procesar.

### Ejemplo de Petición (usando `curl`)

Este comando divide `archivo_grande.xlsx` en partes de 10,000 filas cada una y guarda el resultado en `lotes.zip`.

```bash
curl -X POST "http://127.0.0.1:8000/split-file?chunk_size=10000" \
     -F "file=@/ruta/a/tu/archivo_grande.xlsx" \
     -o "lotes.zip"
```

### Respuestas Posibles

-   **Éxito (`200 OK`)**: La respuesta será un archivo `lotes_divididos.zip` que contiene las partes del archivo original en formato `.csv`.
-   **Error del Cliente (`400 Bad Request`)**: La respuesta será un JSON con un mensaje de error si falta el archivo, el formato no es soportado o `chunk_size` no es válido.
-   **Error del Servidor (`500 Internal Server Error`)**: La respuesta será un JSON si ocurre un problema inesperado durante el procesamiento del archivo.

## ⚙️ Cómo Ejecutarlo Localmente

1.  **Clona el repositorio:**
    ```bash
    git clone https://github.com/tu-usuario/SheetSlice-API.git
    cd SheetSlice-API
    ```

2.  **Crea y activa un entorno virtual (recomendado):**
    ```bash
    # Para macOS/Linux
    python3 -m venv venv
    source venv/bin/activate

    # Para Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Instala las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Inicia la aplicación con Gunicorn:**
    ```bash
    gunicorn "app:app"
    ```

¡Listo! La API estará disponible en `http://127.0.0.1:8000`.