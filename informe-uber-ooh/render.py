#!/usr/bin/env python3
"""Renderiza una edición del informe de campaña: capítulos en Markdown + datos del tablero.

Tres piezas, cada una probada aparte:

1. `chapters_for` — un .md por capítulo. El prefijo numérico del nombre da el orden. Un archivo
   homónimo en la carpeta del mes REEMPLAZA el de base; un nombre nuevo AGREGA un capítulo. Así el
   informe del mes siguiente solo requiere escribir lo que cambió.
   Markdown y no YAML porque el runner del cron solo tiene stdlib, y porque escribir prosa
   ejecutiva en bloques YAML es un dolor de indentación y escapes.

2. `interpolate` — `{{metrica.pais[.dimension].campo.selector}}` se sustituye con el dato real de
   `data.json`. Ninguna cifra del informe se escribe a mano, así que no puede divergir del tablero.
   Un placeholder que no resuelve **aborta el render**: nunca se publica `{{...}}` literal ni un
   cero silencioso en un documento que va a comité.

3. `parse_blocks` + `md_to_html` — una valla ```chart pide una gráfica donde vive el texto que la
   explica, sin dependencias externas.
"""
import os
import re
from html import escape

CH_RE = re.compile(r"^(\d+)-")
PH_RE = re.compile(r"\{\{([a-zA-Z0-9_.]+)(?::([a-z0-9]+))?\}\}")
BLOCK_RE = re.compile(r"^```chart\s*$(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
METRICS_OK = ("brand_lift", "traffic", "exit_poll")
SELECTORES = ("latest", "max", "min")
# Qué puede dibujar un bloque ```chart. Se exige explícita: una `vista` desconocida o ausente
# dejaría un canvas en blanco en el documento y nadie se daría cuenta hasta el comité.
VISTAS = ("expuesto_control", "lift", "usuarios", "cpv", "tasa", "share")


class UnresolvedPlaceholder(Exception):
    """Un placeholder sin resolver aborta el render. Es un error de autoría, no un hueco que
    se llene con un guion: publicar un cero donde no hay medición es peor que no publicar."""


class BadBlock(Exception):
    """Bloque ```chart mal escrito: error de autoría, se falla en el render y no se publica."""


# ── 1. Capítulos ──────────────────────────────────────────────────────────────

def _read_chapter(path):
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else ""
    body = "\n".join(lines[1:]).strip()
    name = os.path.basename(path)
    return {"id": name[:-3], "order": int(CH_RE.match(name).group(1)),
            "title": title, "body": body}


def chapters_for(month, root):
    """base/ mezclado con root/<month>/. Mismo nombre reemplaza; nombre nuevo agrega."""
    found = {}
    for folder in ("base", month):
        d = os.path.join(root, folder)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".md") and CH_RE.match(name):
                found[name] = _read_chapter(os.path.join(d, name))
    return sorted(found.values(), key=lambda c: c["order"])


# ── 2. Interpolación de datos ─────────────────────────────────────────────────

def _uber(fila):
    return next((v for k, v in (fila.get("opciones") or {}).items() if "UBER" in k.upper()), 0)


CAMPOS = {
    "exposed": lambda f: f.get("exposed"),
    "control": lambda f: f.get("control"),
    "lift": lambda f: f.get("lift"),
    "users": lambda f: f.get("users"),
    "spend": lambda f: f.get("spend"),
    "cpv": lambda f: f.get("cpv"),
    "tasa": lambda f: f.get("tasa"),
    "respuestas": lambda f: f.get("respuestas"),
    "registros_web": lambda f: f.get("registros_web"),
    "uber": _uber,
    "uber_share": lambda f: (_uber(f) / f["respuestas"]) if f.get("respuestas") else None,
}


