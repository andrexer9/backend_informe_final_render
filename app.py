from flask import Flask, request, jsonify
from docxtpl import DocxTemplate
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import tempfile
import requests
import uuid

app = Flask(__name__)

cred = credentials.Certificate('/etc/secrets/service_account.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'academico-4a053.firebasestorage.app'
})
db = firestore.client()
bucket = storage.bucket()

@app.route('/ping', methods=['GET'])
def ping():
    return 'pong', 200

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
        ciclo = pao_data.get('ciclo', '')
        nombre_aprobado_por = pao_data.get('nombre_aprobado_por', '')
        fechas_actividades = pao_data.get('fechas_actividades', [''] * 10)

        tutor_query = db.collection('usuarios').where('paoTutor', '==', pao_id).where('rol', '==', 'tutor').limit(1).get()
        if not tutor_query:
            return jsonify({'error': 'No se encontró tutor asignado a este PAO'}), 404

        nombre_tutor = tutor_query[0].to_dict().get('nombre', '')

        contexto = {
            'pao_id': pao_id,
            'pao': pao_data.get('pao', ''),
            'paralelo': paralelos_str,
            'carrera': pao_data.get('carrera', ''),
            'ciclo': ciclo,
            'nombre_tutor': nombre_tutor,
            'nombre_aprobado_por': nombre_aprobado_por,
        }

        for idx in range(7):
            contexto[f'materia_{idx + 1}'] = materias[idx] if idx < len(materias) else ''

        for idx in range(10):
            contexto[f'fecha_{idx + 1}'] = fechas_actividades[idx] if idx < len(fechas_actividades) else ''

        doc = DocxTemplate("plantillas/plantillafinal.docx")
        doc.render(contexto)

        unique_id = str(uuid.uuid4())

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        blob_word = bucket.blob(f'documentos_pao/{pao_id}_{unique_id}.docx')
        blob_word.upload_from_filename(tmp_path)
        blob_word.make_public()

        api_key = os.getenv('PDFCO_API_KEY', 'andrexer9@gmail.com_mdkuIY40IwQuhgOqUXW1JEa96Q440UIDk8JWpBQ5q92E94gZ57BrmryjM7qdsVu0')
        url_api = "https://api.pdf.co/v1/pdf/convert/from/doc"
        payload = {
            "url": f"{blob_word.public_url}?nocache={unique_id}",
            "name": f"{pao_id}_{unique_id}.pdf"
        }
        headers = {
            "x-api-key": api_key
        }

        response = requests.post(url_api, json=payload, headers=headers)
        resultado = response.json()

        if not resultado.get("url"):
            os.remove(tmp_path)
            return jsonify({'error': 'Error al convertir a PDF', 'detalle': resultado}), 500

        pdf_url = resultado["url"]
        pdf_response = requests.get(pdf_url)

        if pdf_response.status_code != 200:
            os.remove(tmp_path)
            return jsonify({'error': 'Error al descargar PDF convertido'}), 500

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(pdf_response.content)
            tmp_pdf_path = tmp_pdf.name

        blob_pdf = bucket.blob(f'documentos_pao/{pao_id}_{unique_id}.pdf')
        blob_pdf.upload_from_filename(tmp_pdf_path)
        blob_pdf.make_public()

        os.remove(tmp_path)
        os.remove(tmp_pdf_path)

        return jsonify({
            'url_word': blob_word.public_url,
            'url_pdf': blob_pdf.public_url,
            'contexto': contexto
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
