from flask import Flask, jsonify
from docxtpl import DocxTemplate
import os
import tempfile

app = Flask(__name__)

@app.route('/prueba_docx', methods=['GET'])
def prueba_docx():
    try:
        print("Ruta absoluta del .docx:", os.path.abspath('plantillas/formato_final.docx'))
        doc = DocxTemplate('plantillas/formato_final.docx')

        # Diccionario de prueba simula los datos que vendrían de Firestore
        context = {
            'pao': '5',
            'paralelo': 'A',
            'carrera': 'Tecnologías de la Información',
            'ciclo': '1',
            'nombre_tutor': 'Juan Pérez',
            'nombre_aprobado_por': 'Maria García',
            'fecha_presentacion_doc': '26/06/2025',
            'conclusion_1': 'Mejora continua observada.',
            'conclusion_2': 'Participación estudiantil alta.',
            'conclusion_3': 'Falta seguimiento en algunos casos.',
            'recomendacion_1': 'Incorporar talleres prácticos.',
            'recomendacion_2': 'Motivar la asistencia.',
            'recomendacion_3': 'Refuerzo académico focalizado.'
        }

        # 7 materias de prueba
        for i in range(1, 8):
            context[f'materia_{i}'] = f'Materia {i}'

        # 10 actividades, cada una con 7 materias
        for num in range(1, 11):
            context[f'fecha_{num}'] = f'0{num}/06/2025'
            for m in range(1, 8):
                context[f'observacion_problemasDetectados_{num}_m{m}'] = f'Problema {m} actividad {num}'
                context[f'observacion_accionesDeMejora_{num}_m{m}'] = f'Acción {m} actividad {num}'
                context[f'observacion_resultadosObtenidos_{num}_m{m}'] = f'Resultado {m} actividad {num}'

        print("Contexto de prueba generado correctamente.")

        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, 'prueba_pao.docx')

            doc.render(context)
            doc.save(docx_path)

            return jsonify({'mensaje': 'Documento generado correctamente', 'ruta_local': docx_path}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)



