"""Armado y envío de la tarjeta a Google Chat.

Se usa un WEBHOOK ENTRANTE del espacio: no requiere OAuth, ni publicar una app de Workspace,
ni permisos de administrador más allá de poder crear el webhook en el espacio
(Apps e integraciones → Webhooks). La URL del webhook ES la credencial completa, así que va
en el secret `GCHAT_WEBHOOK_TV` y nunca en el código ni en los logs.

Solo stdlib: el runner no necesita instalar nada para postear.
"""
import json
import os
import urllib.error
import urllib.request

ENV_WEBHOOK = "GCHAT_WEBHOOK_TV"


def _num(x, dec=0):
    if x is None:
        return "s/d"
    return f"{x:,.{dec}f}".replace(",", " ")


def _texto_plano(r):
    """Resumen en una línea. Google Chat lo usa en la notificación push y en clientes que no
    renderizan tarjetas, así que tiene que sostenerse solo."""
    inc = r["incremental"]
    if inc["n"] == 0:
        return f"TV Tuhabi {r['fecha']}: sin horario de spots para estimar incremental."
    sig = "significativo" if inc["significativo"] else "no significativo"
    inv = (f", {_num(r['plan']['inversion'])} MXN"
           if r["plan"].get("inversion") is not None else "")
    return (f"TV Tuhabi {r['fecha']}: incremental 7 días {_num(inc['total'])} visitas ({sig}). "
            f"Ayer {_num(r['plan']['spots'])} spots{inv}.")


def construir_tarjeta(r):
    """`r` es el dict que arma `reporte_diario.calcular`."""
    plan, inc, dia = r["plan"], r["incremental"], r["dia"]
    secciones = []

    # TRP e inversión vienen del secret TV_INVERSION_JSON y pueden faltar; el conteo de spots
    # sale del calendario público y siempre está. Se omiten las partes ausentes en vez de
    # imprimir "$s/d", que se lee como un error de cálculo.
    partes = [f"{_num(plan['spots'])} spots"]
    if plan.get("trp") is not None:
        partes.append(f"{_num(plan['trp'], 1)} TRP")
    if plan.get("inversion") is not None:
        partes.append(f"${_num(plan['inversion'])} MXN")
    ayer = [{"decoratedText": {"topLabel": "Plan del día", "text": " · ".join(partes)}}]
    if plan["franja_top"]:
        f, minv, nh = plan["franja_top"]
        ayer.append({"decoratedText": {
            "topLabel": "Franja más pesada",
            "text": f"{f} · {nh} spots · ${_num(minv)} MXN "
                    f"({100 * minv / plan['inversion']:.0f}% del día)"
            if plan["inversion"] else f"{f} · {nh} spots"}})
    ayer.append({"decoratedText": {
        "topLabel": "Tráfico del día",
        "text": f"{_num(dia['observado'])} visitas · {dia['desvio_pct']:+.1f}% vs esperado",
        "bottomLabel": "movimiento del día — no atribuible a TV por sí solo"}})
    secciones.append({"header": f"Ayer · {r['fecha']}", "widgets": ayer})

    if inc["n"]:
        rango = (f"[{_num(inc['ic_bajo'])} a {_num(inc['ic_alto'])}]"
                 if inc["ic_bajo"] is not None else "")
        marca = "✅" if inc["significativo"] else "⚠️"
        widgets = [{"decoratedText": {
            "topLabel": "Tráfico incremental TV",
            "text": f"{marca} {_num(inc['total'])} visitas {rango}",
            "bottomLabel": (f"{inc['n']} horas-con-spot · t={inc['t']:.2f} · "
                            f"{'significativo' if inc['significativo'] else 'no significativo'}")}}]
        if inc["franja_top"]:
            f, tot, nh = inc["franja_top"]
            widgets.append({"decoratedText": {
                "topLabel": "Franja más incremental",
                "text": f"{f} · {_num(tot)} visitas en {nh} horas-con-spot"}})
        if r.get("costo_por_visita"):
            widgets.append({"decoratedText": {
                "topLabel": "Costo por visita incremental",
                "text": f"${_num(r['costo_por_visita'])} MXN"}})
        secciones.append({"header": "Incremental TV · últimos 7 días", "widgets": widgets})

    if r.get("avisos"):
        secciones.append({"header": "Notas", "widgets": [
            {"textParagraph": {"text": "• " + "<br>• ".join(r["avisos"])}}]})

    return {
        "text": _texto_plano(r),
        "cardsV2": [{"cardId": "tv-diario", "card": {
            "header": {"title": "📺 TV Tuhabi — México",
                       "subtitle": f"Reporte diario · {r['fecha']}"},
            "sections": secciones}}],
    }


def enviar(payload, webhook=None, timeout=30):
    """POST al webhook. Devuelve (ok, detalle) en vez de lanzar: que falle Google Chat no
    debe tumbar el job — el cálculo ya se hizo y queda en los logs y en el artefacto."""
    url = webhook or os.environ.get(ENV_WEBHOOK, "")
    if not url:
        return False, f"falta {ENV_WEBHOOK}"
    datos = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=datos,
                                 headers={"Content-Type": "application/json; charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        # Sin el cuerpo: puede repetir la URL del webhook, que es la credencial.
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError) as e:
        return False, f"red: {type(e).__name__}"
