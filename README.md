# Maximo Desktop

Cliente de escritorio para **IBM Maximo** orientado a la **consulta, actualización y seguimiento de órdenes de trabajo (OT)** en reparación, con base de datos local y actualización automática.

Es una herramienta **interna de productividad**, diseñada para simplificar el acceso a la información de Maximo y reducir fricciones con la web.

---

## 🧩 Funcionalidades principales

- 🔐 Gestión y comprobación de credenciales de IBM Maximo desde la GUI
- 📥 Descarga automática del listado de OT desde Maximo (vía Selenium)
- 🗃️ Almacenamiento local en base de datos SQLite
- 🔄 Actualización manual y automática en segundo plano
- 📊 Visualización, filtrado y búsqueda de OTs
- 🔗 Apertura directa de una OT en Maximo desde la aplicación
- 📝 Sistema de logs para diagnóstico y soporte
- 💾 Persistencia de configuración y estado

---

## 🛠️ Tecnologías utilizadas

### Backend / Core
- **Python 3.14.1**
- **SQLite** (base de datos local)
- **Pandas** (procesado del archivo descargado)
- **lxml** (parseo del contenido HTML/XLS)
- **logging** (sistema de logs)

### Automatización
- **Selenium**
- **Microsoft Edge (Chromium)**
- Ejecución normal y *headless*

### Interfaz gráfica
- **Tkinter / ttk**
- Arquitectura preparada para migración futura a **CustomTkinter**

### Empaquetado
- **Nuitka**
- Build *one-folder* (standalone, sin dependencias externas)

---

## 🧱 Estructura del proyecto

```text
maximo-client-v2/
│
├── gui_main.py       # Punto de entrada (GUI principal)
├── maximo_client.py  # Lógica de interacción con Maximo (Selenium)
├── updater.py        # Actualización de base de datos
├── db.py             # Acceso a SQLite
├── config.py         # Configuración y migración de datos
├── app_paths.py      # Árbol de rutas persistentes
├── credential_store.py # Credenciales protegidas con Windows DPAPI
├── version.py        # Versión de la aplicación
│
├── dist/              # Builds generados por Nuitka (no versionado)
├── requirements.txt
└── README.md
```



---

## ⚙️ Flujo de funcionamiento

1. El usuario configura sus credenciales de Maximo en la GUI
2. La aplicación:
   - inicia sesión en Maximo
   - navega a la sección de seguimiento de OT
   - aplica filtros predefinidos
   - descarga el listado en formato `.xls` (HTML)
3. El archivo se procesa con Pandas y se sincroniza con la base de datos
4. Solo se insertan o actualizan OTs nuevas/modificadas
5. El usuario visualiza y filtra los datos localmente
6. Al hacer doble clic sobre una OT, se abre directamente en Maximo

---

## 🔄 Actualización automática

- Puede configurarse desde la GUI
- Se ejecuta en segundo plano mientras la aplicación está abierta
- Intervalo configurable (en minutos)
- Feedback visual en la barra de estado
- En caso de error:
  - se notifica al usuario
  - se conserva la última actualización correcta

---

## 📂 Rutas y persistencia

Los datos se separan del programa en `%LOCALAPPDATA%\MaximoDesktop`. La pestaña
**Configuración** muestra las rutas efectivas y permite abrir la carpeta principal.

```text
MaximoDesktop/
├── config/     # configuración y credenciales protegidas con Windows DPAPI
├── data/       # SQLite y perfiles de búsqueda
├── backups/    # copias de seguridad de SQLite
├── logs/       # logs rotatorios
├── cache/
│   ├── downloads/ # descarga aislada usada por Edge/Selenium
│   ├── exports/   # XLS procesados y sujetos a limpieza
│   ├── edge-profiles/ # perfiles temporales aislados de Edge
│   └── updates/
└── custom/     # opciones locales de seguimiento
```

En el primer arranque de esta versión se copia y verifica la base de datos
anterior. Los datos originales se conservan para recuperación.

---

## 📝 Logs

Se genera un archivo de log con distintos niveles:

- `INFO`: flujo normal de la aplicación
- `WARNING`: situaciones no críticas
- `ERROR`: errores de ejecución

Los logs permiten:
- diagnóstico de errores
- soporte a usuarios
- análisis de problemas en producción

---

## 🚀 Distribución

La aplicación se distribuye como **ejecutable Windows standalone**:

- Generado con **Nuitka**
- No requiere Python instalado
- Incluye todas las dependencias necesarias
- Se distribuye como ZIP / 7z desde GitHub Releases

---

## 📦 Requisitos para desarrollo

- Python 3.14.1
- Microsoft Edge
- Edge WebDriver compatible
- Entorno virtual recomendado

Instalación de dependencias:

```bash
pip install -r requirements.txt
```

Compilación para distribución:

```powershell
.\build_app.ps1
```

El resultado se crea en `release\MaximoDesktop-<versión>\*.dist`. Distribuye
la carpeta `.dist` completa; contiene el ejecutable y sus dependencias.
---
## 🧪 Estado del proyecto

- ✔️ Funcional y estable para uso interno
- 🔄 En evolución
- 🎨 Migración futura a CustomTkinter (mejora visual)
- 🔔 Posible sistema de auto-actualización desde GitHub Releases

---

## 📄 Licencia

Uso interno / privado.  
No destinado a distribución pública.

---

## 👤 Autor: Joan Camps

Proyecto desarrollado como herramienta interna de mejora de productividad.
