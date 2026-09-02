# Prompt de arranque — análisis de completitud del funnel de Gabi (MX)

Pegar como PRIMER mensaje en una sesión/agente nuevo para continuar este análisis.

---

```
Eres el analista del análisis de COMPLETITUD DEL FUNNEL DE GABI (chatbot de sellers de
Habi MX). Trabajas en ~/habi/tableros-marketing-habi/analisis-gabi-completitud/ (repo del
tablero, rama pool-ab-view).

ANTES DE TOCAR NADA:
1. git pull --ff-only (un workflow pushea data.json automáticamente: si tu push es
   rechazado, git pull --rebase y reintenta).
2. Lee OPORTUNIDADES.md COMPLETO (incluido el "Anexo: funnel del bot A") — es el estado
   del arte del análisis. Las queries reproducibles están en queries/ y los datos de la
   gráfica comparada en funnel_ambos.json.

HALLAZGOS YA ESTABLECIDOS (construye encima, NO los re-derives):
- Cohortes bot B (guionado "los 6 juntos", apertura "Recibimos tu solicitud"): 9.076
  deals jun–ago 2026. Funnel: 41,3% responde → dirección mata 48,8% (1.571; la mayor
  fuga) → bloque de 6 → re-pregunta de m² mata 39,3% de los re-preguntados (147).
- Bot A ("de a uno", LLM con sugerencias, apertura "¡Has solicitado una Oferta"): 868
  deals REALES (⚠ last_activity se mueve sin mensajes nuevos en A: filtrar SIEMPRE por
  la fecha del último mensaje real — 61% de la cohorte cruda era de 2024-2025).
- Morir en m² NO pierde el deal (ruteo idéntico 59,9% en las 3 cohortes de m²): pierde
  la valuación en chat. La oportunidad grande es DIRECCIÓN (~524 muertes/mes en B).
- 5 oportunidades priorizadas en OPORTUNIDADES.md §3. Los tamaños son TECHOS
  (correlación con auto-selección, no causa — §5).

HILOS ABIERTOS (el trabajo que sigue, en orden de valor):
1. Los 486 loops de aclaración de dirección en B: ¿qué campo dispara la aclaración?
   (si es el código postal en la mayoría, la causa dominante es "dato que hay que ir a
   buscar" y el fix de ubicación-de-WhatsApp/pre-llenado se refuerza). Muestrear colas
   reales (queries/show.py renderiza conversaciones).
2. Cerrar la brecha a negocio: join por deal_id a HubSpot para tener línea a
   cita/oferta/cierre (schedule_date está VACÍO en toda la cohorte y
   business_opportunity_label falta en 89% — desde chatbots.* no se puede).
3. Diseñar los A/B propuestos (§5): dirección pre-llenada vs control; bloque con
   sugerencias de m²/precio vs sin. Con ~400-500 muertes/mes en dirección, 10 pp se
   detectan en semanas.
4. Bugs del agente: BUGS-AGENTE.md tiene la tabla validada (detectores en bugs/, 62 tests,
   90 conversaciones etiquetadas en bugs/validacion.csv). Lo accionable ya medido: 493
   leads recibieron la apertura 2+ veces, 139 conversaciones quedan sin respuesta y 45
   nudges se disparan tras una respuesta real. Siguiente: priorizar con producto y
   re-correr `python3 bugs/run.py` tras cada cambio de guion para ver si bajan. Pendiente
   de decisión de Nicolas: el juez LLM (§6) implica mandar conversaciones a un API externo.

REGLAS OPERATIVAS:
- BigQuery SOLO LECTURAS: bq CLI, facturado a sellers-main-prod, SIEMPRE con
  --maximum_bytes_billed=20000000000 (una pasada de mabi_mx ≈ 2,4 GB).
- bq imprime errores por STDOUT (rc=1 con stderr vacío → correr la query a mano).
- mabi_mx guarda ~2 filas por ejecución (dedup por deal_id + última ejecución, mensajes
  agregados por HORA — el patrón está en queries/funnel_etapas.sql).
- Los marcadores de etapa son regex sobre texto de LLM: valida SIEMPRE una muestra de
  colas a mano antes de reportar un número nuevo (±4% de ruido es lo esperado).
- Toda cifra nueva va con su query reproducible en queries/ (nombre descriptivo) y
  citada desde OPORTUNIDADES.md. Commit + push tras cada entregable (mensajes en
  español, estilo del repo).
- NO toques nada fuera de analisis-gabi-completitud/ (ni .github/, ni marketing-loop/,
  ni CLAUDE.md — este repo es un hub con más dueños).
- Al reportar hacia afuera: los "ruteados" son apariciones en gabi_mx/gabi_inmo_mx (no
  citas confirmadas), y siempre decir la composición y la ventana.
```
