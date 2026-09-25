#!/usr/bin/env python3
"""Reporte diario del impacto de TV abierta en México → Google Chat.

Corre en GitHub Actions a las 9:07 CDMX (15:07 UTC), con tres horarios de respaldo (9:31,
10:17 y 11:23) que no hacen nada si el reporte ya salió (`--solo-si-falta`). La hora no es
arbitraria: se midió que el export de GA4 del día D aterriza entre las 13:00 y 13:48 UTC del
día D+1, así que las 15:07 dejan más de una hora de colchón.

QUÉ REPORTA Y POR QUÉ ASÍ:

- El INCREMENTAL va a 7 DÍAS RODANTES, no a 24 horas. Un solo día tiene ~8 spots contra
  ~6.000 visitas: se midió el estimador diario sobre la semana 1 y da 84 ± 337 visitas,
  con días sueltos entre -146 y +368 cuando el efecto real es de unas 65-73 diarias. El
  ruido es cinco veces la señal. Publicar ese número haría que un martes cualquiera el canal
  dijera "-146 visitas" y alguien concluyera que la TV resta. A 7 días, en cambio, el
  estimador da t=2.06 y sí sostiene una lectura.
- El dato de AYER se reporta como movimiento de tráfico, explícitamente NO atribuido a TV.
  Es lo único honesto que se puede decir de un día suelto.
- Spots, TRP, inversión y franja del día sí son exactos: no dependen del estimador.

Uso local:
    python3 reporte_diario.py            # calcula e imprime, no envía
    python3 reporte_diario.py --enviar   # además postea a Google Chat
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import baseline as BL          # noqa: E402
import chat as CHAT            # noqa: E402
import estimador as EST        # noqa: E402
import horario as HOR          # noqa: E402
import panel as PANEL          # noqa: E402

sys.path.insert(0, os.path.dirname(HERE))
import contract as CONTRATO    # noqa: E402

VENTANA_DIAS = 7

# Se traduce a mano en vez de usar `locale`: el runner de GitHub no trae es_MX instalado y
# `setlocale` fallaría en silencio dejando los días en inglés dentro de una tarjeta en español.
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


# Marcador del último día que salió a Chat. Lo leen los horarios de respaldo del workflow
# (`--solo-si-falta`) para no mandar dos veces el mismo reporte. Se escribe SOLO cuando el
# webhook respondió bien: si falló, no hay marca y el siguiente horario lo reintenta.
ULTIMO_ENVIO = os.path.join(HERE, "ultimo_envio.json")


def ya_enviado(fecha, ruta=None):
    try:
        with open(ruta or ULTIMO_ENVIO, encoding="utf-8") as f:
            return json.load(f).get("fecha") == fecha.isoformat()
    except (OSError, ValueError):
        return False


def marcar_enviado(fecha, cuando, ruta=None):
    with open(ruta or ULTIMO_ENVIO, "w", encoding="utf-8") as f:
        json.dump({"fecha": fecha.isoformat(), "enviado": cuando}, f)
        f.write("\n")


def fecha_larga(d):
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


def ahora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SQL_TRAFICO = """
SELECT
  FORMAT_DATETIME('%Y-%m-%d %H:%M',
    DATETIME(TIMESTAMP_MICROS(event_timestamp), 'America/Mexico_City')) AS minuto,
  COUNT(*) AS sesiones
