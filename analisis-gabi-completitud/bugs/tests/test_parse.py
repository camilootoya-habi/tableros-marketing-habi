from datetime import datetime
from parse import parse_turns, redact, is_nudge

C = (
    "Gabi: ¡Hola, Lulu Cruz! *Recibimos tu solicitud*\n\n"
    "📌 ¿Podrías indicarnos si es *casa o departamento*?. HORA: 2026-06-06T13:50:12.434779\n"
    "Usuario: Metepec Edo mex.\nRafias\n703\n52150. HORA: 2026-06-06T13:55:55.904087\n"
    "Gabi: *Sigo pendiente de tu respuesta*\n\n📌 Cuando tengas oportunidad.. HORA: 2026-06-06T15:50:12.316071"
)


def test_parse_separa_turnos_y_roles():
    t = parse_turns(C)
    assert [x.rol for x in t] == ["gabi", "usuario", "gabi"]


def test_parse_conserva_saltos_de_linea_del_usuario():
    t = parse_turns(C)
    assert t[1].texto == "Metepec Edo mex.\nRafias\n703\n52150"


def test_parse_extrae_hora_y_quita_el_sufijo():
    t = parse_turns(C)
    assert t[0].hora == datetime(2026, 6, 6, 13, 50, 12, 434779)
    assert "HORA" not in t[0].texto


def test_parse_sin_hora_da_none():
    t = parse_turns("Gabi: hola\nUsuario: ok")
    assert t[1].hora is None and t[1].texto == "ok"


def test_parse_indices_consecutivos():
    assert [x.idx for x in parse_turns(C)] == [0, 1, 2]


def test_is_nudge():
    assert is_nudge("*Sigo pendiente de tu respuesta*\n\n📌 Cuando tengas oportunidad")
    assert not is_nudge("¡Anotado! Ya quedó la *dirección*")


def test_redact_nombre_telefono_email():
    s = redact("¡Hola, Lulu Cruz! llámame al 55 1234 5678 o a lulu@mail.com")
    assert "Lulu" not in s and "1234" not in s and "@" not in s
