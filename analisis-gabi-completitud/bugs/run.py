"""Corre todos los detectores sobre bugs/data/convs.json.
Escribe bugs/data/hallazgos.jsonl (con PII, ignorado) y bugs/resumen.json (agregados, se commitea)."""
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse import parse_turns, is_nudge   # noqa: E402
import detectores as D                     # noqa: E402

HERE = Path(__file__).resolve().parent
CONVS = HERE / 'data' / 'convs.json'
HALLAZGOS = HERE / 'data' / 'hallazgos.jsonl'
RESUMEN = HERE / 'resumen.json'


def procesar(row):
    turns = parse_turns(row['c'])
    hallazgos = []
    for det in D.TODOS:
        hallazgos.extend(det(turns, row['bot']))
    # la latencia sólo tiene sentido si la línea de tiempo es monótona (ver det_latencia_alta)
    lat = [] if D.det_hora_no_monotona(turns, row['bot']) else [
        D._dt(a, b) for a, b in zip(turns, turns[1:])
        if a.rol == 'usuario' and b.rol == 'gabi' and not is_nudge(b.texto)]
    return {
        'deal_id': row['deal_id'], 'bot': row['bot'], 'etapa_muerte': row['etapa_muerte'],
        'ruteado': 1 if (int(row['agendo']) or int(row['inmo'])) else 0,
        'n_turnos': len(turns), 'n_usuario': sum(1 for t in turns if t.rol == 'usuario'),
        'latencias_s': [x for x in lat if x is not None],
        'hallazgos': hallazgos,
    }


def agregar(convs):
    total = Counter(c['bot'] for c in convs)
    con_resp = Counter(c['bot'] for c in convs if c.get('n_usuario', 1) > 0)
    r = {'total': {'convs': dict(total)}, 'por_tipo': {}}
    tipos = sorted({h['tipo'] for c in convs for h in c['hallazgos']})
    for tipo in tipos:
        ids_con = {c['deal_id'] for c in convs if any(h['tipo'] == tipo for h in c['hallazgos'])}
        con = [c for c in convs if c['deal_id'] in ids_con]
        sin = [c for c in convs if c['deal_id'] not in ids_con]
        por_bot = Counter(c['bot'] for c in con)
        por_etapa = defaultdict(Counter)
        for c in con:
            por_etapa[c['bot']][c['etapa_muerte']] += 1
        subtipos = Counter(h.get('subtipo') or '-' for c in con for h in c['hallazgos'] if h['tipo'] == tipo)
        r['por_tipo'][tipo] = {
            'hallazgos': sum(1 for c in convs for h in c['hallazgos'] if h['tipo'] == tipo),
            'convs': dict(por_bot),
            'pct_convs': {b: round(100 * por_bot[b] / total[b], 1) for b in por_bot},
            'pct_convs_con_respuesta': {b: round(100 * por_bot[b] / con_resp[b], 1) for b in por_bot if con_resp[b]},
            'subtipos': dict(subtipos),
            'por_etapa': {b: dict(v) for b, v in por_etapa.items()},
            'ruteo': {
                'con_bug': round(100 * sum(c['ruteado'] for c in con) / max(len(con), 1), 1),
                'sin_bug': round(100 * sum(c['ruteado'] for c in sin) / max(len(sin), 1), 1),
            },
        }
    return r


def main():
    rows = json.load(open(CONVS))
    convs = [procesar(r) for r in rows]
    with open(HALLAZGOS, 'w') as f:
        for c in convs:
            for h in c['hallazgos']:
                f.write(json.dumps({'deal_id': c['deal_id'], 'bot': c['bot'], 'etapa_muerte': c['etapa_muerte'],
                                    'ruteado': c['ruteado'], **h}, ensure_ascii=False) + '\n')
    resumen = agregar(convs)
    lat = defaultdict(list)
    for c in convs:
        lat[c['bot']].extend(c['latencias_s'])
    resumen['latencia_gabi_s'] = {b: {'mediana': round(statistics.median(v)), 'p90': round(sorted(v)[int(.9 * len(v))]),
                                      'n': len(v)} for b, v in lat.items() if v}
    resumen['convs_con_respuesta'] = dict(Counter(c['bot'] for c in convs if c['n_usuario'] > 0))
    json.dump(resumen, open(RESUMEN, 'w'), ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in resumen.items() if k != 'por_tipo'}, ensure_ascii=False))
    print()
    for tipo, v in resumen['por_tipo'].items():
        print(f"{tipo:<26} hallazgos={v['hallazgos']:>5}  convs={v['convs']}  "
              f"pct_resp={v['pct_convs_con_respuesta']}  ruteo con/sin={v['ruteo']['con_bug']}/{v['ruteo']['sin_bug']}")


if __name__ == '__main__':
    main()
