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

async function replacePdfIndraLogo(report) {
  const brand = typeof module !== "undefined" ? require("./report_brand.js") : globalThis.MaximoReportBrand;
  const { PDFRawStream, PDFName, PDFNumber, decodePDFRawStream } = PDFLib;
  const targets = [];
  for (const [ref, object] of report.context.enumerateIndirectObjects()) {
    if (!(object instanceof PDFRawStream) ||
        object.dict.get(PDFName.of("Subtype")) !== PDFName.of("Image")) continue;
    const width = object.dict.get(PDFName.of("Width"));
    const height = object.dict.get(PDFName.of("Height"));
    if (!(width instanceof PDFNumber) || !(height instanceof PDFNumber) ||
        width.asNumber() !== 304 || height.asNumber() !== 147) continue;
    try {
      if (brand.isLegacyLogo(304, 147, decodePDFRawStream(object).decode())) targets.push(ref);
    } catch (_) { /* Leave unknown image encodings untouched. */ }
  }
  if (!targets.length) return false;
  const image = await report.embedPng("data:image/png;base64," + brand.pngBase64);
  const relativeHeight = (image.height / image.width) / (147 / 304);
  // A unit-sized Form preserves the native image's bounding box and centring.
  for (const ref of targets) {
    const form = report.context.flateStream(
      `q\n1 0 0 ${relativeHeight} 0 ${(1 - relativeHeight) / 2} cm\n/IndraCurrent Do\nQ\n`,
      { Type: "XObject", Subtype: "Form", FormType: 1, BBox: [0, 0, 1, 1],
        Resources: { XObject: { IndraCurrent: image.ref } } }
    );
    report.context.assign(ref, form);
  }
  return true;
}

function nativeBirtTextPositions(report, page) {
  const contents = page.node.Contents();
  const streams = contents instanceof PDFLib.PDFArray ? contents.asArray() : [contents];
  const raw = streams.map(ref => repairPdfByteString(
    PDFLib.decodePDFRawStream(report.context.lookup(ref)).decode())).join("\n");
  const number = "[-+]?(?:\\d*\\.\\d+|\\d+)";
  const matrixPattern = new RegExp(
    "(" + number + ")\\s+(" + number + ")\\s+(" + number + ")\\s+(" + number + ")\\s+(" + number + ")\\s+(" + number + ")\\s+(cm|Tm)\\b", "g");
  const texts = [];
  for (const match of raw.matchAll(/(?:^|\n)BT\s*\n([\s\S]*?)\nET(?=\n|$)/g)) {
    const block = match[1];
    const text = block.match(/\(((?:\\[\s\S]|[^\\)])*)\)\s*Tj/);
    const hexText = block.match(/<([0-9a-f]+)>\s*Tj/i);
    const font = block.match(new RegExp("/[^\\s]+\\s+(" + number + ")\\s+Tf"));
    if ((!text && !hexText) || !font) continue;
    let x = 0, y = 0, supported = true;
    for (const matrix of block.matchAll(matrixPattern)) {
      if (Number(matrix[1]) !== 1 || Number(matrix[2]) !== 0 ||
          Number(matrix[3]) !== 0 || Number(matrix[4]) !== 1) { supported = false; break; }
      x += Number(matrix[5]); y += Number(matrix[6]);
    }
    if (!supported) continue;
    const decoded = hexText ? hexText[1].replace(/../g, pair => String.fromCharCode(parseInt(pair,16))) :
      text[1].replace(/\\([0-7]{1,3}|[\s\S])/g, (_, char) =>
      /^[0-7]+$/.test(char) ? String.fromCharCode(parseInt(char, 8)) :
        ({n:"\n",r:"\r",t:"\t",b:"\b",f:"\f"}[char] ?? char));
    texts.push({ text: decoded, x, y, size: Number(font[1]) });
  }
  return {raw, texts};
}

