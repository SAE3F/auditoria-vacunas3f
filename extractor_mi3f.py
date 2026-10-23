"""
Extractor y Sincronizador de Certificados de Vacunación desde Mi3F (Muni 3F).
Descarga de forma selectiva y optimizada los archivos adjuntos del trámite.
"""
import os
import re
import json
import time
import urllib3
import requests
import sqlite3
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Any

from config import (
    DIR_CERTIFICADOS, DB_PATH, PADRON_JARDINES_PATH,
    URL_LOGIN, URL_TRAMITE, URL_DOC_DOWNLOAD, ARCHIVO_SESION,
    CUIL_DEFAULT, PASSWORD_DEFAULT, MI3F_PHPSESSID
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def inicializar_bd():
    """Crea las tablas necesarias en SQLite para el seguimiento de la digitalización."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Tabla de expedientes/inscriptos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inscriptos (
                codigo_tramite TEXT PRIMARY KEY,
                id_tramite TEXT,
                dni_menor TEXT,
                nombre_menor TEXT,
                apellido_menor TEXT,
                fecha_nacimiento TEXT,
                genero TEXT,
                jardin TEXT,
                sala TEXT,
                turno TEXT,
                estado_tramite TEXT,
                cant_archivos_vacuna INTEGER DEFAULT 0,
                estado_descarga TEXT DEFAULT 'PENDIENTE',
                fecha_descarga TEXT
            )
        """)
        
        # Tabla de archivos físicos descargados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archivos_certificados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_tramite TEXT,
                codigo_doc TEXT,
                seccion TEXT,
                nombre_archivo TEXT,
                ruta_local TEXT,
                tamano_bytes INTEGER,
                content_type TEXT,
                fecha_descarga TEXT,
                FOREIGN KEY (codigo_tramite) REFERENCES inscriptos(codigo_tramite)
            )
        """)
        
        # Tabla de auditoría IA y validación clínica
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_vacunas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_tramite TEXT UNIQUE,
                dni_menor TEXT,
                edad_meses INTEGER,
                calidad_imagen TEXT,           -- 'ALTA', 'MEDIA', 'BAJA', 'INVALIDA'
                estado_esquema TEXT,           -- 'AL_DIA', 'INCOMPLETO', 'REVISION_REQUERIDA'
                requiere_revision_humana INTEGER DEFAULT 0, -- 1 o 0
                motivo_revision TEXT,
                vacunas_detectadas_json TEXT,  -- Array de vacunas con fecha y lote
                vacunas_faltantes_json TEXT,   -- Array de vacunas obligatorias no encontradas
                observaciones_ia TEXT,
                revisado_por_humano INTEGER DEFAULT 0,
                fecha_analisis TEXT,
                usuario_revisor TEXT,
                fecha_revision_humana TEXT,
                FOREIGN KEY (codigo_tramite) REFERENCES inscriptos(codigo_tramite)
            )
        """)
        conn.commit()

def obtener_sesion_requests() -> requests.Session:
    """Crea una sesión de Requests reutilizando las cookies activas de Mi3F."""
    session = requests.Session()
    # Deshabilitar herencia de proxies locales en la sesión para evitar bloqueos
    session.trust_env = False
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": URL_LOGIN,
        "Connection": "keep-alive"
    })
    
    # 1. Prioridad: Variable de entorno en la nube (Render) o cookie configurada
    phpsessid = MI3F_PHPSESSID or os.environ.get("MI3F_PHPSESSID")
    if phpsessid:
        phpsessid = phpsessid.strip()
        session.headers["Cookie"] = f"PHPSESSID={phpsessid}"
        session.cookies.set("PHPSESSID", phpsessid)
        return session

    # 2. Archivo de sesión local
    if ARCHIVO_SESION and Path(ARCHIVO_SESION).exists():
        try:
            with open(ARCHIVO_SESION, "r", encoding="utf-8") as f:
                data = json.load(f)
            session.headers.update({"User-Agent": data.get("user_agent", "Mozilla/5.0")})
            cookie_strs = []
            for cookie in data.get("cookies", []):
                session.cookies.set(cookie["name"], cookie["value"])
                cookie_strs.append(f"{cookie['name']}={cookie['value']}")
            if cookie_strs:
                session.headers["Cookie"] = "; ".join(cookie_strs)
            return session
        except Exception:
            pass

    # Si estamos en un servidor sin display ni Chrome (como Render), NO ejecutar Selenium para evitar timeout
    if os.environ.get("RENDER") or not os.name == "nt":
        return session
            
    # Si estamos en local y la sesión no es válida, autenticar con Selenium
    try:
        return autenticar_selenium()
    except Exception as e:
        print(f"Aviso autenticacion Selenium no disponible: {e}")
        return session

