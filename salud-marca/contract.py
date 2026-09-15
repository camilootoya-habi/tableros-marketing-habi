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
    # El encuestador todavía no existe: es un agente que contactará gente por WhatsApp para
    # preguntarle por la marca mes a mes. Se declara igual, con su razón, porque un indicador
    # planeado que no aparece en ninguna parte es un indicador que nadie construye. La
    # infraestructura de envío y de captura de respuestas ya existe (Infobip + WABA MX/CO en
    # `marketing-loop-sellers`); lo que falta es el instrumento y, sobre todo, definir a quién
    # se encuesta.
    ("encuestador", "MX"): "El agente encuestador todavía no existe. Falta definir el universo: no hay base de teléfonos de la audiencia de propiedades.com, y encuestar solo a leads de Habi sesga la pregunta de reconocimiento.",
    ("encuestador", "CO"): "El agente encuestador todavía no existe. Falta definir el universo: no hay base de teléfonos de la audiencia de propiedades.com, y encuestar solo a leads de Habi sesga la pregunta de reconocimiento.",
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
