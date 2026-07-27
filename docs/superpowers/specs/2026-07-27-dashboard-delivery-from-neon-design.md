# Tablero: entrega desde Neon (fuente durable) — diseño

**Fecha:** 2026-07-27 · **Repo:** `tableros-marketing` (hub) · **Tablero:** `marketing-loop`

## Problema
El tablero calcula la ENTREGA de la cosecha/errores/A/B cruzando `message_id` contra `mbm` =
mart de BigQuery **+** Infobip `/logs` en vivo. Ambas fuentes fallaron para el 22-jul (hueco de
ingesta del mart + `/logs` expira en pocos días) → la cosecha del 22-jul muestra `entregados=0`
falso. El motor ahora **persiste la entrega en Neon `send_log`** (columnas `delivery_status`,
`error_name`, `error_id`, `delivered_at`) de forma durable, pero **el tablero no la lee todavía**.

## Objetivo
Que el tablero incorpore la entrega persistida en Neon como **tercera fuente** de `mbm`, durable y
sin lag, de modo que la cosecha/errores/A/B no vuelvan a tener huecos tipo 22-jul para ningún cohorte
que exista en Neon. **No revive el 22-jul** (ya no está en ninguna fuente); blinda de aquí en adelante.

## Alcance / límites
- Solo ENTREGA + errores (cosecha `entregados`, `errores_serie`, `_ab` delivery, `embudo`).
- **Read-rate (`seen`) NO cambia** — Neon no expone `seen`; sigue viniendo del mart. El merge PRESERVA
  el `seen` que ya tiene `mbm`.
- Un solo repo (`tableros-marketing`). El motor ya persiste (feature aparte, hecha).

## Arquitectura

### 1. Fuente — `sources_neon.delivery_by_msgid(country=None) -> dict`
- Consulta `send_log`: `SELECT message_id, delivery_status, error_name, error_id FROM send_log
  WHERE message_id IS NOT NULL AND delivery_status IS NOT NULL [AND country=%s]`.
- Devuelve `{message_id: {"status": <delivery_status>, "error_name": <"NAME (code ID)">}}`.
- El `error_name` se formatea con un helper **puro** `_delivery_dict(delivery_status, error_name, error_id)`
  para que `agg.err_bucket` lo parsee igual que el mart/Infobip:
  - con error → `f"{error_name} (code {error_id})"` (ej. `"EC_FREQUENCY_CAPPING (code 7032)"`).
  - sin error / `error_id` en (None, 0) → `"No Error (code 0)"`.
  - `status` = `delivery_status` tal cual (ya viene lowercase: delivered/undeliverable/pending/rejected).
- Sigue el patrón de `sources_infobip.map_log` (pieza pura testeable + wrapper de I/O).

### 2. Merge — `agg.merge_neon_delivery(mbm, nbm) -> mbm` (PURO)
Aplica la precedencia acordada:
```python
_TERMINAL = {"delivered", "undeliverable", "rejected"}
def merge_neon_delivery(mbm, nbm):
    for mid, v in nbm.items():
        prev = mbm.get(mid)
        if prev is None or v.get("status") in _TERMINAL:
            mbm[mid] = {**(prev or {}), **v}   # Neon pisa status/error; conserva `seen` de prev
    return mbm
```
- **Rellena** lo que mart+Infobip no tienen (arregla huecos para cohortes presentes en Neon).
- **Pisa** con estado terminal (delivered/undeliverable/rejected).
- **Nunca regresa** un terminal fresco a `pending` (si Neon va detrás de Infobip live para hoy).
- **Preserva `seen`**: `{**prev, **v}` — `v` (Neon) no trae la clave `seen`, así que el `seen` de `prev`
  (mart/Infobip) sobrevive.

### 3. Integración — `build_data.py`
Justo **después** del bloque que mergea Infobip en `mbm` (y antes del `old_repo` setdefault), agregar:
```python
    nbm = N.delivery_by_msgid(pais)
    agg.merge_neon_delivery(mbm, nbm)
```
Y sumar `"neon_delivery": len(nbm)` al bloque de conteos de diagnóstico (junto a `mart_msgids`/`infobip`).

## Testing (TDD)
- `tests/test_sources_neon.py` (nuevo o extendido): `_delivery_dict` puro —
  - con error_id 7032 → `status` correcto + `error_name == "EC_FREQUENCY_CAPPING (code 7032)"`;
  - error_id 0/None → `"No Error (code 0)"`;
  - verificar que `agg.err_bucket(_delivery_dict(...)["error_name"])` cae en el bucket esperado
    (7032→freq_cap, 351→invalido, sin error→entregado).
- `tests/test_agg.py` (extender): `merge_neon_delivery` —
  - mid ausente en mbm + Neon delivered → se agrega;
  - mid con mart `pending` + Neon `delivered` → queda `delivered`;
  - mid con Infobip `delivered`+`seen=True` + Neon `pending` → **se conserva** `delivered` y `seen=True`
    (no regresa);
  - mid con mart `delivered`+`seen=True` + Neon `undeliverable` → pasa a `undeliverable`, `seen=True` preservado.
- Suite del tablero verde: `python3 -m pytest marketing-loop/tests/ -q` (o el runner del hub).

## Rollout (reglas del hub)
- Rama `feat/dashboard-delivery-neon` desde `main`; **PR, NO push directo a `main`** (Camilo mergea).
- Revisar en **localhost:8091** antes del push (gate del workflow).
- **NO regenerar `data.json` a mano** (necesita llaves Infobip/GH; se blanquearía). El cron
  `update-marketing-loop.yml` lo reconstruye tras el merge — ya tiene `NEON_DATABASE_URL` + INFOBIP_*.
- Verificación post-merge: en el `data.json` reconstruido, `diagnostico.neon_delivery > 0` y la cosecha
  de días recientes con entrega consistente (sanity: comparar con el conteo de `delivered` en Neon).

## Fuera de alcance
- Revivir el 22-jul (data perdida en todas las fuentes).
- Read-rate/`seen` desde Neon (no lo persiste el motor; requeriría webhook SEEN — futuro).
</content>
