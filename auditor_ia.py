"""
Motor de Visión IA Multimodal (Gemini) para Digitalización y Auditoría de Certificados de Vacunación.
Extrae registros de dosis, evalúa calidad del documento y clasifica necesidad de revisión humana.
"""
import os
import json
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
import io
import fitz
from PIL import Image

from config import GEMINI_API_KEY, MODELO_VISION

PROMPT_SISTEMA_VACUNACION = """
Sos un médico pediatra auditor y especialista en lectura de registros sanitarios de la República Argentina.
Tu tarea es analizar minuciosamente una o más imágenes de un Certificado / Carnet de Vacunación infantil argentino (Carnet Unificado Nacional, Libreta Sanitaria de la Provincia de Buenos Aires o certificados de vacunatorios públicos/privados).

El objetivo es extraer con máxima precisión cada vacuna y dosis aplicada, y evaluar con rigor la calidad de la imagen para determinar si se necesita intervención de un auditor humano.

IMPORTANTE SOBRE LA IMAGEN:
1. La imagen puede estar rotada (boca abajo a 180°, girada 90° o torcida). Debes leerla correctamente sin importar su orientación y reportar la rotación necesaria para que un humano la vea derecha (0, 90, 180 o 270 grados).
2. Pueden existir etiquetas adhesivas de viales (stickers con nombre comercial como 'Menveo', 'Prevenar', 'Viraflu', 'Rotarix', etc.), sellos redondos de vacunatorios y firmas de enfermeros sobre las casillas de fechas.
3. Las fechas manuscritas suelen estar en formato DD/MM/AA o DD/MM/AAAA.
4. Si una casilla está en blanco o solo tiene una raya sin fecha ni sello, esa dosis NO fue aplicada.

DEBES RESPONDER EXCLUSIVAMENTE CON UN OBJETO JSON VÁLIDO CON LA SIGUIENTE ESTRUCTURA EXACTA:
{
  "es_carnet_valido": true/false, // false si subieron un DNI, partida de nacimiento, factura u otro documento ajeno
  "calidad_imagen": "ALTA" | "MEDIA" | "BAJA" | "NULA",
  "rotacion_detectada_grados": 0 | 90 | 180 | 270,
  "tipo_soporte": "Carnet Unificado Nacional" | "Libreta Sanitaria PBA" | "Certificado Privado" | "Otro",
  "datos_identificacion_visibles": {
    "nombre_nino": "Nombre si figura en el carnet o null",
    "dni_nino": "DNI si figura o null",
    "fecha_nacimiento": "Fecha si figura o null"
  },
  "dosis_aplicadas": [
    {
      "vacuna_canonica": "BCG" | "Hepatitis B" | "Neumococo Conjugada" | "Quintuple" | "Polio IPV" | "Rotavirus" | "Meningococo" | "Triple Viral SRP" | "Hepatitis A" | "Varicela" | "Triple Bacteriana Celular DTP" | "Gripe" | "COVID-19" | "Otra",
      "dosis": "Neonatal" | "1° dosis" | "2° dosis" | "3° dosis" | "1° Refuerzo" | "2° Refuerzo" | "Refuerzo" | "Única" | "Anual",
      "fecha_aplicacion": "DD/MM/AAAA" | "AAAA-MM-DD",
      "lote": "Texto del lote si es visible o null",
      "institucion_o_firma": "Texto del sello o enfermero si es visible o null",
      "confianza_lectura": "ALTA" | "MEDIA" | "DUDOSA"
    }
  ],
  "requiere_revision_humana": true/false,
  "motivo_revision": "Explicación detallada del motivo por el cual un humano debe revisar (ej: 'Fecha de Menveo 2° dosis ilegible', 'Imagen cortada en el margen inferior', 'Baja resolución') o null si es confiable",
  "observaciones_adicionales": "Notas clínicas relevantes (ej: carnet con sellos de CABA, Libreta PBA desgastada, etc.)"
}
"""

REGLAS_APRENDIDAS_FILE = Path(__file__).resolve().parent / "reglas_aprendidas.json"

def obtener_prompt_con_aprendizaje() -> str:
    """Carga dinámicamente las reglas aprendidas del feedback humano y las inyecta en el prompt."""
    reglas_txt = ""
    if REGLAS_APRENDIDAS_FILE.exists():
        try:
            with open(REGLAS_APRENDIDAS_FILE, "r", encoding="utf-8") as f:
                reglas = json.load(f)
                if reglas:
                    reglas_txt = "\n\n### REGLAS Y APRENDIZAJES APORTADOS POR AUDITORES HUMANOS (PRIORITARIAS):\n"
                    for r in reglas[-10:]: # Inyectar las últimas 10 reglas aprendidas
                        reglas_txt += f"- {r.get('regla')}\n"
        except Exception:
            pass
    return PROMPT_SISTEMA_VACUNACION + reglas_txt

