const express = require('express');
const cors = require('cors');
const admin = require('firebase-admin');
const { Storage } = require('@google-cloud/storage');
const { readFileSync, writeFileSync, unlinkSync } = require('fs');
const { v4: uuidv4 } = require('uuid');
const { Document } = require('docxtemplater');
const PizZip = require('pizzip');
const path = require('path');
const docxConverter = require('docx-pdf');
const serviceAccount = require('./serviceAccountKey.json');

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: "<academico-4a053.appspot.com>"
});
const db = admin.firestore();
const bucket = admin.storage().bucket();

const app = express();
app.use(cors());
app.use(express.json());

app.post('/generar_informe_final', async (req, res) => {
  const { paoID, tutor, conclusiones, recomendaciones, fecha_presentacion } = req.body;

  try {
    const actividadesSnap = await db.collection('reportesPAO')
      .doc(paoID)
      .collection('actividades')
      .where('estado', '==', 'aprobado')
      .get();

    const actividades = {};
    actividadesSnap.forEach(doc => {
      const data = doc.data();
      const tipo = data.tipoActividad || 'otros';
      if (!actividades[tipo]) actividades[tipo] = [];
      actividades[tipo].push(data);
    });

    const content = readFileSync(path.join(__dirname, 'PAO5_TI_FORMATO_2_template_FINAL.docx'), 'binary');
    const zip = new PizZip(content);
    const doc = new Document(zip, { paragraphLoop: true, linebreaks: true });

    doc.render({
      facultad: "FACULTAD DE INFORMÁTICA Y ELECTRÓNICA",
      carrera: "TECNOLOGÍAS DE LA INFORMACIÓN",
      pao: paoID,
      paralelo: "A",  // Puede hacerse dinámico si lo guardas en Firestore
      tutor,
      fecha_presentacion,
      elaborado_por: tutor,
      aprobado_por: "Coordinador/a de Carrera",
      conclusiones,
      recomendaciones,
      actividades: Object.entries(actividades).flatMap(([tipo, acts]) =>
        acts.map(act => ({
          tipo,
          fecha: act.fecha.split('T')[0],
          materia: act.materia,
          descripcion: tipo,
          problemas: act.problemas,
          acciones: act.acciones,
          responsables: act.responsables,
          resultados: act.resultados,
        }))
      )
    });

    const buf = doc.getZip().generate({ type: 'nodebuffer' });
    const docxPath = path.join(__dirname, `${paoID}.docx`);
    const pdfPath = path.join(__dirname, `${paoID}.pdf`);
    writeFileSync(docxPath, buf);

    await new Promise((resolve, reject) => {
      docxConverter(docxPath, pdfPath, (err, result) => {
        if (err) reject(err);
        else resolve(result);
      });
    });

    const uuid = uuidv4();
    await bucket.upload(pdfPath, {
      destination: `informes_finales/${paoID}/informe_final_${paoID}.pdf`,
      metadata: {
        metadata: {
          firebaseStorageDownloadTokens: uuid,
        },
      },
    });

    const url = `https://firebasestorage.googleapis.com/v0/b/${bucket.name}/o/${encodeURIComponent("informes_finales/" + paoID + "/informe_final_" + paoID + ".pdf")}?alt=media&token=${uuid}`;

    await db.collection("reportesPAO").doc(paoID).update({
      informeFinal: url
    });

    unlinkSync(docxPath);
    unlinkSync(pdfPath);

    res.json({ url });
  } catch (error) {
    console.error(error);
    res.status(500).send("Error al generar informe");
  }
});

app.listen(3000, () => console.log("Servidor corriendo en puerto 3000"));
