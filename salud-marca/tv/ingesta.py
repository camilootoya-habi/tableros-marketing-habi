#!/usr/bin/env python3
"""Convierte el as-run semanal de la central en las dos piezas que usa el reporte.

POR QUÉ EXISTE ESTE PASO EN VEZ DE COMMITEAR EL XLSX

Este repo es **público** (sirve el hub por GitHub Pages). El xlsx de la central trae las
tarifas negociadas con Televisa: costo por spot, CPP por canal, el desglose del paquete LRDG
y el tarifario completo por programa. Eso es información comercial de Habi y no puede quedar
en un repo que cualquiera clona. El xlsx está en `.gitignore` a propósito.

La separación es:

- `spots.csv` → **público, se commitea.** Solo el calendario: fecha, hora, canal, programa y
  franja. Con eso le alcanza al estimador, que únicamente pregunta qué horas tuvieron spot.
  No lleva ni un peso ni un punto de rating. Además nada de esto es secreto: que Habi
  anuncia en La Rosa de Guadalupe a las 19:30 lo ve cualquiera que prenda la tele.
- `inversion.json` → **privado, NO se commitea.** Inversión y TRP agregados por día y franja.
  Viaja como el secret `TV_INVERSION_JSON`, que el workflow inyecta como variable de entorno.

Así la tarjeta conserva la inversión por franja sin publicar tarifas unitarias.

Uso, cada vez que llega el reporte semanal:

    python3 ingesta.py ~/Downloads/Tuhabi_2026_....xlsx

Imprime el JSON que hay que pegar en el secret y deja `spots.csv` listo para commitear.
"""
import argparse
import csv
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPOTS_CSV = os.path.join(HERE, "spots.csv")
INVERSION_JSON = os.path.join(HERE, "inversion.json")

CAMPOS = ["fecha", "hora", "minuto", "canal", "programa", "franja"]


def _leer(ruta):
    import horario
    return horario.leer_asrun(ruta)


def filas_publicas(spots):
    """Calendario sin dinero ni rating."""
    out = []
    for s in spots:
        out.append({"fecha": s["ts"].date().isoformat(), "hora": s["ts"].hour,
                    "minuto": s["ts"].minute, "canal": s["canal"],
                    "programa": s["programa"], "franja": s["franja"]})
    return out


def agregados_privados(spots):
    """{fecha: {franja: {spots, trp, inversion}}} — agregado por día y franja.

    Se agrega y no se guarda spot por spot porque el reporte solo necesita el total de la
    franja. Un costo por emisión, aun en un secret, es más detalle del que hace falta.
    """
    acc = {}
    for s in spots:
        d = s["ts"].date().isoformat()
        f = s.get("franja") or "?"
        a = acc.setdefault(d, {}).setdefault(f, {"spots": 0, "trp": 0.0, "inversion": 0.0})
        a["spots"] += 1
        a["trp"] += s["trp"]
        a["inversion"] += s["inversion"]
    for dia in acc.values():
        for a in dia.values():
            a["trp"] = round(a["trp"], 2)
            a["inversion"] = round(a["inversion"], 2)
    return acc


def _cargar_csv_existente():
    if not os.path.exists(SPOTS_CSV):
        return []
    with open(SPOTS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fundir(existentes, nuevas):
    """Une deduplicando por (fecha, hora, minuto, canal, programa).

    Si la central reenvía una semana corregida la fila repetida no debe duplicarse; y una
    semana nueva se suma sin borrar el histórico.
    """
    vistos, out = set(), []
    for fila in list(existentes) + list(nuevas):
        f = {k: str(fila[k]) for k in CAMPOS}
        clave = (f["fecha"], f["hora"], f["minuto"], f["canal"], f["programa"])
        if clave not in vistos:
            vistos.add(clave)
            out.append(f)
    return sorted(out, key=lambda r: (r["fecha"], int(r["hora"]), int(r["minuto"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", help="as-run semanal de la central")
    args = ap.parse_args()

    sys.path.insert(0, HERE)
    spots = _leer(args.xlsx)
    if not spots:
        print("ERROR: el archivo no trajo ninguna emisión. ¿Es el as-run correcto?")
        return 1

    filas = fundir(_cargar_csv_existente(), filas_publicas(spots))
    with open(SPOTS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(filas)

    previo = {}
    if os.path.exists(INVERSION_JSON):
        with open(INVERSION_JSON, encoding="utf-8") as f:
            previo = json.load(f)
    previo.update(agregados_privados(spots))
    with open(INVERSION_JSON, "w", encoding="utf-8") as f:
        json.dump(previo, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    dias = sorted({s["ts"].date() for s in spots})
    print(f"Leídas {len(spots)} emisiones · {dias[0]} → {dias[-1]}")
    print(f"  {SPOTS_CSV}  → {len(filas)} filas. COMMITEAR.")
    print(f"  {INVERSION_JSON}  → {len(previo)} días. NO COMMITEAR (está en .gitignore).")
    print()
    print("Pegar esto en el secret TV_INVERSION_JSON del repo")
    print("(Settings → Secrets and variables → Actions):")
    print()
    print(json.dumps(previo, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
