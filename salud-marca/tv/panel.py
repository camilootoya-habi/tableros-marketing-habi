"""Alimenta el panel de TV del tablero de salud de marca (`salud-marca/data.json`).

DOS SERIES, con alcances distintos a propósito:

- `series` (diaria) — tráfico observado contra el contrafactual del baseline, día a día desde
  antes del arranque de la campaña. Es DESCRIPTIVA: la brecha incluye todo lo que movió el día
  —pauta digital, estacionalidad, feriados—, no solo televisión. Se rotula así en el tablero,
  igual que en la tarjeta de Chat. Sirve para ver la forma de la campaña, no para atribuir.
- `minuto` — el último día completo, minuto a minuto, con su contrafactual. Es donde SÍ se ve
  el efecto de una emisión: el 22-sep la integración de La Rosa de Guadalupe dejó 206 visitas
  en el minuto 20:08 contra 7 esperadas.

POR QUÉ SOLO UN DÍA DE MINUTO A MINUTO: son 1.440 puntos por día. Guardar una semana metería
~10.000 puntos en un `data.json` que ya pesa 200 KB y que el navegador descarga entero antes
de pintar nada. Un día es ~25 KB y es el que la gente va a mirar.

ESTE MÓDULO NO DECIDE SI HUBO EFECTO. Solo prepara lo que se dibuja. La cifra de
incrementalidad con su intervalo vive en `reporte_diario.py` y se publica en Chat, que es
donde tiene el contexto para leerse bien.
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JSON = os.path.join(os.path.dirname(HERE), "data.json")

# Se arranca antes del primer spot (7-sep) para que el tablero muestre el contraste con los
# días previos. Sin ese tramo, la serie empieza ya dentro de la campaña y no hay contra qué
# comparar visualmente.
DESDE = datetime.date(2026, 8, 31)

RAZON_CO = ("La campaña de TV abierta es solo de México. Para CO no hay emisiones que medir "
            "ni export de GA4 con el que construir el contrafactual minuto a minuto.")


def _origen(spots_d):
    if not spots_d:
        return None
    return "proyectado" if any(f.get("origen") == "proyectado" for f in spots_d) else "as-run"


def serie_diaria(serie, perfil, horas_sd, spots, desde, hasta, minutos_de_dia, est, hor, bl):
    """[{fecha, observado, esperado, exceso, spots, spots_origen, anomalia, sigmas_max}, ...]

    `spots_origen` (as-run | proyectado | None) deja al tablero distinguir los días cuyo conteo
    de spots es real de los que salen del horario proyectado.
    """
    out = []
    d = desde
    while d <= hasta:
        mins = minutos_de_dia(serie, d)
        if mins:
            pdia = bl.perfil_de_dia(perfil, d.weekday())
            obs = sum(mins.values())
            esp = sum(pdia.values())
            spots_d = hor.para_fecha(spots, d)
            k = est.factor_del_dia(mins, pdia, hor.horas_con_spot(spots_d))
            anom = est.horas_anomalas(mins, pdia, bl.sd_de_dia(horas_sd, d.weekday()), k)
            out.append({
                "fecha": d.isoformat(),
                "observado": round(obs, 1),
                "esperado": round(esp, 1),
                "exceso": round(obs - esp, 1),
                "spots": len(spots_d),
                "spots_origen": _origen(spots_d),
                "anomalia": bool(anom),
                "sigmas_max": round(max(a[4] for a in anom), 1) if anom else None,
                "horas_anomalas": [a[0] for a in anom],
            })
        d += datetime.timedelta(days=1)
    return out


def serie_minutal(serie, perfil, horas_sd, spots, dia, minutos_de_dia, est, hor, bl):
    """{fecha, puntos: [[minuto, observado, esperado], ...], spots, spots_origen,
    horas_anomalas, horas_con_spot}.

    `spots` va al minuto ([[minuto, canal, programa], ...]) porque el tablero marca cada
    emisión sobre la curva; con solo la hora no se puede ubicar dentro de un bloque de 10 min.
    `spots_origen` dice si salen del as-run o del horario proyectado: un spot proyectado puede
    haber salido minutos antes o después, y el tablero lo rotula así.

    El esperado va reescalado por el nivel del día, igual que en el estimador: si no, un día
    globalmente bajo pintaría toda la línea observada por debajo del contrafactual y se leería
    como si la campaña restara tráfico.
    """
    mins = minutos_de_dia(serie, dia)
    if not mins:
        return None
    pdia = bl.perfil_de_dia(perfil, dia.weekday())
    spots_d = hor.para_fecha(spots, dia)
    horas = hor.horas_con_spot(spots_d)
    k = est.factor_del_dia(mins, pdia, horas)
    anom = est.horas_anomalas(mins, pdia, bl.sd_de_dia(horas_sd, dia.weekday()), k)
    puntos = [[m, round(mins.get(m, 0.0), 1), round(pdia.get(m, 0.0) * k, 2)]
              for m in range(1440)]
    marcas = sorted([f["ts"].hour * 60 + f["ts"].minute, f.get("canal", ""),
                     f.get("programa", "")] for f in spots_d)
    return {"fecha": dia.isoformat(), "puntos": puntos,
            "spots": marcas, "spots_origen": _origen(spots_d),
            "factor_dia": round(k, 3),
            "horas_con_spot": sorted(horas),
            "horas_anomalas": [{"hora": a[0], "observado": round(a[1], 1),
                                "esperado": round(a[2], 1), "exceso": round(a[3], 1),
                                "sigmas": round(a[4], 1)} for a in anom]}


def construir(serie, perfil, horas_sd, spots, hasta, minutos_de_dia, est, hor, bl,
              contrato, ahora):
    """El bloque `metrics.tv` completo, listo para inyectar en data.json."""
    diaria = serie_diaria(serie, perfil, horas_sd, spots, DESDE, hasta,
                          minutos_de_dia, est, hor, bl)
    if not diaria:
        mx = contrato.metric("error", reason="No hubo tráfico que leer para el período de TV.")
    else:
        mx = contrato.metric("ok", source="bq", series=diaria, last_updated=ahora)
        # `minuto` viaja fuera de `series` a propósito: no es otra fila de la misma serie sino
        # una vista distinta del último día, y meterlo dentro obligaría a que el tablero
        # distinguiera dos formas de fila en el mismo arreglo.
        m = serie_minutal(serie, perfil, horas_sd, spots, hasta,
                          minutos_de_dia, est, hor, bl)
        if m:
            mx["minuto"] = m
    return {"MX": mx, "CO": contrato.metric("not_available", reason=RAZON_CO)}


def inyectar(bloque, ruta=DATA_JSON):
    """Escribe `metrics.tv` en data.json SIN tocar el resto.

    No se regenera el archivo entero porque las otras métricas —Brand Lift, exit poll,
    encuestador— vienen de fuentes distintas y de corridas manuales de `build.py`. Un rewrite
    completo desde el cron diario borraría el caché de Brand Lift, que es el histórico bueno.
    """
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"no existe {ruta}: correr primero salud-marca/build.py")
    with open(ruta, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("metrics", {})["tv"] = bloque
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return ruta
