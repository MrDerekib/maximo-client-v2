import http from 'node:http';
import https from 'node:https';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(fileURLToPath(new URL('./public/',import.meta.url)));
const types={'.html':'text/html; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png'};
const demo=process.argv.includes('--http');
const port=demo?3001:3000;
function handler(req,res) {
  // No request bodies or mail data are accepted or logged. Only public assets are served.
  if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
  try {
    const requestPath=decodeURIComponent(new URL(req.url,'https://localhost').pathname);
    const file=path.resolve(root,'.'+(requestPath==='/'?'/taskpane.html':requestPath));
    if(!file.startsWith(root+path.sep) && file!==path.join(root,'taskpane.html')) throw Error();
    const ext=path.extname(file);
    if(!types[ext]) throw Error();
    const data=readFileSync(file);
    res.writeHead(200,{'Content-Type':types[ext],'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'});
    res.end(req.method==='HEAD'?undefined:data);
  }catch{res.writeHead(404);res.end('No encontrado');}
}
let server;
try {
 server=demo?http.createServer(handler):https.createServer({pfx:readFileSync(new URL('./.local/localhost.pfx',import.meta.url)),passphrase:readFileSync(new URL('./.local/password.txt',import.meta.url),'utf8').trim()},handler);
}catch{console.error('Falta el certificado local. Ejecuta primero Start-Mvp.ps1.');process.exit(1);}
server.on('error',error=>{console.error(error.code==='EADDRINUSE'?'El puerto ya está ocupado. Cierra la otra instancia.':error.message);process.exitCode=1;});
server.listen(port,'127.0.0.1',()=>console.log(`MVP disponible en ${demo?'http':'https'}://localhost:${port}/taskpane.html${demo?'?demo=1':''}\nMantén esta ventana abierta. Ctrl+C para detener.`));
