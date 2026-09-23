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
    """Regresión: BigQuery no devuelve fila para los minutos sin una sola sesión. Si se
    recorriera lo observado en vez del perfil, esos minutos desaparecerían del cálculo en vez
    de contar como cero. Sobre la semana 1 real eso daba -88 visitas donde había +591."""
    perfil = perfil_plano(10.0)
    dia = {m: 10.0 for m in range(1440)}
    for m in range(20 * 60 + 30, 20 * 60 + 60):      # media hora sin filas en BQ
        del dia[m]
    ex = estimador.exceso_por_hora(dia, perfil, {20})
    # 30 min observados × 10 = 300 contra 60 min esperados × 10 = 600 → exceso -300.
    # Ignorando los ausentes daría 0, como si la hora hubiera estado normal.
    assert abs(ex[0][1] + 300.0) < 1e-6


def test_factor_del_dia_resiste_una_hora_anomala():
    """El caso LRDG del 22-sep: una emisión fuera del horario cae en una hora tratada como
    limpia. Sin recorte, ese pico infla `k`, sube el esperado de las horas con spot y hunde
    el exceso medido — el día del pico más alto de la campaña daba -60 visitas."""
    perfil = perfil_plano(10.0)
    dia = {m: 10.0 for m in range(1440)}
    for m in range(14 * 60, 14 * 60 + 60):           # hora 14: pico x30, fuera del horario
        dia[m] = 300.0
    k = estimador.factor_del_dia(dia, perfil, {20})
    assert abs(k - 1.0) < 0.05        # el pico no arrastra la referencia del día

    ex = estimador.exceso_por_hora(dia, perfil, {20})
    assert abs(ex[0][1]) < 40.0       # y la hora con spot no queda castigada


def test_horas_anomalas_detecta_el_pico_y_lo_cuantifica():
    perfil = perfil_plano(10.0)
    sd = {h: 50.0 for h in range(24)}
    dia = {m: 10.0 for m in range(1440)}
    for m in range(20 * 60, 20 * 60 + 60):
        dia[m] = 30.0                                # 1800 obs contra 600 esperadas
    an = estimador.horas_anomalas(dia, perfil, sd, 1.0, umbral=4.0)
    assert len(an) == 1
    hora, obs, esp, exceso, sigmas = an[0]
    assert hora == 20
    assert abs(exceso - 1200.0) < 1e-6
    assert abs(sigmas - 24.0) < 1e-6                 # 1200 / 50


def test_horas_anomalas_no_dispara_en_un_dia_normal():
    """El umbral de 4 sigmas busca el evento evidente. Con 24 horas al día, uno de 2 sigmas
    daría un falso positivo casi diario."""
    perfil = perfil_plano(10.0)
    sd = {h: 50.0 for h in range(24)}
    dia = {m: 11.0 for m in range(1440)}             # día 10% arriba, parejo
    assert estimador.horas_anomalas(dia, perfil, sd, 1.1, umbral=4.0) == []


def test_horas_anomalas_sin_dispersion_no_inventa_sigmas():
    """Una hora con sd=0 en el baseline no permite calificar nada: se omite en vez de
    dividir por cero o reportar sigmas infinitas."""
    perfil = perfil_plano(10.0)
    dia = {m: 100.0 for m in range(1440)}
    assert estimador.horas_anomalas(dia, perfil, {h: 0.0 for h in range(24)}, 1.0) == []
