import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline  # noqa: E402
import estimador  # noqa: E402
import horario  # noqa: E402
import panel  # noqa: E402

DIA = datetime.date(2026, 9, 23)  # miércoles


def _minutal(spots):
    # Tráfico plano de 5/min y un perfil igual: lo que se prueba es el rotulado de spots,
    # no el estimador.
    perfil = {(DIA.weekday(), m): 5.0 for m in range(1440)}
    horas_sd = {(DIA.weekday(), h): {"sd": 10.0} for h in range(24)}
    return panel.serie_minutal(None, perfil, horas_sd, spots, DIA,
                               lambda serie, d: {m: 5.0 for m in range(1440)},
                               estimador, horario, baseline)


def _spot(fecha, hh, mm, canal="CON-Canal 5", programa="NOTICIERO"):
    return {"ts": datetime.datetime.combine(fecha, datetime.time(hh, mm)),
            "canal": canal, "programa": programa}


def test_spots_al_minuto_y_ordenados():
    m = _minutal([_spot(DIA, 17, 30, "CON-nu9ve", "NOVELA"), _spot(DIA, 11, 13)])
    assert m["spots"] == [[11 * 60 + 13, "CON-Canal 5", "NOTICIERO"],
                          [17 * 60 + 30, "CON-nu9ve", "NOVELA"]]
    assert m["spots_origen"] == "as-run"
    assert m["horas_con_spot"] == [11, 17]


def test_spots_proyectados_se_rotulan():
    # El as-run es de la semana anterior: para DIA el horario sale proyectado.
    m = _minutal([_spot(DIA - datetime.timedelta(days=7), 9, 45)])
    assert m["spots"] == [[9 * 60 + 45, "CON-Canal 5", "NOTICIERO"]]
    assert m["spots_origen"] == "proyectado"


def test_sin_spots():
    m = _minutal([])
    assert m["spots"] == [] and m["spots_origen"] is None


def test_serie_diaria_rotula_origen_de_spots():
    antes = DIA - datetime.timedelta(days=7)
    perfil = {(d, m): 5.0 for d in range(7) for m in range(1440)}
    horas_sd = {(d, h): {"sd": 10.0} for d in range(7) for h in range(24)}
    serie = panel.serie_diaria(None, perfil, horas_sd, [_spot(antes, 9, 45)], antes, DIA,
                               lambda s, d: {m: 5.0 for m in range(1440)},
                               estimador, horario, baseline)
    por_fecha = {r["fecha"]: r for r in serie}
    assert por_fecha[antes.isoformat()]["spots_origen"] == "as-run"
    assert por_fecha[DIA.isoformat()]["spots_origen"] == "proyectado"
    assert por_fecha[DIA.isoformat()]["spots"] == 1
    # Entre medio no hay as-run de ese día de semana: ni spots ni origen.
    lunes = (antes + datetime.timedelta(days=5)).isoformat()
    assert por_fecha[lunes]["spots"] == 0 and por_fecha[lunes]["spots_origen"] is None


def _leads(desde, hasta, f):
    out, d = {}, desde
    while d <= hasta:
        out[d] = f(d)
        d += datetime.timedelta(days=1)
    return out


def test_leads_contrafactual_es_mediana_por_dia_de_semana():
    base = (datetime.date(2026, 7, 20), datetime.date(2026, 9, 6))
    # 7 semanas de base con directo=50; dos semanas infladas a 90 (como la pauta de 17-30 ago).
    def f(d):
        inflada = datetime.date(2026, 8, 17) <= d <= datetime.date(2026, 8, 30)
        return {"directo": 90 if inflada else 50, "marca": 20, "web": 200}
    leads = _leads(base[0], DIA, f)
    ld = panel.serie_leads(leads, [], datetime.date(2026, 9, 7), DIA, horario, base=base)
    fila = ld["series"]["directo"][0]
    # La mediana ignora las dos semanas infladas: el normal es 50, no el promedio (~61).
    assert fila["esperado"] == 50 and fila["observado"] == 50 and fila["exceso"] == 0
    assert len(ld["series"]["directo"]) == (DIA - datetime.date(2026, 9, 7)).days + 1
    assert set(ld["series"]) == {"directo", "marca", "web"}
    assert ld["ruido"]["directo"] > 0 and ld["ruido"]["marca"] == 0


def test_leads_rotula_spots_del_dia():
    base = (DIA - datetime.timedelta(days=14), DIA - datetime.timedelta(days=1))
    leads = _leads(base[0], DIA, lambda d: {"directo": 5, "marca": 1, "web": 10})
    ld = panel.serie_leads(leads, [_spot(DIA, 20, 8)], DIA, DIA, horario, base=base)
    fila = ld["series"]["marca"][0]
    assert fila["spots"] == 1 and fila["spots_origen"] == "as-run"


def test_sin_leads_no_hay_bloque():
    assert panel.serie_leads(None, [], DIA, DIA, horario) is None
    assert panel.serie_leads({}, [], DIA, DIA, horario) is None
