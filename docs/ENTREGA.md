# Entrega — Salud de marca, reporte de TV y encuesta Pulso

**Para:** Camilo Otoya (`camilootoya-habi`) y Esteban Castel.
**De:** Nicolás Otero, que deja Habi. Estado al **25-sep-2026**.

Este documento cubre lo que Nicolás construyó o mantenía alrededor del hub de tableros. Si
algo aquí contradice el código, manda el código; avísale a quien mantenga este archivo.

---

## 1. Qué hay y dónde vive

| Pieza | Qué es | Dónde vive | Dueño hoy |
|---|---|---|---|
| **Tablero Salud de marca** | Brand Lift, exit poll, tráfico por plaza, encuestador Pulso y panel de TV | `salud-marca/` en este repo | Camilo ✅ |
| **Reporte diario de TV** | Tarjeta en Google Chat con el incremental de la campaña de TV (MX) + panel en el tablero | `salud-marca/tv/` + `.github/workflows/tv-diario.yml` | Camilo ✅ |
| **Reloj externo del reporte de TV** | 4 jobs que le piden a GitHub correr el reporte (GitHub se salta sus propios cron) | **cron-job.org**, cuenta de Nicolás | ⚠ Nicolás |
| **Encuesta Pulso Inmobiliario** | App de la encuesta (Next.js) | Código: `notero-88/pulso-inmobiliario` → **transferencia a Camilo pendiente de aceptar**. App: **Vercel personal de Nicolás**. Base: **Supabase personal de Nicolás** | ⚠ Nicolás |
| **Campañas que mandan la encuesta** | Envíos por WhatsApp de cada ola | `camilootoya-habi/marketing-loop-sellers` → `campanas/` | Camilo ✅ |
| **Agente SDR (backend)** | API del inbox, envíos a pedido, ventanas | Vercel personal de Nicolás (`nicolasotero-3879s-projects/agente-sdr`) | ⚠ Nicolás |
| **Marketing Loop v2** | Tablero en la sección de Nicolás del hub | `canales/nicolas-otero/marketing-loop-v2/` | Reasignar |

Todo lo marcado ⚠ **deja de funcionar si se cierran las cuentas de Nicolás**. Ver §4.

---

## 2. Qué se actualiza solo

| Workflow | Cuándo (CDMX) | Qué hace |
|---|---|---|
| `salud-marca.yml` | 7:41 diario | Corre `salud-marca/build.py`: Brand Lift, exit poll, tráfico, encuestador. **Conserva el panel de TV.** |
| `tv-diario.yml` | 9:07, 9:31, 10:17, 11:23 (cron de GitHub) + disparos de cron-job.org a 9:07, 9:31, 12:07, 15:07 | Reporte de TV a Google Chat + panel del tablero. **Sale una sola vez por día** (marcador `salud-marca/tv/ultimo_envio.json`). |
| `update-data.yml` | cada ~4 h | Pipelines generales del hub (de Camilo). El 25-sep se le agregó reintento al push. |

Detalles que importan:

- **GitHub no garantiza los cron.** En horas de carga los atrasa horas o los descarta; el 25-sep
  no corrió ninguno de los del reporte de TV. Por eso existe el reloj externo: un disparo por
  API (`workflow_dispatch`) GitHub no lo descarta. Explicación completa en
  `salud-marca/tv/README.md` → "Reloj externo".
- **El reporte espera a GA4.** Si la tabla `events_AAAAMMDD` del día anterior no llegó a
  BigQuery (`papyrus-data-mx.analytics_325611813`), no envía ni marca, y reintenta en el
  siguiente horario. Nunca manda "0 visitas".
- `salud-marca.yml` y `tv-diario.yml` comparten grupo de concurrencia: los dos escriben
  `salud-marca/data.json` y nunca corren a la vez.
- `update-marketing-loop.yml` quedó **desactivado** el 25-sep (buscaba la rama `pool-ab-view`,
  que ya no existe). El archivo sigue en el repo por si se quiere reactivar.

---

## 3. Tareas humanas recurrentes

| Cada cuánto | Qué | Quién puede | Cómo |
|---|---|---|---|
| **Semanal** (llega de la central) | Cargar el as-run de TV (horarios reales de los spots) | Cualquiera con el repo | `python3 salud-marca/tv/ingesta.py ~/Downloads/<xlsx>` → commit de `salud-marca/tv/spots.csv` por PR. **El xlsx NO se commitea** (trae tarifas). |
| **Semanal** | Actualizar inversión y TRP de TV | **Solo Camilo** (secrets del repo) | `ingesta.py` imprime un JSON → pegarlo en el secret `TV_INVERSION_JSON`. Sin esto la tarjeta sale "sin cifras de inversión" (pasa desde el 14-sep). |
| **Mensual** | Mapear los estudios nuevos de Brand Lift | Cualquiera con el repo | Meta crea un `experiment_id` nuevo cada mes: agregarlo a `salud-marca/questions.json` siguiendo las reglas de su campo `_nota`. Si no, la serie se corta. |
| **Por ola** | Abrir una ola nueva de Pulso y mandarla | Quien tenga Pulso + marketing-loop-sellers | Ola en la app de Pulso; envío con `campanas/` (specs `campanas/specs/encuesta-pulso-*.toml`, ver `campanas/README.md`). |
| **Al vencer** | Renovar tokens | Dueño de cada token | Ver §5. |

---

## 4. Pendientes al día de la entrega

**Antes de que se cierren las cuentas de Nicolás (lo más urgente):**

