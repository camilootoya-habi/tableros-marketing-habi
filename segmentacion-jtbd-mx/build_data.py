#!/usr/bin/env python3
"""Pipeline JTBD — Estudio segmentación Tuhabi MX (GDV).

Lee la BDD en Excel, asigna cada encuestado a un Job To Be Done (job dominante por
jerarquía de acuidad sobre P.4 + P.22), reproduce los cruces de GDV cortados por JTBD
y por las personas originales, y escribe data.json para el tablero.

Uso:  python3 build_data.py /ruta/a/BDD_Segmentación Tuhabi.xlsx
Si no se pasa ruta, busca en ~/Downloads (vía /mnt/c) o junto al script.
"""
import sys, os, json, glob, re
import pandas as pd
import numpy as np

# ----------------------------------------------------------------------------- IO
def find_excel(argv):
    if len(argv) > 1 and os.path.exists(argv[1]):
        return argv[1]
    for base in ["/mnt/c/Users/Administrador/Downloads", os.path.dirname(__file__) or "."]:
        hits = glob.glob(os.path.join(base, "BDD_Segmentaci*Tuhabi.xlsx"))
        if hits:
            return hits[0]
    raise SystemExit("No encuentro el Excel BDD_Segmentación Tuhabi.xlsx")

XLSX = find_excel(sys.argv)
ET = pd.read_excel(XLSX, sheet_name="ETIQUETAS", header=0)
CO = pd.read_excel(XLSX, sheet_name="CODIGOS", header=0)
DMAP = pd.read_excel(XLSX, sheet_name="DATA MAP", header=None, skiprows=1,
                     names=["VAR", "ET"]).dropna(subset=["VAR"])
N = len(ET)

# ------------------------------------------------------------------- JTBD mapping
GROW = {"Para buscar una mejor propiedad, en tamaño, zona y condiciones de la casa",
        "Crecimiento familiar y necesito una más grande",
        "Cambio / Mudanza por una oportunidad laboral",
        "Comprar otra propiedad"}
SOLTAR = {"No habito/vivo en la propiedad", "Es una herencia que no usaré",
          "Me divorcié / Por separación de bienes",
          "Repartir el dinero entre mis hijos / herencia repartida entre hermanos",
          "Rentar en otro lugar"}
INVERTIR = {"Para invertir en otros activos", "Aumento de plusvalía en la zona",
            "Aproveché mi alta demanda en el mercado", "Invertir el dinero"}
URGENCIA = {"Gastos imprevistos", "Necesidad de liquidez inmediata por algún tema de salud",
            "Necesidad de liquidez inmediata para pagar deudas",
            "Necesita una remodelación costosa y no la puedo costear",
            "Necesidad de liquidez inmediata para pagar los estudios de mis hijos",
            "Pagar deudas", "Emergencia médica (pagar medicinas, operación, rehabilitación)",
            "Aumento de costos en servicios / mantenimiento",
            "Aumento de inseguridad en la zona"}

JOBMAP = {}
for lab in GROW: JOBMAP[lab] = "Crecer"
for lab in SOLTAR: JOBMAP[lab] = "Soltar"
for lab in INVERTIR: JOBMAP[lab] = "Invertir"
for lab in URGENCIA: JOBMAP[lab] = "Urgencia"

JOBS = ["Urgencia", "Soltar", "Invertir", "Crecer"]   # también jerarquía de acuidad
JOB_LABEL = {
    "Urgencia": "Resolver una urgencia",
    "Soltar":   "Soltar un activo ocioso",
    "Invertir": "Hacer rendir el capital",
    "Crecer":   "Crecer / dar el siguiente paso",
}
JOB_COLOR = {"Urgencia": "#e4572e", "Soltar": "#f3a712",
             "Invertir": "#2e9e5b", "Crecer": "#3d6fd1"}

PERSONA = {1: "Isadora", 2: "Emilia", 3: "Clara", 4: "Esteban"}
PERSONA_LABEL = {"Isadora": "Buscadora Liquidez Rápida", "Emilia": "Negociadora Pragmática",
                 "Clara": "Analista Precavido", "Esteban": "Orientado a Estabilidad"}