def autenticar_selenium() -> requests.Session:
    """Inicia sesión automatizada en SSO Tres de Febrero y guarda cookies."""
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)
    try:
        driver.get(URL_LOGIN)
        campo_usuario = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//input[@name='cuil' or @type='number' or contains(@placeholder, 'CUIL')]")
        ))
        campo_usuario.clear()
        campo_usuario.send_keys(CUIL_DEFAULT)

        campo_pass = driver.find_element(By.XPATH, "//input[@type='password']")
        campo_pass.clear()
        campo_pass.send_keys(PASSWORD_DEFAULT)
        campo_pass.send_keys(Keys.RETURN)

        time.sleep(8)
        cookies = driver.get_cookies()
        user_agent = driver.execute_script("return navigator.userAgent;")
        driver.quit()

        session_data = {
            "timestamp": time.time(),
            "cookies": cookies,
            "user_agent": user_agent
        }
        with open(ARCHIVO_SESION, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)

        session = requests.Session()
        session.headers.update({"User-Agent": user_agent, "Referer": URL_LOGIN})
        for c in cookies:
            session.cookies.set(c["name"], c["value"])
        return session
    except Exception as e:
        try: driver.quit()
        except Exception: pass
        raise RuntimeError(f"Error autenticando en Mi3F: {e}")

def cargar_padron_a_bd():
    """Carga los inscriptos de Jardines 2026 desde el Excel a SQLite."""
    inicializar_bd()
    if not PADRON_JARDINES_PATH.exists():
        raise FileNotFoundError(f"No se encontró el padrón en {PADRON_JARDINES_PATH}")

    df = pd.read_excel(PADRON_JARDINES_PATH)
    # Filtramos únicamente los inscriptos válidos
    if "Estado del tramite" in df.columns:
        df = df[df["Estado del tramite"] == "Inscripto"]

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for _, row in df.iterrows():
            codigo = str(row.get("Código", "")).strip()
            if codigo.endswith(".0"):
                codigo = codigo[:-2]
            if not codigo or codigo == "nan":
                continue

            id_tramite = str(row.get("Id", "")).strip()
            dni_menor = str(row.get("Número de documento.2.1", "")).strip()
            if dni_menor.endswith(".0"):
                dni_menor = dni_menor[:-2]

            nombre = str(row.get("Nombre del solicitante", "")).strip()
            apellido = str(row.get("Apellido del solicitante", "")).strip()
            fnac = str(row.get("Fecha de Nacimiento.2", "")).strip()
            genero = str(row.get("Género del solicitante", "")).strip()
            jardin = str(row.get("Jardin a inscribir", "")).strip()
            sala = str(row.get("Sala a la que se inscribe para el ciclo 2026", "")).strip()
            turno = str(row.get("Turno Asignado", row.get("Horario deinicio", ""))).strip()
            estado = str(row.get("Estado del tramite", "Inscripto")).strip()

            cursor.execute("""
                INSERT INTO inscriptos (
                    codigo_tramite, id_tramite, dni_menor, nombre_menor, apellido_menor,
                    fecha_nacimiento, genero, jardin, sala, turno, estado_tramite
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(codigo_tramite) DO UPDATE SET
                    dni_menor=excluded.dni_menor,
                    nombre_menor=excluded.nombre_menor,
                    apellido_menor=excluded.apellido_menor,
                    fecha_nacimiento=excluded.fecha_nacimiento,
                    jardin=excluded.jardin,
                    sala=excluded.sala
            """, (codigo, id_tramite, dni_menor, nombre, apellido, fnac, genero, jardin, sala, turno, estado))
        conn.commit()
    print(f"Padrón cargado en SQLite: {len(df)} inscriptos.")

