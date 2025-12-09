# API de Utilidades para Archivos CSV/XLSX

Esta es una API simple construida con Flask para realizar operaciones comunes en archivos de datos, como dividir archivos grandes, extraer encabezados y convertir datos a formato JSON.

## Endpoints

### 1. Dividir Archivo (`/split-file`)

Este endpoint divide un archivo `.csv` o `.xlsx` en múltiples archivos `.csv` más pequeños y los devuelve dentro de un archivo `.zip`.

*   **Método:** `POST`
*   **URL:** `/split-file`
*   **Parámetros de URL (Query Params):**
    *   `chunk_size` (opcional): Número de filas por cada archivo dividido.
        *   **Tipo:** `entero`
        *   **Valor por defecto:** `5000`
*   **Cuerpo de la Petición (Body):**
    *   `multipart/form-data` con un campo `file` que contiene el archivo `.csv` o `.xlsx`.

#### Respuestas

*   **Éxito (200 OK):**
    *   **Content-Type:** `application/zip`
    *   **Contenido:** Un archivo `lotes_divididos.zip` que contiene:
        *   `part_1.csv`, `part_2.csv`, ...: Los archivos divididos.
        *   `sample_data.csv`: Un archivo de muestra con los encabezados y las 3 primeras filas del archivo original.

*   **Error (400 Bad Request):**
    *   Si no se envía un archivo, el archivo está vacío, el formato no es soportado (`.csv`, `.xlsx`) o `chunk_size` no es un entero positivo.
    ```json
    {
      "error": "Mensaje descriptivo del error."
    }
    ```

*   **Error (500 Internal Server Error):**
    *   Si ocurre un error inesperado durante el procesamiento del archivo.
    ```json
    {
      "error": "Ocurrió un error al procesar el archivo: [detalle del error]"
    }
    ```

#### Ejemplo de uso con `curl`

```bash
# Usando el tamaño de lote por defecto (5000)
curl -X POST -F "file=@/ruta/a/tu/archivo.csv" "http://localhost:8080/split-file" -o lotes.zip

# Especificando un tamaño de lote de 1000
curl -X POST -F "file=@/ruta/a/tu/archivo.xlsx" "http://localhost:8080/split-file?chunk_size=1000" -o lotes.zip
```

---

### 2. Extraer Encabezados (`/extract-headers`)

Este endpoint lee un archivo `.csv`, extrae sus encabezados y devuelve tanto los encabezados formateados como el contenido completo del archivo en una respuesta JSON.

*   **Método:** `POST`
*   **URL:** `/extract-headers`
*   **Cuerpo de la Petición (Body):**
    *   `multipart/form-data` con un campo `file` que contiene el archivo `.csv`.

#### Respuestas

*   **Éxito (200 OK):**
    *   **Content-Type:** `application/json`
    *   **Contenido:** Un objeto JSON con dos claves:
        *   `input_column_literals`: Un string con los nombres de las columnas entre comillas simples y separados por comas (ej: `'col1', 'col2', 'col3'`).
        *   `CSV_content_file`: Un string con el contenido completo del archivo CSV.

*   **Error (400 Bad Request):**
    *   Si no se envía un archivo, el archivo está vacío o el formato no es `.csv`.

*   **Error (500 Internal Server Error):**
    *   Si ocurre un error inesperado durante la lectura del archivo.

#### Ejemplo de uso con `curl`

```bash
curl -X POST -F "file=@/ruta/a/tu/archivo.csv" "http://localhost:8080/extract-headers"
```

---

### 3. Extraer a JSON (`/extractjson`)

Este endpoint convierte el contenido de un archivo `.csv` o de múltiples archivos `.csv` dentro de un `.zip` a formato JSON.

*   **Método:** `POST`
*   **URL:** `/extractjson`
*   **Cuerpo de la Petición (Body):**
    *   `multipart/form-data` con un campo `file` que contiene el archivo `.csv` o `.zip`.

#### Lógica de Conversión

*   Cada fila del CSV se convierte en un objeto JSON.
*   Las columnas con valores vacíos o que solo contienen espacios en blanco se omiten del objeto JSON resultante para esa fila.

#### Respuestas

*   **Éxito (200 OK):**
    *   **Content-Type:** `application/json`
    *   **Si el input es un `.csv`:** Devuelve un array de objetos JSON.
        ```json
        [
          { "col1": "valorA", "col2": "valorB" },
          { "col1": "valorC", "col3": "valorD" }
        ]
        ```
    *   **Si el input es un `.zip`:** Devuelve un objeto donde cada clave es el nombre de un archivo CSV dentro del ZIP, y su valor es el array de objetos JSON correspondiente.
        ```json
        {
          "archivo1.csv": [
            { "col1": "valorA" },
            { "col1": "valorB" }
          ],
          "archivo2.csv": [
            { "id": "123", "name": "test" }
          ]
        }
        ```

*   **Error (400 Bad Request):**
    *   Si no se envía un archivo, el archivo está vacío, el formato no es soportado (`.csv`, `.zip`) o el ZIP no contiene archivos CSV.

*   **Error (500 Internal Server Error):**
    *   Si ocurre un error inesperado durante el procesamiento.

#### Ejemplo de uso con `curl`

```bash
# Con un archivo CSV
curl -X POST -F "file=@/ruta/a/tu/archivo.csv" "http://localhost:8080/extractjson"

# Con un archivo ZIP
curl -X POST -F "file=@/ruta/a/tu/archivos.zip" "http://localhost:8080/extractjson"
```

---

### 4. Health Check (`/health`)

Endpoint simple para verificar que la aplicación está en funcionamiento. Es útil para servicios de monitoreo o para mantener activa la aplicación en plataformas de hosting gratuitas.

*   **Método:** `GET`
*   **URL:** `/health`

#### Respuestas

*   **Éxito (200 OK):**
    ```json
    {
      "status": "ok",
      "message": "La aplicación está activa."
    }
    ```

#### Ejemplo de uso con `curl`

```bash
curl "http://localhost:8080/health"
```