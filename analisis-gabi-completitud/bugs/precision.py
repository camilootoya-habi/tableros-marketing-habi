"""Precisión por tipo a partir de bugs/validacion.csv. Imprime una tabla markdown para el informe.
Sólo cuenta las validaciones que el detector VIGENTE sigue produciendo (cruce con data/hallazgos.jsonl):
las etiquetas de versiones anteriores quedan como registro de por qué se ajustó cada regex."""
import csv
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(HERE / 'validacion.csv')))
producidos = {(json.loads(l)['tipo'], str(json.loads(l)['deal_id']))
              for l in open(HERE / 'data' / 'hallazgos.jsonl')}
vigentes = [r for r in rows if (r['tipo'], r['deal_id']) in producidos]

acc = defaultdict(lambda: {'TP': 0, 'FP': 0})
for r in vigentes:
    acc[(r['tipo'], r['bot'])][r['veredicto'].strip().upper()] += 1

print('| Tipo | Bot | n validado | TP | Precisión | Estatus |')
print('|---|---|---|---|---|---|')
for (tipo, bot), v in sorted(acc.items()):
    n = v['TP'] + v['FP']
    p = 100 * v['TP'] / n if n else 0
    estatus = 'cifra' if p >= 80 else 'indicio' if p >= 60 else 'retirado'
    print(f'| {tipo} | {bot} | {n} | {v["TP"]} | {p:.0f}% | {estatus} |')

descartados = len(rows) - len(vigentes)
print(f'\n({len(vigentes)} de {len(rows)} conversaciones etiquetadas a mano siguen siendo hallazgos del '
      f'detector vigente; las otras {descartados} las produjeron versiones anteriores y quedan como '
      f'registro de por qué se ajustó cada regex.)')
