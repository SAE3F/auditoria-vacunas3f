"""
Servidor Web Nativo y API REST para el Panel de Auditoría y Digitalización de Vacunación.
"""
import os
import io
import re
import sys
import json
import sqlite3
import urllib.parse
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

# Asegurar codificación UTF-8 en consola de Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from config import DIR_PROYECTO, DIR_FRONTEND, DIR_CERTIFICADOS, DB_PATH, DIR_RESULTADOS, GEMINI_API_KEY
from calendario_vacunacion import ESQUEMA_NACIONAL
from extractor_mi3f import cargar_padron_a_bd, descargar_certificado_tramite, obtener_sesion_requests
from auditor_ia import analizar_certificado_con_ia
from evaluador_clinico import evaluar_estado_vacunacion
from exportador_excel import exportar_informe_auditoria_excel

PUERTO = int(os.environ.get("PORT", 8080))

# Estado global de procesamiento por lote
ESTADO_PROCESO_LOTE = {
    "corriendo": False,
    "total": 0,
    "procesados": 0,
    "actual": "",
    "mensaje": ""
}

class VacunacionAPIHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.OK)
        self.end_headers()

    def _responder_json(self, data, status=HTTPStatus.OK):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # Estado del procesamiento en segundo plano
        if path == "/api/estado_lote":
            self._responder_json(ESTADO_PROCESO_LOTE)
            return

        # Servir Frontend
        if path == "/" or path == "/index.html":
            archivo_html = DIR_FRONTEND / "index.html"
            if archivo_html.exists():
                with open(archivo_html, "rb") as f:
                    contenido = f.read()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(contenido)))
                self.end_headers()
                self.wfile.write(contenido)
                return

        # Servir imágenes de certificados (desde disco local o proxy directo desde Mi3F al vuelo)
        if path.startswith("/api/imagen/"):
            nombre_archivo = urllib.parse.unquote(path.replace("/api/imagen/", ""))
            ruta_img = DIR_CERTIFICADOS / nombre_archivo
            data = None
            mime = "image/jpeg"
            ext = Path(nombre_archivo).suffix.lower()

            # 1. Si existe en disco local
            if ruta_img.exists() and ruta_img.is_file():
                if ext == ".pdf":
                    try:
                        import fitz
                        doc = fitz.open(ruta_img)
                        if len(doc) > 0:
                            pix = doc[0].get_pixmap(dpi=150)
                            data = pix.tobytes("jpeg")
                            mime = "image/jpeg"
                            doc.close()
                    except Exception as err_pdf:
                        print(f"Error renderizando PDF {ruta_img}: {err_pdf}")
                else:
                    if ext == ".png": mime = "image/png"
                    with open(ruta_img, "rb") as f:
                        data = f.read()

            # 2. Si no está en disco local, obtener por proxy directo desde Mi3F usando metadatos en BD
            if data is None:
                try:
                    cod_doc = None
                    sec = "243"
                    cod_tra = None

                    with sqlite3.connect(DB_PATH) as conn:
                        conn.row_factory = sqlite3.Row
                        c = conn.cursor()
                        c.execute("SELECT * FROM archivos_certificados WHERE nombre_archivo = ? OR ruta_local LIKE ?", 
                                  (nombre_archivo, f"%{nombre_archivo}%"))
                        doc_info = c.fetchone()

                    if doc_info:
                        cod_doc = doc_info["codigo_doc"]
                        sec = doc_info["seccion"] or "243"
                        cod_tra = doc_info["codigo_tramite"]
                    elif "_" in nombre_archivo:
                        # Extraer codigo_tramite y codigo_doc directamente del nombre (formato: {tramite}_{doc}_...)
                        m_parts = re.match(r"^(\d+)_(\d+)", nombre_archivo)
                        if m_parts:
                            cod_tra = m_parts.group(1)
                            cod_doc = m_parts.group(2)
                            sec = "243"

                    if cod_doc and cod_tra:
                        url_download = f"https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_am_documentos_download.php?codigo={cod_doc}&seccion={sec}&tramiteproductora={cod_tra}"
                        ses = obtener_sesion_requests()
                        resp_proxy = ses.get(url_download, timeout=12, verify=False)
                        if resp_proxy.status_code == 200 and len(resp_proxy.content) > 100:
                            raw_bytes = resp_proxy.content
                            
                            # Verificar si nos devolvió una página HTML de login en vez de un archivo binario
                            if b"<!DOCTYPE html" in raw_bytes[:150] or b"<html" in raw_bytes[:150]:
                                print(f"⚠️ Mi3F devolvió pantalla de login. Verifique la variable MI3F_PHPSESSID en Render.")
                            else:
                                # Si es un PDF, renderizar en memoria como JPEG
                                if ext == ".pdf" or raw_bytes.startswith(b"%PDF"):
                                    try:
                                        import fitz
                                        doc = fitz.open(stream=raw_bytes, filetype="pdf")
                                        if len(doc) > 0:
                                            pix = doc[0].get_pixmap(dpi=150)
                                            data = pix.tobytes("jpeg")
                                            mime = "image/jpeg"
                                            doc.close()
                                    except Exception as err_pdf:
                                        print(f"Error procesando PDF desde Mi3F: {err_pdf}")
                                else:
                                    # Validar que sea una imagen válida con Pillow
                                    try:
                                        from PIL import Image
                                        im_test = Image.open(io.BytesIO(raw_bytes))
                                        im_test.verify()
                                        data = raw_bytes
                                        if ext == ".png": mime = "image/png"
                                        else: mime = "image/jpeg"
                                    except Exception as err_img:
                                        print(f"Bytes no reconocidos como imagen: {err_img}")

                                if data:
                                    # Cachear en disco para que las siguientes vistas sean inmediatas
                                    try:
                                        with open(ruta_img, "wb") as f_cache:
                                            f_cache.write(raw_bytes)
                                    except Exception:
                                        pass
                except Exception as e_proxy:
                    print(f"Error obteniendo documento via proxy Mi3F: {e_proxy}")

            if data:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Imagen no encontrada ni disponible en Mi3F")
                return

        # API: Heartbeat / Health check para mantener activo Render
        if path in ["/api/ping", "/healthz"]:
            self._responder_json({
                "status": "ok",
                "servicio": "auditoria-vacunas3f",
                "timestamp": datetime.now().isoformat()
            })
            return

        # API: Estado de la sesión Mi3F
        if path == "/api/estado_sesion":
            ses = obtener_sesion_requests()
            cookie_activa = ses.headers.get("Cookie", "")
            valida = False
            if "PHPSESSID=" in cookie_activa:
                try:
                    url_test = "https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_unica_am.php?tramiteproductoracod=340844"
                    r = ses.get(url_test, timeout=6, verify=False)
                    if r.status_code == 200 and "ingreso" not in r.url and "iniciar sesión" not in r.text.lower():
                        valida = True
                except Exception:
                    pass
            self._responder_json({
                "activa": valida,
                "cookie_configurada": bool("PHPSESSID=" in cookie_activa)
            })
            return

        # API: Diagnóstico de conexión Mi3F
        if path == "/api/diagnostico_mi3f":
            # Detectar si el usuario le puso otro nombre a la variable en Render
            posibles_keys = [k for k in os.environ.keys() if any(x in k.upper() for x in ["MI3F", "PHP", "COOKIE", "SESSI", "PASS", "CUIL"])]
            
            # Buscar el valor de sesión bajo cualquier clave coincidente
            phpsessid_val = os.environ.get("MI3F_PHPSESSID") or os.environ.get("PHPSESSID") or os.environ.get("MI3F_COOKIE") or ""
            
            diag = {
                "env_mi3f_set": bool(phpsessid_val),
                "env_mi3f_len": len(phpsessid_val.strip()),
                "env_mi3f_prefix": (phpsessid_val.strip()[:4] + "...") if phpsessid_val else "NO_SET",
                "matching_env_keys_found": posibles_keys
            }
            try:
                import socket
                diag["dns_ip"] = socket.gethostbyname("backend.mistramites.tresdefebrero.gob.ar")
            except Exception as e_dns:
                diag["dns_error"] = str(e_dns)

            try:
                ses = obtener_sesion_requests()
                diag["cookie_header_sent"] = ses.headers.get("Cookie", "NINGUNA")
                test_url = "https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_am_documentos_download.php?codigo=584972&seccion=243&tramiteproductora=340844"
                resp = ses.get(test_url, timeout=10, verify=False)
                diag["test_doc_status"] = resp.status_code
                diag["test_doc_url"] = resp.url
                diag["test_doc_content_type"] = resp.headers.get("Content-Type")
                diag["test_doc_len"] = len(resp.content)
                diag["test_doc_is_html"] = b"<!DOCTYPE html" in resp.content[:150] or b"<html" in resp.content[:150]
                if diag["test_doc_is_html"]:
                    diag["test_doc_preview"] = resp.text[:300]
            except Exception as e_req:
                diag["test_req_error"] = str(e_req)

            self._responder_json(diag)
            return

        # API: Métricas generales
        if path == "/api/stats":
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM inscriptos")
                total_inscriptos = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM inscriptos WHERE cant_archivos_vacuna > 0")
                total_con_certificado = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM auditoria_vacunas WHERE estado_esquema = 'AL_DIA'")
                al_dia = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM auditoria_vacunas WHERE estado_esquema = 'INCOMPLETO'")
                incompletos = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM auditoria_vacunas WHERE estado_esquema = 'SOLICITAR_REENVIO'")
                solicitar_reenvio = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM auditoria_vacunas WHERE estado_esquema = 'REVISION_REQUERIDA' AND (revisado_por_humano = 0 OR revisado_por_humano IS NULL)")
                revision_humana = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM auditoria_vacunas")
                procesados_ia = cursor.fetchone()[0]

            self._responder_json({
                "total_inscriptos": total_inscriptos,
                "total_con_certificado": total_con_certificado,
                "procesados_ia": procesados_ia,
                "al_dia": al_dia,
                "incompletos": incompletos,
                "requiere_revision_humana": revision_humana,
                "solicitar_reenvio": solicitar_reenvio
            })
            return

        # API: Listar inscriptos con filtros y paginación
        if path == "/api/inscriptos":
            q = params.get("q", [""])[0].strip()
            jardin = params.get("jardin", [""])[0].strip()
            estado = params.get("estado", [""])[0].strip()
            solo_revision = params.get("revision", [""])[0] == "1"
            offset = int(params.get("offset", [0])[0])
            limit = int(params.get("limit", [50])[0])

            where_clauses = ["1=1"]
            query_params = []

            if q:
                where_clauses.append("(i.dni_menor LIKE ? OR i.nombre_menor LIKE ? OR i.apellido_menor LIKE ? OR i.codigo_tramite LIKE ?)")
                patt = f"%{q}%"
                query_params.extend([patt, patt, patt, patt])

            if jardin:
                where_clauses.append("i.jardin = ?")
                query_params.append(jardin)

            if estado:
                where_clauses.append("a.estado_esquema = ?")
                query_params.append(estado)

            if solo_revision:
                where_clauses.append("a.requiere_revision_humana = 1")

            where_sql = " AND ".join(where_clauses)

            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                count_sql = f"""
                    SELECT COUNT(*) FROM inscriptos i
                    LEFT JOIN auditoria_vacunas a ON i.codigo_tramite = a.codigo_tramite
                    WHERE {where_sql}
                """
                cursor.execute(count_sql, query_params)
                total_filtrados = cursor.fetchone()[0]

                sql = f"""
                    SELECT i.*, 
                           a.calidad_imagen, a.estado_esquema, a.requiere_revision_humana, 
                           a.motivo_revision, a.revisado_por_humano
                    FROM inscriptos i
                    LEFT JOIN auditoria_vacunas a ON i.codigo_tramite = a.codigo_tramite
                    WHERE {where_sql}
                    ORDER BY a.requiere_revision_humana DESC, i.apellido_menor ASC
                    LIMIT ? OFFSET ?
                """
                cursor.execute(sql, query_params + [limit, offset])
                filas = [dict(r) for r in cursor.fetchall()]

            self._responder_json({
                "total": total_filtrados,
                "offset": offset,
                "limit": limit,
                "data": filas
            })
            return

        # API: Detalle de un inscripto individual
        if path.startswith("/api/inscripto/"):
            codigo = path.replace("/api/inscripto/", "").strip()
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inscriptos WHERE codigo_tramite = ?", (codigo,))
                inscripto = cursor.fetchone()
                if not inscripto:
                    self.send_error(HTTPStatus.NOT_FOUND, "Inscripto no encontrado")
                    return

                cursor.execute("SELECT * FROM archivos_certificados WHERE codigo_tramite = ?", (codigo,))
                archivos = [dict(r) for r in cursor.fetchall()]

                # Si no tiene archivos registrados, consultar la bandeja de Mi3F al vuelo
                if not archivos:
                    try:
                        ses = obtener_sesion_requests()
                        url_exp = f"https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_unica_am.php?tramiteproductoracod={codigo}"
                        resp_exp = ses.get(url_exp, timeout=5, verify=False)
                        if resp_exp.status_code == 200 and "iniciar sesión" not in resp_exp.text.lower() and "sso.tresdefebrero" not in resp_exp.url:
                            soup = BeautifulSoup(resp_exp.text, "html.parser")
                            enlaces = soup.find_all("a", href=re.compile(r"tra_tramites_bandeja_am_documentos_download\.php"))
                            docs_encontrados = []
                            for a in enlaces:
                                card = a.find_parent("div", class_=re.compile(r"card|col|row"))
                                txt_card = card.get_text(" ", strip=True).lower() if card else a.get_text(strip=True).lower()
                                if "vacun" in txt_card:
                                    href = a.get("href", "")
                                    m_doc = re.search(r"codigo=(\d+)", href)
                                    m_sec = re.search(r"seccion=(\d+)", href)
                                    c_doc = m_doc.group(1) if m_doc else "0"
                                    c_sec = m_sec.group(1) if m_sec else "243"
                                    nombre_gen = f"{codigo}_{c_doc}_vacunas.jpg"
                                    
                                    cursor.execute("""
                                        INSERT OR IGNORE INTO archivos_certificados (
                                            codigo_tramite, codigo_doc, seccion, nombre_archivo, ruta_local, tamano_bytes, content_type, fecha_descarga
                                        ) VALUES (?, ?, ?, ?, ?, 0, 'image/jpeg', datetime('now'))
                                    """, (codigo, c_doc, c_sec, nombre_gen, nombre_gen))
                                    docs_encontrados.append({
                                        "codigo_tramite": codigo,
                                        "codigo_doc": c_doc,
                                        "seccion": c_sec,
                                        "nombre_archivo": nombre_gen,
                                        "ruta_local": nombre_gen,
                                        "tamano_bytes": 0,
                                        "content_type": "image/jpeg"
                                    })
                            
                            conn.commit()
                            if docs_encontrados:
                                archivos = docs_encontrados
                                cursor.execute("UPDATE inscriptos SET cant_archivos_vacuna = ?, estado_descarga = 'DISPONIBLE' WHERE codigo_tramite = ?", (len(docs_encontrados), codigo))
                                conn.commit()
                            else:
                                cursor.execute("UPDATE inscriptos SET cant_archivos_vacuna = 0, estado_descarga = 'SIN_CERTIFICADO' WHERE codigo_tramite = ?", (codigo,))
                                conn.commit()
                    except Exception as err_sync:
                        print(f"Aviso sync al vuelo para tramite {codigo}: {err_sync}")

                cursor.execute("SELECT * FROM auditoria_vacunas WHERE codigo_tramite = ?", (codigo,))
                auditoria = cursor.fetchone()

            res = {
                "inscripto": dict(inscripto),
                "archivos": archivos,
                "auditoria": dict(auditoria) if auditoria else None
            }
            self._responder_json(res)
            return

        # API: Exportar Excel
        if path == "/api/exportar_excel":
            ruta_excel = exportar_informe_auditoria_excel()
            self._responder_json({
                "status": "ok",
                "archivo": ruta_excel.name,
                "ruta_completa": str(ruta_excel)
            })
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            datos = json.loads(body)
        except Exception:
            datos = {}

        # API: Configurar y persistir PHPSESSID en base de datos
        if path == "/api/configurar_sesion":
            nueva_cookie = str(datos.get("phpsessid", "")).strip()
            if nueva_cookie.startswith("PHPSESSID="):
                nueva_cookie = nueva_cookie.replace("PHPSESSID=", "").strip()
            
            if not nueva_cookie:
                self._responder_json({"status": "error", "mensaje": "Cookie PHPSESSID vacía."}, status=HTTPStatus.BAD_REQUEST)
                return

            # Probar si funciona contra Mi3F
            try:
                import requests
                s_test = requests.Session()
                s_test.trust_env = False
                s_test.headers["Cookie"] = f"PHPSESSID={nueva_cookie}"
                url_test = "https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_unica_am.php?tramiteproductoracod=340844"
                r = s_test.get(url_test, timeout=8, verify=False)
                if "sso.tresdefebrero" in r.url or "iniciar sesión" in r.text.lower() or "ingreso" in r.url:
                    self._responder_json({
                        "status": "error",
                        "mensaje": "La cookie ingresada no es válida o ya expiró en Mi3F (redirigió al login)."
                    }, status=HTTPStatus.UNAUTHORIZED)
                    return
            except Exception as e_test:
                print(f"Aviso prueba sesion: {e_test}")

            # Persistir en SQLite
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("CREATE TABLE IF NOT EXISTS config_app (clave TEXT PRIMARY KEY, valor TEXT)")
                    c.execute("INSERT OR REPLACE INTO config_app (clave, valor) VALUES (?, ?)", ('MI3F_PHPSESSID', nueva_cookie))
                    conn.commit()
                self._responder_json({"status": "ok", "mensaje": "¡Sesión configurada y validada exitosamente!"})
            except Exception as e_db:
                self._responder_json({"status": "error", "mensaje": str(e_db)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        # API: Cargar Padrón Base desde Excel
        if path == "/api/accion/cargar_padron":
            try:
                cargar_padron_a_bd()
                self._responder_json({"status": "ok", "mensaje": "Padrón cargado exitosamente en SQLite."})
            except Exception as e:
                self._responder_json({"status": "error", "mensaje": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        # API: Descargar Certificado de un trámite
        if path == "/api/accion/descargar_tramite":
            codigo = str(datos.get("codigo_tramite", "")).strip()
            if not codigo:
                self._responder_json({"status": "error", "mensaje": "codigo_tramite requerido"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                sesion = obtener_sesion_requests()
                docs = descargar_certificado_tramite(sesion, codigo)
                self._responder_json({"status": "ok", "archivos_descargados": len(docs), "docs": docs})
            except Exception as e:
                self._responder_json({"status": "error", "mensaje": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        # API: Analizar trámite con IA
        if path == "/api/accion/analizar_tramite":
            codigo = str(datos.get("codigo_tramite", "")).strip()
            api_key = datos.get("api_key") or GEMINI_API_KEY
            if not codigo:
                self._responder_json({"status": "error", "mensaje": "codigo_tramite requerido"}, status=HTTPStatus.BAD_REQUEST)
                return

            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inscriptos WHERE codigo_tramite = ?", (codigo,))
                inscripto = cursor.fetchone()
                cursor.execute("SELECT * FROM archivos_certificados WHERE codigo_tramite = ?", (codigo,))
                archivos = cursor.fetchall()

            if not inscripto:
                self._responder_json({"status": "error", "mensaje": "Inscripto no encontrado"}, status=HTTPStatus.NOT_FOUND)
                return

            # Si no tiene archivos descargados localmente, intentar descargar primero
            if not archivos:
                sesion = obtener_sesion_requests()
                descargar_certificado_tramite(sesion, codigo)
                with sqlite3.connect(DB_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM archivos_certificados WHERE codigo_tramite = ?", (codigo,))
                    archivos = cursor.fetchall()

            # Obtener rutas válidas de archivos buscando en DIR_CERTIFICADOS o ruta directa
            rutas = []
            for r in archivos:
                nombre = r["nombre_archivo"] or os.path.basename(r["ruta_local"])
                p1 = DIR_CERTIFICADOS / nombre
                p2 = Path(r["ruta_local"])
                if p1.exists():
                    rutas.append(p1)
                elif p2.exists():
                    rutas.append(p2)
            if not rutas:
                self._responder_json({
                    "status": "error",
                    "mensaje": "El trámite no posee certificados de vacunación adjuntos en Mi3F."
                }, status=HTTPStatus.BAD_REQUEST)
                return

            # Ejecutar Gemini Multimodal
            res_ia = analizar_certificado_con_ia(rutas, api_key=api_key)
            
            # Evaluación Clínica
            fnac = inscripto["fecha_nacimiento"]
            res_clinico = evaluar_estado_vacunacion(fnac, res_ia)

            # Persistir en BD
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO auditoria_vacunas (
                        codigo_tramite, dni_menor, edad_meses, calidad_imagen,
                        estado_esquema, requiere_revision_humana, motivo_revision,
                        vacunas_detectadas_json, vacunas_faltantes_json, observaciones_ia,
                        fecha_analisis
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(codigo_tramite) DO UPDATE SET
                        edad_meses=excluded.edad_meses,
                        calidad_imagen=excluded.calidad_imagen,
                        estado_esquema=excluded.estado_esquema,
                        requiere_revision_humana=excluded.requiere_revision_humana,
                        motivo_revision=excluded.motivo_revision,
                        vacunas_detectadas_json=excluded.vacunas_detectadas_json,
                        vacunas_faltantes_json=excluded.vacunas_faltantes_json,
                        observaciones_ia=excluded.observaciones_ia,
                        fecha_analisis=excluded.fecha_analisis
                """, (
                    codigo, inscripto["dni_menor"], res_clinico["edad_meses"],
                    res_ia.get("calidad_imagen", "MEDIA"), res_clinico["estado_esquema"],
                    1 if res_clinico["requiere_revision_humana"] else 0,
                    res_clinico["motivo_revision"],
                    json.dumps(res_ia.get("dosis_aplicadas", []), ensure_ascii=False),
                    json.dumps(res_clinico.get("vacunas_faltantes", []), ensure_ascii=False),
                    res_ia.get("observaciones_adicionales", ""),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()

            self._responder_json({
                "status": "ok",
                "analisis_ia": res_ia,
                "evaluacion_clinica": res_clinico
            })
            return

        # API: Procesamiento por Lote (Descarga + IA masiva)
        if path == "/api/accion/procesar_lote":
            limite = int(datos.get("limite", 10))
            api_key = datos.get("api_key") or GEMINI_API_KEY
            
            def _tarea_segundo_plano():
                global ESTADO_PROCESO_LOTE
                try:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT i.codigo_tramite, i.fecha_nacimiento, i.nombre_menor, i.apellido_menor
                            FROM inscriptos i
                            LEFT JOIN auditoria_vacunas a ON i.codigo_tramite = a.codigo_tramite
                            WHERE a.id IS NULL
                            LIMIT ?
                        """, (limite,))
                        pendientes = [dict(r) for r in cursor.fetchall()]

                    if not pendientes:
                        ESTADO_PROCESO_LOTE["corriendo"] = False
                        ESTADO_PROCESO_LOTE["mensaje"] = "No hay trámites pendientes."
                        return

                    ESTADO_PROCESO_LOTE["corriendo"] = True
                    ESTADO_PROCESO_LOTE["total"] = len(pendientes)
                    ESTADO_PROCESO_LOTE["procesados"] = 0

                    sesion = obtener_sesion_requests()
                    for idx, p in enumerate(pendientes):
                        cod = p["codigo_tramite"]
                        fnac = p["fecha_nacimiento"]
                        nom = f"{p.get('nombre_menor','')} {p.get('apellido_menor','')}"
                        ESTADO_PROCESO_LOTE["procesados"] = idx + 1
                        ESTADO_PROCESO_LOTE["actual"] = f"{nom} (Trámite #{cod})"

                        try:
                            descargar_certificado_tramite(sesion, cod)
                            with sqlite3.connect(DB_PATH) as conn:
                                conn.row_factory = sqlite3.Row
                                c2 = conn.cursor()
                                c2.execute("SELECT ruta_local FROM archivos_certificados WHERE codigo_tramite = ?", (cod,))
                                archivos = [Path(r["ruta_local"]) for r in c2.fetchall() if Path(r["ruta_local"]).exists()]

                            if archivos and api_key:
                                rutas = []
                                for r in archivos:
                                    nombre = r["nombre_archivo"] or os.path.basename(r["ruta_local"])
                                    p1 = DIR_CERTIFICADOS / nombre
                                    p2 = Path(r["ruta_local"])
                                    if p1.exists():
                                        rutas.append(p1)
                                    elif p2.exists():
                                        rutas.append(p2)

                                if rutas:
                                    res_ia = analizar_certificado_con_ia(rutas, api_key=api_key)
                                res_clinico = evaluar_estado_vacunacion(fnac, res_ia)

                                with sqlite3.connect(DB_PATH) as conn:
                                    c2 = conn.cursor()
                                    c2.execute("""
                                        INSERT INTO auditoria_vacunas (
                                            codigo_tramite, dni_menor, edad_meses, calidad_imagen,
                                            estado_esquema, requiere_revision_humana, motivo_revision,
                                            vacunas_detectadas_json, vacunas_faltantes_json, observaciones_ia,
                                            fecha_analisis
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(codigo_tramite) DO UPDATE SET
                                            edad_meses=excluded.edad_meses,
                                            calidad_imagen=excluded.calidad_imagen,
                                            estado_esquema=excluded.estado_esquema,
                                            requiere_revision_humana=excluded.requiere_revision_humana,
                                            motivo_revision=excluded.motivo_revision,
                                            vacunas_detectadas_json=excluded.vacunas_detectadas_json,
                                            vacunas_faltantes_json=excluded.vacunas_faltantes_json,
                                            observaciones_ia=excluded.observaciones_ia,
                                            fecha_analisis=excluded.fecha_analisis
                                    """, (
                                        cod, "", res_clinico["edad_meses"],
                                        res_ia.get("calidad_imagen", "MEDIA"), res_clinico["estado_esquema"],
                                        1 if res_clinico["requiere_revision_humana"] else 0,
                                        res_clinico["motivo_revision"],
                                        json.dumps(res_ia.get("dosis_aplicadas", []), ensure_ascii=False),
                                        json.dumps(res_clinico.get("vacunas_faltantes", []), ensure_ascii=False),
                                        res_ia.get("observaciones_adicionales", ""),
                                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    ))
                                    conn.commit()
                            time.sleep(1)
                        except Exception as err:
                            print(f"Error procesando lote {cod}: {err}")

                    ESTADO_PROCESO_LOTE["corriendo"] = False
                    ESTADO_PROCESO_LOTE["mensaje"] = f"Finalizado con éxito: {len(pendientes)} certificados procesados."
                except Exception as ex:
                    ESTADO_PROCESO_LOTE["corriendo"] = False
                    ESTADO_PROCESO_LOTE["mensaje"] = f"Error en lote: {ex}"

            import threading
            threading.Thread(target=_tarea_segundo_plano, daemon=True).start()
            self._responder_json({"status": "ok", "mensaje": f"Iniciado procesamiento en segundo plano para {limite} expedientes."})
            return

        # API: Marcar / Alternar una vacuna específica manualmente
        if path == "/api/accion/marcar_vacuna_individual":
            codigo = str(datos.get("codigo_tramite", "")).strip()
            vacuna_nombre = str(datos.get("vacuna", "")).strip()
            dosis_nombre = str(datos.get("dosis", "")).strip()
            accion = str(datos.get("accion", "APLICAR")).upper() # 'APLICAR' o 'DESMARCAR'
            motivo = str(datos.get("motivo", "")).strip()

            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM auditoria_vacunas WHERE codigo_tramite = ?", (codigo,))
                fila = cursor.fetchone()

                cursor.execute("SELECT dni_menor, fecha_nacimiento FROM inscriptos WHERE codigo_tramite = ?", (codigo,))
                insc = cursor.fetchone()
                dni_menor = insc["dni_menor"] if insc else ""
                fnac = insc["fecha_nacimiento"] if insc else ""

                if not fila:
                    res_base = evaluar_estado_vacunacion(fnac, {"dosis_aplicadas": []})
                    detectadas = []
                    faltantes = res_base.get("vacunas_faltantes", [])
                    edad_meses = res_base.get("edad_meses", 0)
                else:
                    detectadas = json.loads(fila["vacunas_detectadas_json"]) if fila["vacunas_detectadas_json"] else []
                    faltantes = json.loads(fila["vacunas_faltantes_json"]) if fila["vacunas_faltantes_json"] else []
                    edad_meses = fila["edad_meses"] or 0

                if accion == "APLICAR":
                    faltantes = [f for f in faltantes if not (f.get("vacuna") == vacuna_nombre and f.get("dosis") == dosis_nombre)]
                    ya_esta = any(d.get("vacuna_canonica", d.get("vacuna")) == vacuna_nombre and d.get("dosis") == dosis_nombre for d in detectadas)
                    if not ya_esta:
                        detectadas.append({
                            "vacuna_canonica": vacuna_nombre,
                            "vacuna": vacuna_nombre,
                            "dosis": dosis_nombre,
                            "fecha_aplicacion": "Validada manualmente",
                            "lote": "Verificado visualmente",
                            "confianza_lectura": "VALIDADA_POR_HUMANO",
                            "observacion": motivo
                        })
                else: # DESMARCAR
                    detectadas = [d for d in detectadas if not (d.get("vacuna_canonica", d.get("vacuna")) == vacuna_nombre and d.get("dosis") == dosis_nombre)]
                    faltantes.append({
                        "vacuna": vacuna_nombre,
                        "dosis": dosis_nombre,
                        "edad_obligatoria_meses": 0
                    })

                nuevo_estado = "AL_DIA" if len(faltantes) == 0 else "INCOMPLETO"
                cursor.execute("""
                    INSERT INTO auditoria_vacunas (
                        codigo_tramite, dni_menor, edad_meses, calidad_imagen,
                        estado_esquema, requiere_revision_humana, motivo_revision,
                        vacunas_detectadas_json, vacunas_faltantes_json, observaciones_ia,
                        revisado_por_humano, fecha_revision_humana, fecha_analisis
                    ) VALUES (?, ?, ?, 'MEDIA', ?, 0, ?, ?, ?, '', 1, datetime('now'), datetime('now'))
                    ON CONFLICT(codigo_tramite) DO UPDATE SET
                        vacunas_detectadas_json = excluded.vacunas_detectadas_json,
                        vacunas_faltantes_json = excluded.vacunas_faltantes_json,
                        estado_esquema = excluded.estado_esquema,
                        revisado_por_humano = 1,
                        fecha_revision_humana = datetime('now')
                """, (
                    codigo, dni_menor, edad_meses,
                    nuevo_estado, motivo,
                    json.dumps(detectadas, ensure_ascii=False),
                    json.dumps(faltantes, ensure_ascii=False)
                ))
                conn.commit()

            # Aprendizaje Continuo: Destilar regla si hubo un motivo explicativo
            if motivo and len(motivo) > 6:
                import threading
                from auditor_ia import destilar_regla_de_feedback
                diagnostico = f"Vacuna {vacuna_nombre} ({dosis_nombre}) marcada como faltante por la IA"
                threading.Thread(
                    target=destilar_regla_de_feedback,
                    args=(codigo, diagnostico, motivo, GEMINI_API_KEY),
                    daemon=True
                ).start()

            self._responder_json({
                "status": "ok",
                "mensaje": f"Vacuna {vacuna_nombre} actualizada con éxito.",
                "nuevo_estado_esquema": nuevo_estado,
                "total_faltantes": len(faltantes)
            })
            return

        # API: Validación humana manual
        if path == "/api/accion/guardar_revision_humana":
            codigo = str(datos.get("codigo_tramite", "")).strip()
            estado = datos.get("estado_esquema", "AL_DIA")
            observaciones = datos.get("observaciones", "")
            usuario = datos.get("usuario", "Auditor Municipal")

            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM auditoria_vacunas WHERE codigo_tramite = ?", (codigo,))
                fila_prev = cursor.fetchone()

                cursor.execute("SELECT dni_menor, fecha_nacimiento FROM inscriptos WHERE codigo_tramite = ?", (codigo,))
                insc = cursor.fetchone()
                dni_menor = insc["dni_menor"] if insc else ""
                fnac = insc["fecha_nacimiento"] if insc else ""

                motivo_prev = fila_prev["motivo_revision"] if fila_prev else ""
                
                # Si se aprueba como AL_DIA, las vacunas que estaban faltantes se pasan a detectadas validadas manualmente
                if fila_prev:
                    try:
                        detectadas_list = json.loads(fila_prev["vacunas_detectadas_json"]) if fila_prev["vacunas_detectadas_json"] else []
                    except Exception:
                        detectadas_list = []
                    try:
                        faltantes_list = json.loads(fila_prev["vacunas_faltantes_json"]) if fila_prev["vacunas_faltantes_json"] else []
                    except Exception:
                        faltantes_list = []
                else:
                    detectadas_list = []
                    faltantes_list = []

                if estado == "AL_DIA":
                    for f in faltantes_list:
                        vac_nom = f.get("vacuna", "")
                        dos_nom = f.get("dosis", "")
                        ya_esta = any(d.get("vacuna_canonica", d.get("vacuna")) == vac_nom and d.get("dosis") == dos_nom for d in detectadas_list)
                        if not ya_esta:
                            detectadas_list.append({
                                "vacuna_canonica": vac_nom,
                                "vacuna": vac_nom,
                                "dosis": dos_nom,
                                "fecha_aplicacion": "Validada manualmente",
                                "lote": "Verificado visualmente",
                                "confianza_lectura": "VALIDADA_POR_HUMANO",
                                "observacion": observaciones or "Aprobado manualmente en esquema completo"
                            })
                    vacunas_faltantes_val = "[]"
                    vacunas_detectadas_val = json.dumps(detectadas_list, ensure_ascii=False)
                else:
                    vacunas_faltantes_val = fila_prev["vacunas_faltantes_json"] if fila_prev else "[]"
                    vacunas_detectadas_val = fila_prev["vacunas_detectadas_json"] if fila_prev else "[]"

                calidad_val = fila_prev["calidad_imagen"] if fila_prev else "ALTA"
                edad_val = fila_prev["edad_meses"] if fila_prev else 0

                cursor.execute("""
                    INSERT INTO auditoria_vacunas (
                        codigo_tramite, dni_menor, edad_meses, calidad_imagen,
                        estado_esquema, requiere_revision_humana, motivo_revision,
                        vacunas_detectadas_json, vacunas_faltantes_json, observaciones_ia,
                        revisado_por_humano, usuario_revisor, fecha_revision_humana, fecha_analisis
                    ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 1, ?, datetime('now'), datetime('now'))
                    ON CONFLICT(codigo_tramite) DO UPDATE SET
                        estado_esquema = excluded.estado_esquema,
                        requiere_revision_humana = 0,
                        revisado_por_humano = 1,
                        usuario_revisor = excluded.usuario_revisor,
                        motivo_revision = excluded.motivo_revision,
                        vacunas_detectadas_json = excluded.vacunas_detectadas_json,
                        vacunas_faltantes_json = excluded.vacunas_faltantes_json,
                        fecha_revision_humana = datetime('now')
                """, (
                    codigo, dni_menor, edad_val, calidad_val,
                    estado, observaciones, vacunas_detectadas_val, vacunas_faltantes_val,
                    observaciones, usuario
                ))
                conn.commit()

            # Aprendizaje Continuo: Destilar nueva regla si hubo observaciones explicativas
            if observaciones and len(observaciones.strip()) > 8:
                import threading
                from auditor_ia import destilar_regla_de_feedback
                threading.Thread(
                    target=destilar_regla_de_feedback,
                    args=(codigo, motivo_prev, observaciones, GEMINI_API_KEY),
                    daemon=True
                ).start()

            self._responder_json({
                "status": "ok", 
                "mensaje": "Revisión humana guardada correctamente y aprendizaje registrado.",
                "nuevo_estado": estado
            })
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Acción POST no encontrada")

def iniciar_servidor(puerto=None):
    if puerto is None:
        puerto = int(os.environ.get("PORT", 8080))

    try:
        if PADRON_JARDINES_PATH and Path(PADRON_JARDINES_PATH).exists():
            cargar_padron_a_bd()
    except Exception as e:
        print(f"⚠️ Aviso al cargar padrón base: {e} (Continuando con la BD existente)")

    print(f"🚀 Iniciando servidor HTTP en 0.0.0.0:{puerto} (PORT={os.environ.get('PORT')})...")
    servidor = HTTPServer(("0.0.0.0", puerto), VacunacionAPIHandler)
    print(f"✅ Servidor de Auditoría de Vacunas escuchando exitosamente en http://0.0.0.0:{puerto}")
    servidor.serve_forever()

if __name__ == "__main__":
    iniciar_servidor()
