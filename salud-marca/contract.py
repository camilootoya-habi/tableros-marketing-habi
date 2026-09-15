"""Forma de data.json. Un status explícito por métrica × país: 'not_available' con su
razón es lo que hace visible que a CO le faltan fuentes, en vez de mostrar ceros."""

VALID = ("ok", "not_available", "stale", "error")

NOT_AVAILABLE = {
    ("traffic", "CO"): "Sin export de GA4 usable para CO. El tráfico de CO se mide por Segment en el WBR 2.0.",
    # Investigado a fondo el 2026-08-31: la fuente existe pero NO es utilizable. No es trabajo
    # pendiente, es un campo muerto — por eso la razón dice qué se verificó, para que nadie
    # vuelva a gastar un día en el mismo callejón.
    ("exit_poll", "CO"): (
        "La fuente existe pero no es utilizable, verificado el 31-ago-2026. "
        "`habi_db.tabla_contacto_v2.fuente_conocio_habi` es el único campo de este tipo en CO "
        "(se buscó en todo habi_db y habi_wh_bi) y tiene 14.973 respuestas, pero: (1) está "
        "vacío desde abr-2025, 17 meses seguidos sin una sola respuesta; (2) no se puede "
        "fechar — su `created_at` es el timestamp de una migración (las 14.973 caen en el mismo "
        "mes, junto a 1,67M de filas), y ni `vid` ni `uuid` enlazan con "
        "`tabla_inmueble_v2` para recuperar la fecha real del registro. "
        "Para encender este indicador en CO hay que volver a capturar la pregunta en el "
        "formulario, no escribir una query."),
    # El encuestador YA existe: es Pulso Inmobiliario (repo `pulso-inmobiliario`), que desde
    # sep-2026 encuesta por WhatsApp y por un agente de voz a dueños que publican vivienda en
    # propiedades.com. Resolvió justo lo que antes lo bloqueaba: el universo. La base es la de
    # propiedades.com, no leads de Habi, así que la pregunta de reconocimiento no queda sesgada.
    # MX se sirve desde su API pública de agregados (ver sources_pulso.py). CO no: la línea de
    # WhatsApp, la base de teléfonos y el cuestionario son de México.
    #
    # Ojo con lo que cubre: de las tres preguntas que promete este indicador, Pulso responde dos
    # (¿nos conocen? y ¿con qué atributo nos relacionan?) y agrega el embudo de consideración.
    # La tercera — si nos ven como comprador directo, como inmobiliaria o como varias cosas — NO
    # está en el cuestionario todavía.
("encuestador", "CO"): "Pulso Inmobiliario, el agente encuestador, corre solo en México: la línea de WhatsApp, la base de teléfonos de propiedades.com y el cuestionario (marcas mexicanas) son de MX. Para encender CO hay que abrir una ola con marcas colombianas sobre la WABA de CO, que ya existe en `marketing-loop-sellers`.",
}


def metric(status, source=None, series=None, reason=None, last_updated=None, planned=False):
    """`planned=True` distingue un indicador que TODAVÍA NO EXISTE de uno cuya fuente existe
    pero no está conectada. Las dos cosas son `not_available` y las dos exigen razón, pero el
    lector necesita saber si está esperando una conexión o una decisión: en el primer caso hay
    trabajo técnico pendiente, en el segundo hay algo que definir antes de escribir código."""
    if status not in VALID:
        raise ValueError(f"status inválido: {status} (válidos: {VALID})")
    if status in ("not_available", "error") and not reason:
        raise ValueError(f"status={status} exige reason explícita")
    if planned and status != "not_available":
        raise ValueError("planned solo aplica a not_available")
    out = {"status": status}
    if planned:
        out["planned"] = True
    if source:
        out["source"] = source
    if last_updated:
        out["last_updated"] = last_updated
    if reason:
        out["reason"] = reason
    if status in ("ok", "stale"):
        out["series"] = series or []
    return out


def envelope(metrics, now):
    return {"generated_at": now, "metrics": metrics}
