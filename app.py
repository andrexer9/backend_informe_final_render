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
        logger.error("Solicitud sin paoID")
        return jsonify({'error': 'Falta el paoID'}), 400

    try:
        logger.info(f"Iniciando generación de PAO para ID: {pao_id}")
        
        # Obtener documento PAO principal
        doc_pao = db.collection('PAOs').document(pao_id).get()
        if not doc_pao.exists:
            logger.error(f"PAO no encontrado: {pao_id}")
            return jsonify({'error': 'PAO no encontrado'}), 404

        pao_data = doc_pao.to_dict()
        validate_pao_data(pao_data)
        
        # Obtener todas las actividades
        actividades_ref = db.collection('PAOs').document(pao_id).collection('actividades')
        actividades = [act.to_dict() for act in actividades_ref.stream()]
        logger.info(f"Encontradas {len(actividades)} actividades")

        # Cargar plantilla
        template_path = 'plantillas/formato_prueba.docx'
        if not os.path.exists(template_path):
            logger.error(f"Plantilla no encontrada en: {os.path.abspath(template_path)}")
            return jsonify({'error': 'Plantilla no encontrada'}), 500
            
        doc = DocxTemplate(template_path)

        # Contexto base
        context = {
            'pao': pao_data.get('pao', ''),
            'paralelo': pao_data.get('paralelo', ''),
            'ciclo': pao_data.get('ciclo', ''),
            'carrera': pao_data.get('carrera', 'Tecnologías de la información'),
            'nombre_tutor': pao_data.get('nombre_tutor', ''),
            'nombre_aprobado_por': pao_data.get('nombre_aprobado_por', ''),
            'fecha_generacion': datetime.now().strftime('%d/%m/%Y'),
            'fecha_presentacion_doc': pao_data.get('fecha_presentacion_doc', ''),
            'conclusion_1': pao_data.get('conclusion_1', ''),
            'conclusion_2': pao_data.get('conclusion_2', ''),
            'conclusion_3': pao_data.get('conclusion_3', ''),
            'recomendacion_1': pao_data.get('recomendacion_1', ''),
            'recomendacion_2': pao_data.get('recomendacion_2', ''),
            'recomendacion_3': pao_data.get('recomendacion_3', '')
        }

        # Procesar materias
        materias = process_materias(pao_data.get('materias', []))
        logger.info(f"Materias procesadas: {materias}")

        # Agregar materias al contexto
        for i, materia in enumerate(materias, 1):
            context[f'materia_{i}'] = materia

        # Procesar actividades
        for actividad in actividades:
            num = actividad.get('numeroActividad')
            if not num:
                continue
                
            context[f'fecha_{num}'] = actividad.get('fecha', '')

            # Procesar datos por materia en cada actividad
            for i, materia_nombre in enumerate(materias, 1):
                materia_data = next(
                    (m for m in actividad.get('materias', []) 
                     if isinstance(m, dict) and m.get('nombre') == materia_nombre),
                    {}
                )
                
                context[f'observacion_problemasDetectados_{num}_m{i}'] = materia_data.get('problemasDetectados', '')
                context[f'observacion_accionesDeMejora_{num}_m{i}'] = materia_data.get('accionesMejora', '')
                context[f'observacion_resultadosObtenidos_{num}_m{i}'] = materia_data.get('resultadosObtenidos', '')

        logger.info("Contexto generado para el documento:")
        logger.info(context)

        # Generar y subir documento
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, f'PAO_{pao_id}.docx')
            doc.render(context)
            doc.save(docx_path)

            # Subir a Firebase Storage
            bucket = storage.bucket()
            blob = bucket.blob(f'documentos_pao/PAO_{pao_id}.docx')
            blob.upload_from_filename(docx_path)
            blob.make_public()

            logger.info(f"Documento generado y subido correctamente: {blob.public_url}")
            return jsonify({
                'url_docx': blob.public_url,
                'nombre_archivo': f'PAO_{pao_id}.docx'
            }), 200

    except ValueError as ve:
        logger.error(f"Error de validación: {str(ve)}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}", exc_info=True)
        return jsonify({'error': f"Error al generar el documento: {str(e)}"}), 500

@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'false').lower() == 'true')
