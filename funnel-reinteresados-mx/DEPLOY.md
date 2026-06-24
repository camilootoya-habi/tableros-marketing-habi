# Backend en vivo — Cloud Function `reinteresados-data`

Convierte el tablero en app web: consulta `hubspot.deals` al momento (~7 min de lag) en vez de depender del cron. El botón "🔄 Actualizar" del tablero la llama con `?force=1`.

## Requisitos
- Permisos para desplegar Cloud Functions (gen2 / Cloud Run) en el proyecto.
- La **misma service account que usa el cron** (la del secret `GCP_CREDENTIALS`); su email está dentro de ese JSON (`client_email`). Ya tiene acceso a `sellers-main-prod`, `papyrus-master`, etc.

## Deploy (1 comando)
```bash
gcloud functions deploy reinteresados-data \
  --gen2 --runtime=python312 --region=us-central1 \
  --source=funnel-reinteresados-mx --entry-point=reinteresados \
  --trigger-http --allow-unauthenticated \
  --service-account=<CLIENT_EMAIL_DEL_CRON> \
  --memory=512Mi --timeout=120s \
  --project=<PROJECT_ID>
```
Al terminar imprime la **URL** (algo como `https://us-central1-<proj>.cloudfunctions.net/reinteresados-data`).

## Conectar el tablero
En `funnel-reinteresados-mx/index.html`, pon esa URL en:
```js
const BACKEND_URL = ''; // ← pega aquí la URL de la función
```
Commit + push. Listo: el tablero carga en vivo y el botón refresca al instante.

## Notas
- CORS: la función solo acepta el origen `https://camilootoya-habi.github.io` (editable en `main.py` `_ALLOW_ORIGIN`).
- Cache de 60 s en memoria (clics seguidos no re-corren BQ; `?force=1` lo salta).
- Costo: la query filtra por `utm_campaign` → scan chico, centavos. La función escala a 0 (solo paga cuando se invoca).
- `BACKEND_URL` vacío = el tablero sigue leyendo `data.json` (fallback del cron). Si la función falla, también cae al `data.json`.
- ⚠ El cron (`update-reinteresados.yml`, */10) puede dejarse como respaldo o apagarse una vez la función esté estable.
