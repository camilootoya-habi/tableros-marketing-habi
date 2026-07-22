# Ledger continuo de A/B testing de plantillas — diseño

**Fecha:** 2026-07-22 · **Repo:** `tableros-marketing` (hub) · **Tablero:** `marketing-loop`
**Contexto:** vamos a hacer A/B de plantillas de WhatsApp con frecuencia. Hoy la página de
Documentación de cada país muestra una **tarjeta única** con el resultado del primer experimento.
Se reemplaza por un **ledger continuo**: una tabla con una fila por prueba, alimentada por datos
(no escrita a mano), para capturar resultados de forma sostenible prueba tras prueba.

## Objetivo
Que abrir/cerrar una prueba A/B sea agregar/editar **una línea de metadata**, y que la tabla del
tablero se llene sola con los resultados (por brazo) y el veredicto bayesiano de cada prueba,
por país, en la página de Documentación.

## No-objetivos (YAGNI)
- No se automatiza el registro desde el motor (`marketing-loop-sellers`); abrir/cerrar prueba es un
  paso humano (agregar/editar el JSON) — consistente con que cerrar el A/B ya es un paso humano en el motor.
- No se congelan snapshots: la ventana de una prueba cerrada es fija y el mart retiene desde
  2026-01-01, así que recalcular en cada build da el mismo número. No hace falta persistir resultados.
- No se toca la tabla **A/B de plantillas** en vivo ni el veredicto del dashboard principal (siguen
  para el día a día del experimento activo).

## Arquitectura (3 piezas)

### 1. Fuente de verdad — `marketing-loop/ab_experiments.json` (versionado)
Arreglo de registros; **solo metadata**, un objeto por prueba×país:
```json
[
  { "n": 1, "pais": "MX", "nombre": "tpl_v1_vs_v2_jul26",
    "control": "reactivacion_sellers_mx_v1_jul26",            "control_label": "v1 · control",
    "experimento": "reactivacion_sellers_mx_v2_oferta_jul26", "experimento_label": "v2 · oferta",
    "desde": "2026-07-16", "hasta": "2026-07-22",
    "estado": "cerrado", "ganador": "experimento", "nota": "" },
  { "n": 1, "pais": "CO", "nombre": "tpl_co_v1_vs_v2_jul26",
    "control": "reactivacion_sellers_co_v1_jul26",            "control_label": "v1 · control",
    "experimento": "reactivacion_sellers_co_v2_oferta_jul26", "experimento_label": "v2 · oferta",
    "desde": "2026-07-17", "hasta": "2026-07-22",
    "estado": "cerrado", "ganador": "experimento",
    "nota": "adoptado por analogía con MX (sin muestra propia suficiente)" }
]
```
Campos:
- `n` — número de prueba dentro del país (1, 2, …).
- `control` / `experimento` — nombre exacto de la plantilla Infobip de cada brazo.
- `*_label` — etiqueta corta para la UI (ej. "v1 · control", "v2 · oferta").
- `desde` — fecha (YYYY-MM-DD, local del país) de inicio de la prueba.
- `hasta` — fecha de cierre; **`null` si está en curso** (ventana = hasta hoy).
- `estado` — `"activo"` | `"cerrado"`.
- `ganador` — `"control"` | `"experimento"` | `null` (decisión **humana** adoptada; puede diferir
  del veredicto estadístico, ej. CO adoptado por analogía). Nullable mientras `activo`.
- `nota` — texto libre opcional (ej. la salvedad de CO).

**Abrir prueba** = append de un objeto con `estado:"activo"`, `hasta:null`, `ganador:null`.
**Cerrar prueba** = set `hasta`, `estado:"cerrado"`, `ganador`.

### 2. Backend — `ab_experimentos(pais)` en `build_data.py`
Para cada registro del país, calcula sobre su ventana `[desde, hasta]` (si `hasta` es `null`, hasta
hoy), desde el mart (`mart_infobip_messages_daily_{pais}`) + Neon (`send_log`, para `template` por envío):

Por cada brazo (`control` y `experimento`), sobre la ventana:
- `enviados` — envíos con esa plantilla (send_log de Neon, país, template, ventana).
- `entregados` — de ésos, `status="delivered"` en el mart.
- `leidos` — entregados con `seen_at` (read).
- `respondieron` — entregados cuyo teléfono respondió (inbound del mart).
- `interesados` — respuestas de botón INTERESADO (payload con NID).
- `bajas` — respuestas de botón YAVENDIÓ / opt-out.
- rates: `entrega=entregados/enviados`, `read=leidos/entregados`, `respond=respondieron/entregados`,
  `interesado=interesados/entregados`, `baja=bajas/entregados`.
