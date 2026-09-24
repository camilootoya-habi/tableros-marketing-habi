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
