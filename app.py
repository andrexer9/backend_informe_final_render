from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, storage
from docxtpl import DocxTemplate
import os
import tempfile
import logging
from datetime import datetime

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Inicialización de Firebase
try:
    cred = credentials.Certificate('/etc/secrets/service_account.json')
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'academico-4a053.firebasestorage.app'
    })
    db = firestore.client()
    logger.info("Firebase inicializado correctamente")
except Exception as e:
    logger.error(f"Error al inicializar Firebase: {str(e)}")
    raise

def process_materias(materias_data):
    """Procesa la estructura de materias que puede venir en diferentes formatos"""
    if isinstance(materias_data, list):
        return materias_data
    elif isinstance(materias_data, dict):
        # Si es diccionario, extraemos las materias ordenadas por clave numérica
        return [materias_data[key] for key in sorted(materias_data.keys()) 
                if key.isdigit() and isinstance(materias_data[key], str)]
    return []

def validate_pao_data(pao_data):
    """Valida los datos mínimos requeridos del PAO"""
    required_fields = ['pao', 'paralelo', 'materias']
    missing_fields = [field for field in required_fields if field not in pao_data]
    if missing_fields:
        raise ValueError(f"Campos requeridos faltantes: {', '.join(missing_fields)}")

@app.route('/generar_pao', methods=['POST'])
def generar_pao():
    data = request.get_json()
    pao_id = data.get('paoID')
    
    if not pao_id:
        return jsonify({'error': 'Falta el paoID'}), 400

    try:
        # Obtener documento PAO principal
        doc_pao = db.collection('PAOs').document(pao_id).get()
        if not doc_pao.exists:
            return jsonify({'error': 'PAO no encontrado'}), 404

        pao_data = doc_pao.to_dict()
        
        # Validar campos obligatorios
        required_fields = ['pao', 'paralelo', 'materias', 'nombre_tutor', 'fecha_presentacion_doc']
        missing_fields = [field for field in required_fields if field not in pao_data]
        if missing_fields:
            return jsonify({
                'error': 'Campos requeridos faltantes',
                'missing_fields': missing_fields
            }), 400

        # Obtener actividades ordenadas
        actividades_ref = db.collection('PAOs').document(pao_id).collection('actividades')
        actividades = sorted(
            [act.to_dict() for act in actividades_ref.stream()],
            key=lambda x: x.get('numeroActividad', 0)
        )

        # Procesar materias (limitar a 6 como muestra el log)
        materias = pao_data['materias'][:6] if isinstance(pao_data['materias'], list) else []
        
        # Preparar contexto base
        context = {
            'pao': pao_data['pao'],
            'paralelo': pao_data['paralelo'],
            'ciclo': pao_data.get('ciclo', ''),
            'carrera': 'Tecnologías de la Información',  # Valor fijo según formato
            'nombre_tutor': pao_data['nombre_tutor'],
            'nombre_aprobado_por': pao_data.get('nombre_aprobado_por', ''),
            'fecha_presentacion_doc': pao_data['fecha_presentacion_doc'],
            'conclusion_1': pao_data.get('conclusion_1', ''),
            'conclusion_2': pao_data.get('conclusion_2', ''),
            'conclusion_3': pao_data.get('conclusion_3', ''),
            'recomendacion_1': pao_data.get('recomendacion_1', ''),
            'recomendacion_2': pao_data.get('recomendacion_2', ''),
            'recomendacion_3': pao_data.get('recomendacion_3', '')
        }

        # Agregar materias al contexto
        for i, materia in enumerate(materias, 1):
            context[f'materia_{i}'] = materia

        # Rellenar hasta 6 materias para que el formato no falle
        for i in range(len(materias) + 1, 7):
            context[f'materia_{i}'] = ''

        # Procesar actividades (1-10)
        for actividad in actividades:
            num = actividad.get('numeroActividad')
            if not num or num < 1 or num > 10:
                continue
                
            # Formatear fecha correctamente
            fecha = actividad.get('fecha', '')
            if isinstance(fecha, datetime.datetime):
                context[f'fecha_{num}'] = fecha.strftime('%d/%m/%Y')
            else:
                context[f'fecha_{num}'] = fecha if fecha else ''

            # Procesar datos por materia
            for i, materia_nombre in enumerate(materias, 1):
                materia_data = next(
                    (m for m in actividad.get('materias', []) 
                     if isinstance(m, dict) and m.get('nombre') == materia_nombre),
                    {}
                )
                
                # Asignar valores con texto por defecto si están vacíos
                context[f'observacion_problemasDetectados_{num}_m{i}'] = materia_data.get('problemasDetectados', 'Sin datos')
                context[f'observacion_accionesDeMejora_{num}_m{i}'] = materia_data.get('accionesMejora', 'Sin datos')
                context[f'observacion_resultadosObtenidos_{num}_m{i}'] = materia_data.get('resultadosObtenidos', 'Sin datos')

        # Rellenar observaciones vacías para todas las combinaciones actividad-materia
        for num in range(1, 11):
            for i in range(1, 7):
                for prefix in ['problemasDetectados', 'accionesDeMejora', 'resultadosObtenidos']:
                    key = f'observacion_{prefix}_{num}_m{i}'
                    if key not in context:
                        context[key] = 'Sin datos'

        # Generar documento con la plantilla correcta
        doc = DocxTemplate('plantillas/formato_final.docx')
        doc.render(context)
        
        # Guardar y subir el documento
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, f'PAO_{pao_id}.docx')
            doc.save(docx_path)

            bucket = storage.bucket()
            blob = bucket.blob(f'documentos_pao/PAO_{pao_id}.docx')
            blob.upload_from_filename(docx_path)
            blob.make_public()

            return jsonify({
                'success': True,
                'url_docx': blob.public_url,
                'nombre_archivo': f'PAO_{pao_id}.docx'
            }), 200

    except Exception as e:
        logger.error(f"Error al generar PAO: {str(e)}", exc_info=True)
        return jsonify({'error': f"Error al generar el documento: {str(e)}"}), 500
        if __name__ == '__main__':
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port)
