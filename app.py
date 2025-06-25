from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, storage
from docxtpl import DocxTemplate
import os
import tempfile
import cloudconvert
import requests

app = Flask(__name__)

cred = credentials.Certificate('/etc/secrets/service_account.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'gs://academico-4a053.firebasestorage.app'
})
db = firestore.client()
cloudconvert.configure(api_key=os.environ['CLOUDCONVERT_API_KEY'])

@app.route('/generar_pao', methods=['POST'])
def generar_pao():
    data = request.get_json()
    pao_id = data.get('paoID')
    if not pao_id:
        return jsonify({'error': 'Falta el paoID'}), 400

    try:
        doc_pao = db.collection('PAOs').document(pao_id).get()
        if not doc_pao.exists:
            return jsonify({'error': 'PAO no encontrado'}), 404

        pao_data = doc_pao.to_dict()

        actividades = db.collection('PAOs').document(pao_id).collection('actividades').stream()

        doc = DocxTemplate('plantillas/formato_final.docx')

        context = {
            'pao': pao_data.get('pao'),
            'paralelo': pao_data.get('paralelo'),
            'nombre_tutor': 'Tutor asignado',
            'materias': pao_data.get('materias', [])
        }

        for actividad in actividades:
            act = actividad.to_dict()
            num = act['numeroActividad']
            for idx, materia in enumerate(act['materias']):
                n_materia = f'm{idx+1}'
                context[f'observacion_problemasDetectados_{num}_{n_materia}'] = materia.get('problemasDetectados', '')
                context[f'observacion_accionesDeMejora_{num}_{n_materia}'] = materia.get('accionesMejora', '')
                context[f'observacion_resultadosObtenidos_{num}_{n_materia}'] = materia.get('resultadosObtenidos', '')

        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, f'{pao_id}.docx')
            pdf_path = os.path.join(tmpdir, f'{pao_id}.pdf')

            doc.render(context)
            doc.save(docx_path)

            job = cloudconvert.Job.create(payload={
                "tasks": {
                    "import-my-file": {
                        "operation": "import/upload"
                    },
                    "convert-my-file": {
                        "operation": "convert",
                        "input": "import-my-file",
                        "input_format": "docx",
                        "output_format": "pdf"
                    },
                    "export-my-file": {
                        "operation": "export/url",
                        "input": "convert-my-file"
                    }
                }
            })

            upload_task = job['tasks'][0]
            upload_url = upload_task['result']['form']['url']
            upload_params = upload_task['result']['form']['parameters']

            with open(docx_path, 'rb') as f:
                response = requests.post(upload_url, data=upload_params, files={'file': f})
                response.raise_for_status()

            job = cloudconvert.Job.wait(id=job['id'])

            export_task = [t for t in job['tasks'] if t['operation'] == 'export/url'][0]
            pdf_url = export_task['result']['files'][0]['url']
            pdf_content = requests.get(pdf_url).content

            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)

            bucket = storage.bucket()
            blob = bucket.blob(f'documentos_pao/{pao_id}.pdf')
            blob.upload_from_filename(pdf_path)
            blob.make_public()

            return jsonify({'url_pdf': blob.public_url}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
