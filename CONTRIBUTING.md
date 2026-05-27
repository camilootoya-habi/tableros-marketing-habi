# Cómo agregar tu tablero (líderes de canal)

1. `git pull && git checkout -b <tu-nombre>/<slug-del-tablero>`
2. Copia la plantilla:
   `cp scripts/templates/dashboard.html canales/<tu-carpeta>/<slug>/index.html`
3. Crea `canales/<tu-carpeta>/<slug>/meta.json`:
   ```json
   { "title": "...", "description": "...", "country": "CO", "section": "dashboard", "order": 1, "query": "query.sql" }
   ```
4. Escribe `query.sql` y pruébalo en BigQuery con TUS credenciales.
   El resultado de `bq query --format=json` es lo que tu `index.html` leerá como `data.json`.
5. `git push` y abre un Pull Request.
6. Camilo revisa el query (costo/correctitud) y mergea.
7. El cron corre tu query → `data.json`, regenera el hub → tu card aparece y se actualiza a diario.

⚠️ NO edites `index.html` (la raíz): es generado por `scripts/build_hub.py`.
⚠️ Tope de costo por query: 5 GB (`maximum_bytes_billed`). Súbelo en tu `meta.json` solo si lo justificas.
