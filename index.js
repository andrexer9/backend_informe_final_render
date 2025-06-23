
const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const admin = require('firebase-admin');
const { Storage } = require('@google-cloud/storage');
const PizZip = require('pizzip');
const Docxtemplater = require('docxtemplater');

const serviceAccount = require('./service_account.json');

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: 'academico-4a053.appspot.com',
});

const db = admin.firestore();
const bucket = admin.storage().bucket();

const app = express();
app.use(cors());
app.use(express.json());

app.post('/generar', async (req, res) => {
  try {
    const { paoID, tutor } = req.body;

    if (!paoID || !tutor) {
      return res.status(400).json({ error: 'Faltan parámetros paoID o tutor' });
    }

    // Obtener las actividades de Firestore
    const actividadesSnapshot = await db.collection('pao_actividades').orderBy('orden').get();

    const actividades = [];
    for (const actividadDoc of actividadesSnapshot.docs) {
      const actividadData = actividadDoc.data();
      const aportesSnapshot = await actividadDoc.ref.collection('aportaciones_docentes').get();

      const problemas = [];
      const acciones = [];
      const resultados = [];

      aportesSnapshot.forEach(aporteDoc => {
        const aporte = aporteDoc.data();
        problemas.push(`${aporte.materia}: ${aporte.problemas}`);
        acciones.push(`${aporte.materia}: ${aporte.acciones}`);
        resultados.push(`${aporte.materia}: ${aporte.resultados}`);
      });

      actividades.push({
        fecha: actividadData.fecha || new Date().toLocaleDateString(),
        actividad: actividadData.actividad || 'Sin actividad',
        problemas: problemas.join('\n'),
        acciones: acciones.join('\n'),
        resultados: resultados.join('\n'),
      });
    }

    // Cargar plantilla
    const templatePath = path.join(__dirname, 'documents', 'Documento_sin_titulo.docx');
    const content = fs.readFileSync(templatePath, 'binary');
    const zip = new PizZip(content);
    const doc = new Docxtemplater(zip, { paragraphLoop: true, linebreaks: true });

    // Preparar datos
    doc.setData({
      pao: paoID,
      tutor,
      actividades,
    });

    doc.render();
    const buffer = doc.getZip().generate({ type: 'nodebuffer' });

    // Guardar en Storage
    const filename = `documentos_pao/PAO_${Date.now()}.docx`;
    const file = bucket.file(filename);
    await file.save(buffer, {
      metadata: { contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
    });

    const url = `https://storage.googleapis.com/${bucket.name}/${filename}`;
    res.json({ url });
    
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Error al generar el documento' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Servidor corriendo en puerto ${PORT}`));
