# Backend para generación de informe final PAO

Este backend genera un archivo PDF usando una plantilla .docx y lo sube a Firebase Storage.
Utiliza CloudConvert para convertir DOCX a PDF y responde con una URL de descarga.

## Variables necesarias (.env)
- CLOUDCONVERT_API_KEY
- GOOGLE_CREDENTIALS (contenido JSON del serviceAccountKey)