PERSONAS = ["Isadora", "Emilia", "Clara", "Esteban"]

def cols_with_prefix(pref):
    return [c for c in ET.columns if str(c).startswith(pref)]

P4COLS = cols_with_prefix("P4M")
P22COLS = cols_with_prefix("P22M")

def row_signals(row, cols):
    out = set()
    for c in cols:
        v = row[c]
        if pd.notna(v):
            out.add(str(v).strip())
    return out

# ----------------------------------------------------- asignación job + jerarquía
job_of = []
njobs_of = []
jobset_of = []
IGNORE = {"nan", "Otros (Especificar)", "Otro (Especificar)",
          "Otra: [P8.Choices(99).OpenEnd]"}
for _, row in ET.iterrows():
    sig = row_signals(row, P4COLS) | row_signals(row, P22COLS)
    jset = set()
    for a in sig:
        if a in JOBMAP:
            jset.add(JOBMAP[a])
        elif a not in IGNORE:
            pass  # etiqueta no mapeable -> se ignora
    dom = next((j for j in JOBS if j in jset), None)
    job_of.append(dom if dom else "SinSeñal")
    njobs_of.append(len(jset))
    jobset_of.append(jset)

ET = ET.assign(_job=job_of, _njobs=njobs_of)
ET["_persona"] = CO["Op4Groupsv1"].map(PERSONA)

# máscara: trabajamos con quien tiene job asignado (descartamos SinSeñal=1)
HAS = ET["_job"].isin(JOBS)
base_job = {j: int((ET["_job"] == j).sum()) for j in JOBS}
base_persona = {p: int((ET["_persona"] == p).sum()) for p in PERSONAS}

# --------------------------------------------------------- transparencia overlap
njobs_dist = {int(k): int(v) for k, v in ET["_njobs"].value_counts().sort_index().items()}
n_single = int((ET["_njobs"] == 1).sum())
n_multi = int((ET["_njobs"] >= 2).sum())
# matriz de co-ocurrencia entre jobs (cuántas personas tienen señal de A y B)
cooc = {a: {b: 0 for b in JOBS} for a in JOBS}
for jset in jobset_of:
    for a in JOBS:
        for b in JOBS:
            if a in jset and b in jset:
                cooc[a][b] += 1

# puente persona x job (cuenta y % por columna-job)
bridge = {p: {j: 0 for j in JOBS} for p in PERSONAS}
for _, row in ET[HAS].iterrows():
    p, j = row["_persona"], row["_job"]
    if p in bridge and j in JOBS:
        bridge[p][j] += 1

# ------------------------------------------------------------------- crosstab fn
def pct_table(item_masks, group_col, groups, answered):
    """item_masks: dict item->boolean Series. `answered`: bool Series de quién contestó
    la pregunta (denominador). Devuelve % por grupo + total + índice + bases."""
    out = {}
    base = HAS & answered
    total_base = int(base.sum())
    bases = {"total": total_base}
    for g in groups:
        bases[g] = int((base & (ET[group_col] == g)).sum())
    for item, mask in item_masks.items():
        m = mask & base
        row = {"total": round(100 * m.sum() / total_base, 1) if total_base else 0.0}
        for g in groups:
            gmask = base & (ET[group_col] == g)
            gb = int(gmask.sum())
            pc = round(100 * (m & gmask).sum() / gb, 1) if gb else 0.0
            row[g] = pc
            row[g + "_idx"] = int(round(100 * pc / row["total"])) if row["total"] else None
        out[item] = row
    out["__base__"] = bases
    return out

def multi_response_masks(cols, label_to_item):
    """label_to_item: dict etiqueta-cruda -> nombre de item agregado (o None)."""
    items = {}
    sig_per_row = [row_signals(r, cols) for _, r in ET.iterrows()]
    sig_series = pd.Series(sig_per_row, index=ET.index)
    for label, item in label_to_item.items():
        if item is None:
            continue
        mask = sig_series.apply(lambda s, l=label: l in s)
        if item in items:
            items[item] = items[item] | mask
        else:
            items[item] = mask
    return items

