
from flask import Flask, request, jsonify
from docxtpl import DocxTemplate
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import tempfile
import requests
import time

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
            'nombre_tutor': nombre_tutor
        }

        doc = DocxTemplate("plantillas/plantillafinal.docx")
        doc.render(contexto)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        with open(tmp_path, 'rb') as f:
            files = {'file': f}
            headers = {
                'Authorization': f'Bearer {os.environ.get("CLOUDCONVERT_API_KEY")}'
            }
            upload_response = requests.post('https://api.cloudconvert.com/v2/import/upload', headers=headers)
            upload_data = upload_response.json()
            upload_url = upload_data['data']['url']

            upload_file_response = requests.put(upload_url, data=f)
            if upload_file_response.status_code not in [200, 201]:
                return jsonify({'error': 'Error al subir archivo a CloudConvert'}), 500

        job_payload = {
            "tasks": {
                "import-my-file": {"operation": "import/upload"},
                "convert-my-file": {
                    "operation": "convert",
                    "input": "import-my-file",
                    "output_format": "pdf"
                },
                "export-my-file": {
                    "operation": "export/url",
                    "input": "convert-my-file"
                }
            }
        }

        job_response = requests.post(
            "https://api.cloudconvert.com/v2/jobs",
            json=job_payload,
            headers=headers
        )

        if job_response.status_code not in [200, 201]:
            return jsonify({'error': 'Error al crear job en CloudConvert'}), 500

        job_id = job_response.json()['data']['id']

        while True:
            status_response = requests.get(f"https://api.cloudconvert.com/v2/jobs/{job_id}", headers=headers)
            status_data = status_response.json()
            if status_data['data']['status'] == 'finished':
                break
            time.sleep(2)

        export_task = next(task for task in status_data['data']['tasks'] if task['operation'] == 'export/url' and task['status'] == 'finished')
        pdf_url = export_task['result']['files'][0]['url']

        pdf_file = requests.get(pdf_url)
        pdf_path = tmp_path.replace('.docx', '.pdf')

        with open(pdf_path, 'wb') as pdf_f:
            pdf_f.write(pdf_file.content)

        blob_pdf = bucket.blob(f'documentos_pao/{pao_id}.pdf')
        blob_pdf.upload_from_filename(pdf_path)
        blob_pdf.make_public()

        return jsonify({'url_pdf': blob_pdf.public_url}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