def descargar_certificado_tramite(session: requests.Session, codigo_tramite: str) -> List[Dict[str, Any]]:
    """
    Inspecciona la página del expediente en Mi3F, detecta las tarjetas de
    'Certificados de vacunación actualizados' y descarga cada archivo individual.
    """
    url_expediente = URL_TRAMITE.format(codigo_tramite)
    try:
        resp = session.get(url_expediente, timeout=20, verify=False)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        archivos_descargados = []

        # Buscar enlaces de descarga que pertenezcan a la sección 6 (Vacunación)
        enlaces = soup.find_all("a", href=re.compile(r"tra_tramites_bandeja_am_documentos_download\.php"))
        for a in enlaces:
            card = a.find_parent("div", class_=re.compile(r"card|col"))
            texto_card = card.get_text(" ", strip=True) if card else a.get_text(strip=True)
            
            if "vacunac" in texto_card.lower():
                href = a.get("href")
                # Extraer codigo de documento y seccion
                m_doc = re.search(r"codigo=(\d+)", href)
                m_sec = re.search(r"seccion=(\d+)", href)
                codigo_doc = m_doc.group(1) if m_doc else "0"
                seccion = m_sec.group(1) if m_sec else "243"

                url_descarga = "https://backend.mistramites.tresdefebrero.gob.ar/" + href.lstrip("/")
                resp_doc = session.get(url_descarga, timeout=25, verify=False)
                
                if resp_doc.status_code == 200 and len(resp_doc.content) > 50:
                    # Determinar extensión del archivo
                    cd = resp_doc.headers.get("Content-Disposition", "")
                    m_fn = re.search(r'filename="?([^";]+)"?', cd)
                    nombre_orig = m_fn.group(1) if m_fn else f"vacuna_{codigo_doc}.jpg"
                    ext = Path(nombre_orig).suffix or ".jpg"
                    if ext.lower() not in [".jpg", ".jpeg", ".png", ".pdf", ".webp"]:
                        ext = ".jpg"

                    nombre_archivo_local = f"{codigo_tramite}_{codigo_doc}_{nombre_orig}"
                    # Sanitizar nombre
                    nombre_archivo_local = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', nombre_archivo_local)
                    ruta_local = DIR_CERTIFICADOS / nombre_archivo_local
                    
                    with open(ruta_local, "wb") as f:
                        f.write(resp_doc.content)

                    info_doc = {
                        "codigo_tramite": codigo_tramite,
                        "codigo_doc": codigo_doc,
                        "seccion": seccion,
                        "nombre_archivo": nombre_archivo_local,
                        "ruta_local": str(ruta_local),
                        "tamano_bytes": len(resp_doc.content),
                        "content_type": resp_doc.headers.get("Content-Type", "image/jpeg"),
                        "fecha_descarga": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    archivos_descargados.append(info_doc)

        # Registrar en BD
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            for doc in archivos_descargados:
                cursor.execute("""
                    INSERT INTO archivos_certificados (
                        codigo_tramite, codigo_doc, seccion, nombre_archivo,
                        ruta_local, tamano_bytes, content_type, fecha_descarga
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc["codigo_tramite"], doc["codigo_doc"], doc["seccion"],
                    doc["nombre_archivo"], doc["ruta_local"], doc["tamano_bytes"],
                    doc["content_type"], doc["fecha_descarga"]
                ))
            
            estado = "DESCARGADO" if archivos_descargados else "SIN_CERTIFICADO"
            cursor.execute("""
                UPDATE inscriptos 
                SET cant_archivos_vacuna = ?, estado_descarga = ?, fecha_descarga = ?
                WHERE codigo_tramite = ?
            """, (len(archivos_descargados), estado, time.strftime("%Y-%m-%d %H:%M:%S"), codigo_tramite))
            conn.commit()

        return archivos_descargados
    except Exception as e:
        print(f"Error descargando trámite {codigo_tramite}: {e}")
        return []
