# Diagnóstico y proyección de asignados de performance — CO 2026 (temporada mundial)

**Fecha:** 2026-06-15 · **Autor:** Camilo Otoya — growth/marketing
**Tipo de entregable:** Informe HTML narrativo (patrón `analisis-asignados-co` / `analisis-mty-multimedios`)
**Scope:** Colombia · fuentes de **performance** (con inversión paid): **WEB · Lead Forms · Habímetro (Estudio Inmueble)**
**Slug / ubicación:** `tableros-marketing/diagnostico-performance-co/`

---

## 1. Problema y objetivo

En la temporada del **Mundial 2026** (arranca 11-jun) coinciden tres presiones sobre los asignados de marketing CO:

1. **Lunes festivos** de junio en el calendario colombiano (Ley Emiliani) → menos días hábiles efectivos de demanda.
2. **Fuerte inversión de pauta política** por las **elecciones presidenciales 2026** (1ª vuelta 31-may, 2ª vuelta 21-jun — *fechas a verificar y anclar en el build*) → inflación de subasta → CPM/CPC arriba.
3. La **caída estructural de la conversión registro→asignado (−16%)** ya documentada en *Análisis de asignados de marketing — Colombia 2026* (Backbone nuevo, 12-mar).

**Objetivo:** aterrizar a la compañía en por qué no estamos cumpliendo las metas, hacer un diagnóstico total **por fuente de performance**, y entregar una **proyección Q2+Q3** en dos escenarios (optimista y conservador). El indicador de conversión registro→asignado debe estar presente para confirmar que la tesis del −16% sigue viva.

## 2. Marco causal — descomposición en 3 palancas (por fuente)

Identidad multiplicativa que estructura todo el informe:

```
Asignados = Inversión × (1 / CPL) × CVR(registro → asignado)
```

Cada palanca aísla un culpable separable:

| Palanca | Métrica | Culpable principal | Estado |
|---|---|---|---|
| **Inversión** | spend por fuente | decisión propia / inflación de subasta | a medir |
| **Eficiencia de captación** | CPL = spend/registros; CPM; CPC | pauta política (elecciones) | a medir |
| **Conversión** | CVR = asignados/registros | Backbone (−16%, estructural) | verificar vigencia |
| *(transversal)* | **Demanda** | registros totales | Mundial + lunes festivos | a medir |

La gracia del marco: separa **lo que ya sabíamos** (Backbone) de **lo nuevo de esta temporada** (elecciones + mundial + festivos).

## 3. Granularidad

- **Series principales: semanales** (no mensuales), desde la primera semana de 2026.
- **Zoom diario desde el 1-may-2026** (~6 semanas hasta hoy 15-jun): series diarias de spend, CPM/CPC, registros, asignados y CVR por fuente, con **hitos anotados y descritos** en el relato:
  - 11-jun: arranque Mundial 2026.
  - 1ª y 2ª vuelta presidencial (fechas a verificar).
  - Lunes festivos de junio (Ley Emiliani — verificar fechas exactas).
  - Saltos puntuales de CPM/CPC o caídas de registros que ameriten explicación.

## 4. Estructura del informe (capítulos)

- **Resumen ejecutivo** — gap total Q2, su descomposición en las 3 palancas, y los dos escenarios Q2+Q3 en una frase cada uno.
- **Cap. 1 — Dónde estamos vs las 3 varas:** cumplimiento semanal por fuente vs **(a)** meta original, **(b)** meta recalibrada −16% (post-Backbone), **(c)** YoY 2025. Mostrar que contra la vara recalibrada el equipo cumple y contra la original no.
- **Cap. 2 — Palanca inversión & costos:** spend, CPM, CPC por fuente, serie semanal 2026 + zoom diario desde 1-may. Overlay de ventana electoral y arranque de mundial para evidenciar el salto de CPM.
- **Cap. 3 — Palanca CPL & captación:** CPL por fuente (spend/registros) y registros por fuente. Cuánto del menor volumen es "menos pesos eficientes" vs "menos demanda".
- **Cap. 4 — Palanca conversión:** CVR registro→asignado por fuente, serie semanal 2026, confirmando/actualizando el −16%. Contrapeso positivo (asignado→cita +2pp post-Backbone).
- **Cap. 5 — Proyección Q2+Q3:** escenarios conservador y optimista por fuente, con supuestos explícitos por palanca, suma vs meta (original y recalibrada). Cono optimista–conservador.

