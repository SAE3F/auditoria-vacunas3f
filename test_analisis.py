from pathlib import Path
from auditor_ia import analizar_certificado_con_ia
from evaluador_clinico import evaluar_estado_vacunacion
import json

img_path = Path(r"c:\Users\Matias\Desktop\digitalizacion certificados\certificados_descargados\340844_584972_vacunas.jpg")
print("Analizando carnet 340844...")
res_ia = analizar_certificado_con_ia([img_path])
print("Calidad imagen:", res_ia.get("calidad_imagen"))
print("Rotación detectada:", res_ia.get("rotacion_detectada_grados"))
print("Requiere revisión humana:", res_ia.get("requiere_revision_humana"))
print("Motivo:", res_ia.get("motivo_revision"))
print("Dosis detectadas total:", len(res_ia.get("dosis_aplicadas", [])))
for d in res_ia.get("dosis_aplicadas", []):
    print(f"  - {d.get('vacuna_canonica')} ({d.get('dosis')}): {d.get('fecha_aplicacion')} [Lote: {d.get('lote')}]")

res_clinico = evaluar_estado_vacunacion("19/05/2023", res_ia)
print("\n--- EVALUACION CLINICA ---")
print("Estado esquema:", res_clinico.get("estado_esquema"))
print("Edad meses:", res_clinico.get("edad_meses"))
print("Total exigidas:", res_clinico.get("total_exigidas"))
print("Total cumplidas:", res_clinico.get("total_cumplidas"))
print("Total faltantes:", res_clinico.get("total_faltantes"))
print("Porcentaje cumplimiento:", res_clinico.get("porcentaje_cumplimiento"), "%")
if res_clinico.get("vacunas_faltantes"):
    print("Vacunas faltantes:")
    for f in res_clinico["vacunas_faltantes"]:
        print(f"  * {f['vacuna']} ({f['dosis']}) - Exigible a los {f['edad_obligatoria_meses']} meses")
