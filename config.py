"""
Configuración global del Sistema de Digitalización y Auditoría de Vacunación (Muni 3F)
"""
import os
from pathlib import Path

# Directorios principales
DIR_PROYECTO = Path(__file__).resolve().parent
DIR_CERTIFICADOS = DIR_PROYECTO / "certificados_descargados"
DIR_RESULTADOS = DIR_PROYECTO / "resultados_auditoria"
DIR_FRONTEND = DIR_PROYECTO / "frontend"

DIR_CERTIFICADOS.mkdir(exist_ok=True, parents=True)
DIR_RESULTADOS.mkdir(exist_ok=True, parents=True)

# Base de datos SQLite local para persistencia y auditoría
DB_PATH = DIR_RESULTADOS / "vacunacion_jardines.sqlite"

# Archivo de padrón de inscripciones (Ficha Social / Mi3F)
PADRON_JARDINES_PATH = os.environ.get("PADRON_JARDINES_PATH")
if PADRON_JARDINES_PATH:
    PADRON_JARDINES_PATH = Path(PADRON_JARDINES_PATH)
else:
    PADRON_JARDINES_PATH = DIR_PROYECTO / "Inscripciones_Jardines_2026.xlsx"
    if not PADRON_JARDINES_PATH.exists():
        p1 = Path(r"C:\Users\Matias\Desktop\cruce informacion datos\Inscripciones_Jardines_2026.xlsx")
        p2 = Path(r"C:\Users\Matias\Desktop\INSCRIPCIONES JARDINES\Inscripciones_Jardines_2026.xlsx")
        if p1.exists():
            PADRON_JARDINES_PATH = p1
        elif p2.exists():
            PADRON_JARDINES_PATH = p2

# Credenciales y URLs del Backoffice Mi3F
URL_LOGIN = "https://backend.mistramites.tresdefebrero.gob.ar/"
URL_TRAMITE = "https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_unica_am.php?tramiteproductoracod={}"
URL_DOC_DOWNLOAD = "https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_am_documentos_download.php?codigo={}&seccion={}&tramiteproductora={}"

CUIL_DEFAULT = "27388808611"
PASSWORD_DEFAULT = "Municipalidad1234"

# Archivo de sesión compartida
ARCHIVO_SESION = os.environ.get("ARCHIVO_SESION")
if ARCHIVO_SESION:
    ARCHIVO_SESION = Path(ARCHIVO_SESION)
else:
    ARCHIVO_SESION = DIR_PROYECTO / "session_jardines.json"
    if not ARCHIVO_SESION.exists():
        p_ses = Path(r"C:\Users\Matias\Desktop\cruce informacion datos\conectores\session_jardines.json")
        if p_ses.exists():
            ARCHIVO_SESION = p_ses

# Configuración IA (Gemini Multimodal)
# La API key se obtiene de variables de entorno (en local vía entorno o en Render vía Environment Variables)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
MODELO_VISION = "gemini-2.5-flash"  # Rápido, económico y altamente preciso para OCR y visión estructurada
