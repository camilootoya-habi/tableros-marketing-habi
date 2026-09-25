import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import reporte_diario as R  # noqa: E402

DIA = datetime.date(2026, 9, 24)


def test_sin_marcador_no_hay_envio(tmp_path):
    assert not R.ya_enviado(DIA, ruta=tmp_path / "no-existe.json")


def test_el_marcador_es_por_fecha(tmp_path):
    ruta = tmp_path / "ultimo_envio.json"
    R.marcar_enviado(DIA, "2026-09-25T15:07:00Z", ruta=ruta)
    assert R.ya_enviado(DIA, ruta=ruta)
    assert not R.ya_enviado(DIA + datetime.timedelta(days=1), ruta=ruta)


def test_marcador_corrupto_cuenta_como_no_enviado(tmp_path):
    # Mejor un posible duplicado que un día sin reporte.
    ruta = tmp_path / "ultimo_envio.json"
    ruta.write_text("{roto")
    assert not R.ya_enviado(DIA, ruta=ruta)


def test_solo_si_falta_no_consulta_nada_si_ya_salio(tmp_path, monkeypatch):
    ruta = tmp_path / "ultimo_envio.json"
    R.marcar_enviado(DIA, "2026-09-25T15:07:00Z", ruta=ruta)
    monkeypatch.setattr(R, "ULTIMO_ENVIO", str(ruta))
    def no_llamar(*a, **k):
        raise AssertionError("un horario de respaldo no debe volver a calcular ni enviar")
    monkeypatch.setattr(R, "consultar_trafico", no_llamar)
    monkeypatch.setattr(R.CHAT, "enviar", no_llamar)
    monkeypatch.setattr(sys, "argv", ["reporte_diario.py", "--fecha", DIA.isoformat(),
                                      "--enviar", "--solo-si-falta"])
    assert R.main() == 0


def test_solo_si_falta_sigue_si_no_ha_salido(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ULTIMO_ENVIO", str(tmp_path / "ultimo_envio.json"))
    llamado = []
    def trafico(*a, **k):
        llamado.append(True)
        raise RuntimeError("corte del test: llegó a consultar")
    monkeypatch.setattr(R, "consultar_trafico", trafico)
    monkeypatch.setattr(sys, "argv", ["reporte_diario.py", "--fecha", DIA.isoformat(),
                                      "--enviar", "--solo-si-falta"])
    try:
        R.main()
    except RuntimeError:
        pass
    assert llamado


def test_un_envio_fallido_no_deja_marcador(tmp_path, monkeypatch):
    ruta = tmp_path / "ultimo_envio.json"
    monkeypatch.setattr(R, "ULTIMO_ENVIO", str(ruta))
    dia = datetime.datetime.combine(DIA, datetime.time(12, 0))
    monkeypatch.setattr(R, "consultar_trafico", lambda *a, **k: {dia: 5.0})
    monkeypatch.setattr(R, "calcular", lambda *a, **k: _r())
    monkeypatch.setattr(R.HOR, "cargar", lambda: [{"ts": datetime.datetime(2026, 9, 7, 9, 0)}])
    monkeypatch.setattr(R.CHAT, "construir_tarjeta", lambda r: {"text": "x"})
    monkeypatch.setattr(R.CHAT, "enviar", lambda p: (False, "HTTP 500"))
    monkeypatch.setattr(sys, "argv", ["reporte_diario.py", "--fecha", DIA.isoformat(),
                                      "--enviar", "--sin-panel"])
    assert R.main() == 0
    assert not ruta.exists()
    monkeypatch.setattr(R.CHAT, "enviar", lambda p: (True, "HTTP 200"))
    assert R.main() == 0
    assert R.ya_enviado(DIA, ruta=ruta)


def _r():
    return {"fecha_iso": DIA.isoformat(),
            "plan": {"spots": 8, "trp": None, "inversion": None, "origen": "proyectado"},
            "dia": {"observado": 7000, "desvio_pct": -2.7},
            "incremental": {"n": 0}, "anomalias": [], "avisos": []}


def test_si_ga4_no_publico_el_dia_no_envia_ni_marca(tmp_path, monkeypatch):
    ruta = tmp_path / "ultimo_envio.json"
    monkeypatch.setattr(R, "ULTIMO_ENVIO", str(ruta))
    # Hay tráfico hasta el día anterior, pero nada del día a reportar.
    ayer = datetime.datetime.combine(DIA - datetime.timedelta(days=1), datetime.time(12, 0))
    monkeypatch.setattr(R, "consultar_trafico", lambda *a, **k: {ayer: 5.0})
    monkeypatch.setattr(R.HOR, "cargar", lambda: [{"ts": datetime.datetime(2026, 9, 7, 9, 0)}])
    def no_llamar(*a, **k):
        raise AssertionError("sin el día en GA4 no se calcula ni se envía")
    monkeypatch.setattr(R, "calcular", no_llamar)
    monkeypatch.setattr(R.CHAT, "enviar", no_llamar)
    monkeypatch.setattr(sys, "argv", ["reporte_diario.py", "--fecha", DIA.isoformat(),
                                      "--enviar", "--solo-si-falta"])
    assert R.main() == 0
    assert not ruta.exists()
