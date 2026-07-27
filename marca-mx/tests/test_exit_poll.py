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
