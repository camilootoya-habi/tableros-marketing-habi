#!/usr/bin/env python3
"""Ensambla salud-marca/data.json. Tres drivers independientes: si uno falla, los otros
escriben (mismo criterio de aislamiento que scripts/run_queries.py).
Uso: python3 build.py  (desde la carpeta del tablero; requiere bq autenticado y
META_SYSTEM_USER_TOKEN o META_PCOM_TOKEN para Brand Lift)."""
import datetime
import json
import os

import contract
import sources_bq as BQ
import sources_brand_lift as BL

HERE = os.path.dirname(os.path.abspath(__file__))


def collect_exit_poll():
    return BQ.exit_poll_series(BQ.run_query("queries/exit_poll.sql"))


def collect_traffic():
    return BQ.traffic_series(BQ.run_query("queries/trafico_plazas.sql"))


def _refresco_reciente(last_refresh, now):
    """¿Ya se refrescó hoy? El cron del hub corre cada 4 h; los estudios de Brand Lift son
    mensuales y sus resultados se actualizan a diario como máximo, así que refrescar en cada
    corrida gastaría 12 llamadas diarias por país contra una cuenta publicitaria de PRODUCCIÓN
    sin traer un solo dato nuevo.

    Se compara la **fecha UTC**, no las horas transcurridas. Con un umbral en horas el gate no
    cumple lo que promete: con 20 h y un cron alineado a múltiplos de 4, un refresco a la hora 0
    vuelve a ser elegible a la hora 20 del MISMO día → dos llamadas en un día. Comparar fechas
    da la garantía dura de una llamada por país por día calendario, sin depender de la
    alineación del cron."""
    if not last_refresh or not now:
        return False
    return str(last_refresh)[:10] == str(now)[:10]


def marca_parciales(series, now):
    """Marca las filas cuyo estudio todavía no cerró.

    Un estudio mensual de Brand Lift sigue abierto hasta el primer día del mes siguiente, así que
    el mes en curso siempre es un dato en vuelo: su cifra puede moverse. Sin marcarlo, el tablero
    lo pinta igual que un mes cerrado y alguien lo lee como definitivo.

    Ojo con la interpretación: Meta llena su cuota de encuestados a lo largo de la ventana, no
    proporcional a los días transcurridos, así que un mes parcial suele traer una muestra casi
    completa y un intervalo de confianza igual de estrecho que un mes cerrado. Parcial no es
    sinónimo de impreciso — pero sí de provisional."""
    for r in series:
        r["parcial"] = bool(r.get("end_time")) and str(r["end_time"])[:10] > str(now)[:10]
    return series


def _sin_identificar(country):
    """Un país con estudios pero sin preguntas mapeadas no está 'desactualizado': le falta una
    pieza distinta. Servirlo como `stale` con serie vacía pintaría un chart en blanco, que se
    lee como 'no hay marca que medir' en vez de 'falta identificar las preguntas'."""
    return (f"Hay estudios de Brand Lift de {country} en el caché, pero sus preguntas todavía no "
            f"están identificadas: el `experiment_id` cambia cada mes y la API no trae la etiqueta "
            f"de la pregunta. Publicar la serie sin saber cuál es Ad Recall y cuál TOMA sería "
            f"adivinar. Pendiente de leer las etiquetas en Ads Manager → Experimentos y agregarlas "
            f"a questions.json.")


