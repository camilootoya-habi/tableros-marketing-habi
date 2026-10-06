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
import sources_pulso as PULSO
import sources_fb_posts as FBP
import sources_ig_posts as IGP
import sources_social as SOCIAL

HERE = os.path.dirname(os.path.abspath(__file__))


def collect_exit_poll():
    return BQ.exit_poll_series(BQ.run_query("queries/exit_poll.sql"))


def collect_traffic():
    return BQ.traffic_series(BQ.run_query("queries/trafico_plazas.sql"))


def collect_encuestador():
    """Serie de Pulso Inmobiliario, por su API pública de agregados.

    Una llamada HTTP sin credenciales: ese endpoint solo devuelve conteos, así
    que el tablero no necesita (ni debe tener) acceso a la base de la encuesta.
    Una fila por público (dueños y brokers): el tablero elige cuál mostrar.
    Hoy hay una sola ola; `series()` ya devuelve lista para que las siguientes
    se acumulen sin tocar esto."""
    return PULSO.series([PULSO.fetch(audiencia=a) for a in PULSO.AUDIENCIAS])


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


def _auto_map(rows, country, avisar=True):
    nuevos, saltados = BL.auto_map(rows, country)
    if nuevos:
        print(f"  brand_lift {country}: {len(nuevos)} preguntas nuevas mapeadas en questions.json")
    for sid, motivo in (saltados if avisar else []):
        print(f"WARN brand_lift {country}: estudio {sid} sin mapear — {motivo}")


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
    # Se vuelve a correr sobre lo fusionado si hay refresco: el aviso de lo que no se pudo mapear
    # sale una sola vez, en la segunda pasada (o aquí si se sirve desde el caché).
    _auto_map(country_cache, country, avisar=False)

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
        _auto_map(country_cache, country)
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

    _auto_map(merged, country)
    rows = BL.map_questions([r for r in merged if r["country"] == country])
    series = marca_parciales(BL.publishable(BL.nombrar_sin_identificar(BL.series(rows))), now)
    if not series:
        return contract.metric("not_available", reason=_sin_identificar(country))
    return contract.metric("ok", source="api", series=series, last_updated=now)