def _agrupa_por_mes(serie, metric):
    """Suma las plazas de un mes cuando el placeholder no nombra dimensión."""
    acc = {}
    for r in serie:
        a = acc.setdefault(r["month"], {"month": r["month"]})
        if metric == "traffic":
            a["users"] = a.get("users", 0) + (r.get("users") or 0)
            if r.get("spend") is not None:
                a["spend"] = (a.get("spend") or 0) + r["spend"]
        else:
            a["registros_web"] = a.get("registros_web", 0) + r.get("registros_web", 0)
            a["respuestas"] = a.get("respuestas", 0) + r.get("respuestas", 0)
            op = a.setdefault("opciones", {})
            for k, v in (r.get("opciones") or {}).items():
                op[k] = op.get(k, 0) + v
    for a in acc.values():
        if metric == "traffic":
            a["cpv"] = (a["spend"] / a["users"]) if (a.get("spend") is not None and a["users"]) else None
        else:
            a["tasa"] = a["respuestas"] / a["registros_web"] if a["registros_web"] else 0.0
    return sorted(acc.values(), key=lambda a: a["month"])


def resolve(path, data, mes=False):
    """`metrica.pais[.dimension].campo.selector`.

    La dimensión es la pregunta en Brand Lift y la plaza en tráfico y exit poll. Sin dimensión,
    tráfico y exit poll se agregan sobre todas las plazas. Selectores: latest, max, min.

    `mes=True` selecciona la fila con el MISMO criterio y devuelve su mes, no el valor. Esto es
    lo que hace que "{{...lift.max:pts}} en {{...lift.max:month}}" cite el mes del pico y no el
    último mes de la serie: seleccionar por mes en vez de por el campo era el bug que rompía la
    sincronía entre la cifra y su fecha.
    """
    p = path.split(".")
    if len(p) == 4:
        metric, country, dim, (field, selector) = p[0], p[1], None, (p[2], p[3])
    elif len(p) == 5:
        metric, country, dim, field, selector = p
    else:
        raise UnresolvedPlaceholder(
            f"{path}: se esperaba metrica.pais.campo.selector o metrica.pais.dimension.campo.selector")

    if metric not in METRICS_OK:
        raise UnresolvedPlaceholder(f"{path}: métrica '{metric}' desconocida (válidas: {METRICS_OK})")
    if selector not in SELECTORES:
        raise UnresolvedPlaceholder(f"{path}: selector '{selector}' no soportado (válidos: {SELECTORES})")

    m = ((data.get("metrics") or {}).get(metric) or {}).get(country)
    if not m:
        raise UnresolvedPlaceholder(f"{path}: no hay métrica '{metric}' para el país '{country}'")
    if m.get("status") not in ("ok", "stale"):
        raise UnresolvedPlaceholder(
            f"{path}: la métrica está en '{m.get('status')}' ({m.get('reason', '')[:90]}), "
            f"no hay dato que citar")

    serie = m.get("series") or []
    if dim:
        key = "question" if metric == "brand_lift" else "plaza"
        serie = [r for r in serie if r.get(key) == dim]
        if not serie:
            raise UnresolvedPlaceholder(f"{path}: no hay filas con {key}='{dim}'")
    elif metric != "brand_lift":
        serie = _agrupa_por_mes(serie, metric)

    getter = CAMPOS.get(field)
    if not getter:
        raise UnresolvedPlaceholder(f"{path}: campo '{field}' desconocido")
    fila = _pick(serie, selector, getter, path)
    if mes:
        return fila["month"], "raw"
    valor = getter(fila)
    if valor is None:
        raise UnresolvedPlaceholder(f"{path}: el campo existe pero vale None en {fila.get('month')}")
    return valor, None


def _pick(serie, selector, getter, path):
    if selector == "latest":
        return sorted(serie, key=lambda r: r["month"])[-1]
    conval = [r for r in serie if getter(r) is not None]
    if not conval:
        raise UnresolvedPlaceholder(f"{path}: ninguna fila tiene valor para ese campo")
    return (max if selector == "max" else min)(conval, key=getter)


def _fmt(valor, spec):
    if spec in (None, "raw"):
        return str(valor)
    if spec == "num":
        return f"{valor:,.0f}".replace(",", ".")
    if spec == "pct1":
        return f"{100 * valor:.1f}%"
    if spec == "pct2":
        return f"{100 * valor:.2f}%"
    if spec == "pts":
        return f"{100 * valor:+.1f} pts"
    if spec == "money":
        return "$" + f"{valor:,.2f}"
    raise UnresolvedPlaceholder(f"formato desconocido: {spec}")