def single_response_masks(col, categories=None):
    items = {}
    vals = ET[col]
    cats = categories or [c for c in vals.dropna().unique()]
    for c in cats:
        items[c] = (vals == c)
    return items

ALL_TRUE = pd.Series(True, index=ET.index)

def answered_single(col):
    return ET[col].notna() if col in ET.columns else ALL_TRUE

def answered_multi(cols):
    if not cols:
        return ALL_TRUE
    return ET[cols].notna().any(axis=1)

def crosstab_both(item_masks, answered=ALL_TRUE):
    return {
        "job": pct_table(item_masks, "_job", JOBS, answered),
        "persona": pct_table(item_masks, "_persona", PERSONAS, answered),
    }

# ------------------------------------------------------------- P4 motivos (slide8)
P4_GROUPS = {  # bucket -> sub-etiquetas
    "CRECIMIENTO": ["Para buscar una mejor propiedad, en tamaño, zona y condiciones de la casa",
                    "Crecimiento familiar y necesito una más grande",
                    "Cambio / Mudanza por una oportunidad laboral"],
    "NO LA USO / USARÉ": ["No habito/vivo en la propiedad", "Es una herencia que no usaré",
                          "Me divorcié / Por separación de bienes"],
    "PARA INVERTIR": ["Para invertir en otros activos", "Aumento de plusvalía en la zona",
                      "Aproveché mi alta demanda en el mercado"],
    "GASTOS DE EMERGENCIA": ["Gastos imprevistos",
                             "Necesidad de liquidez inmediata por algún tema de salud",
                             "Necesidad de liquidez inmediata para pagar deudas",
                             "Necesita una remodelación costosa y no la puedo costear",
                             "Necesidad de liquidez inmediata para pagar los estudios de mis hijos"],
    "OTROS PUSH": ["Aumento de inseguridad en la zona",
                   "Aumento de costos en servicios / mantenimiento"],
}

def grouped_multi(cols, groups):
    """Devuelve item_masks con headers de grupo + sub-items, y orden."""
    sig_per_row = [row_signals(r, cols) for _, r in ET.iterrows()]
    sig_series = pd.Series(sig_per_row, index=ET.index)
    masks, order = {}, []
    for gname, subs in groups.items():
        gmask = pd.Series(False, index=ET.index)
        for s in subs:
            gmask = gmask | sig_series.apply(lambda x, l=s: l in x)
        masks[gname] = gmask
        order.append({"item": gname, "type": "group"})
        for s in subs:
            masks[s] = sig_series.apply(lambda x, l=s: l in x)
            order.append({"item": s, "type": "sub"})
    return masks, order

p4_masks, p4_order = grouped_multi(P4COLS, P4_GROUPS)
P22_GROUPS = {
    "LIQUIDEZ PARA OTROS FINES": ["Comprar otra propiedad", "Rentar en otro lugar",
        "Mantenimiento / renovación / construcción de otra propiedad",
        "Repartir el dinero entre mis hijos / herencia repartida entre hermanos",
        "Comprar un carro"],
    "INVERTIR EL DINERO": ["Invertir el dinero"],
    "LIQUIDEZ PARA UNA EMERGENCIA": ["Pagar deudas",
        "Emergencia médica (pagar medicinas, operación, rehabilitación)"],
}
p22_masks, p22_order = grouped_multi(P22COLS, P22_GROUPS)

# --------------------------------------------------- cruces simples (single/multi)
def clean(lbl):
    if "OpenEnd" in lbl or lbl.startswith("Otra:"):
        return "Otra marca (texto libre)"
    if lbl == "Otro (Especificar)" or lbl == "Otros (Especificar)":
        return "Otro (texto libre)"
    return lbl

# P12 marca que usaría (single)
p12_masks = {clean(k): v for k, v in single_response_masks("P12").items()}
# P29 % descuento (single, ordinal)
P29_ORDER = ["No lo bajaría", "Menos del 5%", "5 al 10%", "11 al 20%", "Más del 20%"]
p29_masks = single_response_masks("P29")
# P14 evaluación general (single, escala)
P14_ORDER = ["Excelente", "Muy buena", "Buena", "Regular", "Mala"]
p14_masks = single_response_masks("P14_A1") if "P14_A1" in ET.columns else {}
# P28 barreras iBuyer (multi)
P28COLS = cols_with_prefix("P28M")
p28_masks = multi_response_masks(P28COLS,
            {v: clean(v) for v in pd.unique(ET[P28COLS].values.ravel()) if pd.notna(v)})