def collect_seguidores(now):
    """Seguidores FB + IG por marca. Mismo criterio de estados que Brand Lift: un fallo con
    caché se sirve `stale` con la fecha del último éxito real, nunca disfrazado de refresco."""
    cache = SOCIAL.load_cache()
    try:
        ok, fresh, errores = SOCIAL.fetch(now[:10])
    except Exception as e:
        ok, fresh, errores = False, {}, {"_": f"{type(e).__name__}: {e}"}
    for k, e in errores.items():
        print(f"WARN seguidores {k}: {e}")
    if ok:
        cache = SOCIAL.merge(cache, fresh)
        # Métricas mensuales de Instagram: el mes en curso y el anterior. Un fallo aquí no tumba
        # los seguidores diarios: se avisa y se sirve lo que ya había en el caché.
        try:
            cache = SOCIAL.merge_ig(cache, SOCIAL.fetch_ig_meses(meses=2))
        except Exception as e:
            print(f"WARN seguidores IG mensual: {type(e).__name__}: {e}")
        # Demografía de seguidores: Meta solo da la de hoy, así que se guarda como la foto del mes
        # (se sobrescribe cada día; la del último día del mes es la que queda).
        for clave, m in SOCIAL.MARCAS.items():
            try:
                cache["ig_demo"].setdefault(clave, {})[now[:7]] = SOCIAL.fetch_demografia(m["ig"])
            except Exception as e:
                print(f"WARN demografía {clave}: {type(e).__name__}: {e}")
        cache["last_refresh"] = now
    # Publicaciones de Instagram: las 100 más recientes de cada marca (likes, comentarios y, en las
    # de los últimos 45 días, vistas y demás). Un fallo de una marca no toca a las otras.
    imagenes = {}
    for clave, m in SOCIAL.MARCAS.items():
        if not ok:
            break
        try:
            cache["posts"][clave], imgs = IGP.actualizar(cache["posts"].get(clave, {}), m["ig"], hoy=now[:10])
            imagenes.update(imgs)
        except Exception as e:
            print(f"WARN publicaciones {clave}: {type(e).__name__}: {e}")
    # Facebook: las 100 publicaciones más recientes de cada página y la ciudad de sus seguidores.
    # Van con el token de la PÁGINA, que sale de `me/accounts`.
    fb_imagenes, fb_tokens = {}, {}
    if ok:
        _, _, paginas = SOCIAL._token_paginas()
        for clave, m in SOCIAL.MARCAS.items():
            ptok = (paginas.get(m["fb"]) or {}).get("access_token")
            if not ptok:
                print(f"WARN Facebook {clave}: el token no ve la página")
                continue
            fb_tokens[clave] = ptok
            try:
                cache["fb_posts"][clave], imgs = FBP.actualizar(cache["fb_posts"].get(clave, {}), m["fb"], ptok, hoy=now[:10])
                fb_imagenes.update(imgs)
            except Exception as e:
                print(f"WARN publicaciones FB {clave}: {type(e).__name__}: {e}")
            try:
                cache["ig_demo"].setdefault(clave, {}).setdefault(now[:7], {})["fb_ciudad"] = \
                    SOCIAL.fetch_fb_ciudades(m["fb"], ptok)
            except Exception as e:
                print(f"WARN ciudades FB {clave}: {type(e).__name__}: {e}")
    # Top 5 de los últimos 180 días (por interacciones de Meta) y de toda la historia (por likes +
    # comentarios, la única métrica que tienen todos los posts), cada uno con todas las
    # publicaciones y solo las orgánicas. Verificar la pauta llama a la API: se hace solo con los
    # candidatos y el resultado queda en el caché. Sin conexión (`ok` falso) no se verifica nada.
    verificar = IGP.con_pauta if ok else None
    hace180 = (datetime.date.fromisoformat(now[:10]) - datetime.timedelta(days=180)).isoformat()
    tops = {}
    for c in SOCIAL.MARCAS:
        posts_c = cache["posts"].get(c, {})
        tops[c] = {}
        for periodo, desde, criterio in (("180", hace180, IGP.puntaje), ("historico", "", IGP.likes_coment)):
            todas = IGP.top(posts_c, desde, n=10, criterio=criterio)
            for p in todas:
                if "pauta" not in p and verificar:
                    v = verificar(p["id"])
                    if v is not None:
                        p["pauta"] = posts_c[p["id"]]["pauta"] = v
            tops[c][periodo] = {"todas": todas,
                                "organicas": IGP.top(posts_c, desde, n=10, organicas=True, criterio=criterio, verificar=verificar)}
    # Top 10 de Facebook por reacciones + comentarios + compartidos. Sin filtro de pauta: la API no
    # dice si un post de Facebook se promocionó (ver sources_fb_posts.py).
    fb_tops = {c: {"180": FBP.top(cache["fb_posts"].get(c, {}), hace180),
                   "historico": FBP.top(cache["fb_posts"].get(c, {}))} for c in SOCIAL.MARCAS}
    if ok:
        SOCIAL.save_cache(cache["datos"], now, cache.get("ig_mes"), cache.get("posts"), cache.get("ig_demo"),
                          cache.get("fb_posts"))
    fb_en_top = [p for c, per in fb_tops.items() for lista in per.values() for p in lista]
    for p in fb_en_top:
        c = next(k for k, t in fb_tops.items() if p in t["180"] or p in t["historico"])
        if (p["id"] not in fb_imagenes and c in fb_tokens
                and not os.path.exists(os.path.join(FBP.MINIATURAS, f"{p['id']}.jpg"))):
            fb_imagenes[p["id"]] = FBP.url_imagen(p["id"], fb_tokens[c])
    try:
        fb_con_img = FBP.miniaturas([fb_en_top], fb_imagenes)
    except Exception as e:
        print(f"WARN miniaturas FB: {type(e).__name__}: {e}")
        fb_con_img = set()

    # Miniaturas: las de la lista de hoy ya traen URL; las de posts viejos se piden una por una.
    en_top = [p for c in tops.values() for per in c.values() for lista in per.values() for p in lista]
    if ok:
        for p in en_top:
            if p["id"] not in imagenes and not os.path.exists(os.path.join(IGP.MINIATURAS, f"{p['id']}.jpg")):
                imagenes[p["id"]] = IGP.url_imagen(p["id"])
    try:
        con_img = IGP.miniaturas([en_top], imagenes)
    except Exception as e:
        print(f"WARN miniaturas: {type(e).__name__}: {e}")
        con_img = set()

    # `series` va por MES (años de historia sin inflar data.json) y `diario` trae los últimos 45
    # días, que es donde vive la serie de Instagram (Meta solo da 30 días de nuevos).
    out = {}
    for clave in SOCIAL.MARCAS:
        diaria = SOCIAL.series(cache.get("datos", {}), clave)
        serie = SOCIAL.mensual(diaria, cache.get("ig_mes", {}).get(clave))
        # Publicaciones por mes y formato: van en la misma fila del mes que el resto.
        por_mes = {r["month"]: r for r in serie}
        for mes, v in IGP.mensual(cache["posts"].get(clave, {})).items():
            por_mes.setdefault(mes, {"month": mes}).update(v)
        for mes, v in FBP.mensual(cache["fb_posts"].get(clave, {})).items():
            por_mes.setdefault(mes, {"month": mes}).update(v)
        serie = [por_mes[k] for k in sorted(por_mes)]
        fallo = (not ok) or clave in errores
        if not serie:
            out[clave] = contract.metric(
                "error", reason=errores.get(clave) or errores.get("_") or "Sin datos de seguidores.")
            continue
        if fallo:
            out[clave] = contract.metric("stale", source="cache", series=serie,
                                         last_updated=cache.get("last_refresh"))
        else:
            out[clave] = contract.metric("ok", source="api", series=serie, last_updated=now)
        out[clave]["diario"] = diaria[-45:]
        img = lambda p: dict(p, img=f"ig_miniaturas/{p['id']}.jpg" if p["id"] in con_img else None)
        out[clave]["top_posts"] = {per: {k: [img(p) for p in lista] for k, lista in listas.items()}
                                   for per, listas in tops[clave].items()}
        fb_img = lambda p: dict(p, img=f"fb_miniaturas/{p['id']}.jpg" if p["id"] in fb_con_img else None)
        out[clave]["fb_top"] = {per: [fb_img(p) for p in lista] for per, lista in fb_tops[clave].items()}
        demo = cache.get("ig_demo", {}).get(clave) or {}
        if demo:
            out[clave]["demografia"] = {"mes": max(demo), **demo[max(demo)]}
        # Cuántas publicaciones de los últimos 180 días tuvieron pauta: contexto para el filtro.
        recientes = [p for p in cache["posts"].get(clave, {}).values() if p["fecha"] >= hace180]
        out[clave]["pauta_180"] = {"total": len(recientes),
                                   "con_pauta": sum(1 for p in recientes if p.get("pauta") is True),
                                   "verificadas": sum(1 for p in recientes if "pauta" in p)}
    return out


