# 📋 Especificación y Arquitectura: Digitalización y Auditoría Inteligente de Certificados de Vacunación — Jardines 3F

Este proyecto automatiza la descarga, extracción con Inteligencia Artificial Multimodal (Gemini Vision), validación clínica según el **Calendario Nacional de Vacunación de Argentina**, y auditoría humana asistida de los certificados de más de 2.000 niños inscriptos en los Jardines Municipales y EPIs de Tres de Febrero.

---

## 🔍 1. Hallazgos del Diagnóstico del Ecosistema 3F

1. **Padrón Base (Ficha Única Social / Mi3F):**
   - El archivo maestro de inscripciones ya se encuentra consolidado en el municipio (`Inscripciones_Jardines_2026.xlsx` en la carpeta `cruce informacion datos`).
   - Contiene **2.195 niños con estado `Inscripto`**.
   - Campos clave ya vinculados: `Código` (ID de trámite en el backoffice), `Id`, `Nombre del solicitante`, `Apellido del solicitante`, `Número de documento.2.1` (DNI), `Fecha de Nacimiento.2`, `Jardin a inscribir`, `Sala a la que se inscribe`.

2. **Estructura del Backoffice (`backend.mistramites.tresdefebrero.gob.ar`):**
   - Cada expediente individual se consulta mediante:  
     `https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_unica_am.php?tramiteproductoracod={Código}`
   - El bloque **"6- Certificados de vacunación actualizados"** contiene enlaces directos de descarga:  
     `tra_tramites_bandeja_am_documentos_download.php?codigo={ID_DOC}&seccion=243&tramiteproductora={Código}`
   - **Optimización de ancho de banda:** Descargar directamente el documento 6 (~150 KB a 500 KB por imagen) en lugar de descargar el archivo `.zip` completo de cada expediente (~9 MB) ahorra **más del 95% de tiempo y transferencia de red** para los 2.200 expedientes.

3. **Retos de las Imágenes de Certificados:**
   - Fotos tomadas con celular en diversas orientaciones (frecuentemente rotadas 90° o 180°).
   - Variabilidad de soportes: Libreta Sanitaria provincial, Carnet Unificado Nacional, hojas de vacunatorios privados.
   - Manuscritos, sellos, firmas y etiquetas adhesivas superpuestas sobre las casillas de fechas.

---

## 🏗️ 2. Arquitectura del Proyecto

```
digitalizacion certificados/
│
├── ⚙️ config.py                 # Credenciales de acceso Mi3F, paths, API Keys y configuración global
├── 💉 calendario_vacunacion.py  # Reglas oficiales del Calendario Nacional de Vacunación (Argentina)
├── 🌐 extractor_mi3f.py         # Descarga selectiva y automatizada de imágenes desde Mi3F
├── 👁️ auditor_ia.py             # Motor Multimodal de Visión IA (Gemini 2.5 Flash) con scoring de calidad
├── 🩺 evaluador_clinico.py      # Motor de contraste: Vacunas Detectadas vs. Vacunas Requeridas por Edad
├── 📊 exportador_excel.py       # Generador de reportes ejecutivos en Excel con alertas y métricas
├── 🖥️ panel_web.py              # Servidor web local para auditoría visual humana y corrección ágil
│
├── 🎨 frontend/
│   ├── index.html               # Interfaz interactiva de auditoría (Split Screen carnet + datos IA)
│   └── styles.css               # Diseño institucional Muni 3F (Azul #163C68, Naranja #F69321)
│
├── 📁 certificados_descargados/ # Almacén local de imágenes descargadas indexadas por Código y DNI
└── 💾 resultados_auditoria/     # Base SQLite y registros JSON estructurados de cada carnet
```

---

## 💉 3. Matriz del Calendario Nacional de Vacunación (0 a 5 años)

El motor evalúa automáticamente el esquema obligatorio según la edad exacta calculada desde `Fecha de Nacimiento.2`:

| Edad Hito | Vacuna Oficial | Dosis Requerida |
| :--- | :--- | :--- |
| **Recién Nacido** | Hepatitis B | 1 dosis neonatal (primeras 12h) |
| **Recién Nacido** | BCG | 1 dosis única (antes del alta de maternidad) |
| **2 Meses** | Neumococo Conjugada | 1° dosis |
| **2 Meses** | Quíntuple / Pentavalente | 1° dosis |
| **2 Meses** | Polio IPV (Salk) | 1° dosis |
| **2 Meses** | Rotavirus | 1° dosis |
| **3 Meses** | Meningococo | 1° dosis |
| **4 Meses** | Neumococo Conjugada | 2° dosis |
| **4 Meses** | Quíntuple / Pentavalente | 2° dosis |
| **4 Meses** | Polio IPV (Salk) | 2° dosis |
| **4 Meses** | Rotavirus | 2° dosis |
| **5 Meses** | Meningococo | 2° dosis |
| **6 Meses** | Quíntuple / Pentavalente | 3° dosis |
| **6 Meses** | Polio IPV (Salk) | 3° dosis |
| **6 a 24 Meses** | Gripe | Anual (2 dosis en primovacunación, 1 dosis anual) |
| **12 Meses (1 año)** | Neumococo Conjugada | Refuerzo |
| **12 Meses (1 año)** | Triple Viral (SRP) | 1° dosis |
| **12 Meses (1 año)** | Hepatitis A | Dosis única |
| **15 Meses** | Varicela | 1° dosis |
| **15 Meses** | Meningococo | Refuerzo |
| **15 a 18 Meses** | Quíntuple / Pentavalente | 1° Refuerzo |
| **5 Años (Ingreso)**| Polio IPV (Salk) | Refuerzo |
| **5 Años (Ingreso)**| Triple Viral (SRP) | 2° dosis |
| **5 Años (Ingreso)**| Triple Bacteriana Celular (DTP) | 2° Refuerzo |
| **5 Años (Ingreso)**| Varicela | 2° dosis |

---

## 🚦 4. Clasificación de Calidad y Human-in-the-Loop

La IA clasifica cada certificado en tres dimensiones de certeza:

1. **Semáforo de Calidad de Imagen (`calidad_imagen`):**
   - 🟢 **Alta:** Nitidez total, texto y fechas claramente identificables.
   - 🟡 **Media:** Alguna sección con menor luz, sello semi-borroso, pero legible en lo sustancial.
   - 🔴 **Baja:** Borrosa, desenfocada, reflejo flash sobre las casillas, resolución insuficiente.
   - ⚠️ **Inválida / Error:** No es un carnet (ej. subió el DNI de nuevo, factura de luz, imagen en blanco).

2. **Flag de Revisión Humana Obligatoria (`requiere_revision_humana: true/false`):**
   - Se activa si:
     - Calidad es Baja o Inválida.
     - Hay discrepancia notable entre la edad del niño y las vacunas leídas (ej. tiene 3 años pero no se detecta ninguna vacuna posterior a los 2 meses, sugiriendo que falta fotografiar la segunda cara del carnet).
     - La IA duda de una fecha manuscrita crítica.

3. **Panel de Verificación Rápida:**
   - La persona revisora ve la imagen del carnet a la izquierda con botones para rotar 90°/180°, invertir color o hacer zoom.
   - A la derecha ve la tabla precargada por la IA y puede marcar con un clic "Aprobar", "Corregir fecha" o "Rechazar certificado / Solicitar reenvío a la familia".