# P26 medios (multi)
P26COLS = cols_with_prefix("P26M")
p26_masks = multi_response_masks(P26COLS,
            {v: clean(v) for v in pd.unique(ET[P26COLS].values.ravel()) if pd.notna(v)})

# ============================================================================
# DOCUMENTO — Lámina 10 (P.1 MaxDiff) y Lámina 11 (P.17), por JTBD
# Reconstrucción propia (no replica la ponderación HB de GDV):
#   · Lámina 10: best-worst share = share de veces elegido "lo más importante".
#   · Lámina 11: share de menciones (atributo asociado a alguna marca).
# Validado: el ranking Total reproduce el de GDV (ver prints abajo).
# ============================================================================

def share_table_by_job(count_by_jobitem, items_order, groups, base_counts):
    """count_by_jobitem[job][item] -> conteo. Devuelve % (share dentro del job)
    + total + índice, en formato {item: {total, <job>, <job>_idx}} con __base__."""
    jobs_tot = {j: sum(count_by_jobitem[j].values()) or 1 for j in JOBS}
    tot_all = sum(jobs_tot.values())
    out = {}
    for it in items_order:
        if it.get("type") == "group":
            subs = groups[it["item"]]
            row = {"total": round(100 * sum(sum(count_by_jobitem[j][s] for s in subs)
                                            for j in JOBS) / tot_all, 1)}
            for j in JOBS:
                pc = round(100 * sum(count_by_jobitem[j][s] for s in subs) / jobs_tot[j], 1)
                row[j] = pc
                row[j + "_idx"] = int(round(100 * pc / row["total"])) if row["total"] else None
            out[it["item"]] = row
        else:
            s = it["item"]
            row = {"total": round(100 * sum(count_by_jobitem[j][s] for j in JOBS) / tot_all, 1)}
            for j in JOBS:
                pc = round(100 * count_by_jobitem[j][s] / jobs_tot[j], 1)
                row[j] = pc
                row[j + "_idx"] = int(round(100 * pc / row["total"])) if row["total"] else None
            out[s] = row
    out["__base__"] = {"total": int(HAS.sum()), **base_counts}
    return out

# ---- Lámina 10: P.1 MaxDiff (best-worst) ----
md_code2txt = {}
for c in [x for x in ET.columns if re.match(r'MXFM\d+$', str(x))]:
    for cd, tx in pd.DataFrame({"c": CO[c], "t": ET[c]}).dropna().drop_duplicates().itertuples(index=False):
        md_code2txt[int(cd)] = tx.strip()
MD_GROUPS = {  # categorías del slide 10 -> códigos de atributo (NN)
    "FORMALIDAD EN EL PROCESO": [2, 15, 3, 17, 8, 5, 6, 14, 10, 16, 7],
    "SEGURIDAD": [12, 9, 13, 4, 1],
    "PRECIO JUSTO": [18, 11],
}
md_best = {j: {a: 0 for a in range(1, 19)} for j in JOBS}
MDCOLS = [c for c in ET.columns if re.match(r'MD_V\d+S\d+_A1$', str(c))]  # A1 = "Más"
def _nn(v):
    m = re.search(r'Choices\((\d+)\)', str(v))
    return int(m.group(1)) if m else None
for idx, row in ET.iterrows():
    j = row["_job"]
    if j not in JOBS:
        continue
    for c in MDCOLS:
        a = _nn(row[c])
        if a:
            md_best[j][a] += 1
# orden + grupos en formato del documento (con textos)
md_order, md_group_subs = [], {}
for gname, codes in MD_GROUPS.items():
    md_order.append({"item": gname, "type": "group"})
    subs = [md_code2txt[a] for a in codes]
    md_group_subs[gname] = subs
    # remap conteos de NN->texto
    for a in codes:
        md_order.append({"item": md_code2txt[a], "type": "sub"})
