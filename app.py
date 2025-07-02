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

        # CORREGIDO: buscar con paoTutor en lugar de paoID
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
            headers = {'x-api-key': os.environ.get('PDFCO_API_KEY')}
            pdfco_url = 'https://api.pdf.co/v1/pdf/convert/from/doc'

            pdf_response = requests.post(pdfco_url, headers=headers, files=files)

            if pdf_response.status_code != 200:
                return jsonify({'error': 'Error al convertir a PDF con PDF.co'}), 500

            pdf_result = pdf_response.json()
            pdf_url_temp = pdf_result.get('url')

            if not pdf_url_temp:
                return jsonify({'error': 'No se obtuvo URL del PDF'}), 500

            pdf_file = requests.get(pdf_url_temp)
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
