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
if(typeof module!=="undefined")module.exports={repairPdfBase64,mergeRepairPdfs};
