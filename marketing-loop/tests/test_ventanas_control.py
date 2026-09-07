"""Capa PURA de ventanas_control: ruta, calendario, construir(). Sin base de datos."""
import datetime as dt
from ventanas_control import ruta, es_habil, madura, mediana, construir

HOY = "2026-09-07"  # lunes


def test_ruta_flujo_primero_kind_despues():
    assert ruta("compra_wa", "llamada", "NO CONTACTABLE 3") == "compra_directa"
    assert ruta(None, "whatsapp", None) == "tibio"
    assert ruta(None, None, "Contactar por WhatsApp") == "tibio"      # recuperado sin kind
    assert ruta(None, "llamada", "NO CONTACTABLE 3") == "nocontesta"
    assert ruta(None, None, None) == "nocontesta"

def test_calendario():
    assert es_habil("2026-09-04") is True and es_habil("2026-09-05") is False
    assert madura("2026-09-03", HOY) is True and madura("2026-09-04", HOY) is False

def test_mediana():
    assert mediana([]) is None and mediana([1, 5, 3]) == 3 and mediana([1, 2, 3, 4]) == 2.5


def _hs(phone, fecha, hora, action, flujo=None, kind="llamada", gestion="NO CONTACTABLE 3", template=None):
    return {"phone": phone, "fecha": fecha, "hora": hora, "ts": f"{fecha}T{hora}:00", "action": action,
            "flujo": flujo, "kind": kind, "gestion": gestion, "template": template}

def _env(phone, fecha, template, mid, accepted=True):
    return {"phone": phone, "fecha": fecha, "template": template, "accepted": accepted, "message_id": mid}

def _raw():
    return {
        "hs": [
            _hs("A", "2026-09-03", "08:00", "SENT", flujo="compra_wa", template="ventanas_compra_co_v1"),
            _hs("B", "2026-09-03", "09:00", "SENT", template="ventanas_nocontesta_co_v1"),
            _hs("B", "2026-09-03", "09:30", "DEDUP"),
            _hs("C", "2026-09-04", "07:00", "RECUPERADO_28AGO", kind=None),
            _hs("D", "2026-09-04", "10:00", "SIN_DIRECCION", kind="whatsapp", gestion="Contactar por WhatsApp"),
            _hs("F", "2026-09-04", "11:00", "SENT", template="ventanas_nocontesta_co_v1"),
            _hs("E", "2026-09-07", "08:30", "SENT", flujo="compra_wa", template="ventanas_compra_co_v1"),
        ],
        "env": [
            _env("A", "2026-09-03", "ventanas_compra_co_v1", "m1"),
            _env("B", "2026-09-03", "ventanas_nocontesta_co_v1", "m2"),
            _env("C", "2026-09-04", "ventanas_nocontesta_co_v1", "m3"),
            _env("E", "2026-09-07", "ventanas_compra_co_v1", "m4"),
            _env("E", "2026-09-07", "ventanas_reenganche_co_v1", "m5"),
        ],
        "resp": {"A"}, "consent": {"A"}, "completa": {"A"},
        "deal_ok": {"A": True, "C": False}, "deal_fallo": {"E": ["500"]},
        "handoff": {}, "optout": {"B"}, "lead_fired": {"A": "2026-09-04T08:30:00"},
        "delivered": {"m1", "m3"},
        "plantillas": [{"nombre": "ventanas_compra_co_v1", "estado": "APPROVED"},
                       {"nombre": "ventanas_tibio_co_v1", "estado": "PENDING"}],
    }

def _dia(out, fecha):
    return next(d for d in out["dias"] if d["fecha"] == fecha)


def test_bloque1_dia_completo():
    d = _dia(construir(_raw(), HOY, "10:07"), "2026-09-03")
    b1 = d["todas"]["b1"]
    assert d["habil"] and d["madura"] and not d["hoy"]
    assert (b1["posts"], b1["personas"], b1["nuevas"]) == (3, 2, 2)
    assert b1["dedup_pct"] == 33.3 and b1["ultimo_post"] == "09:30" and b1["bloqueos"] == {}
    assert _dia(construir(_raw(), HOY, "10:07"), "2026-09-04")["todas"]["b1"]["bloqueos"] == {"SIN_DIRECCION": 1}

