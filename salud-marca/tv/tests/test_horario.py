import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import horario  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def spot(dia, hora, minuto=0, canal="CON-Las Estrellas", programa="X", franja="AAA",
         trp=1.0, inversion=1000.0):
    return {"ts": datetime.datetime(2026, 9, dia, hora, minuto), "canal": canal,
            "programa": programa, "trp": trp, "inversion": inversion, "franja": franja,
            "origen": "as-run"}


def test_horas_con_spot_colapsa_minutos():
    s = [spot(7, 20, 5), spot(7, 20, 47), spot(7, 9, 12)]
    assert horario.horas_con_spot(s) == {20, 9}


def test_franja_de_hora_prefiere_la_mas_especifica():
    """Dos spots en la misma hora con franja distinta pasa en los bordes de bloque."""
    s = [spot(7, 19, 5, franja="AA"), spot(7, 19, 55, franja="AAA")]
    assert horario.franja_de_hora(s)[19] == "AAA"


def test_proyectar_usa_el_mismo_dia_de_semana():
    s = [spot(7, 20), spot(7, 9)]                      # lunes 7-sep
    proy = horario.proyectar(s, datetime.date(2026, 9, 14))   # lunes siguiente
    assert {f["ts"].hour for f in proy} == {20, 9}
    assert all(f["origen"] == "proyectado" for f in proy)
    assert all(f["ts"].date() == datetime.date(2026, 9, 14) for f in proy)


def test_proyectar_sin_patron_devuelve_vacio():
    """Mejor vacío que asumir cero spots: 'no sé' y 'no hubo TV' son cosas distintas."""
    s = [spot(7, 20)]                                   # solo lunes
    assert horario.proyectar(s, datetime.date(2026, 9, 9)) == []   # miércoles


def test_para_fecha_prefiere_el_asrun_sobre_la_proyeccion():
    s = [spot(7, 20), spot(14, 6)]                      # dos lunes, el segundo con otra hora
    r = horario.para_fecha(s, datetime.date(2026, 9, 14))
    assert {f["ts"].hour for f in r} == {6}
    assert r[0]["origen"] == "as-run"


def test_patron_toma_la_semana_mas_reciente():
    """Una parrilla que cambió debe REEMPLAZAR a la vieja, no promediarse con ella."""
    s = [spot(7, 20), spot(14, 6)]
    proy = horario.proyectar(s, datetime.date(2026, 9, 21))
    assert {f["ts"].hour for f in proy} == {6}


def test_regularidad_none_con_una_sola_semana():
    assert horario.regularidad([spot(7, 20), spot(8, 19)]) is None


def test_regularidad_detecta_parrilla_estable():
    s = [spot(7, 20), spot(8, 19), spot(14, 20), spot(15, 19)]
    assert horario.regularidad(s) == 1.0


def test_regularidad_detecta_parrilla_cambiada():
    s = [spot(7, 20), spot(8, 19), spot(14, 6), spot(15, 7)]
    assert horario.regularidad(s) == 0.0


def test_lee_el_spots_csv_real_del_repo():
    """Contrato con spots.csv: si ingesta.py cambia el formato, esto avisa."""
    spots = horario.cargar(str(RAIZ / "spots.csv"))
    assert len(spots) == 59
    assert min(f["ts"] for f in spots).date() == datetime.date(2026, 9, 7)
    assert max(f["ts"] for f in spots).date() == datetime.date(2026, 9, 13)
    assert {f["franja"] for f in spots} == {"A", "AA", "AAA"}


def test_spots_csv_no_lleva_dinero_ni_trp():
    """Este repo es PÚBLICO. Las tarifas negociadas con Televisa no pueden quedar aquí:
    van agregadas por día y franja en el secret TV_INVERSION_JSON."""
    texto = (RAIZ / "spots.csv").read_text(encoding="utf-8")
    cabecera = texto.splitlines()[0].lower()
    for prohibido in ("trp", "inversion", "inversión", "costo", "tarifa", "cpp"):
        assert prohibido not in cabecera, f"spots.csv no debe llevar '{prohibido}'"


def test_no_hay_xlsx_commiteado():
    """El as-run crudo trae el tarifario completo. Debe quedar fuera del repo."""
    assert not list(RAIZ.glob("**/*.xlsx")), "hay un xlsx dentro de salud-marca/tv/"


def test_cargar_deduplica_por_clave():
    spots = horario.cargar(str(RAIZ / "spots.csv"))
    claves = [(f["ts"], f["canal"], f["programa"]) for f in spots]
    assert len(claves) == len(set(claves))


def test_totales_del_dia_suma_franjas():
    # Cifras inventadas y redondas a propósito: este repo es público y los importes reales
    # de la central no deben quedar ni siquiera dentro de un test.
    inv = {"2026-09-07": {"AAA": {"spots": 3, "trp": 5.0, "inversion": 100000.0},
                          "A": {"spots": 1, "trp": 1.0, "inversion": 10000.0}}}
    n, trp, total, por_franja = horario.totales_del_dia(inv, datetime.date(2026, 9, 7))
    assert n == 4
    assert abs(trp - 6.0) < 0.01
    assert abs(total - 110000.0) < 0.01
    assert por_franja[0][0] == "AAA"          # ordenado por inversión desc


def test_totales_del_dia_sin_datos_devuelve_none():
    assert horario.totales_del_dia({}, datetime.date(2026, 9, 7)) is None


def test_cargar_inversion_prefiere_el_secret(monkeypatch):
    monkeypatch.setenv("TV_INVERSION_JSON", '{"2026-09-07":{"AAA":{"spots":1,"trp":1,"inversion":5}}}')
    assert horario.cargar_inversion()["2026-09-07"]["AAA"]["inversion"] == 5


def test_cargar_inversion_con_secret_corrupto_no_revienta(monkeypatch):
    """Mejor una tarjeta sin cifras de dinero que un job caído."""
    monkeypatch.setenv("TV_INVERSION_JSON", "{esto no es json")
    assert horario.cargar_inversion() == {}