1. **Camilo: aceptar la transferencia de `pulso-inmobiliario`** (correo de GitHub o
   github.com/notifications). Después: `git remote set-url origin
   https://github.com/camilootoya-habi/pulso-inmobiliario.git` en quien lo clone.
2. **Nicolás: mover Pulso** (proyecto de Vercel `pulso-inmobiliario` + su base en Supabase) a
   una cuenta de Habi. Hasta hoy se despliega con `vercel --prod` desde local, sin
   integración con GitHub. El tablero solo lee su API pública
   (`https://pulso-inmobiliario.vercel.app/api/resultados`): si cambia la URL, actualizar
   `API` en `salud-marca/sources_pulso.py`.
3. **Nicolás: mover `agente-sdr`** (Vercel `nicolasotero-3879s-projects`) a una cuenta de Habi.
4. **Reloj del reporte de TV:** crear una cuenta de cron-job.org a nombre de Habi o de Camilo y
   recrear los 4 jobs (configuración exacta en `salud-marca/tv/README.md` → "Reloj externo").

**Tokens:**

5. **Camilo: crear UN token fine-grained** (GitHub → Settings → Developer settings →
   Fine-grained tokens) con acceso a `tableros-marketing-habi` y `marketing-loop-sellers`,
   permiso **Actions: Read and write** y nada más. Sirve para dos cosas:
   - el reloj de TV (reemplaza el token clásico temporal de `notero-88`, que después se revoca);
   - `GH_DISPATCH_TOKEN` en Vercel (agente-sdr): **el actual responde 404** contra el repo
     nuevo, así que el botón "Envío" del tablero de Marketing Loop no dispara tandas. El
     ciclo diario de envíos no depende de él.
6. **Brand Lift congelado desde el 31-ago:** Meta responde *"API access blocked"* con
   `META_ACCESS_TOKEN`. Hace falta un token de usuario de sistema de Meta Business con acceso a
   las cuentas `act_205661715114408` (MX) y `act_770068953990542` (CO), guardado como secret
   `META_ACCESS_TOKEN` (o `META_SYSTEM_USER_TOKEN`). El workflow ya lo usa: al cambiarlo,
   se actualiza solo al día siguiente.

**Datos:**

7. **GA4 no publicó el 24-sep** en BigQuery (seguía faltando el 25-sep en la tarde). Si pasa
   varios días seguidos, revisar la vinculación GA4 → BigQuery en la propiedad de GA4.

**Orden:**

8. Reasignar `canales/nicolas-otero/` (Marketing Loop v2) a quien lo herede y quitar a
   `notero-88` de colaborador cuando Nicolás se vaya.

---

## 5. Secrets y cuentas

| Secret (repo del tablero) | Para qué | Dueño / renovar |
|---|---|---|
| `GCP_CREDENTIALS` | BigQuery (factura en `sellers-main-prod`) | Cuenta de servicio de Habi |
| `GCHAT_WEBHOOK_TV` | Espacio de Google Chat del reporte de TV. La URL **es** la credencial | Quien administre el espacio |
| `TV_INVERSION_JSON` | Inversión y TRP de TV por día y franja (tarifas negociadas: por eso no va en el repo) | Camilo, semanal |
| `META_ACCESS_TOKEN`, `META_PCOM_TOKEN` | Brand Lift y pauta | Ver pendiente 6 |

Fuera de GitHub: cron-job.org (reloj de TV, cuenta de Nicolás), Vercel y Supabase de Pulso
(Nicolás), Vercel de agente-sdr (Nicolás).

---

## 6. Qué hacer si…

**…el reporte de TV no llegó a las 9:07.** Normal si GA4 no publicó el día anterior: sale solo en
el primer horario después de que llegue (hasta las 15:07). Ver el log de `tv-diario.yml`: dice
"GA4 todavía no publica…" o "ya se envió". Para forzarlo:
`gh workflow run tv-diario.yml -R camilootoya-habi/tableros-marketing-habi -f solo_si_falta=true`
(con `solo_si_falta=true` nunca duplica).

**…llegaron dos mensajes el mismo día.** Alguien corrió `tv-diario.yml` a mano sin
`solo_si_falta`. Las corridas manuales sin ese flag no miran el marcador.

**…el tablero de salud de marca muestra un badge "sin refrescar".** Es el estado *stale*: la
fuente falló y se muestra el último dato bueno. Ver el log de `salud-marca.yml`, que imprime
el estado de cada métrica.

**…falla `update-data.yml`.** Ver el paso que falla. Si es "Commit and push", ya reintenta 5
veces; si igual falla, es un conflicto real de rebase y hay que mirarlo a mano.

**…hay que cambiar un horario del reporte.** Los cron de GitHub están en `tv-diario.yml`; los
del reloj, en cron-job.org (consola web o API). Ambos pueden convivir: el marcador evita
duplicados.

---

## 7. Documentación técnica

- Método del reporte de TV (por qué el incremental va a 7 días, estimadores, factor del día,
  horas anómalas, reloj externo): `salud-marca/tv/README.md`.
- Métricas del tablero y contrato de `data.json`: `salud-marca/contract.py` y
  `salud-marca/sources_*.py` (cada fuente explica su criterio en el encabezado).
- Cuestionario de Pulso: `ENCUESTA.md` en el repo `pulso-inmobiliario`.
- Reglas del hub (tableros vs documentos, cómo agregar uno): `CLAUDE.md` y `CONTRIBUTING.md`.