async function insertPdfOriginInEquipment(report, page, company) {
  const {raw, texts} = nativeBirtTextPositions(report, page);
  const normalize = text => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase();
  const unique = caption => {
    const found = texts.filter(item => normalize(item.text) === caption);
    return found.length === 1 ? found[0] : null;
  };
  const equipment = unique("datos del equipo"), order = unique("datos orden reparacion");
  const client = unique("cliente:");
  if (!equipment || !order || !client || !(equipment.y > client.y && client.y > order.y))
    throw new Error("No se pudo identificar «Datos del equipo» en el PDF de BIRT.");
  const value = texts.filter(item => Math.abs(item.y - client.y) < 1 && item.x > client.x + 20)
    .sort((a,b) => a.x - b.x)[0];
  if (!value || page.getRotation().angle !== 0)
    throw new Error("El formato de la tabla del PDF no permite insertar el origen con seguridad.");
  const {width,height} = page.getSize();
  const boundaries = [...raw.matchAll(/1 0 0 1 ([-\d.]+) ([-\d.]+) cm\s+0 0 m\s+([-\d.]+) 0 l/g)]
    .map(match => ({x:Number(match[1]),y:Number(match[2]),width:Number(match[3])}))
    .filter(line => line.y > order.y + order.size / 2 && line.y < client.y &&
      line.width > width / 2);
  if (boundaries.length !== 1)
    throw new Error("No se encontró el límite de la sección del equipo en el PDF.");
  const boundary = boundaries[0], cutoff = boundary.y, footerTop = 72;
  const regular = await report.embedFont(PDFLib.StandardFonts.Helvetica);
  const bold = await report.embedFont(PDFLib.StandardFonts.HelveticaBold);
  const maxWidth = boundary.x + boundary.width - value.x - 4;
  const longest = Math.max(...company.split(/\s+/).map(word => regular.widthOfTextAtSize(word, client.size)));
  const size = Math.min(client.size, client.size * maxWidth / Math.max(maxWidth, longest));
  const lineHeight = size + 3;
  const lines = PDFLib.breakTextIntoLines(company, [" "], maxWidth, line => regular.widthOfTextAtSize(line,size));
  const gap = Math.max(16, 6 + lines.length * lineHeight);
  const lowerText = texts.filter(item => item.y > footerTop && item.y < cutoff);
  if (!lowerText.length) throw new Error("No se reconoce el contenido de la reparación en el PDF.");
  const needsContinuation = Math.min(...lowerText.map(item => item.y)) - gap < footerTop + size;
  let split = footerTop;
  if (needsContinuation) {
    // Break at a native row border, not through a line of repair text. If the
    // section has no safe internal border, carry that whole section forward.
    const safeBorders = [...raw.matchAll(/1 0 0 1 ([-\d.]+) ([-\d.]+) cm\s+0 0 m\s+([-\d.]+) 0 l/g)]
      .map(match => ({y:Number(match[2]),width:Number(match[3])}))
      .filter(line => line.width > width / 2 && line.y >= footerTop + gap + size &&
        line.y < cutoff - size && !lowerText.some(item =>
          item.y - item.size / 3 < line.y && item.y + item.size > line.y))
      .sort((a,b) => a.y - b.y);
    split = safeBorders[0]?.y ?? cutoff;
  }
  // Preserve native text, font sizes and page size: only displace the body.
  const upper = await report.embedPage(page, {left:0,bottom:cutoff,right:width,top:height});
  const body = split < cutoff ? await report.embedPage(page,
    {left:0,bottom:split,right:width,top:cutoff}) : null;
  const footer = await report.embedPage(page, {left:0,bottom:0,right:width,top:footerTop});
  const result = report.insertPage(0, [width,height]);
  result.drawPage(upper, {x:0,y:cutoff});
  if (body) result.drawPage(body, {x:0,y:split-gap});
  result.drawPage(footer, {x:0,y:0});
  result.drawText("Origen:", {x:client.x,y:cutoff-size-3,size,font:bold});
  result.drawText(lines.join("\n"), {x:value.x,y:cutoff-size-3,size,lineHeight,font:regular});
  let continuation = null, continuationOffset = 0;
  if (needsContinuation) {
    const headerBottom = equipment.y + equipment.size + 8;
    const continuationTop = headerBottom - 12;
    continuationOffset = continuationTop - split;
    if (footerTop + continuationOffset < footerTop + size)
      throw new Error("El formato del PDF no permite continuar la reparación en otra página sin cortes.");
    const header = await report.embedPage(page,
      {left:0,bottom:headerBottom,right:width,top:height});
    const carried = await report.embedPage(page,
      {left:0,bottom:footerTop,right:width,top:split});
    continuation = report.insertPage(1,[width,height]);
    continuation.drawPage(header,{x:0,y:headerBottom});
    continuation.drawPage(carried,{x:0,y:footerTop+continuationOffset});
    continuation.drawPage(footer,{x:0,y:0});
  }
  for (const ref of page.node.Annots()?.asArray() || []) {
    const annotation = report.context.lookup(ref);
    const rect = annotation.get(PDFLib.PDFName.of("Rect"));
    let destination = result;
    if (rect instanceof PDFLib.PDFArray) {
      const bounds = rect.asArray().map(item => item.asNumber());
      if (bounds[1] >= footerTop && bounds[3] <= cutoff) {
        const carried = continuation && bounds[3] <= split;
        const offset = carried ? continuationOffset : -gap;
        if (carried) destination = continuation;
        bounds[1] += offset; bounds[3] += offset;
        annotation.set(PDFLib.PDFName.of("Rect"), report.context.obj(bounds));
        const points = annotation.get(PDFLib.PDFName.of("QuadPoints"));
        if (points instanceof PDFLib.PDFArray)
          annotation.set(PDFLib.PDFName.of("QuadPoints"), report.context.obj(
            points.asArray().map((point,index) => point.asNumber() + (index % 2 ? offset : 0))));
      }
    }
    annotation.set(PDFLib.PDFName.of("P"), destination.ref);
    destination.node.addAnnot(ref);
  }
  report.removePage(continuation ? 2 : 1);
  if (continuation) {
    // BIRT's footer still refers to its original page count. Update every
    // footer in this variant before the two Boixeres variants are combined.
    for (const [index,current] of report.getPages().entries()) {
      const currentWidth=current.getWidth();
      current.drawRectangle({x:currentWidth-98,y:55,width:64,height:18,color:PDFLib.rgb(1,1,1)});
      current.drawText(`${index+1} / ${report.getPageCount()}`,
        {x:currentWidth-76,y:62,size:7,font:regular});
    }
  }
}

async function prepareRepairPdf(bytes, company, options = {}) {
  const report = await PDFLib.PDFDocument.load(bytes, { updateMetadata: false });
  const [page] = report.getPages();
  if (!page) throw new Error("El parte PDF no contiene páginas.");
  const cleaned = options.cleanResources !== false && removePdfResourceNotices(report);
  const rebranded = options.replaceLogo !== false && await replacePdfIndraLogo(report);
  if (!company) return cleaned || rebranded ? report.save() : bytes;
  await insertPdfOriginInEquipment(report, page, company);
  return report.save();
}

if(typeof module!=="undefined")module.exports={repairPdfBase64,mergeRepairPdfs,prepareRepairPdf};
