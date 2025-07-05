from flask import Flask, request, jsonify
from docxtpl import DocxTemplate
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import tempfile
import requests
from datetime import timedelta

app = Flask(__name__)

cred = credentials.Certificate('/etc/secrets/service_account.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'academico-4a053.firebasestorage.app'  # Asegúrate que esté bien escrito
})
db = firestore.client()
bucket = storage.bucket()

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
            'nombre_tutor': nombre_tutor
        }

        doc = DocxTemplate("plantillas/plantillafinal.docx")
        doc.render(contexto)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        # Subir el Word a Storage
        blob_word = bucket.blob(f'documentos_pao/{pao_id}.docx')
        blob_word.upload_from_filename(tmp_path)

        # Generar URL firmada válida por 15 minutos
        signed_url = blob_word.generate_signed_url(expiration=timedelta(minutes=15))

        # Enviar a PDF.co usando el signed URL
        pdfco_url = 'https://api.pdf.co/v1/pdf/convert/from/url'
        headers = {'x-api-key': os.environ.get('PDFCO_API_KEY')}
        payload = {
            'url': signed_url,
            'name': f'{pao_id}.pdf'
        }

        pdf_response = requests.post(pdfco_url, headers=headers, json=payload)

        if pdf_response.status_code != 200:
            print(pdf_response.text)
            return jsonify({'error': 'Error al convertir a PDF con PDF.co'}), 500

        pdf_result = pdf_response.json()
        pdf_url_temp = pdf_result.get('url')

        if not pdf_url_temp:
            return jsonify({'error': 'No se obtuvo URL del PDF'}), 500

        # Descargar PDF y subirlo a Firebase
        pdf_file = requests.get(pdf_url_temp)
        pdf_path = tmp_path.replace('.docx', '.pdf')

        with open(pdf_path, 'wb') as pdf_f:
            pdf_f.write(pdf_file.content)

        blob_pdf = bucket.blob(f'documentos_pao/{pao_id}.pdf')
        blob_pdf.upload_from_filename(pdf_path)
        blob_pdf.make_public()

        return jsonify({
            'url_pdf': blob_pdf.public_url,
            'url_word': signed_url
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
