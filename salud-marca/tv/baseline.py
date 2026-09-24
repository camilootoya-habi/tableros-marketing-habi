"""Perfil minuto a minuto del tráfico SIN televisión. Es el contrafactual del reporte.

Se construye una sola vez sobre el período previo a la campaña (20-jul a 6-sep 2026, siete
semanas Lun-Dom completas) y se congela en `baseline.json`, que se commitea al repo.

POR QUÉ CONGELADO Y NO ROLANTE: si el baseline se recalculara con datos recientes, iría
absorbiendo el propio efecto de la campaña — cada semana el "normal" subiría un poco y el
incremental medido bajaría, hasta desaparecer. Un contrafactual tiene que venir de un
período donde el tratamiento no existía. Como la campaña arranca el 7-sep y termina en
noviembre, siete semanas previas alcanzan sin que la deriva estacional muerda.

LO QUE SÍ SE AJUSTA EN CADA CORRIDA: el NIVEL del día, vía `estimador.factor_del_dia`, que
se estima con las horas sin spot de ese mismo día. Así el perfil aporta la FORMA (cómo se
reparte el tráfico dentro del día, qué día de la semana pesa más) y el día aporta su propia
altura. Sin eso, cualquier cambio de nivel — más pauta digital, un feriado — se leería como
efecto de TV.

CUÁNDO HAY QUE REGENERARLO: si la campaña se extiende más allá de 2026 o si el sitio cambia
de forma estructural (rediseño, dominio nuevo, cambio de medición). Regenerar con:
    python3 salud-marca/tv/baseline.py
"""
import datetime
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(HERE, "baseline.json")

INICIO, FIN = "2026-07-20", "2026-09-06"
PROYECTO_GA4 = "papyrus-data-mx.analytics_325611813"

SQL = """
SELECT
  FORMAT_DATETIME('%Y-%m-%d %H:%M',
    DATETIME(TIMESTAMP_MICROS(event_timestamp), 'America/Mexico_City')) AS minuto,
  COUNT(*) AS sesiones
FROM `{proyecto}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{ini}' AND '{fin}'
  AND event_name = 'session_start'
GROUP BY 1
"""


def consultar(ini=INICIO, fin=FIN, max_bytes=20_000_000_000):
    """Trae el conteo de session_start por minuto en hora CDMX.

    Se pide un día extra a cada lado del rango en el sufijo de tabla: las tablas de GA4 están
    particionadas por fecha UTC y CDMX va 6 horas atrás, así que los primeros minutos de un
    día local viven en la tabla del día anterior.
    """
    d_ini = (datetime.date.fromisoformat(ini) - datetime.timedelta(days=1)).strftime("%Y%m%d")
    d_fin = (datetime.date.fromisoformat(fin) + datetime.timedelta(days=1)).strftime("%Y%m%d")
    sql = SQL.format(proyecto=PROYECTO_GA4, ini=d_ini, fin=d_fin)
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", "--max_rows=200000",
         f"--maximum_bytes_billed={max_bytes}"],
        input=sql, capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        raise RuntimeError(f"bq falló construyendo el baseline: {out.stderr.strip()[:400]}")
    return json.loads(out.stdout or "[]")


