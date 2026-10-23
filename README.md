# 💉 Sistema de Digitalización y Auditoría Inteligente de Certificados de Vacunación
### Municipalidad de Tres de Febrero — Dirección de Educación y Primera Infancia

Este proyecto automatiza de punta a punta la **extracción, auditoría visual con Inteligencia Artificial Multimodal (Gemini Vision)** y **validación clínica** de los certificados de vacunación de más de **2.195 niños inscriptos** en los Jardines Municipales y Espacios de Primera Infancia (EPIs) del ciclo lectivo 2026.

---

## 🎯 Objetivos Resueltos

1. **Lectura Masiva Asistida por IA:** Nadie leía manualmente más de 2.000 carnets. Ahora Gemini Vision analiza cada imagen (incluso si está rotada 90°/180°, con sellos, firmas manuscritas o etiquetas adhesivas de viales).
2. **Evaluación de Calidad del Dato:** Clasificación automática de la legibilidad de la imagen (`ALTA`, `MEDIA`, `BAJA`, `INVÁLIDA`) y detección de documentos erróneos (ej. fotos de DNI o partidas subidas por error en la casilla de vacunas).
3. **Contraste Clínico por Edad:** Cruce automático entre la fecha de nacimiento del alumno y el **Calendario Nacional de Vacunación de Argentina**, determinando qué dosis exactas le faltan o están atrasadas para su edad.
4. **Human-in-the-Loop (Auditoría Humana Asistida):** Panel web con visualizador dividido (*split-screen*) que presenta la foto del carnet (con herramientas de rotación y zoom) junto a las vacunas leídas por IA, alertando prioritariamente sobre los casos donde la calidad es baja o hay dudas clínicas.
5. **Exportación a Excel Ejecutivo:** Reporte multi-hoja con semáforos de colores para la toma de decisiones, campañas territoriales de vacunación y derivación a centros de salud municipales.

---

## 🏗️ Arquitectura de Componentes

```
digitalizacion certificados/
│
├── ⚙️ config.py                 # Rutas, credenciales Mi3F y configuración global
├── 💉 calendario_vacunacion.py  # Esquema oficial argentino (BCG, Pentavalente, IPV, Neumo, etc.)
├── 🌐 extractor_mi3f.py         # Descarga selectiva de adjuntos desde Mi3F (ahorra 95% de ancho de banda)
├── 👁️ auditor_ia.py             # Motor Multimodal Gemini Vision (OCR estructurado + scoring de certeza)
├── 🩺 evaluador_clinico.py      # Algoritmo de contraste: Vacunas detectadas vs. requeridas por edad
├── 📊 exportador_excel.py       # Generador de reportes Excel con semáforos y filtros de prioridad
├── 🖥️ panel_web.py              # Servidor API REST y visor interactivo local
│
├── 🎨 frontend/
│   └── index.html               # Interfaz SPA (Guía de Estilo Muni 3F: Azul #163C68, Naranja #F69321)
│
├── 🚀 INICIAR_DIGITALIZADOR.bat # Lanzador en 1 clic para Windows
└── 💾 resultados_auditoria/     # Base SQLite local y reportes Excel generados
```

---

## 🚀 Inicio Rápido

### Opción 1: Con 1 Clic (Recomendado)
Hacer doble clic en:
```
INICIAR_DIGITALIZADOR.bat
```
El sistema iniciará el servidor local y abrirá automáticamente el panel en tu navegador:
`http://localhost:8080`

### Opción 2: Desde la Consola (PowerShell o CMD)
```powershell
python main.py
```

### Opciones de Línea de Comandos:
- Recargar el padrón desde la Ficha Social / Mi3F:
  ```powershell
  python main.py --cargar-padron
  ```
- Generar un nuevo reporte Excel consolidado:
  ```powershell
  python main.py --exportar-excel
  ```

---

## 🔗 Integración con Mi3F y Ficha Social
- El sistema sincroniza de forma transparente con el padrón maestro ubicado en `cruce informacion datos/Inscripciones_Jardines_2026.xlsx`.
- En caso de necesitar descargar un carnet no presente en el almacenamiento local, se conecta automáticamente a:
  `https://backend.mistramites.tresdefebrero.gob.ar/tra_tramites_bandeja_unica_am.php?tramiteproductoracod={Codigo}`
  utilizando la sesión activa de la municipalidad.
