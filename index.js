
const express = require('express');
const cors = require('cors');
const Docxtemplater = require('docxtemplater');
const PizZip = require('pizzip');
const fs = require('fs');
const path = require('path');
const admin = require('firebase-admin');
const serviceAccount = require('./service_account.json');

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: 'academico-4a053.appspot.com'
});

const bucket = admin.storage().bucket();

const app = express();
app.use(cors());
app.use(express.json());

app.post('/generar', async (req, res) => {
  try {
    const templatePath = path.join(__dirname, 'documents', 'Documento_sin_titulo.docx');
    const content = fs.readFileSync(templatePath, 'binary');

    const zip = new PizZip(content);
    const doc = new Docxtemplater(zip, { paragraphLoop: true, linebreaks: true });

    doc.render(req.body);

    const buf = doc.getZip().generate({ type: 'nodebuffer' });

    const fileName = `documentos_pao/PAO_${Date.now()}.docx`;
    const file = bucket.file(fileName);
    await file.save(buf, {
      contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });

    const [url] = await file.getSignedUrl({
      action: 'read',
      expires: Date.now() + 1000 * 60 * 60 * 24,
    });

    res.json({ url });
  } catch (error) {
    console.error(error);
    res.status(500).send('Error al generar el documento');
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Servidor corriendo en puerto ${PORT}`));
