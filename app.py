from flask import Flask, request, jsonify
from docxtpl import DocxTemplate
import firebase_admin
from firebase_admin import credentials, storage
import os
import tempfile

app = Flask(__name__)

# Inicializar Firebase
cred = credentials.Certificate('/etc/secrets/service_account.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'academico-4a053.firebasestorage.app'
})
bucket = storage.bucket()


@app.route('/')
def home():
    return '✅ API de generación de Formato PAO funcionando'


@app.route('/generar-pao-docx', methods=['POST'])
def generar_pao_docx():
    """
    Espera un JSON con todo el contexto PAO.
    Devuelve el enlace público del `.docx` en Firebase Storage.
    """
    try:
        contexto = request.json

        doc = DocxTemplate("plantilla/formato_pao_limpio_doble_llave.docx")
        doc.render(contexto)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        blob = bucket.blob(f'documentos_pao/{contexto.get("pao_id", "pao_generico")}.docx')
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
