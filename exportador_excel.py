"""
Generador de Reportes Excel Profesionales con Métricas, Semáforos y Matriz de Vacunas.
"""
import json
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config import DB_PATH, DIR_RESULTADOS

def exportar_informe_auditoria_excel(ruta_destino: Path = None) -> Path:
    """
    Exporta la base de datos de vacunación a un archivo Excel profesional multi-pestaña.
    """
    if not ruta_destino:
        fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
        ruta_destino = DIR_RESULTADOS / f"Auditoria_Vacunacion_Jardines_3F_{fecha_str}.xlsx"

    with sqlite3.connect(DB_PATH) as conn:
        df_inscriptos = pd.read_sql_query("SELECT * FROM inscriptos", conn)
        df_auditoria = pd.read_sql_query("SELECT * FROM auditoria_vacunas", conn)

    if df_auditoria.empty:
        # Si aún no hay procesados, exportar la estructura de inscriptos
        df_merged = df_inscriptos.copy()
        df_merged["estado_esquema"] = "PENDIENTE_PROCESAMIENTO"
        df_merged["calidad_imagen"] = "PENDIENTE"
        df_merged["vacunas_faltantes"] = ""
        df_merged["requiere_revision_humana"] = "NO"
    else:
        df_merged = pd.merge(df_inscriptos, df_auditoria, on="codigo_tramite", how="left")

    # Crear Excel con openpyxl
    with pd.ExcelWriter(ruta_destino, engine="openpyxl") as writer:
        # Hoja 1: Listado General
        cols_detalle = [
            "codigo_tramite", "dni_menor", "nombre_menor", "apellido_menor",
            "jardin", "sala", "turno", "fecha_nacimiento", "edad_meses",
            "estado_esquema", "calidad_imagen", "requiere_revision_humana",
            "motivo_revision"
        ]
        cols_existentes = [c for c in cols_detalle if c in df_merged.columns]
        df_vista = df_merged[cols_existentes].copy()
        
        # Parsear vacunas faltantes para mostrarlas en texto legible
        if "vacunas_faltantes_json" in df_merged.columns:
            faltantes_txt = []
            for item in df_merged["vacunas_faltantes_json"]:
                if pd.notna(item) and item:
                    try:
                        lst = json.loads(item)
                        faltantes_txt.append(", ".join([f"{v.get('vacuna')} ({v.get('dosis')})" for v in lst]))
                    except Exception:
                        faltantes_txt.append("")
                else:
                    faltantes_txt.append("")
            df_vista["vacunas_especificas_faltantes"] = faltantes_txt

        df_vista.to_excel(writer, sheet_name="Auditoría General", index=False)

        # Hoja 2: Cola de Revisión Humana (Filtro prioritario)
        if "requiere_revision_humana" in df_vista.columns:
            df_revision = df_vista[df_vista["requiere_revision_humana"].isin([1, "1", True, "SI", "SÍ"])].copy()
            df_revision.to_excel(writer, sheet_name="Casos a Revisar por Persona", index=False)

        # Hoja 3: Resumen por Jardín
        if "jardin" in df_vista.columns and "estado_esquema" in df_vista.columns:
            resumen = df_vista.groupby(["jardin", "estado_esquema"]).size().unstack(fill_value=0)
            resumen["Total Chicos"] = resumen.sum(axis=1)
            resumen.to_excel(writer, sheet_name="Métricas por Jardín")

    # Aplicar diseño institucional Muni 3F
    wb = pd.ExcelFile(ruta_destino).book
    _estilizar_workbook(ruta_destino)

    return ruta_destino

def _estilizar_workbook(ruta_archivo: Path):
    """Aplica formato condicional, bordes y encabezados con estilo oficial de 3F."""
    import openpyxl

    wb = openpyxl.load_workbook(ruta_archivo)
    fill_header = PatternFill(start_color="163C68", end_color="163C68", fill_type="solid")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    fill_al_dia = PatternFill(start_color="D4EDDA", fill_type="solid") # Verde claro
    fill_incompleto = PatternFill(start_color="FFF3CD", fill_type="solid") # Amarillo alerta
    fill_revision = PatternFill(start_color="F8D7DA", fill_type="solid") # Rojo suave
    fill_solicitar = PatternFill(start_color="FADBD8", fill_type="solid") # Rosa / Alerta Reenvío

    for ws in wb.worksheets:
        ws.views.sheetView[0].showGridLines = True
        
        # Formato de encabezados
        for cell in ws[1]:
            cell.fill = fill_header
            cell.font = font_header
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Autoajustar ancho de columnas
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

        # Colorear según estado_esquema
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                val_up = str(cell.value).upper()
                if val_up == "AL_DIA":
                    cell.fill = fill_al_dia
                elif val_up == "INCOMPLETO":
                    cell.fill = fill_incompleto
                elif val_up == "SOLICITAR_REENVIO":
                    cell.fill = fill_solicitar
                elif val_up in ["REVISION_REQUERIDA", "BAJA", "INVALIDA"]:
                    cell.fill = fill_revision

    wb.save(ruta_archivo)
