"""
Calendario Nacional de Vacunación de la República Argentina (0 a 6 años).
Reglas de obligatoriedad, dosis por edad y tolerancias cronológicas.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple

@dataclass
class RequisitoDosis:
    vacuna_id: str
    vacuna_nombre: str
    dosis_nombre: str       # Ej: '1° dosis', '2° dosis', '3° dosis', 'Refuerzo', 'Única'
    edad_meses_minima: int  # Edad mínima requerida para esta dosis
    edad_meses_obligatoria: int # Edad a partir de la cual se considera atrasada/faltante
    tolerancia_dias: int = 15   # Período de gracia
    aliases: List[str] = field(default_factory=list)

# Matriz Oficial del Calendario Nacional Argentino (Población 0 a 6 años)
ESQUEMA_NACIONAL: List[RequisitoDosis] = [
    # Al Nacer
    RequisitoDosis(
        vacuna_id="hepb_neo",
        vacuna_nombre="Hepatitis B",
        dosis_nombre="Neonatal",
        edad_meses_minima=0,
        edad_meses_obligatoria=1,
        aliases=["hepatitis b", "hep b", "hb neonatal", "h-b"]
    ),
    RequisitoDosis(
        vacuna_id="bcg",
        vacuna_nombre="BCG",
        dosis_nombre="Única",
        edad_meses_minima=0,
        edad_meses_obligatoria=1,
        aliases=["bcg", "tuberculosis"]
    ),

    # 2 Meses
    RequisitoDosis(
        vacuna_id="neumo_1",
        vacuna_nombre="Neumococo Conjugada",
        dosis_nombre="1° dosis",
        edad_meses_minima=2,
        edad_meses_obligatoria=3,
        aliases=["neumococo", "prevenar", "neumo 13", "vnc", "prevenar 13"]
    ),
    RequisitoDosis(
        vacuna_id="quintuple_1",
        vacuna_nombre="Quíntuple / Pentavalente",
        dosis_nombre="1° dosis",
        edad_meses_minima=2,
        edad_meses_obligatoria=3,
        aliases=["quintuple", "pentavalente", "dtp-hb-hib", "penta"]
    ),
    RequisitoDosis(
        vacuna_id="polio_1",
        vacuna_nombre="Polio (IPV / Salk)",
        dosis_nombre="1° dosis",
        edad_meses_minima=2,
        edad_meses_obligatoria=3,
        aliases=["ipv", "salk", "polio", "antipoliomielitica", "vpi"]
    ),
    RequisitoDosis(
        vacuna_id="rota_1",
        vacuna_nombre="Rotavirus",
        dosis_nombre="1° dosis",
        edad_meses_minima=2,
        edad_meses_obligatoria=3,
        aliases=["rotavirus", "rotarix", "rotateq"]
    ),

    # 3 Meses
    RequisitoDosis(
        vacuna_id="meningo_1",
        vacuna_nombre="Meningococo",
        dosis_nombre="1° dosis",
        edad_meses_minima=3,
        edad_meses_obligatoria=4,
        aliases=["meningococo", "menveo", "menactra", "nimenrix"]
    ),

    # 4 Meses
    RequisitoDosis(
        vacuna_id="neumo_2",
        vacuna_nombre="Neumococo Conjugada",
        dosis_nombre="2° dosis",
        edad_meses_minima=4,
        edad_meses_obligatoria=5,
        aliases=["neumococo", "prevenar", "neumo 13", "vnc"]
    ),
    RequisitoDosis(
        vacuna_id="quintuple_2",
        vacuna_nombre="Quíntuple / Pentavalente",
        dosis_nombre="2° dosis",
        edad_meses_minima=4,
        edad_meses_obligatoria=5,
        aliases=["quintuple", "pentavalente", "dtp-hb-hib", "penta"]
    ),
    RequisitoDosis(
        vacuna_id="polio_2",
        vacuna_nombre="Polio (IPV / Salk)",
        dosis_nombre="2° dosis",
        edad_meses_minima=4,
        edad_meses_obligatoria=5,
        aliases=["ipv", "salk", "polio", "antipoliomielitica", "vpi"]
    ),
    RequisitoDosis(
        vacuna_id="rota_2",
        vacuna_nombre="Rotavirus",
        dosis_nombre="2° dosis",
        edad_meses_minima=4,
        edad_meses_obligatoria=6,
        aliases=["rotavirus", "rotarix", "rotateq"]
    ),

    # 5 Meses
    RequisitoDosis(
        vacuna_id="meningo_2",
        vacuna_nombre="Meningococo",
        dosis_nombre="2° dosis",
        edad_meses_minima=5,
        edad_meses_obligatoria=6,
        aliases=["meningococo", "menveo", "menactra", "nimenrix"]
    ),

    # 6 Meses
    RequisitoDosis(
        vacuna_id="quintuple_3",
        vacuna_nombre="Quíntuple / Pentavalente",
        dosis_nombre="3° dosis",
        edad_meses_minima=6,
        edad_meses_obligatoria=7,
        aliases=["quintuple", "pentavalente", "dtp-hb-hib", "penta"]
    ),
    RequisitoDosis(
        vacuna_id="polio_3",
        vacuna_nombre="Polio (IPV / Salk)",
        dosis_nombre="3° dosis",
        edad_meses_minima=6,
        edad_meses_obligatoria=7,
        aliases=["ipv", "salk", "polio", "antipoliomielitica", "vpi"]
    ),

    # 12 Meses (1 año)
    RequisitoDosis(
        vacuna_id="neumo_ref",
        vacuna_nombre="Neumococo Conjugada",
        dosis_nombre="Refuerzo",
        edad_meses_minima=12,
        edad_meses_obligatoria=13,
        aliases=["neumococo", "prevenar", "neumo 13", "vnc"]
    ),
    RequisitoDosis(
        vacuna_id="srp_1",
        vacuna_nombre="Triple Viral (SRP)",
        dosis_nombre="1° dosis",
        edad_meses_minima=12,
        edad_meses_obligatoria=13,
        aliases=["triple viral", "srp", "sarampion", "rubeola", "paperas"]
    ),
    RequisitoDosis(
        vacuna_id="hepa_1",
        vacuna_nombre="Hepatitis A",
        dosis_nombre="Única",
        edad_meses_minima=12,
        edad_meses_obligatoria=13,
        aliases=["hepatitis a", "hep a", "ha"]
    ),

    # 15 Meses
    RequisitoDosis(
        vacuna_id="varicela_1",
        vacuna_nombre="Varicela",
        dosis_nombre="1° dosis",
        edad_meses_minima=15,
        edad_meses_obligatoria=16,
        aliases=["varicela", "varilrix"]
    ),
    RequisitoDosis(
        vacuna_id="meningo_ref",
        vacuna_nombre="Meningococo",
        dosis_nombre="Refuerzo",
        edad_meses_minima=15,
        edad_meses_obligatoria=16,
        aliases=["meningococo", "menveo", "menactra", "nimenrix"]
    ),

    # 15 a 18 Meses
    RequisitoDosis(
        vacuna_id="quintuple_ref",
        vacuna_nombre="Quíntuple / Pentavalente",
        dosis_nombre="1° Refuerzo",
        edad_meses_minima=15,
        edad_meses_obligatoria=19,
        aliases=["quintuple", "pentavalente", "dtp-hb-hib", "penta"]
    ),

    # 5 Años (Ingreso Escolar)
    RequisitoDosis(
        vacuna_id="polio_ingreso",
        vacuna_nombre="Polio (IPV / Salk)",
        dosis_nombre="Refuerzo Ingreso Escolar",
        edad_meses_minima=60,
        edad_meses_obligatoria=62,
        aliases=["ipv", "salk", "polio", "antipoliomielitica"]
    ),
    RequisitoDosis(
        vacuna_id="srp_ingreso",
        vacuna_nombre="Triple Viral (SRP)",
        dosis_nombre="2° dosis",
        edad_meses_minima=60,
        edad_meses_obligatoria=62,
        aliases=["triple viral", "srp"]
    ),
    RequisitoDosis(
        vacuna_id="dtp_ingreso",
        vacuna_nombre="Triple Bacteriana Celular (DTP)",
        dosis_nombre="2° Refuerzo",
        edad_meses_minima=60,
        edad_meses_obligatoria=62,
        aliases=["triple bacteriana", "dtp", "difteria tetanos pertussis"]
    ),
    RequisitoDosis(
        vacuna_id="varicela_ingreso",
        vacuna_nombre="Varicela",
        dosis_nombre="2° dosis",
        edad_meses_minima=60,
        edad_meses_obligatoria=62,
        aliases=["varicela", "varilrix"]
    )
]

def calcular_edad_meses(fecha_nacimiento: date, fecha_referencia: Optional[date] = None) -> Tuple[int, int]:
    """Calcula la edad en meses cumplidos y días adicionales."""
    if not fecha_referencia:
        fecha_referencia = date.today()
    
    anos = fecha_referencia.year - fecha_nacimiento.year
    meses = fecha_referencia.month - fecha_nacimiento.month
    dias = fecha_referencia.day - fecha_nacimiento.day

    if dias < 0:
        meses -= 1

    total_meses = (anos * 12) + meses
    return max(0, total_meses), anos

def obtener_vacunas_exigibles(edad_meses: int) -> List[RequisitoDosis]:
    """Retorna la lista de dosis que un niño debería tener aplicadas a su edad."""
    return [req for req in ESQUEMA_NACIONAL if edad_meses >= req.edad_meses_minima]
