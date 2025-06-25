from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, storage
from docxtpl import DocxTemplate
import os
import tempfile
import requests

app = Flask(__name__)

cred = credentials.Certificate('ruta/service_account.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'gs://academico-4a053.firebasestorage.app'
})
db = firestore.client()
CLOUDCONVERT_API_KEY = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiYTQ3MGY3ZjgwNWIxM2EzNDU5ZDIyOGM2NTBiNzBjYWUxM2FlZWM4YjliNTEzZDFmYTAxZDJlOWU5NzhlODJhNDdjNjhhZmU0YWJiNTUzNjMiLCJpYXQiOjE3NTA0MTgyMjAuNTY3NDk2LCJuYmYiOjE3NTA0MTgyMjAuNTY3NDk3LCJleHAiOjQ5MDYwOTE4MjAuNTYyODg2LCJzdWIiOiI3MjI1MjkzNCIsInNjb3BlcyI6WyJ0YXNrLnJlYWQiLCJ0YXNrLndyaXRlIl19.TCCkzifTXS_le-ljQCDeLFdUKYkTH1w5AWKQnTnMlUhFG3eYVYlbcypn0d3rQ0qj_77UxisFl4sEsrdwryVudrx9JPsIvHqS_Pf13tGpHykhG9HBfThlR6rRYFCAOI7sDViTMj4HDoTFTGa6ZQxSY5OWSrgNJd1bCDMEWKNK_L3HyzotaoHZzEPCZ96AAVEPW4InJx60PB8nJXTWWGvL2c0ZF6UEZAORT4KBIh2ltXJ6wzZWH4XTcWm1uTve3yJn2eNhf1p0kQpIjJA0zATB8sE2PahwT0mjK7Cipjn3mg_02Z5gqtIfPO2RXZw4KbSwg2uRcpdT61vBhig1gXF3Q0QRaSIw2v_7AVloh0NevMvuSjLWCSJpx0_iQ64NZlZKj5sKzNWVC9KR4mox-f8m9JEP-oAedgRJ5sFYEZxlyANugWZZa7_64XcuQoaieUorPWmzQf25QzWgGkhqpHfkTTV6b_UpqfbWV8qt2UXyGlesNxgraf-xzocJyA28AHmk-eDYR1CMfW3xeakR6qYg1Zhrmh-eDRorzE-4SLpKLYj6D6ZhQtIlEhEi1_GCu2xMaMUJblBJNNhN2vPC9rxfgA8_oPDdDQYgTbqX69xRDB1QrB9r1u8FnBaqzPUOlrvgnMWjjXm_difW0HFFRLpIgx1hrjN8NddLUcLUIxdZ4aw'

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

            # Convertir a PDF con CloudConvert
            with open(docx_path, 'rb') as f:
                r = requests.post(
                    'https://api.cloudconvert.com/v2/convert',
                    headers={'Authorization': f'Bearer {CLOUDCONVERT_API_KEY}'},
                    files={'file': f},
                    data={'inputformat': 'docx', 'outputformat': 'pdf'}
                )
                if r.status_code != 200:
                    return jsonify({'error': 'Error al convertir a PDF'}), 500

                result = r.json()
                pdf_url = result['data']['url']
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
    app.run(debug=True)