def _try(fn, *a, source="bq"):
    """Envoltura genérica para drivers de dos estados (éxito con serie / excepción → error).
    Brand Lift tiene un tercer estado (stale) que depende del resultado de `fetch()`, no de
    una excepción, así que `collect_brand_lift` ya devuelve su propio metric y se aísla aparte
    en `_try_brand_lift` (misma garantía de aislamiento, forma distinta)."""
    try:
        return contract.metric("ok", source=source, series=fn(*a)), None
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
    encuestador_mx, _ = _try(collect_encuestador, source="pulso")
    if exit_poll_mx["status"] == "ok":
        exit_poll_mx["last_updated"] = now
    if traffic_mx["status"] == "ok":
        traffic_mx["last_updated"] = now
    if encuestador_mx["status"] == "ok":
        encuestador_mx["last_updated"] = now

    try:
        seguidores = collect_seguidores(now)
    except Exception as e:
        print(f"WARN collect_seguidores: {e}")
        seguidores = {c: contract.metric("error", reason=f"{type(e).__name__}: {e}")
                      for c in SOCIAL.MARCAS}

    metrics = {
        "seguidores": seguidores,
        "brand_lift": {c: _try_brand_lift(c, now) for c in ("MX", "CO")},
        "traffic": {"MX": traffic_mx,
                    "CO": contract.metric("not_available",
                                          reason=contract.NOT_AVAILABLE[("traffic", "CO")])},
        "exit_poll": {"MX": exit_poll_mx,
                      "CO": contract.metric("not_available",
                                            reason=contract.NOT_AVAILABLE[("exit_poll", "CO")])},
        "encuestador": {"MX": encuestador_mx,
                        "CO": contract.metric("not_available", planned=True,
                                              reason=contract.NOT_AVAILABLE[("encuestador", "CO")])},
    }
    return contract.envelope(metrics, now)


# Bloques de `metrics` que escribe OTRO job y que este build no debe borrar al reescribir el
# archivo. `tv` lo inyecta tv/reporte_diario.py (tv-diario.yml): antes, correr build.py después
# del reporte de TV dejaba el panel vacío y había que respetar un orden a mano.
AJENOS = ("tv",)


def conservar_ajenos(nuevo, ruta):
    """Copia a `nuevo` los bloques AJENOS del data.json que ya existe en `ruta`."""
    try:
        with open(ruta, encoding="utf-8") as f:
            viejo = json.load(f).get("metrics", {})
    except (OSError, ValueError):
        return nuevo
    for k in AJENOS:
        if k in viejo and k not in nuevo["metrics"]:
            nuevo["metrics"][k] = viejo[k]
    return nuevo


if __name__ == "__main__":
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ruta = os.path.join(HERE, "data.json")
    data = conservar_ajenos(collect(now), ruta)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    for k, per in data["metrics"].items():
        for c, m in per.items():
            n = len(m.get("series") or [])
            print(f"  {k:<11} {c}: {m['status']:<14} {n} filas")