md_best_txt = {j: {md_code2txt[a]: md_best[j][a] for a in range(1, 19)} for j in JOBS}
md_base = {j: base_job[j] for j in JOBS}
maxdiff_tbl = share_table_by_job(md_best_txt, md_order, md_group_subs, md_base)

# ---- Lámina 11: P.17 (share de menciones) ----
# A-índice -> texto (sufijo del diccionario) y conteo de menciones por job
p17_txt = {}
for a in range(1, 25):
    rowdm = DMAP[DMAP["VAR"] == f"P17_A{a}M1"]
    if len(rowdm):
        p17_txt[a] = rowdm["ET"].values[0].split(" - ")[-1].strip()
def _theme_p17(t):
    t = t.lower()
    if any(k in t for k in ["confianza", "transparente", "segura", "innovadora", "profesional", "experta"]):
        return "IMAGEN PROFESIONAL"
    if any(k in t for k in ["precios justos", "montos acordados", "gastos innecesarios", "opciones de pago", "liquidez", "maximiza"]):
        return "ECONOMÍA"
    if any(k in t for k in ["acompañamiento", "asesoría", "trámites legales", "cobertura nacional", "estructura sólida", "facilita todo"]):
        return "ACOMPAÑAMIENTO EN EL PROCESO"
    if any(k in t for k in ["comunicación", "ágiles", "servicio al cliente", "garantías", "cobertura amplia"]):
        return "CONVENIENCIA"
    return None
P17_THEME_ORDER = ["IMAGEN PROFESIONAL", "ACOMPAÑAMIENTO EN EL PROCESO", "ECONOMÍA", "CONVENIENCIA"]
p17_count = {j: {} for j in JOBS}
p17_groups = {g: [] for g in P17_THEME_ORDER}
for a in range(1, 25):
    txt = p17_txt.get(a, "")
    if "ninguna" in txt.lower():
        continue
    theme = _theme_p17(txt)
    if not theme:
        continue
    if txt not in p17_groups[theme]:
        p17_groups[theme].append(txt)
    cols = [c for c in ET.columns if re.match(rf'P17_A{a}M\d+$', str(c))]
    cnt_series = ET[cols].notna().sum(axis=1)  # menciones de ese atributo por persona
    for j in JOBS:
        m = HAS & (ET["_job"] == j)
        p17_count[j][txt] = p17_count[j].get(txt, 0) + int(cnt_series[m].sum())
p17_order = []
for g in P17_THEME_ORDER:
    p17_order.append({"item": g, "type": "group"})
    for s in p17_groups[g]:
        p17_order.append({"item": s, "type": "sub"})
p17_base = {j: base_job[j] for j in JOBS}
p17_tbl = share_table_by_job(p17_count, p17_order, p17_groups, p17_base)