def destilar_regla_de_feedback(codigo_tramite: str, diagnostico_ia_previo: str, correccion_humana: str, api_key: Optional[str] = None) -> Optional[str]:
    """Usa Gemini para convertir una corrección humana en una regla general de aprendizaje."""
    key = api_key or GEMINI_API_KEY
    if not key or not correccion_humana.strip():
        return None
    try:
        from google import genai
        client = genai.Client(api_key=key)
        prompt_meta = f"""
Actúa como un sintetizador de reglas de aprendizaje automático para auditoría de salud.
Un auditor humano corrigió la lectura de un carnet de vacunación:
- Lectura previa de la IA: {diagnostico_ia_previo}
- Corrección / Indicación del Auditor Humano: {correccion_humana}

Genera UNA ÚNICA regla o instrucción clara y concisa (en 1 oración, en español) que le sirva a la IA para no volver a equivocarse en carnets similares en el futuro.
Responde ÚNICAMENTE con el texto de la regla, sin introducciones ni comillas.
"""
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_meta)
        nueva_regla = resp.text.strip().strip('"').strip("'")
        
        # Guardar en archivo JSON
        reglas = []
        if REGLAS_APRENDIDAS_FILE.exists():
            try:
                with open(REGLAS_APRENDIDAS_FILE, "r", encoding="utf-8") as f:
                    reglas = json.load(f)
            except Exception:
                reglas = []
        
        reglas.append({
            "id": len(reglas) + 1,
            "fecha": time.strftime("%Y-%m-%d %H:%M:%S") if "time" in globals() else "2026-10-18",
            "tramite_referencia": codigo_tramite,
            "regla": nueva_regla,
            "origen": f"Feedback humano: {correccion_humana[:60]}"
        })

        with open(REGLAS_APRENDIDAS_FILE, "w", encoding="utf-8") as f:
            json.dump(reglas, f, indent=2, ensure_ascii=False)
            
        return nueva_regla
    except Exception as e:
        print(f"Error destilando regla de feedback: {e}")
        return None

def analizar_certificado_con_ia(rutas_imagenes: List[Path], api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Envía una o más imágenes a Gemini Multimodal para extraer vacunas y clasificar calidad.
    """
    key = api_key or GEMINI_API_KEY
    if not key:
        return {
            "es_carnet_valido": False,
            "calidad_imagen": "NULA",
            "requiere_revision_humana": True,
            "motivo_revision": "Falta configurar la API Key de Gemini (GEMINI_API_KEY).",
            "dosis_aplicadas": [],
            "error": "SIN_API_KEY"
        }

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)

        partes_contenido = []
        for ruta in rutas_imagenes:
            if not ruta.exists():
                continue

            # Soporte completo para PDFs (libretas sanitarias escaneadas)
            if ruta.suffix.lower() == ".pdf":
                try:
                    doc_pdf = fitz.open(ruta)
                    for num_pag in range(len(doc_pdf)):
                        pag = doc_pdf[num_pag]
                        pix = pag.get_pixmap(dpi=150)
                        img_pag = Image.open(io.BytesIO(pix.tobytes("png")))
                        if img_pag.mode not in ("RGB", "L"):
                            img_pag = img_pag.convert("RGB")
                        partes_contenido.append(img_pag)
                    doc_pdf.close()
                except Exception as pdf_err:
                    print(f"Error procesando PDF {ruta}: {pdf_err}")
            else:
                try:
                    img = Image.open(ruta)
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    partes_contenido.append(img)
                except Exception as img_err:
                    print(f"Error abriendo imagen {ruta}: {img_err}")

        if not partes_contenido:
            return {
                "es_carnet_valido": False,
                "calidad_imagen": "NULA",
                "requiere_revision_humana": True,
                "motivo_revision": "No se encontraron archivos válidos de certificado para analizar.",
                "dosis_aplicadas": []
            }

        partes_contenido.append(obtener_prompt_con_aprendizaje())

        response = client.models.generate_content(
            model=MODELO_VISION,
            contents=partes_contenido,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

        texto_respuesta = response.text.strip()
        resultado = json.loads(texto_respuesta)
        return resultado

    except Exception as e:
        return {
            "es_carnet_valido": False,
            "calidad_imagen": "NULA",
            "requiere_revision_humana": True,
            "motivo_revision": f"Error al procesar con IA: {str(e)}",
            "dosis_aplicadas": [],
            "error": str(e)
        }
