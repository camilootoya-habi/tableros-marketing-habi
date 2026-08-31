import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_bq

ROWS = [
    {"month": "2026-03", "plaza": "MTY", "opcion": None, "registros_web": "200"},
    {"month": "2026-03", "plaza": "MTY", "opcion": "Publicidad en branding de coches de UBER", "registros_web": "28"},
    {"month": "2026-03", "plaza": "MTY", "opcion": "Google", "registros_web": "572"},
]

def test_tasa_de_respuesta_excluye_los_nulos_del_numerador():
    s = sources_bq.exit_poll_series(ROWS)
    fila = [f for f in s if f["plaza"] == "MTY"][0]
    assert fila["registros_web"] == 800          # 200 + 28 + 572
    assert fila["respuestas"] == 600             # solo los que respondieron
    assert round(fila["tasa"], 4) == 0.75

def test_opciones_no_incluye_la_llave_nula():
    fila = sources_bq.exit_poll_series(ROWS)[0]
    assert None not in fila["opciones"]
    assert fila["opciones"]["Publicidad en branding de coches de UBER"] == 28

def test_serie_ordenada_por_mes_y_plaza():
    rows = ROWS + [{"month": "2026-01", "plaza": "GDL", "opcion": "Google", "registros_web": "10"}]
    s = sources_bq.exit_poll_series(rows)
    assert [(f["month"], f["plaza"]) for f in s] == [("2026-01", "GDL"), ("2026-03", "MTY")]


# ── Selección múltiple y privacidad ───────────────────────────────────────────

def test_seleccion_multiple_se_parte_por_coma():
    assert sources_bq.opciones_elegidas("Televisión, Búsqueda en Google, Vehículos de Uber") == [
        "Televisión", "Búsqueda en Google", "Vehículos de Uber"]

def test_texto_libre_de_otro_se_descarta_por_privacidad():
    """En producción este campo trae correos y nombres de personas reales, y el tablero se
    publica en un repo público. Las fixtures de acá son sintéticas a propósito: copiar un dato
    real a un test lo mete al historial de git, que es justo lo que se quiere evitar."""
    v = "Televisión, Vehículos de Uber, Otro: correo@ejemplo.com"
    assert sources_bq.opciones_elegidas(v) == ["Televisión", "Vehículos de Uber", "Otro"]

def test_texto_libre_con_comas_no_se_fragmenta_en_opciones_falsas():
    v = "Redes sociales, Otro: Nombre Apellido Ejemplo, vecino de la cuadra"
    assert sources_bq.opciones_elegidas(v) == ["Redes sociales", "Otro"]

def test_comillas_literales_del_formulario_se_limpian():
    assert sources_bq.opciones_elegidas('"Redes sociales de la empresa"') == [
        "Redes sociales de la empresa"]

def test_opcion_repetida_no_cuenta_doble():
    assert sources_bq.opciones_elegidas("Cines, Cines") == ["Cines"]

def test_vacio_o_nulo_no_es_respuesta():
    assert sources_bq.opciones_elegidas(None) == []
    assert sources_bq.opciones_elegidas("   ") == []

def test_una_respuesta_multiple_cuenta_una_vez_en_el_denominador():
    """La persona respondió una vez aunque marcó tres opciones: `respuestas` no se infla."""
    s = sources_bq.exit_poll_series([
        {"month": "2026-07", "plaza": "MTY", "registros_web": "10",
         "opcion": "Televisión, Cines, Vehículos de Uber"}])
    assert s[0]["respuestas"] == 10
    assert s[0]["opciones"] == {"Televisión": 10, "Cines": 10, "Vehículos de Uber": 10}
