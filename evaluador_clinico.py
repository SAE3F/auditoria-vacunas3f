"""
Motor de Evaluación Clínica y Contraste con el Calendario Nacional de Vacunación Argentino.
Determina vacunas cumplidas, faltantes o retrasadas según la fecha de nacimiento.
"""
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import re

from calendario_vacunacion import (
    ESQUEMA_NACIONAL, RequisitoDosis, calcular_edad_meses, obtener_vacunas_exigibles
)

def parsear_fecha_nacimiento(fecha_str: Any) -> Optional[date]:
    """Parsea formatos habituales de fecha de nacimiento (DD/MM/AAAA, AAAA-MM-DD, Timestamp)."""
    if not fecha_str or str(fecha_str).strip() in ["", "nan", "None"]:
        return None
    
    if isinstance(fecha_str, (datetime, date)):
        return fecha_str if isinstance(fecha_str, date) else fecha_str.date()

    val = str(fecha_str).strip()
    formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]
    for fmt in formatos:
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            pass
    return None

def _normalizar_texto(t: str) -> str:
    if not t: return ""
    t = t.lower()
    t = re.sub(r'[áàäâ]', 'a', t)
    t = re.sub(r'[éèëê]', 'e', t)
    t = re.sub(r'[íìïî]', 'i', t)
    t = re.sub(r'[óòöô]', 'o', t)
    t = re.sub(r'[úùüû]', 'u', t)
    return re.sub(r'[^a-z0-9]', '', t)

def _coincide_vacuna_y_dosis(dosis_detectada: Dict[str, Any], requisito: RequisitoDosis) -> bool:
    """Evalúa si una dosis leída por la IA corresponde a un requisito del calendario."""
    vac_ia = _normalizar_texto(dosis_detectada.get("vacuna_canonica", ""))
    dosis_ia = _normalizar_texto(dosis_detectada.get("dosis", ""))

    req_vac = _normalizar_texto(requisito.vacuna_nombre)
    req_dosis = _normalizar_texto(requisito.dosis_nombre)

    # Verificar coincidencia de vacuna (por nombre canónico o aliases)
    match_vacuna = False
    if req_vac in vac_ia or vac_ia in req_vac:
        match_vacuna = True
    else:
        for alias in requisito.aliases:
            alias_norm = _normalizar_texto(alias)
            if alias_norm in vac_ia or vac_ia in alias_norm:
                match_vacuna = True
                break

    if not match_vacuna:
        return False

    # Verificar coincidencia de dosis
    if req_dosis in dosis_ia or dosis_ia in req_dosis:
        return True

    # Equivalencias comunes de dosis
    if "1" in dosis_ia and ("1" in req_dosis or "primera" in req_dosis): return True
    if "2" in dosis_ia and ("2" in req_dosis or "segunda" in req_dosis): return True
    if "3" in dosis_ia and ("3" in req_dosis or "tercera" in req_dosis): return True
    if "refuerzo" in dosis_ia and "refuerzo" in req_dosis: return True
    if "unica" in dosis_ia and "unica" in req_dosis: return True
    if "neonatal" in dosis_ia and "neonatal" in req_dosis: return True

    return False

def evaluar_estado_vacunacion(
    fecha_nacimiento_str: str,
    resultado_ia: Dict[str, Any],
    fecha_referencia: Optional[date] = None
) -> Dict[str, Any]:
    """
    Contrasta las vacunas extraídas por la IA contra las exigidas por el calendario según la edad.
    """
    fecha_nac = parsear_fecha_nacimiento(fecha_nacimiento_str)
    if not fecha_nac:
        return {
            "estado_esquema": "REVISION_REQUERIDA",
            "edad_meses": 0,
            "edad_anos": 0,
            "vacunas_cumplidas": [],
            "vacunas_faltantes": [],
            "requiere_revision_humana": True,
            "motivo_revision": "Fecha de nacimiento inválida o no provista en el padrón."
        }

    edad_meses, edad_anos = calcular_edad_meses(fecha_nac, fecha_referencia)
    vacunas_exigibles = obtener_vacunas_exigibles(edad_meses)
    dosis_detectadas = resultado_ia.get("dosis_aplicadas", [])

    cumplidas = []
    faltantes = []

    for req in vacunas_exigibles:
        encontrada = None
        for dosis in dosis_detectadas:
            if _coincide_vacuna_y_dosis(dosis, req):
                encontrada = dosis
                break

        if encontrada:
            cumplidas.append({
                "vacuna": req.vacuna_nombre,
                "dosis": req.dosis_nombre,
                "fecha_aplicacion": encontrada.get("fecha_aplicacion", "Registrada"),
                "lote": encontrada.get("lote"),
                "confianza": encontrada.get("confianza_lectura", "ALTA")
            })
        else:
            faltantes.append({
                "vacuna": req.vacuna_nombre,
                "dosis": req.dosis_nombre,
                "edad_recomendada_meses": req.edad_meses_minima,
                "edad_obligatoria_meses": req.edad_meses_obligatoria
            })

    # Determinar necesidad de revisión humana
    requiere_revision = resultado_ia.get("requiere_revision_humana", False)
    motivos = []
    if resultado_ia.get("motivo_revision"):
        motivos.append(resultado_ia["motivo_revision"])

    calidad = resultado_ia.get("calidad_imagen", "ALTA")
    if calidad in ["BAJA", "NULA"]:
        requiere_revision = True
        motivos.append(f"Calidad de imagen insuficiente ({calidad}).")

    if not resultado_ia.get("es_carnet_valido", True):
        requiere_revision = True
        motivos.append("El documento adjunto no parece ser un carnet de vacunación válido.")

    # Alerta clínica: si tiene más de 12 meses pero no tiene ninguna vacuna posterior a los 2 meses
    if edad_meses >= 12 and len(cumplidas) <= 4:
        requiere_revision = True
        motivos.append("Esquema anormalmente bajo para la edad (posible carnet incompleto o faltan hojas).")

    # Clasificar estado global:
    # 1. Si requiere revisión humana por cualquier motivo (baja calidad, ilegible, faltan hojas, documento dudoso, etc.),
    #    el estado inicial ES 'REVISION_REQUERIDA' hasta que un auditor humano intervenga y valide.
    # 2. Si la lectura es clara y confiable y no requiere revisión humana, queda como 'AL_DIA' o 'INCOMPLETO'.
    if requiere_revision:
        estado_esquema = "REVISION_REQUERIDA"
    elif len(faltantes) == 0:
        estado_esquema = "AL_DIA"
    else:
        estado_esquema = "INCOMPLETO"

    return {
        "estado_esquema": estado_esquema,
        "edad_meses": edad_meses,
        "edad_anos": edad_anos,
        "total_exigidas": len(vacunas_exigibles),
        "total_cumplidas": len(cumplidas),
        "total_faltantes": len(faltantes),
        "porcentaje_cumplimiento": round((len(cumplidas) / len(vacunas_exigibles) * 100), 1) if vacunas_exigibles else 100.0,
        "vacunas_cumplidas": cumplidas,
        "vacunas_faltantes": faltantes,
        "requiere_revision_humana": bool(requiere_revision),
        "motivo_revision": " | ".join(motivos) if motivos else None
    }
