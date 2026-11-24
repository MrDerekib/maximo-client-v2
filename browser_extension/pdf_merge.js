/* Process the native BIRT PDFs locally. */
"use strict";
const { BIRT_RESOURCE_NOTICE } = typeof module !== "undefined"
  ? require("./workflow_logic.js") : globalThis.MaximoPartLogic;

function repairPdfByteString(bytes) {
  let binary="";
  for(let offset=0;offset<bytes.length;offset+=32768)
    binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
  return binary;
}
function repairPdfBase64(bytes) {
  return btoa(repairPdfByteString(bytes));
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

function removePdfResourceNotices(report) {
  const { PDFArray, PDFName, PDFRawStream, PDFRef, decodePDFRawStream } = PDFLib;
  const contentsName = PDFName.of("Contents");
  const subtype = PDFName.of("Subtype");
  const form = PDFName.of("Form");
  const streams = new Set();
  for (const page of report.getPages()) {
    const contents = page.node.Contents();
    if (contents instanceof PDFArray) {
      for (const ref of contents.asArray()) streams.add(ref);
    } else if (contents instanceof PDFRawStream) {
      streams.add(page.node.get(contentsName));
    }
  }
  for (const [ref, object] of report.context.enumerateIndirectObjects()) {
    if (object instanceof PDFRawStream && object.dict.get(subtype) === form) streams.add(ref);
  }

  const literal = BIRT_RESOURCE_NOTICE.replace(".", "\\.");
  const hex = [...BIRT_RESOURCE_NOTICE].map(char => char.charCodeAt(0).toString(16)).join("");
  // Match a complete text-painting operation, never a substring of report data.
  const operation = new RegExp(
    "^[\\t ]*(?:\\(" + literal + "\\)|<" + hex + ">)[\\t ]*Tj[\\t ]*(?=\\r?$)", "gim"
  );
  let changed = false;
  for (const ref of streams) {
    if (!(ref instanceof PDFRef)) continue;
    const stream = report.context.lookup(ref);
    if (!(stream instanceof PDFRawStream)) continue;
    const contents = repairPdfByteString(decodePDFRawStream(stream).decode());
    const cleaned = contents.replace(operation, "() Tj");
    if (cleaned === contents) continue;

    const encoded = report.context.flateStream(Uint8Array.from(cleaned, char => char.charCodeAt(0)));
    const dict = stream.dict.clone(report.context);
    dict.set(PDFName.of("Filter"), PDFName.of("FlateDecode"));
    dict.delete(PDFName.of("DecodeParms"));
    report.context.assign(ref, PDFRawStream.of(dict, encoded.getContents()));
    changed = true;
  }
  return changed;
}

async function prepareRepairPdf(bytes, company) {
  const report = await PDFLib.PDFDocument.load(bytes, { updateMetadata: false });
  const [page] = report.getPages();
  if (!page) throw new Error("El parte PDF no contiene páginas.");
  const cleaned = removePdfResourceNotices(report);
  if (!company) return cleaned ? report.save() : bytes;
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

if(typeof module!=="undefined")module.exports={repairPdfBase64,mergeRepairPdfs,prepareRepairPdf};
