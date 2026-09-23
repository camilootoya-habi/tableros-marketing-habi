import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import estimador  # noqa: E402


def perfil_plano(valor=10.0):
    return {m: valor for m in range(1440)}


def dia_plano(valor=10.0):
    return {m: valor for m in range(1440)}


def test_sin_efecto_el_exceso_es_cero():
    ex = estimador.exceso_por_hora(dia_plano(), perfil_plano(), {20})
    assert len(ex) == 1
    assert abs(ex[0][1]) < 1e-9


def test_detecta_el_exceso_de_la_hora_con_spot():
    dia = dia_plano()
    for m in range(20 * 60, 20 * 60 + 60):
        dia[m] += 2.0                      # +120 visitas en la hora 20
    ex = estimador.exceso_por_hora(dia, perfil_plano(), {20})
    assert abs(ex[0][1] - 120.0) < 1e-6


def test_factor_del_dia_ignora_las_horas_con_spot():
    """Si el nivel del día se midiera con TODAS las horas, el propio efecto de la TV entraría
    en el denominador y se cancelaría solo. Este test fija esa decisión."""
    dia = dia_plano()
    for m in range(20 * 60, 20 * 60 + 60):
        dia[m] += 100.0                    # un pico enorme en la hora con spot
    k = estimador.factor_del_dia(dia, perfil_plano(), {20})
    assert abs(k - 1.0) < 1e-9             # el pico NO movió el factor


def test_dia_globalmente_alto_no_se_lee_como_efecto_de_tv():
    """Un día +30% parejo (más pauta digital, por ejemplo) debe dar exceso cero, no +30%."""
    dia = {m: 13.0 for m in range(1440)}
    ex = estimador.exceso_por_hora(dia, perfil_plano(10.0), {20})
    assert abs(ex[0][1]) < 1e-6


def test_factor_del_dia_sin_horas_limpias_devuelve_uno():
    k = estimador.factor_del_dia(dia_plano(), perfil_plano(), set(range(24)))
    assert k == 1.0


def test_agregar_calcula_total_e_intervalo():
    r = estimador.agregar([10.0, 12.0, 8.0, 11.0, 9.0, 10.0, 10.0, 12.0, 8.0, 10.0])
    assert r["n"] == 10
    assert abs(r["total"] - 100.0) < 1e-6
    assert r["ic_bajo"] < r["total"] < r["ic_alto"]
    assert r["significativo"] is True


def test_agregar_no_es_significativo_cuando_el_ruido_domina():
    r = estimador.agregar([100.0, -90.0, 80.0, -70.0, 60.0, -50.0])
    assert r["significativo"] is False


def test_agregar_lista_vacia_no_revienta():
    r = estimador.agregar([])
    assert r["n"] == 0 and r["total"] == 0.0 and r["significativo"] is False


def test_agregar_una_sola_observacion_no_inventa_intervalo():
    r = estimador.agregar([42.0])
    assert r["n"] == 1 and r["ic_bajo"] is None and r["significativo"] is False


def test_franja_mas_incremental_elige_la_de_mayor_total():
    ex = [(19, 10.0), (20, 30.0), (7, 5.0), (8, 2.0)]
    franjas = {19: "AAA", 20: "AAA", 7: "A", 8: "A"}
    f, total, n = estimador.franja_mas_incremental(ex, franjas)
    assert f == "AAA" and abs(total - 40.0) < 1e-9 and n == 2


def test_franja_mas_incremental_sin_datos_devuelve_none():
    assert estimador.franja_mas_incremental([], {}) is None


def test_exceso_por_spot_usa_la_ventana_pedida():
    import datetime
    ts = datetime.datetime(2026, 9, 7, 20, 0)
    serie = {ts + datetime.timedelta(minutes=i): 10.0 for i in range(60)}
    perfil = {(0, m): 8.0 for m in range(1440)}
    r = estimador.exceso_por_spot(serie, perfil, [ts], ventana=15)
    assert abs(r[0][1] - 30.0) < 1e-6      # 15 min × (10-8)


def test_minutos_ausentes_cuentan_como_cero_no_como_inexistentes():
    """Regresión: BigQuery no devuelve fila para los minutos sin tráfico. Si esos minutos se
    saltan en el denominador del factor del día, `k` se infla y se come el efecto — sobre la
    semana 1 real daba -88 visitas en vez de +591."""
    perfil = perfil_plano(10.0)
    dia = {m: 10.0 for m in range(1440) if not (0 <= m // 60 < 5)}   # madrugada ausente
    k = estimador.factor_del_dia(dia, perfil, {20})
    esperado = (1440 - 5 * 60 - 60) * 10.0 / ((1440 - 60) * 10.0)
    assert abs(k - esperado) < 1e-9
    assert k < 1.0            # sin la corrección daba exactamente 1.0
