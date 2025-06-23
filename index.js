
const express = require('express');
const fileUpload = require('express-fileupload');
const Docxtemplater = require('docxtemplater');
const PizZip = require('pizzip');
const fs = require('fs');
const path = require('path');
const app = express();

app.use(express.json());
app.use(fileUpload());

app.post('/generar', (req, res) => {
    const datos = req.body;

    const content = fs.readFileSync(path.resolve(__dirname, 'documents', 'Documento_sin_titulo.docx'), 'binary');
    const zip = new PizZip(content);
    const doc = new Docxtemplater(zip, { paragraphLoop: true, linebreaks: true });

    doc.setData(datos);

    try {
        doc.render();
    } catch (error) {
        return res.status(500).send(error);
    }

    const buffer = doc.getZip().generate({ type: 'nodebuffer' });
    const outputPath = path.resolve(__dirname, 'documents', 'PAO_generado.docx');
    fs.writeFileSync(outputPath, buffer);

    res.download(outputPath);
});

app.listen(3000, () => console.log('Servidor corriendo en puerto 3000'));
