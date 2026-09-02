"""Imprime N conversaciones redactadas que tienen un hallazgo del tipo dado, marcando el turno que disparó.
Uso: python3 bugs/muestra.py <tipo> [n=15] [seed=7] [bot=A|B] [compacto]
'compacto' imprime sólo el turno que disparó y los 2 vecinos (para validar muchos casos rápido)."""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse import parse_turns, redact  # noqa: E402

HERE = Path(__file__).resolve().parent
tipo = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 7)
bot = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] in ('A', 'B') else None
compacto = 'compacto' in sys.argv

hall = [json.loads(l) for l in open(HERE / 'data' / 'hallazgos.jsonl')]
hall = [h for h in hall if h['tipo'] == tipo and (bot is None or h['bot'] == bot)]
por_deal = {}
for h in hall:
    por_deal.setdefault(h['deal_id'], []).append(h)
convs = {r['deal_id']: r for r in json.load(open(HERE / 'data' / 'convs.json'))}

print(f"# {tipo}: {len(hall)} hallazgos en {len(por_deal)} conversaciones. Muestra de {n}.")
print("# Marca cada deal en bugs/validacion.csv como TP (bug real) o FP (falso positivo).\n")
for deal in random.sample(sorted(por_deal), min(n, len(por_deal))):
    r = convs[deal]
    marcados = {h['idx']: h.get('subtipo') for h in por_deal[deal]}
    print('=' * 78)
    print(f"deal {deal} · bot {r['bot']} · {r['etapa_muerte']} · ruteado={int(r['agendo']) or int(r['inmo'])}")
    print('=' * 78)
    turns = parse_turns(r['c'])
    if compacto:
        cerca = {j for i in marcados for j in range(i - 1, i + 2)}
        turns = [t for t in turns if t.idx in cerca]
    for t in turns:
        flag = f"  <<< {tipo}/{marcados[t.idx]}" if t.idx in marcados else ''
        hora = t.hora.strftime('%m-%d %H:%M') if t.hora else '?'
        print(f"[{hora}] {t.rol.upper()}:{flag}")
        cuerpo = redact(t.texto)
        if compacto:
            cuerpo = cuerpo[:280] + ('…' if len(cuerpo) > 280 else '')
        for line in cuerpo.split('\n'):
            print(f"    {line}")
    print()