def construir_horas(filas, ini=INICIO, fin=FIN):
    """{dia_semana: {hora: {media, sd}}} de los totales por hora del baseline.

    Existe para poder decir si una hora concreta es ANÓMALA, no solo si está por encima del
    promedio. Sin la dispersión no hay forma de distinguir una hora que subió porque el día
    venía bueno de una que subió porque salió un comercial: la del 22-sep a las 20h tuvo
    1.614 visitas contra 470 esperadas, y eso solo se puede calificar comparándolo con
    cuánto varía normalmente esa hora.
    """
    d_ini = datetime.date.fromisoformat(ini)
    d_fin = datetime.date.fromisoformat(fin)
    por_dia = {}
    for f in filas:
        ts = datetime.datetime.strptime(f["minuto"], "%Y-%m-%d %H:%M")
        if not (d_ini <= ts.date() <= d_fin):
            continue
        por_dia.setdefault((ts.date(), ts.hour), 0.0)
        por_dia[(ts.date(), ts.hour)] += float(f["sesiones"])

    agrup = {}
    for (fecha, hora), v in por_dia.items():
        agrup.setdefault((fecha.weekday(), hora), []).append(v)

    out = {}
    for (dow, hora), vals in agrup.items():
        n = len(vals)
        media = sum(vals) / n
        sd = (sum((x - media) ** 2 for x in vals) / (n - 1)) ** 0.5 if n > 1 else 0.0
        out.setdefault(str(dow), {})[str(hora)] = {"media": round(media, 2),
                                                   "sd": round(sd, 2), "n": n}
    return out


def construir(filas, ini=INICIO, fin=FIN):
    """filas de bq → {dia_semana: {minuto_del_dia: sesiones promedio}}.

    Los minutos sin ninguna sesión en el período NO se omiten: se dejan en 0.0 explícito. Un
    minuto ausente y un minuto con cero tráfico son cosas distintas para el estimador, que
    salta los ausentes — si la madrugada quedara ausente, el esperado de esas horas sería
    cero y cualquier visita nocturna se contaría como incremental.
    """
    d_ini = datetime.date.fromisoformat(ini)
    d_fin = datetime.date.fromisoformat(fin)
    suma, dias_por_dow = {}, {}
    for d in range((d_fin - d_ini).days + 1):
        dias_por_dow[(d_ini + datetime.timedelta(days=d)).weekday()] = \
            dias_por_dow.get((d_ini + datetime.timedelta(days=d)).weekday(), 0) + 1

    for f in filas:
        ts = datetime.datetime.strptime(f["minuto"], "%Y-%m-%d %H:%M")
        if not (d_ini <= ts.date() <= d_fin):
            continue
        clave = (ts.weekday(), ts.hour * 60 + ts.minute)
        suma[clave] = suma.get(clave, 0.0) + float(f["sesiones"])

    perfil = {}
    for dow in range(7):
        n = dias_por_dow.get(dow, 0)
        if not n:
            continue
        perfil[str(dow)] = {str(m): round(suma.get((dow, m), 0.0) / n, 4)
                            for m in range(1440)}
    return perfil


def guardar(perfil, horas=None, ruta=RUTA, ini=INICIO, fin=FIN):
    payload = {
        "generado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "periodo": [ini, fin],
        "metrica": "session_start por minuto, hora CDMX",
        "nota": "Baseline CONGELADO a propósito: ver docstring de baseline.py",
        "perfil": perfil,
        "horas": horas or {},
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    return payload


def cargar(ruta=RUTA):
    """→ {(dia_semana, minuto_del_dia): esperado}, que es la forma que consume el estimador."""
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    return {(int(dow), int(m)): v
            for dow, minutos in d["perfil"].items()
            for m, v in minutos.items()}


def perfil_de_dia(perfil, dia_semana):
    return {m: v for (dow, m), v in perfil.items() if dow == dia_semana}


def cargar_horas(ruta=RUTA):
    """→ {(dia_semana, hora): {media, sd, n}} para calificar anomalías por hora."""
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    return {(int(dow), int(h)): v
            for dow, horas in d.get("horas", {}).items()
            for h, v in horas.items()}


def sd_de_dia(horas, dia_semana):
    return {h: v["sd"] for (dow, h), v in horas.items() if dow == dia_semana}


if __name__ == "__main__":
    filas = consultar()
    p = construir(filas)
    meta = guardar(p, construir_horas(filas))
    total = sum(sum(v.values()) for v in p.values())
    print(f"baseline {meta['periodo'][0]} → {meta['periodo'][1]}: "
          f"{len(p)} días de semana, {total:,.0f} sesiones/semana promedio")
