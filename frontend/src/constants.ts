import type { ScreenStep } from './types'

export const STEP_LABELS: Record<ScreenStep, string> = {
  IDLE: 'Listo',
  PROCESSING: 'Procesando',
  HITL_WAITING: 'Revisión humana',
  COMPLETED: 'Completado',
}

export const STEP_INDICATOR: Record<ScreenStep, string> = {
  IDLE: 'bg-slate-500',
  PROCESSING: 'bg-amber-400 animate-pulse',
  HITL_WAITING: 'bg-violet-400 animate-pulse',
  COMPLETED: 'bg-emerald-400',
}

export const EJEMPLO_SOLICITUD =
  '¿Cuál es el panorama actual del mercado de hamburgueserías smash en La Plata para 2026?'

export const INFORME_PRELIMINAR = `## Panorama del mercado smash burger — La Plata 2026

El mercado local muestra **consolidación de marcas premium** con foco en carne smash, papas artesanales y experiencias rápidas de alta calidad.

### Hallazgos clave
- Crecimiento sostenido del segmento premium urbano
- Ticket promedio entre $8.000 y $12.000 ARS
- Mayor competencia en zona centro y Gonnet

### Próximos pasos sugeridos
Validar precios actuales y horarios de apertura de los tres locales líderes.`

export const INFORME_FINAL = `## Informe definitivo — Mercado smash burger La Plata 2026

### Resumen ejecutivo
El ecosistema gastronómico platense ha madurado hacia formatos **fast-casual premium**. Las smash burgers lideran la preferencia en consumidores de 22–35 años.

### Mapa competitivo
1. **Smash Lab** — Referente en técnica y consistencia
2. **Burga Co.** — Fuerte presencia en delivery
3. **Fire Patty** — Apuesta por ingredientes locales

### Conclusión
El mercado permanece atractivo para nuevas propuestas diferenciadas en experiencia de local y storytelling de producto.`

export const LOGS_TECNICOS = [
  '[supervisor] Plan generado · 2 subtareas',
  '[investigador] Tavily · 4 fuentes indexadas',
  '[ejecutor] Informe preliminar redactado',
  '[revisor] Score 4/5 · Aprobado técnicamente',
  '[hitl] Esperando feedback humano…',
]

export const AGENTES_GRAFO = [
  { id: 'supervisor', label: 'Supervisor', desc: 'Planificación' },
  { id: 'investigador', label: 'Investigador', desc: 'Búsqueda Tavily' },
  { id: 'ejecutor', label: 'Ejecutor', desc: 'Redacción' },
  { id: 'revisor', label: 'Revisor', desc: 'Control de calidad' },
] as const
