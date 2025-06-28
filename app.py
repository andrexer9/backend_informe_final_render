from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import os

app = Flask(__name__)

cred = credentials.Certificate('/etc/secrets/service_account.json')
firebase_admin.initialize_app(cred)
db = firestore.client()


@app.route('/obtener-contexto-pao/<pao_id>', methods=['GET'])
def obtener_contexto_pao(pao_id):
    try:
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

        # Cargar materias en contexto
        for idx in range(7):
            key = f'materia_{idx + 1}'
            contexto[key] = materias[idx] if idx < len(materias) else ''

        # Cargar actividades
        actividades_ref = db.collection('PAOs').document(pao_id).collection('actividades').stream()
        for actividad in actividades_ref:
            act_data = actividad.to_dict()
            num = actividad.id  # Asumimos IDs son "1", "2", ..., "10"

            contexto[f'fecha_{num}'] = act_data.get('fecha', '')

            materias_actividad = act_data.get('materias', [])
            for idx in range(7):
                nombre_materia = materias[idx] if idx < len(materias) else ''
                materia_data = next((m for m in materias_actividad if m.get('nombre') == nombre_materia), None)

                contexto[f'observacion_problemasDetectados_{num}_m{idx + 1}'] = materia_data.get('problemasDetectados', '') if materia_data else ''
                contexto[f'observacion_accionesDeMejora_{num}_m{idx + 1}'] = materia_data.get('accionesMejora', '') if materia_data else ''
                contexto[f'observacion_resultadosObtenidos_{num}_m{idx + 1}'] = materia_data.get('resultadosObtenidos', '') if materia_data else ''

        return jsonify(contexto), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
