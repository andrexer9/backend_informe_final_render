from flask import Flask, request, jsonify
from docxtpl import DocxTemplate
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import tempfile
import requests

app = Flask(__name__)

cred = credentials.Certificate('/etc/secrets/service_account.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'academico-4a053.firebasestorage.app'
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
            'nombre_tutor': nombre_tutor,
        }

        for idx in range(7):
            contexto[f'materia_{idx + 1}'] = materias[idx] if idx < len(materias) else ''

        doc = DocxTemplate("plantillas/plantillafinal.docx")
        doc.render(contexto)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        blob_word = bucket.blob(f'documentos_pao/{pao_id}.docx')
        blob_word.upload_from_filename(tmp_path)
        blob_word.make_public()

        api_key = 'andrexer9@gmail.com_mdkuIY40IwQuhgOqUXW1JEa96Q440UIDk8JWpBQ5q92E94gZ57BrmryjM7qdsVu0'

        url_api = "https://api.pdf.co/v1/pdf/convert/from/doc"
        payload = {
            "url": blob_word.public_url,
            "name": f"{pao_id}.pdf"
        }
        headers = {
            "x-api-key": api_key
        }

        response = requests.post(url_api, json=payload, headers=headers)
        resultado = response.json()

        if not resultado.get("url"):
            return jsonify({'error': 'Error al convertir a PDF', 'detalle': resultado}), 500

        pdf_url = resultado["url"]
        pdf_response = requests.get(pdf_url)

        if pdf_response.status_code != 200:
            return jsonify({'error': 'Error al descargar PDF convertido'}), 500

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(pdf_response.content)
            tmp_pdf_path = tmp_pdf.name

        blob_pdf = bucket.blob(f'documentos_pao/{pao_id}.pdf')
        blob_pdf.upload_from_filename(tmp_pdf_path)
        blob_pdf.make_public()

        return jsonify({
            'url_word': blob_word.public_url,
            'url_pdf': blob_pdf.public_url
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
