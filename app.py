from flask import Flask, send_file
from docxtpl import DocxTemplate
import os
import tempfile

app = Flask(__name__)

@app.route('/prueba_docx', methods=['GET'])
def prueba_docx():
    try:
        doc = DocxTemplate('plantillas/formato_final.docx')

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

        for i in range(1, 8):
            context[f'materia_{i}'] = f'Materia {i}'

        for num in range(1, 11):
            context[f'fecha_{num}'] = f'0{num}/06/2025'
            for m in range(1, 8):
                context[f'observacion_problemasDetectados_{num}_m{m}'] = f'Problema {m} actividad {num}'
                context[f'observacion_accionesDeMejora_{num}_m{m}'] = f'Acción {m} actividad {num}'
                context[f'observacion_resultadosObtenidos_{num}_m{m}'] = f'Resultado {m} actividad {num}'

        print("\n----- CONTENIDO DEL CONTEXT -----")
        for k, v in context.items():
            print(f"{k}: {v}")
        print("----- FIN DEL CONTEXT -----\n")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmpfile:
            doc.render(context)
            doc.save(tmpfile.name)
            tmpfile_path = tmpfile.name

        return send_file(tmpfile_path, as_attachment=True, download_name='prueba_pao.docx')

    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
