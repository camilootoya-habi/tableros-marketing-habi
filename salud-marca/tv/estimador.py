"""Estimadores de tráfico incremental de TV. Funciones puras: reciben series y horarios,
devuelven números. Nada de BigQuery ni de red aquí — eso vive en `reporte_diario.py`.

DOS ESTIMADORES, y la diferencia importa:

- `exceso_por_hora` (BANDA) — solo necesita saber QUÉ HORAS tuvieron spot, no el minuto.
  Es el que usa el reporte diario, porque el horario proyectado no conoce el minuto exacto.
  Validado sobre la semana 1: n=52 horas-con-spot, t=2.06, significativo. El control sobre
  364 horas equivalentes de semanas SIN TV da media -0.00 — insesgado, no inventa efecto.

- `exceso_por_spot` (MINUTO) — necesita la hora exacta de emisión, o sea el as-run.
  Es el que corre los lunes para corregir la cifra. Mismo período: t=4.00.

La unidad de observación del estimador de banda es la HORA-CON-SPOT, no el día. Es la
decisión que hace viable el reporte: agrupando por día son 7 observaciones por ventana y
t=1.30 (no significativo); por hora-con-spot son ~52 y t=2.06. El efecto es el mismo, lo
que cambia es cuánta evidencia se aprovecha para medirlo.

POR QUÉ EL FACTOR DEL DÍA SE CALCULA CON LAS HORAS SIN SPOT: un día puede venir alto o bajo
por razones ajenas a la TV — la pauta digital subió, hubo noticia, fue feriado. Si el nivel
del día se estimara con todas las horas, el propio efecto de la TV entraría en el
denominador y se cancelaría solo. Usando únicamente las horas limpias, el factor mide el
día y la comparación queda para las horas con spot.
"""
import math

VENTANA_MIN = 15          # minutos post-emisión del estimador de minuto
DERIVA_MAX_MIN = 15       # deriva de horario que el método tolera (ver README)


def _t_critico():
    """1.96: normal al 95%. Con n>=30 la diferencia contra la t de Student es despreciable
    y evita cargar scipy en el runner."""
    return 1.96


def factor_del_dia(minutos_dia, perfil_dia, horas_con_spot):
    """Nivel del día medido SOLO en las horas sin spot: observado/esperado.

    `minutos_dia`  -> {minuto_del_dia: sesiones observadas}
    `perfil_dia`   -> {minuto_del_dia: sesiones esperadas (baseline congelado)}
    Devuelve 1.0 si no hay horas limpias con las que medir — un día enteramente cubierto de
    spots no permite estimar su propio nivel, y forzar un factor inventado sería peor.

    SE ITERA SOBRE EL PERFIL, NO SOBRE LO OBSERVADO: BigQuery no devuelve fila para los
    minutos sin una sola sesión (la madrugada, sobre todo). Recorriendo lo observado, esos
    minutos desaparecían del denominador mientras seguían contando en las horas con spot,
    lo que inflaba `k` y se comía el efecto — sobre la semana 1 daba -88 visitas en vez de
    +591. Un minuto ausente es un minuto con CERO tráfico, no un minuto inexistente.
    """
    obs = esp = 0.0
    for minuto, e in perfil_dia.items():
        if minuto // 60 in horas_con_spot:
            continue
        obs += minutos_dia.get(minuto, 0.0)
        esp += e
    if esp <= 0:
        return 1.0
    return obs / esp


def exceso_por_hora(minutos_dia, perfil_dia, horas_con_spot):
    """Exceso observado-esperado de cada hora con spot, ya reescalado por el nivel del día.

    Devuelve [(hora, exceso), ...] — una observación por hora, que es la unidad del test.
    """
    k = factor_del_dia(minutos_dia, perfil_dia, horas_con_spot)
    out = []
    for hora in sorted(horas_con_spot):
        obs = esp = 0.0
        for minuto in range(hora * 60, hora * 60 + 60):
            if minuto in minutos_dia:
                obs += minutos_dia[minuto]
            e = perfil_dia.get(minuto)
            if e is not None:
                esp += e
        out.append((hora, obs - esp * k))
    return out


def exceso_por_spot(serie, perfil, emisiones, ventana=VENTANA_MIN):
    """Exceso en [T, T+ventana) para cada emisión con hora exacta.

    `serie`     -> {datetime al minuto: sesiones}
    `perfil`    -> {(dia_semana, minuto_del_dia): sesiones esperadas}
    `emisiones` -> [datetime, ...]
    """
    import datetime as _dt
    out = []
    for ts in emisiones:
        obs = esp = 0.0
        for i in range(ventana):
            t = ts + _dt.timedelta(minutes=i)
            obs += serie.get(t, 0.0)
            e = perfil.get((t.weekday(), t.hour * 60 + t.minute))
            if e is not None:
                esp += e
        out.append((ts, obs - esp))
    return out


def agregar(excesos):
    """Resumen estadístico de una lista de excesos.

    El total es la suma; el intervalo sale de la dispersión ENTRE observaciones, no de una
    Poisson teórica: el ruido real del tráfico web es bastante mayor que el poissoniano y
    asumir lo contrario produciría intervalos demasiado angostos y significancias falsas.
    """
    n = len(excesos)
    if n == 0:
        return {"n": 0, "total": 0.0, "media": 0.0, "ic_bajo": 0.0, "ic_alto": 0.0,
                "t": None, "significativo": False}
    media = sum(excesos) / n
    if n == 1:
        return {"n": 1, "total": excesos[0], "media": media, "ic_bajo": None,
                "ic_alto": None, "t": None, "significativo": False}
    var = sum((x - media) ** 2 for x in excesos) / (n - 1)
    se = math.sqrt(var / n)
    z = _t_critico()
    t = media / se if se > 0 else None
    return {
        "n": n,
        "total": media * n,
        "media": media,
        "ic_bajo": (media - z * se) * n,
        "ic_alto": (media + z * se) * n,
        "t": t,
        "significativo": bool(t is not None and abs(t) > z),
    }


def franja_mas_incremental(excesos_por_hora, franja_de_hora):
    """Agrupa los excesos horarios por franja (A/AA/AAA) y devuelve la de mayor total.

    `excesos_por_hora` -> [(hora, exceso), ...] acumulado de la ventana
    `franja_de_hora`   -> {hora: 'AAA'|'AA'|'A'}
    Devuelve (franja, total, n_horas) o None si no hay nada que agrupar.
    """
    acc = {}
    for hora, exceso in excesos_por_hora:
        f = franja_de_hora.get(hora)
        if f is None:
            continue
        a = acc.setdefault(f, [0.0, 0])
        a[0] += exceso
        a[1] += 1
    if not acc:
        return None
    f = max(acc, key=lambda k: acc[k][0])
    return f, acc[f][0], acc[f][1]