def collect_brand_lift(country, now):
    """Caché + refresco incremental. El estado (ok/stale/error) depende de si `fetch()` tuvo
    éxito, no de si hubo una excepción: `fetch()` fallando y devolviendo el caché de siempre
    NO es lo mismo que un refresco exitoso, y disfrazar uno de otro le mentiría al timestamp
    (`last_updated`) y al badge de "desactualizado" del tablero.

    - Éxito: se funde lo nuevo dentro del caché completo (nunca se encoge) y se persiste en
      disco junto con el timestamp de este éxito → status="ok", source="api".
    - Fallo con caché disponible: se sirve la serie completa del caché tal cual estaba, con
      el timestamp del ÚLTIMO éxito real (no `now`) → status="stale", source="cache".
    - Fallo sin caché para ese país: no hay nada que servir → status="error"."""
    all_cache = BL.load_cache()
    country_cache = [r for r in all_cache if r["country"] == country]

    def _desde_cache(status, last_updated):
        series = marca_parciales(BL.publishable(BL.nombrar_sin_identificar(BL.series(BL.map_questions(country_cache)))), now)
        if not series:
            return contract.metric("not_available", reason=_sin_identificar(country))
        return contract.metric(status, source="cache", series=series, last_updated=last_updated)

    # Compuerta de cuota: si ya se refrescó hoy, no se llama a la API. El dato sigue vigente,
    # así que es `ok`, no `stale` — no está viejo, simplemente no hacía falta volver a pedirlo.
    previo = BL.load_last_refresh().get(country)
    if _refresco_reciente(previo, now):
        print(f"  brand_lift {country}: ya se refrescó hoy ({previo}), se sirve el caché")
        return _desde_cache("ok", previo)

    ok, fresh = BL.fetch(country)

    if not ok:
        if not country_cache:
            return contract.metric(
                "error",
                reason=f"Brand Lift API falló para {country} y no hay caché histórico que servir.")
        return _desde_cache("stale", previo)

    merged = BL.merge_rows(all_cache, fresh)
    refresh_times = BL.load_last_refresh()
    refresh_times[country] = now
    BL.save_cache(merged, refresh_times)

    rows = BL.map_questions([r for r in merged if r["country"] == country])
    series = marca_parciales(BL.publishable(BL.nombrar_sin_identificar(BL.series(rows))), now)
    if not series:
        return contract.metric("not_available", reason=_sin_identificar(country))
    return contract.metric("ok", source="api", series=series, last_updated=now)


def _try(fn, *a):
    """Envoltura genérica para drivers de dos estados (éxito con serie / excepción → error).
    Brand Lift tiene un tercer estado (stale) que depende del resultado de `fetch()`, no de
    una excepción, así que `collect_brand_lift` ya devuelve su propio metric y se aísla aparte
    en `_try_brand_lift` (misma garantía de aislamiento, forma distinta)."""
    try:
        return contract.metric("ok", source="bq", series=fn(*a)), None
    except Exception as e:
        print(f"WARN {fn.__name__}: {e}")
        return contract.metric("error", reason=f"{type(e).__name__}: {e}"), e


def _try_brand_lift(country, now):
    try:
        return collect_brand_lift(country, now)
    except Exception as e:
        print(f"WARN collect_brand_lift({country}): {e}")
        return contract.metric("error", reason=f"{type(e).__name__}: {e}")


def collect(now):
    exit_poll_mx, _ = _try(collect_exit_poll)
    traffic_mx, _ = _try(collect_traffic)
    if exit_poll_mx["status"] == "ok":
        exit_poll_mx["last_updated"] = now
    if traffic_mx["status"] == "ok":
        traffic_mx["last_updated"] = now

    metrics = {
        "brand_lift": {c: _try_brand_lift(c, now) for c in ("MX", "CO")},
        "traffic": {"MX": traffic_mx,
                    "CO": contract.metric("not_available",
                                          reason=contract.NOT_AVAILABLE[("traffic", "CO")])},
        "exit_poll": {"MX": exit_poll_mx,
                      "CO": contract.metric("not_available",
                                            reason=contract.NOT_AVAILABLE[("exit_poll", "CO")])},
    }
    return contract.envelope(metrics, now)


if __name__ == "__main__":
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = collect(now)
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    for k, per in data["metrics"].items():
        for c, m in per.items():
            n = len(m.get("series") or [])
            print(f"  {k:<11} {c}: {m['status']:<14} {n} filas")
