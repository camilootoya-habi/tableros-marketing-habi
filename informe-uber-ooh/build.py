#!/usr/bin/env python3
"""Renderiza la edición del mes en curso del informe de campaña.

Solo escribe la carpeta del mes actual: al cambiar de mes, la anterior deja de tocarse y queda
inmutable **por construcción**, sin un paso manual que alguien pueda olvidar. `--freeze YYYY-MM`
sella un mes concreto antes de tiempo, para mandarlo a comité a mitad de mes.

Las cifras se hornean desde marca-mx/data.json al HTML, así que una edición pasada no depende de
nada externo: se abre en dos años y muestra lo mismo que el día que se firmó.

Uso: python3 build.py [--freeze YYYY-MM]
"""
import argparse
import datetime
import json
import os
import re

import render

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "marca-mx", "data.json")
CONTENIDO = os.path.join(HERE, "contenido")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def editions(root=HERE):
    """Meses ya publicados, del más nuevo al más viejo."""
    return sorted([d for d in os.listdir(root)
                   if MONTH_RE.match(d) and os.path.exists(os.path.join(root, d, "index.html"))],
                  reverse=True)


def write_edition(month, root=HERE, html=""):
    d = os.path.join(root, month)
    os.makedirs(d, exist_ok=True)
    destino = os.path.join(d, "index.html")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(html)
    return destino


def build_html(month, data, plantilla, contenido=CONTENIDO):
    """Capítulos → interpolación → bloques → HTML. Un placeholder sin resolver aborta el render:
    más vale no publicar que publicar un `{{...}}` o un cero inventado."""
    partes, charts = [], []
    capitulos = render.chapters_for(month, contenido)
    if not capitulos:
        raise SystemExit(f"No hay capítulos para {month} en {contenido}")

    for ch in capitulos:
        try:
            body = render.interpolate(ch["body"], data)
        except render.UnresolvedPlaceholder as e:
            raise SystemExit(f"Capítulo '{ch['id']}': {e}")
        body, blocks = render.parse_blocks(body)
        html = render.md_to_html(body)
        for i, b in enumerate(blocks):
            idx = len(charts)
            charts.append(b)
            html = html.replace(
                f"@@BLOCK{i}@@",
                f'<figure class="chart"><div class="ch"><canvas id="c{idx}"></canvas></div>'
                f'<figcaption>{b.get("caption", "")}</figcaption></figure>')
        partes.append(f'<section id="{ch["id"]}"><h1>{ch["title"]}</h1>\n{html}\n</section>')

    indice = "".join(f'<li><a href="#{c["id"]}">{c["title"]}</a></li>' for c in capitulos)
    return (plantilla
            .replace("<!--MONTH-->", month)
            .replace("<!--INDICE-->", indice)
            .replace("<!--CHAPTERS-->", "\n".join(partes))
            .replace("<!--CHARTS-->", json.dumps(charts, ensure_ascii=False))
            .replace("<!--DATA-->", json.dumps(data, ensure_ascii=False)))


def build_index(root=HERE):
    eds = editions(root)
    items = "\n".join(
        f'<li><a href="{m}/">Edición {m}</a>{" · última" if i == 0 else ""}</li>'
        for i, m in enumerate(eds)) or "<li>Todavía no hay ediciones publicadas.</li>"
    plantilla = open(os.path.join(HERE, "plantilla_indice.html"), encoding="utf-8").read()
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as f:
        f.write(plantilla.replace("<!--EDICIONES-->", items))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", help="sellar un mes concreto (YYYY-MM) en vez del mes en curso")
    args = ap.parse_args()
    if args.freeze and not MONTH_RE.match(args.freeze):
        raise SystemExit(f"--freeze espera YYYY-MM, recibió {args.freeze!r}")

    month = args.freeze or datetime.date.today().strftime("%Y-%m")
    data = json.loads(open(DATA, encoding="utf-8").read())
    plantilla = open(os.path.join(HERE, "plantilla.html"), encoding="utf-8").read()
    print("escrito:", write_edition(month, html=build_html(month, data, plantilla)))
    build_index()
    print("ediciones:", ", ".join(editions()) or "(ninguna)")
