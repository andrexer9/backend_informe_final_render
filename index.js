import express from 'express';
import cors from 'cors';
import admin from 'firebase-admin';
import { readFileSync, writeFileSync, unlinkSync } from 'fs';
import { v4 as uuidv4 } from 'uuid';
import { Document } from 'docxtemplater';
import PizZip from 'pizzip';
import path from 'path';
import fetch from 'node-fetch';
import dotenv from 'dotenv';
dotenv.config();

const serviceAccount = JSON.parse(process.env.GOOGLE_CREDENTIALS);

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: "academico-4a053.appspot.com"
});

const db = admin.firestore();
const bucket = admin.storage().bucket();
const app = express();
app.use(cors());
app.use(express.json());

app.get('/', (req, res) => {
  res.send('Servidor CloudConvert operativo');
});

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

    const content = readFileSync(path.join(path.resolve(), 'PAO5_TI_FORMATO_2_template_FINAL.docx'), 'binary');
    const zip = new PizZip(content);
    const doc = new Document(zip, { paragraphLoop: true, linebreaks: true });

    doc.render({
      facultad: "FACULTAD DE INFORMÁTICA Y ELECTRÓNICA",
      carrera: "TECNOLOGÍAS DE LA INFORMACIÓN",
      pao: paoID,
      paralelo: "A",
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

    const buffer = doc.getZip().generate({ type: 'nodebuffer' });
    const docxPath = `./${paoID}.docx`;
    const pdfPath = `./${paoID}.pdf`;
    writeFileSync(docxPath, buffer);

    // CloudConvert: docx -> pdf
    const convertRes = await fetch("https://api.cloudconvert.com/v2/convert", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.CLOUDCONVERT_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        input_format: "docx",
        output_format: "pdf",
        engine: "office",
        input: "upload",
        file: buffer.toString("base64"),
        filename: `${paoID}.docx`
      })
    });

    const convertJson = await convertRes.json();
    if (!convertJson.data || !convertJson.data.url) throw new Error("CloudConvert failed");

    const pdfBuffer = await fetch(convertJson.data.url).then(res => res.arrayBuffer());
    writeFileSync(pdfPath, Buffer.from(pdfBuffer));

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

    await db.collection("reportesPAO").doc(paoID).update({ informeFinal: url });

    unlinkSync(docxPath);
    unlinkSync(pdfPath);

    res.json({ url });
  } catch (e) {
    console.error(e);
    res.status(500).send("Error generando el informe");
  }
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log("Servidor corriendo en puerto", port));
