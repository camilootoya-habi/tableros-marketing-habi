# Growth & Marketing Hub — Habi

Tableros, análisis y documentación de marketing/growth de Habi. Sitio estático en GitHub Pages.

**Hub en vivo:** https://camilootoya-habi.github.io/tableros-marketing-habi/

## Cómo está organizado

- **General** (raíz del repo): contenido de marketing general.
- **Por líder de canal** (`canales/<lider>/`): cada líder tiene su propia sección con sus tableros, análisis y docs.

El `index.html` del hub se **genera** automáticamente con `scripts/build_hub.py` a partir de un `meta.json` por carpeta — **no se edita a mano**.

## ¿Eres líder de canal y quieres publicar un tablero?

Lee **[CONTRIBUTING.md](CONTRIBUTING.md)** — el paso a paso: crear tu carpeta bajo `canales/`, el `meta.json`, el `query.sql`, y abrir un Pull Request. (Agentes de Claude: empiecen por `CLAUDE.md`.)

## Desarrollo

```bash
python3 scripts/build_hub.py        # regenerar el hub
python3 -m pytest scripts/tests/ -q # tests
```

Los datos se actualizan solos vía GitHub Actions (`.github/workflows/update-data.yml`, cada 4 h).