def test_recuperados_no_cuentan_en_bloque1_pero_si_en_cohorte():
    d = _dia(construir(_raw(), HOY, "10:07"), "2026-09-04")
    assert d["todas"]["b1"]["posts"] == 2 and d["todas"]["b1"]["nuevas"] == 2      # D y F
    b3 = d["todas"]["b3"]
    assert b3["cohorte"] == 3 and b3["recuperados"] == 1                           # C, D, F
    assert b3["deal_parcial"] == 1 and b3["deal_completo"] == 0
    assert b3["conversion_total"] is None                                          # inmadura

def test_bloque2_y_bloque3_dia_maduro():
    d = _dia(construir(_raw(), HOY, "10:07"), "2026-09-03")
    assert d["todas"]["b2"] == {"primer_envio": 2, "seguimientos": 0, "rechazos": 0}
    b3 = d["todas"]["b3"]
    assert (b3["cohorte"], b3["recuperados"], b3["respondieron"], b3["consintieron"]) == (2, 0, 1, 1)
    assert (b3["entrevista_completa"], b3["deal_completo"], b3["deal_parcial"], b3["optout"]) == (1, 1, 0, 1)
    assert b3["conversion_total"] == 50.0 and b3["horas_a_deal"] == 24.5

def test_hoy_y_fallas():
    out = construir(_raw(), HOY, "10:07")
    d = _dia(out, "2026-09-07")
    assert d["hoy"] is True and d["todas"]["b1"]["posts"] == 1
    assert d["todas"]["b2"] == {"primer_envio": 1, "seguimientos": 1, "rechazos": 0}
    assert d["todas"]["b3"]["deal_fallo"] == 1 and d["todas"]["b3"]["deal_fallo_codes"] == ["500"]
    assert _dia(out, "2026-09-05")["habil"] is False and _dia(out, "2026-09-05")["todas"]["b1"]["posts"] == 0

def test_por_ruta():
    d = _dia(construir(_raw(), HOY, "10:07"), "2026-09-03")
    assert d["compra_directa"]["b1"]["posts"] == 1 and d["compra_directa"]["b3"]["cohorte"] == 1
    assert d["compra_directa"]["b3"]["deal_completo"] == 1 and d["nocontesta"]["b3"]["optout"] == 1
    assert _dia(construir(_raw(), HOY, "10:07"), "2026-09-04")["tibio"]["b3"]["cohorte"] == 1   # D

def test_semanas_y_plantillas():
    out = construir(_raw(), HOY, "10:07")
    w36 = next(s for s in out["semanas"] if s["semana"] == "2026-W36")
    assert w36["todas"] == {"primer_envio": 3, "entregados": 2}
    assert w36["compra_directa"] == {"primer_envio": 1, "entregados": 1}
    w37 = next(s for s in out["semanas"] if s["semana"] == "2026-W37")
    assert w37["todas"] == {"primer_envio": 1, "entregados": 0}      # el seguimiento no cuenta
    assert out["plantillas"] == [{"nombre": "ventanas_compra_co_v1", "estado": "APPROVED", "aprobada": True},
                                 {"nombre": "ventanas_tibio_co_v1", "estado": "PENDING", "aprobada": False}]

def test_referencia_ultimos_7_habiles_maduros():
    # posts por día: los 7 hábiles maduros más recientes (26-ago..03-sep) valen 10..70; el 04-sep
    # (inmaduro) vale 1000 y hoy 5: ninguno de los dos debe entrar.
    raw = _raw(); raw["hs"] = []; raw["env"] = []
    valores = {"2026-08-24": 1, "2026-08-25": 2, "2026-08-26": 10, "2026-08-27": 20, "2026-08-28": 30,
               "2026-08-31": 40, "2026-09-01": 50, "2026-09-02": 60, "2026-09-03": 70,
               "2026-09-04": 1000, "2026-09-07": 5}
    for f, n in valores.items():
        for i in range(n):
            raw["hs"].append(_hs(f"{f}-{i}", f, "08:00", "SENT", template="ventanas_nocontesta_co_v1"))
    ref = construir(raw, HOY, "10:07")["referencia"]["todas"]
    assert ref["posts"] == 40 and ref["cohorte"] == 40
    assert ref["conversion_total"] == 0.0         # cohortes >= 5 con 0 deals → 0 %, no None

def test_referencia_conversion_ignora_cohortes_chicas():
    assert construir(_raw(), HOY, "10:07")["referencia"]["todas"]["conversion_total"] is None
