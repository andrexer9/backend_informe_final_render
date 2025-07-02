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
            'nombre_aprobado_por': pao_data.get('nombre_aprobado_por', ''),
            'fecha_presentacion_doc': pao_data.get('fecha_presentacion_doc', ''),
            'conclusion_1': pao_data.get('conclusion_1', ''),
            'conclusion_2': pao_data.get('conclusion_2', ''),
            'conclusion_3': pao_data.get('conclusion_3', ''),
            'recomendacion_1': pao_data.get('recomendacion_1', ''),
            'recomendacion_2': pao_data.get('recomendacion_2', ''),
            'recomendacion_3': pao_data.get('recomendacion_3', '')
        }

        for idx in range(7):
            contexto[f'materia_{idx + 1}'] = materias[idx] if idx < len(materias) else ''

        for num in range(1, 11):
            actividad_ref = db.collection('PAOs').document(pao_id).collection('actividades').document(str(num)).get()
            if actividad_ref.exists:
                act_data = actividad_ref.to_dict()
                contexto[f'fecha_{num}'] = act_data.get('fecha', '')
                materias_actividad = act_data.get('materias', [])
            else:
                contexto[f'fecha_{num}'] = ''
                materias_actividad = []

            for idx in range(7):
                nombre_materia = materias[idx] if idx < len(materias) else ''
                materia_data = next(
                    (m for m in materias_actividad if m.get('nombre', '').strip().lower() == nombre_materia.strip().lower()),
                    None
                )

                contexto[f'observacion_problemasDetectados_{num}_m{idx + 1}'] = materia_data.get('problemasDetectados', '') if materia_data else ''
                contexto[f'observacion_accionesDeMejora_{num}_m{idx + 1}'] = materia_data.get('accionesMejora', '') if materia_data else ''
                contexto[f'observacion_resultadosObtenidos_{num}_m{idx + 1}'] = materia_data.get('resultadosObtenidos', '') if materia_data else ''

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
            cloudconvert_url = 'https://api.cloudconvert.com/v2/import/upload'

            # 1. Subir el archivo a CloudConvert
            upload_response = requests.post(cloudconvert_url, headers=headers)
            upload_data = upload_response.json()
            upload_url = upload_data['data']['url']

            upload_file_response = requests.put(upload_url, data=f)
            if upload_file_response.status_code not in [200, 201]:
                return jsonify({'error': 'Error al subir archivo a CloudConvert'}), 500

            # 2. Crear el job de conversión
            job_payload = {
                "tasks": {
                    "import": {
                        "operation": "import/upload"
                    },
                    "convert": {
                        "operation": "convert",
                        "input": "import",
                        "output_format": "pdf"
                    },
                    "export": {
                        "operation": "export/url",
                        "input": "convert"
                    }
                }
            }

            job_response = requests.post(
                "https://api.cloudconvert.com/v2/jobs",
                json=job_payload,
                headers=headers
            )

            if job_response.status_code != 201:
                return jsonify({'error': 'Error al crear job en CloudConvert'}), 500

            job_data = job_response.json()
            job_id = job_data['data']['id']

            # 3. Esperar a que termine el job
            job_status_url = f"https://api.cloudconvert.com/v2/jobs/{job_id}"
            while True:
                status_response = requests.get(job_status_url, headers=headers)
                status_data = status_response.json()
                if status_data['data']['status'] == 'finished':
                    break

            # 4. Obtener URL del PDF
            export_task = next(
                task for task in status_data['data']['tasks']
                if task['name'] == 'export' and task['status'] == 'finished'
            )
            pdf_url = export_task['result']['files'][0]['url']

            # 5. Descargar el PDF y subirlo a Firebase
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