FROM `{proyecto}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{ini}' AND '{fin}'
  AND event_name = 'session_start'
GROUP BY 1
"""


# Leads WEB de México por día (hora CDMX: `fecha_creacion` ya viene en hora local), partidos
# según qué tan plausible es que la TV los mueva:
#   directo — sin UTM: alguien que llegó escribiendo la URL o por orgánico.
#   marca   — Google Ads de búsqueda de MARCA (campañas `sem_brand`): alguien que buscó "habi".
#   web     — todos los WEB. La mayoría es pauta de Meta/Google y se mueve con el presupuesto
#             digital, no con la TV: el salto del 17-30 ago fue eso. Va solo como contexto.
SQL_LEADS = """
SELECT
  FORMAT_DATE('%Y-%m-%d', DATE(fecha_creacion)) AS dia,
  COUNTIF(utm_source IS NULL) AS directo,
  COUNTIF(utm_source = 'google' AND LOWER(campana_mercadeo) LIKE '%sem_brand%') AS marca,
  COUNT(*) AS web
FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`
WHERE fuente_id = 3
  AND DATE(fecha_creacion) BETWEEN '{ini}' AND '{fin}'
GROUP BY 1
"""


def consultar_leads(desde, hasta, max_bytes=1_000_000_000):
    """{date: {directo, marca, web}} de leads WEB MX, entre dos `date` inclusive."""
    sql = SQL_LEADS.format(ini=desde.isoformat(), fin=hasta.isoformat())
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", "--max_rows=10000",
         f"--maximum_bytes_billed={max_bytes}"],
        input=sql, capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError(f"bq falló consultando leads: {out.stderr.strip()[:400]}")
    return {datetime.date.fromisoformat(f["dia"]):
            {k: int(f[k]) for k in ("directo", "marca", "web")}
            for f in json.loads(out.stdout or "[]")}


def consultar_trafico(desde, hasta, max_bytes=20_000_000_000):
    """Sesiones por minuto en hora CDMX, entre dos `date` inclusive.

    Se pide un día extra a cada lado: las tablas de GA4 se particionan por fecha UTC y CDMX
    va 6 horas atrás, así que los primeros minutos de un día local caen en la tabla anterior.
    """
    sql = SQL_TRAFICO.format(
        proyecto=BL.PROYECTO_GA4,
        ini=(desde - datetime.timedelta(days=1)).strftime("%Y%m%d"),
        fin=(hasta + datetime.timedelta(days=1)).strftime("%Y%m%d"))
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", "--max_rows=200000",
         f"--maximum_bytes_billed={max_bytes}"],
        input=sql, capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        raise RuntimeError(f"bq falló consultando tráfico: {out.stderr.strip()[:400]}")
    serie = {}
    for f in json.loads(out.stdout or "[]"):
        ts = datetime.datetime.strptime(f["minuto"], "%Y-%m-%d %H:%M")
        serie[ts] = float(f["sesiones"])
    return serie


def minutos_de_dia(serie, dia):
    return {t.hour * 60 + t.minute: v for t, v in serie.items() if t.date() == dia}


def calcular(serie, perfil, horas_sd, spots, inversion, hasta):
    """Arma el dict del reporte. `hasta` es el último día cubierto (ayer)."""
    dias = [hasta - datetime.timedelta(days=i) for i in range(VENTANA_DIAS - 1, -1, -1)]
    avisos = []

    excesos, horas_franja, sin_horario = [], {}, []
    for d in dias:
        spots_d = HOR.para_fecha(spots, d)
        if not spots_d:
            sin_horario.append(d)
            continue
        horas = HOR.horas_con_spot(spots_d)
        mins = minutos_de_dia(serie, d)
        if not mins:
            sin_horario.append(d)
            continue
        pdia = BL.perfil_de_dia(perfil, d.weekday())
        for hora, ex in EST.exceso_por_hora(mins, pdia, horas):
            excesos.append(ex)
            horas_franja.setdefault(HOR.franja_de_hora(spots_d).get(hora, "?"), []).append(ex)

    inc = EST.agregar(excesos)
    if horas_franja:
        f = max(horas_franja, key=lambda k: sum(horas_franja[k]))
        inc["franja_top"] = (f, sum(horas_franja[f]), len(horas_franja[f]))
    else:
        inc["franja_top"] = None

    # El dinero NO viene de `spots` (que es público y no lo lleva) sino del secret
    # TV_INVERSION_JSON, agregado por día y franja. Ver el docstring de ingesta.py.
    spots_ayer = HOR.para_fecha(spots, hasta)
    tot = HOR.totales_del_dia(inversion, hasta)
    plan = {
        "spots": tot[0] if tot else len(spots_ayer),
        "trp": tot[1] if tot else None,
        "inversion": tot[2] if tot else None,
        "franja_top": tot[3][0] if (tot and tot[3]) else None,
        "origen": (spots_ayer[0]["origen"] if spots_ayer else "sin horario"),
    }

    mins_ayer = minutos_de_dia(serie, hasta)
    pdia = BL.perfil_de_dia(perfil, hasta.weekday())
    obs = sum(mins_ayer.values())
    esp = sum(v for m, v in pdia.items() if m in mins_ayer)
    dia = {"observado": obs, "esperado": esp,
           "desvio_pct": (100 * (obs - esp) / esp) if esp else 0.0}

    # Red de seguridad para lo que el horario no contempla. La integración de LRDG del
    # 22-sep cayó en una hora ausente del horario proyectado: sin esto el reporte no solo la
    # ignoraba, sino que la usaba como referencia de normalidad y publicaba "no significativo"
    # en el día del pico más alto de la campaña.
    k_ayer = EST.factor_del_dia(mins_ayer, pdia, HOR.horas_con_spot(spots_ayer))
    anomalias = EST.horas_anomalas(mins_ayer, pdia, BL.sd_de_dia(horas_sd, hasta.weekday()),
                                   k_ayer)

    inv_7d = sum(v["inversion"]
                 for d in dias
                 for v in inversion.get(d.isoformat(), {}).values())
    costo = (inv_7d / inc["total"]) if (inv_7d and inc.get("total", 0) > 0) else None

    if plan["inversion"] is None:
        avisos.append("Sin cifras de inversión: falta el secret <b>TV_INVERSION_JSON</b> "
                      "para esta fecha.")
    if plan["origen"] == "proyectado":
        avisos.append("Cifras de ayer con <b>horario proyectado</b>: se corrigen al llegar "
                      "el as-run de la central.")
    if sin_horario:
        avisos.append(f"{len(sin_horario)} de {VENTANA_DIAS} días sin horario disponible — "
                      "el incremental cubre solo el resto.")
    if inc["n"] and not inc["significativo"]:
        avisos.append("El incremental de esta ventana <b>no es estadísticamente "
                      "significativo</b>: léelo como indicio, no como cifra firme.")
    reg = HOR.regularidad(spots)
    if reg is not None and reg < 0.7:
        avisos.append(f"La parrilla cambió: solo {100 * reg:.0f}% de las horas se repiten "
                      "entre semanas. La proyección pierde fiabilidad.")

    if anomalias:
        horas_sin_plan = [h for h, *_ in anomalias if h not in HOR.horas_con_spot(spots_ayer)]
        if horas_sin_plan:
            avisos.append(
                "Hay horas anómalas <b>fuera del horario de spots</b> "
                f"({', '.join(f'{h:02d}h' for h in horas_sin_plan)}). El incremental de 7 "
                "días NO las incluye: revisar si salió algo no contemplado en el plan.")

    return {"fecha": fecha_larga(hasta), "fecha_iso": hasta.isoformat(),
            "plan": plan, "dia": dia, "incremental": inc, "anomalias": anomalias,
            "costo_por_visita": costo, "avisos": avisos}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enviar", action="store_true", help="postear a Google Chat")
    ap.add_argument("--fecha", help="día a reportar (YYYY-MM-DD). Por defecto, ayer en CDMX")
    ap.add_argument("--solo-si-falta", action="store_true",
                    help="no hacer nada si el reporte de esa fecha ya se envió (horarios de respaldo)")
    ap.add_argument("--sin-panel", action="store_true",
                    help="no actualizar el panel de TV en salud-marca/data.json")
    args = ap.parse_args()

    hoy_cdmx = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=6)).date()
    hasta = datetime.date.fromisoformat(args.fecha) if args.fecha else \
        hoy_cdmx - datetime.timedelta(days=1)
    if args.solo_si_falta and ya_enviado(hasta):
        print(f"El reporte del {hasta.isoformat()} ya se envió: este horario es de respaldo y no hace nada.")
        return 0

    perfil = BL.cargar()
    horas_sd = BL.cargar_horas()
    spots = HOR.cargar()
    if not spots:
        print("ERROR: spots.csv está vacío o no existe. Correr ingesta.py con el as-run de "
              "la central; sin horario no hay nada que estimar.")
        return 1
    inversion = HOR.cargar_inversion()

    # Se pide desde el arranque del panel, no solo la ventana de 7 días: el tablero muestra la
    # serie diaria completa de la campaña y sale más barato una consulta que dos.
    desde = min(PANEL.DESDE, hasta - datetime.timedelta(days=VENTANA_DIAS))
    serie = consultar_trafico(desde, hasta)
    r = calcular(serie, perfil, horas_sd, spots, inversion, hasta)

    inc = r["incremental"]
    trp = f"{r['plan']['trp']:.1f} TRP" if r['plan']['trp'] is not None else "TRP s/d"
    inv = f"${r['plan']['inversion']:,.0f} MXN" if r['plan']['inversion'] is not None else "inv. s/d"
    print(f"{r['fecha_iso']}  plan: {r['plan']['spots']} spots · {trp} · {inv} "
          f"({r['plan']['origen']})")
    print(f"  tráfico del día: {r['dia']['observado']:,.0f} ({r['dia']['desvio_pct']:+.1f}%)")
    if inc["n"]:
        print(f"  incremental 7d: {inc['total']:,.0f} visitas  n={inc['n']}  "
              f"t={inc['t']:.2f}  {'SIGNIFICATIVO' if inc['significativo'] else 'no signif.'}")
    for h, o, e, x, sig in r["anomalias"]:
        print(f"  🔴 hora {h:02d}h ANÓMALA: obs {o:,.0f} vs esp {e:,.0f} "
              f"({x:+,.0f}, {sig:.1f} sigmas)")
    for a in r["avisos"]:
        print(f"  ⚠ {a}")

    if not args.sin_panel:
        try:
            # Los leads son un agregado aparte: si su consulta falla, el panel de tráfico
            # sale igual y la sección de leads simplemente no aparece.
            try:
                leads = consultar_leads(PANEL.BASE_LEADS[0], hasta)
            except Exception as e:
                leads = None
                print(f"WARN leads: {type(e).__name__}: {e}")
            bloque = PANEL.construir(serie, perfil, horas_sd, spots, hasta,
                                     minutos_de_dia, EST, HOR, BL, CONTRATO, ahora(),
                                     leads=leads)
            ruta = PANEL.inyectar(bloque)
            n = len(bloque["MX"].get("series") or [])
            print(f"  panel: {n} días escritos en {os.path.relpath(ruta)}")
        except Exception as e:
            # Que falle el panel no debe impedir el aviso a Chat: son dos entregables
            # independientes y el de Chat es el que la gente espera cada mañana.
            print(f"WARN panel: {type(e).__name__}: {e}")

    payload = CHAT.construir_tarjeta(r)
    if args.enviar:
        ok, detalle = CHAT.enviar(payload)
        print(f"  Google Chat: {'enviado' if ok else 'FALLÓ'} ({detalle})")
        if ok:
            marcar_enviado(hasta, ahora())
        # No se devuelve error: el cálculo ya está hecho y publicado en el log. Que el
        # webhook falle no debe marcar el job en rojo y disparar alertas de CI.
    else:
        print("\n" + json.dumps(payload, ensure_ascii=False, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
