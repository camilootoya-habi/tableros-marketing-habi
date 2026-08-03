from build_cierres import eje_meses


def test_eje_un_solo_mes():
    assert eje_meses("2026-07", "2026-07") == ["2026-07"]


def test_eje_meses_consecutivos():
    assert eje_meses("2026-06", "2026-09") == ["2026-06", "2026-07", "2026-08", "2026-09"]


def test_eje_cruza_el_ano():
    # El caso que rompe un range() ingenuo sobre el número de mes.
    assert eje_meses("2026-11", "2027-02") == ["2026-11", "2026-12", "2027-01", "2027-02"]


def test_eje_no_retrocede():
    # `hasta` anterior a `desde` no debe generar meses (evita un eje invertido si el reloj falla).
    assert eje_meses("2026-07", "2026-06") == []
