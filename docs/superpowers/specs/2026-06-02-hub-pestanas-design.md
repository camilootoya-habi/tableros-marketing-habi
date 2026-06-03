# Hub de marketing — pestañas en el panel principal

**Fecha:** 2026-06-02
**Estado:** Diseño aprobado, pendiente plan de implementación

## Problema

El hub (`index.html`, generado por `scripts/build_hub.py`) hoy es un scroll vertical único:
sección General arriba y una sección inline por líder de canal debajo. A medida que crecen los
tableros y se suman equipos (Performance/Growth × CO/MX), ese scroll plano se vuelve difícil de
navegar y no comunica la estructura organizacional del área.

## Objetivo

Introducir una **barra de pestañas** como nuevo nivel superior de navegación en el panel
principal, con cinco pestañas fijas y en este orden:

1. **Marketing General**
2. **Performance Colombia**
3. **Growth Colombia**
4. **Performance Mexico**
5. **Growth Mexico**

Esto es el primer paso del trabajo sobre el hub; sienta la estructura para repartir tableros por
equipo más adelante.

## Decisiones de alcance (acordadas)

- **Contenido inicial:** todos los tableros que existen hoy quedan en **Marketing General**. Las
  otras cuatro pestañas arrancan vacías, listas para llenarse después.
- **Layout interno de una pestaña:** se mantiene **igual que hoy** — los owner-blocks con columnas
  por tipo (Analysis / Dashboards / Reference). La única adición visible es la barra de pestañas
  sobre el contenido.
- **Pestañas vacías:** muestran un mensaje discreto de *"próximamente"* (la pestaña existe, es
  clickeable, y el panel indica que aún no hay tableros).
- **Mínimo churn:** no se editan los ~18 `meta.json` existentes. La pestaña por defecto los deja
  a todos en Marketing General.

## Diseño

### Modelo de datos

Las pestañas se reutilizan sobre la arquitectura actual (dueño = `general` para la raíz, o el
líder bajo `canales/<lider>/`). No se inventa una taxonomía paralela.

**Definición de las pestañas** — nuevo arreglo `tabs` en `hub.config.json`:

```json
"tabs": [
  { "id": "marketing-general",    "label": "Marketing General",    "order": 0 },
  { "id": "performance-colombia", "label": "Performance Colombia", "order": 1 },
  { "id": "growth-colombia",      "label": "Growth Colombia",      "order": 2 },
  { "id": "performance-mexico",   "label": "Performance Mexico",   "order": 3 },
  { "id": "growth-mexico",        "label": "Growth Mexico",        "order": 4 }
]
```

La barra se renderiza siempre con las cinco pestañas, en el orden de `order`, tengan o no
tableros.

**Asignación de un tablero a una pestaña** — se resuelve en `build_hub.py`, en este orden de
prioridad:

1. Si el `meta.json` declara `tab` (override explícito) → esa pestaña.
2. Si el dueño es `general` (carpeta en la raíz) → `marketing-general`.
3. Si el dueño es un líder → el `channel` del líder, normalizado al `id` de pestaña
   (slug: minúsculas, sin tildes, espacios → `-`). Ej.: `"Performance Colombia"` →
   `performance-colombia`.

Con esta regla, los 18 tableros actuales (todos `general`) caen en Marketing General sin tocar
sus metas, y los tableros futuros de Sebastián Ciendua (`channel: "Performance Colombia"`) caen
solos en su pestaña.

Si un tablero resuelve a un `id` que no está en `tabs` (líder con un canal nuevo no listado), se
emite un warning y el tablero se asigna a `marketing-general` como fallback, para no perderlo.

### Render (`scripts/build_hub.py`)

- Nueva función para calcular el `tab` de cada tablero (regla de prioridad de arriba), con
  normalización de slug.
- `build_page` agrupa los tableros por pestaña. Para cada pestaña en orden:
  - Si tiene tableros: renderiza sus owner-blocks **reutilizando `render_owner_block` tal cual**
    (General primero, luego líderes por `order`) — idéntico al render de hoy.
  - Si no tiene tableros: renderiza el panel de estado vacío con el mensaje "próximamente".
- El HTML resultante incluye: la barra de pestañas (botones) + un `<div class="tab-panel">` por
  pestaña, marcando como activo el primero (`marketing-general`).
- Los placeholders del template pasan a ser `{{TABS}}` (barra) y `{{PANELS}}` (paneles), o un
  único `{{CONTENT}}` que contenga ambos — a definir en el plan según lo que dé un render más
  limpio.

### Template (`scripts/templates/hub.html`)

- **Barra de pestañas** bajo el header: botones horizontales, coherentes con el tema (acento
  índigo `--accent`, soporte claro/oscuro vía las variables CSS existentes). La pestaña activa se
  resalta. Scroll/wrap horizontal en viewport angosto.
- **Paneles:** un contenedor por pestaña; solo el activo es visible (`display`), el resto oculto.
- **Estado vacío:** bloque centrado y discreto con texto tipo *"Próximamente — aún no hay
  tableros en esta sección."*
- **JS de cambio de pestaña:**
  - Click en un botón muestra su panel y oculta los demás; actualiza el botón activo.
  - Pestaña por defecto: `marketing-general`.
  - Recuerda la última pestaña en `localStorage`.
  - Soporta deep-link por `location.hash` (ej. `#performance-colombia`) y actualiza el hash al
    cambiar, para poder compartir un link directo a una pestaña.
  - Reusar el patrón de inicialización que ya existe para el tema (IIFE al final del `<body>`).

### Tests (`scripts/tests/`)

Actualizar/añadir cobertura del generador para:
- La barra renderiza las 5 pestañas en orden, aun cuando algunas no tengan tableros.
- Un tablero `general` cae en `marketing-general`; un tablero de líder cae en la pestaña derivada
  de su `channel`; un `tab` explícito en `meta.json` gana sobre la derivación.
- Una pestaña sin tableros renderiza el estado vacío "próximamente".
- El fixture `mini_repo` sigue construyendo sin error con el nuevo modelo.

## Fuera de alcance

- Repartir los tableros existentes entre las cuatro pestañas nuevas (queda para después; hoy todo
  va a Marketing General).
- Crear nuevos líderes/canales para Growth CO, Performance MX, Growth MX.
- Cambios al cron, a los pipelines de datos, o al layout interno de los owner-blocks.

## Riesgos / notas

- `index.html` es **generado**: todo el cambio visual vive en `hub.html` + `build_hub.py`; nunca
  se edita `index.html` a mano (se regenera con `python3 scripts/build_hub.py`).
- El nombre de la rama usa caracteres no-ASCII (`feat/hub-pestañas`); irrelevante para el
  resultado, solo cosmético.
</content>
</invoke>
