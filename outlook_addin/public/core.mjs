export const MAXIMO = 'https://eam.indraweb.net/maximo/ui/';
export function validOt(value) { return /^\d{1,20}$/.test(String(value)); }
export function linksFor(ot, development = false) {
  if (!validOt(ot)) throw new Error('Introduce un número de OT válido.');
  const url = new URL(MAXIMO);
  url.search = new URLSearchParams({event:'loadapp', value:'wo_tr', additionalevent:'sqlwhere',
    additionaleventvalue:`wonum='${ot}' and siteid='LAB-BAD'`});
  return {web:url.href, md:`${development ? 'maximodesk-dev' : 'maximodesk'}://ot/${ot}`};
}
export function detectOts(text, hrefs = []) {
  const found = new Set();
  const contextual = /\b(?:orden\s+de\s+trabajo|OT)\s*(?:n[úuº°.]*(?:mero)?\s*)?[:#\-]?\s*['"‘’]?\s*(\d{1,20})(?!\d)/giu;
  for (const match of String(text).matchAll(contextual)) found.add(match[1]);
  const rawUrls = String(text).match(/https:\/\/eam\.indraweb\.net\/maximo\/[^\s<>"\]]+/gi) || [];
  for (const href of [...hrefs, ...rawUrls]) {
    try {
      const url = new URL(href);
      if (url.origin !== 'https://eam.indraweb.net' || !url.pathname.startsWith('/maximo/')) continue;
      // workorderid and uniqueid are internal identifiers, never visible OT numbers.
      for (const value of [url.searchParams.get('additionaleventvalue'), url.searchParams.get('sqlwhere')]) {
        for (const match of String(value || '').matchAll(/\bwonum\s*=\s*['"]?(\d{1,20})(?!\d)/gi)) found.add(match[1]);
      }
    } catch { /* Unrelated or malformed links cannot become launch destinations. */ }
  }
  return [...found];
}
export function mailParts(html, subject = '') {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('script,style').forEach(node => node.remove());
  doc.querySelectorAll('br,p,div,tr').forEach(node => node.append(doc.createTextNode('\n')));
  return detectOts(subject + '\n' + doc.body.textContent,
    [...doc.querySelectorAll('a[href]')].map(a => a.getAttribute('href')));
}
