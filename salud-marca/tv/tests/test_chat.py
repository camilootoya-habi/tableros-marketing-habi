import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import chat  # noqa: E402


def reporte(**over):
    base = {
        "fecha": "martes 22 sep", "fecha_iso": "2026-09-22",
        "plan": {"spots": 8, "trp": 9.2, "inversion": 233564.0, "franja_top": None,
                 "origen": "proyectado"},
        "dia": {"observado": 8664, "esperado": 7962, "desvio_pct": 8.8},
        "incremental": {"n": 52, "total": 1195.0, "media": 23.0, "ic_bajo": -20.0,
                        "ic_alto": 2410.0, "t": 1.94, "significativo": False,
                        "franja_top": None},
        "anomalias": [], "costo_por_visita": None, "avisos": [],
    }
    base.update(over)
    return base


def _botones(payload):
    out = []
    for sec in payload["cardsV2"][0]["card"]["sections"]:
        for w in sec["widgets"]:
            for b in (w.get("buttonList") or {}).get("buttons", []):
                out.append(b)
    return out


def test_la_tarjeta_siempre_enlaza_al_panel():
    """El enlace va SIEMPRE: la tarjeta resume y el tablero tiene el detalle. Sin él, quien
    quiere mirar la serie completa no sabe dónde buscarla."""
    for r in (reporte(),
              reporte(incremental={"n": 0, "total": 0.0, "media": 0.0, "ic_bajo": None,
                                   "ic_alto": None, "t": None, "significativo": False,
                                   "franja_top": None}),
              reporte(avisos=["algo"]),
              reporte(anomalias=[(20, 1614.0, 377.7, 1236.3, 15.8)])):
        bs = _botones(chat.construir_tarjeta(r))
        assert len(bs) == 1, "debe haber exactamente un botón al panel"
        assert bs[0]["onClick"]["openLink"]["url"] == chat.PANEL_URL


def test_el_texto_plano_tambien_lleva_la_url():
    """Google Chat usa `text` en la notificación push y en clientes sin tarjetas: ahí el
    botón no existe, así que la URL tiene que ir en el texto."""
    assert chat.PANEL_URL in chat.construir_tarjeta(reporte())["text"]
    sin_datos = reporte(incremental={"n": 0, "total": 0.0, "media": 0.0, "ic_bajo": None,
                                     "ic_alto": None, "t": None, "significativo": False,
                                     "franja_top": None})
    assert chat.PANEL_URL in chat.construir_tarjeta(sin_datos)["text"]


def test_la_url_apunta_al_ancla_del_panel_de_tv():
    assert chat.PANEL_URL.endswith("#h-tv")
    assert "pais=MX" in chat.PANEL_URL
