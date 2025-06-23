
const express = require('express');
const Docxtemplater = require('docxtemplater');
const PizZip = require('pizzip');
const fs = require('fs');
const path = require('path');
const app = express();
app.use(express.json());

const ordenMateriasPorPAO = {
  "5": [
    "Tecnologías Web",
    "Base de Datos Avanzadas",
    "Comunicaciones y Enrutamiento",
    "Ética y Relaciones Humanas",
    "Interacción Hombre Máquina",
    "Derecho Informático"
  ]
};

app.post('/generar', (req, res) => {
  const datos = req.body;
  const paoID = datos.paoID;

  const ordenMaterias = ordenMateriasPorPAO[paoID];
  if (!ordenMaterias) return res.status(400).send('PAO no configurado');

  const aportaciones = datos.aportaciones || [];

  const resultadoFinal = { ...datos };

  ordenMaterias.forEach((materia, index) => {
    const aporte = aportaciones.find(a => a.materia === materia);
    resultadoFinal[`materia_${index+1}`] = materia;
    resultadoFinal[`problemas_${index+1}_m${index+1}`] = aporte ? aporte.problemas : '';
    resultadoFinal[`acciones_${index+1}_m${index+1}`] = aporte ? aporte.acciones : '';
    resultadoFinal[`responsables_${index+1}_m${index+1}`] = aporte ? aporte.responsables : '';
    resultadoFinal[`resultados_${index+1}_m${index+1}`] = aporte ? aporte.resultados : '';
  });

  const content = fs.readFileSync(path.resolve(__dirname, 'documents', 'Documento_sin_titulo.docx'), 'binary');
  const zip = new PizZip(content);
  const doc = new Docxtemplater(zip, { paragraphLoop: true, linebreaks: true });

  doc.setData(resultadoFinal);

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
