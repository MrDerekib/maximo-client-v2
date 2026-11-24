/* Merge the two native BIRT PDFs locally; never convert the HTML report. */
"use strict";
function repairPdfBase64(bytes) {
  let binary="";
  for(let offset=0;offset<bytes.length;offset+=32768)
    binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
  return btoa(binary);
}
async function mergeRepairPdfs(parts) {
  if(parts.length!==2)throw new Error("Faltan las dos variantes PDF del parte.");
  const merged=await PDFLib.PDFDocument.create();
  for(const bytes of parts){
    const source=await PDFLib.PDFDocument.load(bytes);
    if(!source.getPageCount())throw new Error("Una variante del parte no contiene páginas.");
    const pages=await merged.copyPages(source,source.getPageIndices());
    for(const page of pages)merged.addPage(page);
  }
  return merged.saveAsBase64({dataUri:true});
}

async function addRepairPdfOrigin(bytes, company) {
  const report = await PDFLib.PDFDocument.load(bytes);
  const [page] = report.getPages();
  if (!page) throw new Error("El parte PDF no contiene páginas.");
  const font = await report.embedFont(PDFLib.StandardFonts.HelveticaBold);
  const { width, height } = page.getSize();
  const text = "Empresa / Ubicación inicial: " + company;
  const left = 32;
  const lineHeight = 13;
  const maxWidth = width - 2 * left;
  const widestWord = Math.max(...text.split(" ").map(word => font.widthOfTextAtSize(word, 10)));
  const size = Math.min(10, 10 * maxWidth / widestWord);
  const lines = PDFLib.breakTextIntoLines(text, [" "], maxWidth, line => font.widthOfTextAtSize(line, size));
  // Reserve a band above the original content while preserving the page size.
  const top = 16;
  const band = top + lines.length * lineHeight + 6;
  const scale = (height - band) / height;
  if (scale <= 0) throw new Error("No hay espacio para añadir la empresa de origen al PDF.");
  page.scaleContent(scale, scale);
  page.scaleAnnotations(scale, scale);
  page.drawText(lines.join("\n"), { x: left, y: height - top - size, size, lineHeight, font });
  return report.save();
}

if(typeof module!=="undefined")module.exports={repairPdfBase64,mergeRepairPdfs,addRepairPdfOrigin};
