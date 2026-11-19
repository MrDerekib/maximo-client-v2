# Maximo Desktop · MVP para Outlook

Prototipo separado de la build de MD. No forma parte de la release 1.4.1.
Un panel lee el correo seleccionado y ofrece dos rutas de apertura de la OT.

## Qué permite probar

- Reconocer `La orden de trabajo: '4448382 '` o `OT 4448382` en el mensaje/asunto.
- Leer el WONUM de enlaces filtrados de Maximo. Nunca tratar `workorderid` o
  `uniqueid` como el número visible de OT.
- Elegir entre varias OTs detectadas en un hilo o introducir una manualmente.
- **Abrir en Maximo:** enlace HTTPS por OT y planta LAB-BAD. Resultado verificado:
  listado con una sola OT; requiere pulsar la fila para abrir su ficha.
- **Abrir con MD:** enlace `maximodesk://ot/…`, o `maximodesk-dev://ot/…`
  al activar la opción de desarrollo. Su aceptación por Outlook está pendiente
  de validación real. No se registra éxito solo por pulsar el botón.
- Enlace alternativo a una página local que permite pedir la apertura de MD desde
  el navegador, con la opción web disponible si MD no abre.
- Panel fijable que limpia la OT al cambiar de mensaje y descarta respuestas
  tardías; no abre nada automáticamente.

El contenido del mensaje se analiza en el cliente. No se guarda ni se envía al
servidor. No se necesitan Graph, credenciales de Maximo ni permisos de escritura.
El servidor solo entrega archivos estáticos; no acepta mensajes ni lanza procesos.
Los enlaces se construyen con destino fijo y número exclusivamente numérico.

## Opciones al abrir con MD

El selector conserva en este cliente la última elección: abrir Edge (predeterminado),
abrir Edge y filtrar MD, o solo filtrar MD. El modo se conserva también al pasar
por la página del navegador. El enlace web sigue funcionando igual.

Los modos de filtrado requieren el MD de desarrollo con estos cambios; la build
1.4.1 publicada todavía no los interpreta y abriría Edge. Para validarlos, reiniciar
MD de desarrollo y marcar «Usar MD de desarrollo» en el panel. El lanzador de
MD de desarrollo pide cerrar primero la instalación estable si está ejecutándose.

Al filtrar se limpian filtros previos, prioridades y selecciones para mostrar solo
la OT exacta. No se modifican búsquedas guardadas ni datos de Maximo. Si la OT no
está en la base local, se informa y el listado queda vacío; «solo filtrar» no
consulta Maximo ni necesita credenciales. Se puede volver al listado con Limpiar.

## 1. Prueba visual sin instalar nada en Outlook

Requiere Node.js en PATH o el runtime de Node incluido en la instalación de Codex. El lanzador intenta ambos, incluidas las instalaciones de Codex cuyo runtime tiene un nombre con versión. Si fuera necesario, acepta `-NodePath` con la ruta del ejecutable. `Start-Mvp.ps1 -CheckRuntime` comprueba la detección sin arrancar el servidor ni instalar certificados. No requiere `npm install`.

En PowerShell, desde esta carpeta:

```powershell
.\Start-Mvp.ps1 -Demo
```

Abre `http://localhost:3001/taskpane.html?demo=1`. Puedes pegar el cuerpo HTML
o texto de un correo en el área de prueba. La demo no conecta con Outlook.
Los botones sí abren los destinos reales cuando los pulsas, únicamente para
consultar la OT. No ejecutan operaciones de negocio.

## 2. Preparar HTTPS para Outlook

Office exige HTTPS incluso para localhost. El siguiente comando crea un
certificado de desarrollo de 30 días, lo exporta a `.local` y lo incorpora al
almacén de confianza **del usuario actual**. Solo ejecutar si aceptas confiar
este certificado de prueba; no requiere cambiar certificados corporativos.

```powershell
.\Start-Mvp.ps1 -TrustCertificate
```

Mantén abierta esa consola. En siguientes usos basta con `.\Start-Mvp.ps1`.
Comprueba que `https://localhost:3000/taskpane.html?demo=1` abre sin advertencia
de certificado antes de instalar el manifiesto. Si la política corporativa
impide confiar certificados o conectar a localhost, el siguiente paso es alojar
los mismos archivos en un HTTPS corporativo autorizado y ajustar el manifiesto;
no se debe desactivar la validación HTTPS.

Los archivos privados de `.local` están excluidos de Git y fuera de la carpeta
servida. No compartirlos. No se ha instalado ningún certificado automáticamente
durante la preparación del MVP.

## 3. Instalar solo para la prueba

1. Con la misma cuenta de Microsoft 365 que usas en Outlook, abre
   <https://aka.ms/olksideload>.
2. En los complementos personalizados, elige **Agregar desde archivo** y selecciona
   `manifest.xml` de esta carpeta. Los nombres pueden variar según el cliente.
3. Si tu organización no permite complementos personalizados, será necesaria
   una instalación de prueba por el administrador; no es un fallo del parser.
4. Abre un correo de Maximo. En Aplicaciones/Complementos de Outlook busca
   **Maximo · Abrir OT** y abre el panel. Puede fijarse mediante la chincheta.
5. Primero prueba **Abrir en Maximo**. Después **Abrir con MD**, con MD abierto
   y cerrado. MD debe estar instalado y haberse ejecutado al menos una vez para
   registrar su protocolo. El MVP no modifica su registro ni las credenciales.

No hay soporte de móviles en este manifiesto. Deben comprobarse por separado
Outlook clásico, nuevo Outlook y web en el equipo de prueba; la documentación
de esas plataformas no sustituye la validación del cliente corporativo.

## Recorrido de aceptación

| Prueba | Resultado esperado |
| --- | --- |
| Correo de la OT 4448382 con `workorderid=4483953` | Detecta 4448382, nunca 4483953 |
| Cambiar a otro correo mientras se lee el anterior | No quedan enlaces a la OT anterior |
| Correo sin OT o con varias OTs | Campo manual o elección explícita; no abre nada |
| Abrir en Maximo sin sesión | Login y listado filtrado de la OT |
| Abrir MD abierto / cerrado | Entrega a la instancia o arranque; registrar avisos/bloqueos |
| MD no instalado o protocolo bloqueado | No afirmar éxito; alternativa web visible |
| Abrir mediante navegador | Página local y clic explícito para abrir MD |

Para reportar un fallo anotar cliente de Outlook, versión, botón utilizado y
mensaje visible. No es necesario enviar el cuerpo del correo ni credenciales.

## Pruebas locales y retirada

```powershell
node --test tests/core.test.mjs
# Opcional, con el servidor demo arrancado y Selenium/lxml disponibles:
..\.venv\Scripts\python.exe tests/browser_smoke.py
```

Para retirar el MVP: quitar el complemento desde Outlook y detener la consola
con Ctrl+C. Para retirar únicamente su certificado y archivos locales:

```powershell
.\Remove-DevCertificate.ps1
```

## Documentación de referencia

- [Instalar un complemento de Outlook para pruebas](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/sideload-outlook-add-ins-for-testing).
- [Panel fijable y cambio de mensaje](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/pinnable-taskpane).
- [Permisos de Outlook](https://learn.microsoft.com/en-us/outlook/add-ins/understanding-outlook-add-in-permissions).
- [Requisito HTTPS de Office Add-ins](https://learn.microsoft.com/en-us/outlook/add-ins/quick-start?tabs=yeomangenerator).
