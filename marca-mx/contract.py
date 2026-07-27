"""Forma de data.json. Un status explícito por métrica × país: 'not_available' con su
razón es lo que hace visible que a CO le faltan fuentes, en vez de mostrar ceros."""

VALID = ("ok", "not_available", "stale", "error")

NOT_AVAILABLE = {
    ("traffic", "CO"): "Sin export de GA4 usable para CO. El tráfico de CO se mide por Segment en el WBR 2.0.",
    ("exit_poll", "CO"): "El exit poll de CO vive en habi_db.tabla_contacto_v2.fuente_conocio_habi, con otro esquema. Pendiente de mapear.",
}


def metric(status, source=None, series=None, reason=None, last_updated=None):
    if status not in VALID:
        raise ValueError(f"status inválido: {status} (válidos: {VALID})")
    if status in ("not_available", "error") and not reason:
        raise ValueError(f"status={status} exige reason explícita")
    out = {"status": status}
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
