from flask import Flask, request, jsonify
from docxtpl import DocxTemplate
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import tempfile

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

        contexto = {
            'pao_id': pao_id,
            'pao': pao_data.get('pao', ''),
            'paralelo': pao_data.get('paralelo', ''),
            'carrera': pao_data.get('carrera', ''),
            'ciclo': pao_data.get('ciclo', ''),
            'nombre_tutor': pao_data.get('nombre_tutor', ''),
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

        actividades_ref = db.collection('PAOs').document(pao_id).collection('actividades').stream()
        for actividad in actividades_ref:
            act_data = actividad.to_dict()
            num = actividad.id

            contexto[f'fecha_{num}'] = act_data.get('fecha', '')
            materias_actividad = act_data.get('materias', [])
            for idx in range(7):
                nombre_materia = materias[idx] if idx < len(materias) else ''
                materia_data = next((m for m in materias_actividad if m.get('nombre') == nombre_materia), None)

                contexto[f'observacion_problemasDetectados_{num}_m{idx + 1}'] = materia_data.get('problemasDetectados', '') if materia_data else ''
                contexto[f'observacion_accionesDeMejora_{num}_m{idx + 1}'] = materia_data.get('accionesMejora', '') if materia_data else ''
                contexto[f'observacion_resultadosObtenidos_{num}_m{idx + 1}'] = materia_data.get('resultadosObtenidos', '') if materia_data else ''

        # Generar el documento
        doc = DocxTemplate("plantillas/plantillafinal.docx")
        doc.render(contexto)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        blob = bucket.blob(f'documentos_pao/{pao_id}.docx')
        blob.upload_from_filename(tmp_path)
        blob.make_public()

        return jsonify({'url_docx': blob.public_url}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