- **Excluir** envíos fallidos por plantilla sin imagen (error 7008), igual que la tabla A/B viva.

**Veredicto bayesiano** sobre `interesado_rate` reusando `ab_stats.py` (Beta-Binomial): `P(mejor)`,
`pérdida esperada (pp)`, y Fisher p como sanity. Mismo criterio de decisión del A/B (P≥95%,
pérdida≤0,5pp, ≥300 entregados/brazo, ≥7 días).

Salida en `data.json`:
```
"ab_experimentos": { "MX": [ {n, labels, ventana, estado, ganador, nota,
                              control:{enviados,entregados,entrega,read,respond,interesado,baja},
                              experimento:{…}, veredicto:{prob,loss_pp,fisher,decidido, dias}} ], "CO":[…] }
```
Reutilizar la lógica que ya existe para `ab_templates`/`ab_veredicto`, parametrizada por
`(control_tpl, experimento_tpl, desde, hasta)`. Si un experimento no tiene datos (ventana futura o
mart aún sin cargar), devuelve brazos en 0 y `veredicto.disponible=false`.

### 3. Frontend — tabla en la página de Documentación (`renderDocs`)
Reemplaza la tarjeta única `ab_result` (objeto `DOCS[pais].ab_result` + helper `abResult()`) por una
tabla alimentada de `D.ab_experimentos[docC]`. **Una fila por prueba**, con **todos los resultados
inline** (sin expandibles). Cada métrica se muestra **control→experimento**, con el lado ganador en
negrita:

| # | Control | Experimento | Ventana | Estado | Enviados (C/E) | Entregados (C/E) | Entrega (C→E) | Read (C→E) | Respond (C→E) | Interesado (C→E) | Baja (C→E) | P(mejor) | Ganador |

- **Ventana**: "16→22 jul" (cerrada) o "23 jul → en curso" (activa).
- **Estado**: badge `cerrado` / `en curso`; si `ganador` fue adoptado sin señal estadística, badge
  extra "por analogía" con tooltip a la `nota`.
- **Interesado (C→E)** es la columna clave (resaltada, clase `ab-key`).
- **Ganador**: badge con el `*_label` del brazo ganador + ✅ (si `estado:"cerrado"`), o "en curso".
- La tabla scrollea horizontal (patrón `.rawtbl`/`overflow-x:auto` del hub) por el número de columnas.
- **Leyenda fija** debajo: "La plantilla ganadora de una prueba es el control de la siguiente." +
  metodología bayesiana (ya existe el bloque "Cómo funciona el A/B testing" — se conserva debajo).

## Estado inicial del ledger (seed)
Dos registros (MX #1 y CO #1), ambos `cerrado`, `ganador:"experimento"` (v2). CO con la `nota` de
analogía. Son el experimento que ya cerramos el 2026-07-22.

## Testing
- `agg`/stats: test unitario de `ab_experimentos` con datos mock (brazos, ventana, veredicto) —
  verifica que respeta la ventana, excluye 7008, y computa rates + P.
- Validación de datos reales: correr el build y confirmar que MX #1 reproduce los números del cierre
  (v1 2,3% / v2 6,7% interesado, P≈99,7%) y que CO #1 sale sin crash (números crudos o vacío).
- Frontend: revisar en `localhost:8091` la tabla en Documentación MX y CO antes de cualquier push.

## Despliegue
- Rama `feat/ab-experiments-ledger` (incluye también el desbloqueo de "Mejor hora de envío" para CO).
- Revisión en localhost → **PR, sin merge** (Camilo revisa y mergea; regla del hub).
- El cron `update-marketing-loop.yml` regenera `data.json` en prod tras el merge.

## Cómo se opera de aquí en adelante (runbook)
1. Crear plantilla retadora en Meta y esperar APPROVED.
2. En el motor: control = ganadora anterior, experimento = retadora, `active=True`.
3. En el hub: append al `ab_experiments.json` con `estado:"activo"`, `hasta:null`.
4. La tabla la muestra "en curso" con números vivos.
5. Al decidir: set `hasta` + `estado:"cerrado"` + `ganador`; la ganadora es el control de la siguiente.
</content>