# ----------------------------------------------------------------------- ensamble
data = {
    "meta": {
        "n": N,
        "n_con_job": int(HAS.sum()),
        "fuente": "GDV — Segmentación de vendedores Tuhabi MX (mayo 2026)",
        "jobs": [{"key": j, "label": JOB_LABEL[j], "color": JOB_COLOR[j],
                  "base": base_job[j]} for j in JOBS],
        "personas": [{"key": p, "label": PERSONA_LABEL[p], "base": base_persona[p]}
                     for p in PERSONAS],
    },
    "transparencia": {
        "njobs_dist": njobs_dist,
        "n_single": n_single, "n_multi": n_multi,
        "pct_single": round(100 * n_single / N, 0),
        "pct_multi": round(100 * n_multi / N, 0),
        "cooccurrence": cooc,
    },
    "bridge": bridge,
    "crosstabs": {
        "P4":  {"title": "Motivaciones para vender (P.4)", "kind": "grouped",
                "order": p4_order, **crosstab_both(p4_masks, answered_multi(P4COLS))},
        "P22": {"title": "Uso del dinero de la venta (P.22)", "kind": "grouped",
                "order": p22_order, **crosstab_both(p22_masks, answered_multi(P22COLS))},
        "P12": {"title": "Marca que usaría / usó para vender (P.12)", "kind": "single",
                **crosstab_both(p12_masks, answered_single("P12"))},
        "P29": {"title": "% dispuesto a bajar el precio por liquidez (P.29)", "kind": "single",
                "order": [{"item": c} for c in P29_ORDER],
                **crosstab_both(p29_masks, answered_single("P29"))},
        "P14": {"title": "Evaluación general de la experiencia (P.14)", "kind": "single",
                "order": [{"item": c} for c in P14_ORDER],
                **crosstab_both(p14_masks, answered_single("P14_A1"))},
        "P28": {"title": "Barreras para contactar iBuyers (P.28)", "kind": "multi",
                **crosstab_both(p28_masks, answered_multi(P28COLS))},
        "P26": {"title": "Medios en que ofrece la propiedad (P.26)", "kind": "multi",
                **crosstab_both(p26_masks, answered_multi(P26COLS))},
    },
    "documento": {
        "maxdiff": {
            "title": "Necesidades de la categoría — qué valora del proceso de venta (P.1)",
            "metodo": "Reconstrucción propia · best-worst: share de veces elegido como “lo más importante” en el MaxDiff. No replica las utilidades HB de GDV; el ranking Total sí reproduce el del estudio.",
            "order": md_order, "tbl": maxdiff_tbl,
        },
        "p17": {
            "title": "Drivers para elegir con quién vender (P.17)",
            "metodo": "Reconstrucción propia · share de menciones (atributo asociado a alguna marca). Etiquetas tomadas del diccionario de la base.",
            "order": p17_order, "tbl": p17_tbl,
        },
    },
}

OUT = os.path.join(os.path.dirname(__file__) or ".", "data.json")
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=1)

# ------------------------------------------------------------------- validación
print(f"OK -> {OUT}")
print(f"N={N}  con job={int(HAS.sum())}")
print("Bases JTBD:", base_job, " suma", sum(base_job.values()))
print("Bases persona:", base_persona)
print(f"Single-job: {n_single} ({100*n_single/N:.0f}%) | Multi-job: {n_multi} ({100*n_multi/N:.0f}%)")
print("\n--- VALIDACIÓN vs PDF (P.4 por persona, debe ~= slide 8) ---")
for g in ["CRECIMIENTO", "NO LA USO / USARÉ", "PARA INVERTIR", "GASTOS DE EMERGENCIA"]:
    r = data["crosstabs"]["P4"]["persona"][g]
    print(f"  {g:22} Total {r['total']:>5}  Isa {r['Isadora']:>5}  Emi {r['Emilia']:>5}  Cla {r['Clara']:>5}  Est {r['Esteban']:>5}")
print("\n--- P.22 por persona (debe ~= slide 9) ---")
for g in ["LIQUIDEZ PARA OTROS FINES", "INVERTIR EL DINERO", "LIQUIDEZ PARA UNA EMERGENCIA"]:
    r = data["crosstabs"]["P22"]["persona"][g]
    print(f"  {g:30} Total {r['total']:>5}  Isa {r['Isadora']:>5}  Emi {r['Emilia']:>5}  Cla {r['Clara']:>5}  Est {r['Esteban']:>5}")
print("\n--- LÁMINA 10 MaxDiff: top atributos por share-de-Más (Total) ---")
md_subs = [o["item"] for o in md_order if o.get("type") == "sub"]
for s in sorted(md_subs, key=lambda x: -maxdiff_tbl[x]["total"])[:6]:
    r = maxdiff_tbl[s]
    print(f"  {r['total']:>4}  U{r['Urgencia']:>4} S{r['Soltar']:>4} I{r['Invertir']:>4} C{r['Crecer']:>4}  {s[:50]}")
print("--- LÁMINA 11 P.17: categorías (Total) ---")
for g in P17_THEME_ORDER:
    r = p17_tbl[g]
    print(f"  {g:30} Total {r['total']:>5}  U{r['Urgencia']:>5} S{r['Soltar']:>5} I{r['Invertir']:>5} C{r['Crecer']:>5}")