## 5. Escenarios de proyección (Q2 + Q3, hasta sep)

Ambos parten del **run-rate real reciente por fuente** y aplican factores semanales por palanca:

- **Conservador:** CPM elevado persiste hasta 2ª vuelta y se relaja lento; drag del mundial hasta 19-jul; CVR se queda en el piso post-Backbone. Q3 recupera parcial.
- **Optimista:** CPM normaliza rápido tras 2ª vuelta; fin de mundial (19-jul) libera demanda; el modelo termina de aprender y CVR recupera hacia el +2pp de calidad downstream. Rebote claro en Q3.

Los supuestos numéricos por palanca/semana se fijan en el `build_data.py` y se documentan visibles en el informe.

## 6. Plomería técnica (datos)

Todas las fuentes verificadas con acceso BQ el 2026-06-15.

### Atribución por UTM (eje central, por pedido del usuario)
Tanto **inversión** como **registros** se clasifican por la **misma taxonomía UTM**, vía el diccionario:

- `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  - Llave: `campana_mercadeo_original`
  - Devuelve: `mkt_channel_big`, `mkt_media`, `mkt_platform`, `mkt_channel_medium/small`, `mkt_campaign_name`
  - Valores Paid relevantes de `mkt_channel_big`: **WEB**, **lead_forms**, **Estudio Inmueble** (= Habímetro), Brand.
  - Filtro de performance: `mkt_media = 'Paid'`.

### Tablas
| Dato | Tabla | Llave / nota |
|---|---|---|
| Inversión diaria (spend, clicks, impressions) | `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co` | `campana_original` → diccionario UTM → `mkt_channel_big` + `mkt_media='Paid'` |
| Registros + asignados + CVR por fuente | `funnel_registros.sql` (base `papyrus-data.habi_wh_bi.funnel_diarios_col` + histórico estados) | ya produce registros (t) y asignados (asg) por `fuente_id`/período |
| Asignados oficiales (WBR) | `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` | campo `fuente`; fuente oficial del número |
| Metas vs actual por fuente/semana | `okr-marketing/data.json` (sheet Cumplimiento Fuentes) | trae meta, mtd, actual, prev por fuente y semana |

### Reconciliación a resolver en implementación
- El mart WBR clasifica asignados por `fuente`; el diccionario UTM clasifica por `mkt_channel_big`. Verificar que las etiquetas reconcilian (WEB / lead_forms / Habímetro≈Estudio Inmueble) y documentar cualquier desfase. La fuente de verdad del número de asignados sigue siendo el mart WBR.
- Confirmar la columna `campana_mercadeo_original` en la tabla de registros para el join del CPL (verificar en `funnel_diarios_col` / `tabla_inmuebles_general`).
- CPL = spend / registros, ambos filtrados a la misma fuente y a `mkt_media='Paid'`.

### Pipeline
`query.sql` (CTEs: asignados+metas, inversión/CPM/CPC por UTM, registros+CVR por UTM, escenarios) → `build_data.py` → `data.json` → `index.html` autocontenido con Chart.js. Entrada en el hub vía `meta.json` con campo `order` (al final de la sección que corresponda).

## 7. Fuera de alcance (YAGNI)
- México (solo CO en esta versión).
- Fuentes sin inversión performance (CRM, Broker, Comercial) — solo aparecen como contexto dentro del TOTAL, sin análisis de costos.
- Tablero interactivo / auto-refresh (este entregable es informe narrativo; el seguimiento vivo ya vive en WBR 2.0 y OKR).

## 8. Criterios de éxito
- El lector ejecutivo entiende, por fuente, cuánto del incumplimiento es Backbone (viejo) vs elecciones+mundial+festivos (nuevo).
- CPM/CPC/CPL por fuente con la ventana electoral y el mundial visibles en las series.
- Conversión registro→asignado confirmando la tesis del −16%.
- Proyección Q2+Q3 con banda optimista–conservador y supuestos explícitos.
- Tono ejecutivo (ver memoria `feedback_informe_tono`): sin jerga, framing positivo + ROI donde aplique.
