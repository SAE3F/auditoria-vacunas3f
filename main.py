"""
Punto de Entrada y Orquestador del Sistema de Digitalización de Certificados de Vacunación (Muni 3F).
"""
import sys
import argparse
import webbrowser
import threading
import time

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from config import DB_PATH
from extractor_mi3f import cargar_padron_a_bd, obtener_sesion_requests, descargar_certificado_tramite
from panel_web import iniciar_servidor, PUERTO
from exportador_excel import exportar_informe_auditoria_excel

def main():
    parser = argparse.ArgumentParser(description="Sistema de Digitalización y Auditoría de Vacunación Infantil - Muni 3F")
    parser.add_argument("--cargar-padron", action="store_true", help="Carga o actualiza los inscriptos desde el Excel a SQLite")
    parser.add_argument("--exportar-excel", action="store_true", help="Genera el reporte de auditoría en Excel")
    parser.add_argument("--puerto", type=int, default=PUERTO, help=f"Puerto del servidor web (por defecto {PUERTO})")
    parser.add_argument("--sin-navegador", action="store_true", help="No abrir automáticamente el navegador web")

    args = parser.parse_args()

    if args.cargar_padron:
        print("Cargando padrón...")
        cargar_padron_a_bd()
        return

    if args.exportar_excel:
        print("Generando informe Excel...")
        ruta = exportar_informe_auditoria_excel()
        print(f"Informe listo en: {ruta}")
        return

    # Iniciar servidor web con navegador automático
    url_local = f"http://localhost:{args.puerto}"
    if not args.sin_navegador:
        def _abrir():
            time.sleep(1.5)
            webbrowser.open(url_local)
        threading.Thread(target=_abrir, daemon=True).start()

    print(f"=================================================================")
    print(f"  🏛️ MUNICIPALIDAD DE TRES DE FEBRERO — DIGITALIZACIÓN VACUNAS  ")
    print(f"=================================================================")
    print(f"  Iniciando panel de auditoría interactivo...")
    print(f"  Acceso local: {url_local}")
    print(f"=================================================================")
    iniciar_servidor(puerto=args.puerto)

if __name__ == "__main__":
    main()
