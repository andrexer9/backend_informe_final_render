from flask import Flask, request, jsonify
from docxtpl import DocxTemplate
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import tempfile
import requests  # Necesario para llamar a la API de PDF.co
import time

app = Flask(__name__)

# Configuración de Firebase
cred = credentials.Certificate('/etc/secrets/service_account.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'academico-4a053.firebasestorage.app'
})
db = firestore.client()
bucket = storage.bucket()

# Configuración de PDF.co (deberías poner esto en variables de entorno)
PDF_CO_API_KEY = 'andrexer9@gmail.com_mdkuIY40IwQuhgOqUXW1JEa96Q440UIDk8JWpBQ5q92E94gZ57BrmryjM7qdsVu0'  # Mejor usa os.environ.get('PDF_CO_API_KEY')
PDF_CO_API_URL = 'https://api.pdf.co/v1'

@app.route('/generar-pao-directo', methods=['POST'])
def generar_pao_directo():
    try:
        data = request.json
        pao_id = data.get('pao_id')

        if not pao_id:
            return jsonify({'error': 'Falta el pao_id'}), 400

        doc_pao = db.collection('PAOs').document(pao_id).get()
        if not doc_pao.exists:
            return jsonify({'error': 'PAO no encontrado'}), 404

        pao_data = doc_pao.to_dict()
        materias = pao_data.get('materias', [])
        paralelos = pao_data.get('paralelos', [])
        paralelos_str = '-'.join(paralelos) if paralelos else ''

        tutor_query = db.collection('usuarios').where('paoTutor', '==', pao_id).where('rol', '==', 'tutor').limit(1).get()
        if not tutor_query:
            return jsonify({'error': 'No se encontró tutor asignado a este PAO'}), 404

        nombre_tutor = tutor_query[0].to_dict().get('nombre', '')

        contexto = {
            'pao_id': pao_id,
            'pao': pao_data.get('pao', ''),
            'paralelo': paralelos_str,
            'carrera': pao_data.get('carrera', ''),
            'ciclo': pao_data.get('ciclo', ''),
            'nombre_tutor': nombre_tutor,
        }

        # Agregar las materias al contexto
        for idx in range(7):
            contexto[f'materia_{idx + 1}'] = materias[idx] if idx < len(materias) else ''

        # 1. Generar el documento Word
        doc = DocxTemplate("plantillas/plantillafinal.docx")
        doc.render(contexto)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        # 2. Subir el Word a Firebase Storage
        blob_word = bucket.blob(f'documentos_pao/{pao_id}.docx')
        blob_word.upload_from_filename(tmp_path)
        blob_word.make_public()
        word_url = blob_word.public_url

        # 3. Convertir el Word a PDF usando PDF.co
        pdf_result = convert_word_to_pdf(word_url, pao_id)
        
        if not pdf_result.get('success'):
            return jsonify({
                'url_word': word_url,
                'error_pdf': pdf_result.get('error', 'Error desconocido al convertir a PDF')
            }), 200

        # 4. Subir el PDF a Firebase Storage
        pdf_url = pdf_result['url']
        pdf_content = requests.get(pdf_url).content
        
        blob_pdf = bucket.blob(f'documentos_pao/{pao_id}.pdf')
        blob_pdf.upload_from_string(pdf_content, content_type='application/pdf')
        blob_pdf.make_public()

        # Limpiar archivos temporales
        os.unlink(tmp_path)

        return jsonify({
            'url_word': word_url,
            'url_pdf': blob_pdf.public_url
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def convert_word_to_pdf(word_url, pao_id):
    """Función para convertir Word a PDF usando PDF.co"""
    try:
        # Paso 1: Subir el archivo Word a PDF.co (o usar URL pública)
        # En este caso ya tenemos una URL pública de Firebase Storage
        
        # Paso 2: Solicitar la conversión
        convert_endpoint = f"{PDF_CO_API_URL}/pdf/convert/from/url"
        
        payload = {
            "url": word_url,
            "name": f"pao_{pao_id}.pdf",
            "async": False  # Procesamiento sincrónico para simplificar
        }
        
        headers = {
            "x-api-key": PDF_CO_API_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.post(convert_endpoint, json=payload, headers=headers)
        response_data = response.json()
        
        if response.status_code != 200:
            return {
                'success': False,
                'error': f"Error en la API: {response_data.get('message', 'Error desconocido')}"
            }
        
        # Verificar si la conversión fue exitosa
        if not response_data.get('url'):
            return {
                'success': False,
                'error': 'No se obtuvo URL del PDF convertido'
            }
        
        return {
            'success': True,
            'url': response_data['url']
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