def interpolate(text, data):
    """`:month` devuelve el mes del dato citado, para que texto y cifra no se desincronicen."""
    def sub(m):
        path, spec = m.group(1), m.group(2)
        if spec == "month":
            valor, _ = resolve(path, data, mes=True)
            return str(valor)
        valor, forzado = resolve(path, data)
        return _fmt(valor, forzado or spec)
    return PH_RE.sub(sub, text)


# ── 3. Bloques y Markdown ─────────────────────────────────────────────────────

def parse_blocks(md):
    """Saca los bloques ```chart y los reemplaza por @@BLOCKn@@."""
    blocks = []

    def take(m):
        spec = {}
        for line in m.group(1).strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                spec[k.strip()] = v.strip()
        if spec.get("metrica") not in METRICS_OK:
            raise BadBlock(f"bloque sin `metrica` válida (opciones: {METRICS_OK}): {spec}")
        if not spec.get("pais"):
            raise BadBlock(f"bloque sin `pais`: {spec}")
        if spec.get("vista") not in VISTAS:
            raise BadBlock(f"bloque sin `vista` válida (opciones: {VISTAS}): {spec}")
        blocks.append(spec)
        return f"@@BLOCK{len(blocks) - 1}@@"

    return BLOCK_RE.sub(take, md), blocks


def _inline(t):
    t = escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)


def md_to_html(md):
    """Markdown mínimo: encabezados, listas, negrita, cursiva, links, párrafos, citas y tablas.
    Suficiente para prosa ejecutiva y sin una sola dependencia.

    Une las líneas de un mismo párrafo antes de procesar el markup inline (comportamiento normal
    de Markdown con saltos suaves). No hacerlo rompe cualquier énfasis que cruce un salto de
    línea — un `*cursiva que\nsigue abajo*` deja los asteriscos a la vista — y además genera un
    `<p>` por línea del archivo, con el interlineado roto que eso implica.
    """
    out, en_lista, tabla = [], False, []
    buf, modo = [], None          # líneas acumuladas del párrafo o del <li> en curso

    def flush():
        nonlocal buf, modo
        if buf:
            txt = _inline(" ".join(buf))
            out.append(f"<li>{txt}</li>" if modo == "li" else f"<p>{txt}</p>")
        buf, modo = [], None

    def cierra_lista():
        nonlocal en_lista
        if en_lista:
            out.append("</ul>")
            en_lista = False

    def cierra_tabla():
        if not tabla:
            return
        filas = [f for f in tabla if not set(f.replace("|", "").strip()) <= set("-: ")]
        celdas = [[c.strip() for c in f.strip().strip("|").split("|")] for f in filas]
        head = "".join(f"<th>{_inline(c)}</th>" for c in celdas[0])
        body = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in fila) + "</tr>"
                       for fila in celdas[1:])
        out.append(f'<div class="tabla"><table><thead><tr>{head}</tr></thead>'
                   f"<tbody>{body}</tbody></table></div>")
        tabla.clear()

    for line in md.splitlines():
        s = line.strip()

        if s.startswith("|") and s.endswith("|"):
            flush(); cierra_lista()
            tabla.append(s)
            continue
        cierra_tabla()

        if not s:                                   # línea en blanco cierra el bloque en curso
            flush(); cierra_lista()
            continue

        if s.startswith("- "):                      # nuevo ítem de lista
            flush()
            if not en_lista:
                out.append("<ul>"); en_lista = True
            buf, modo = [s[2:]], "li"
            continue

        if s.startswith(("## ", "### ", "> ", "@@BLOCK")):
            flush(); cierra_lista()
            if s.startswith("### "):
                out.append(f"<h3>{_inline(s[4:])}</h3>")
            elif s.startswith("## "):
                out.append(f"<h2>{_inline(s[3:])}</h2>")
            elif s.startswith("> "):
                out.append(f"<blockquote>{_inline(s[2:])}</blockquote>")
            else:
                out.append(s)
            continue

        # línea corriente: continúa el párrafo o el ítem de lista abierto, o abre uno nuevo
        if modo is None:
            modo = "p"
        buf.append(s)

    flush(); cierra_lista(); cierra_tabla()
    return "\n".join(out)
