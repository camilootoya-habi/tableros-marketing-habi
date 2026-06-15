#!/usr/bin/env python3
"""
Ensambla data.json para el informe "Diagnóstico Performance CO — Mundial 2026".

Entradas:
  _inversion.json  -> [{dt, fuente, spend, impr, clicks}]   (UTM-attributed, paid)
  _funnel.json     -> [{dt, fuente, registros, asignados}]   (cohort por fecha_creacion)
  _co_sheet.csv    -> sheet Cumplimiento Fuentes (metas/actual/prev por fuente, oficial WBR)
  hitos.json       -> [{date, label, tipo}]

Uso: python build_data.py <updated_YYYY-MM-DD> [out=data.json]

Diseño:
- Series SEMANALES (ISO) 2026 por fuente de performance: costos+funnel (cohort) + metas/actual/prev (oficial sheet).
- Series DIARIAS desde 2026-05-01 por fuente: spend/CPM/CPC/registros.
- 3 varas: meta_orig (sheet), meta_recal (meta_orig * RECAL[fuente]), prev (YoY 2025).
- Proyección Q2+Q3 por fuente y escenario (conservador/optimista) con factores por palanca.
"""
import csv, json, sys, datetime
from collections import defaultdict

sys.path.insert(0, '/home/administrador/habi/tableros-marketing/okr-marketing')
from build_data import parse_sheet, SOURCES_CO  # reusa el parser del OKR

PERF = ['WEB', 'lead_forms', 'Estudio Inmueble']
DIARIO_DESDE = '2026-05-01'

# Factor de recalibración post-Backbone por fuente (doc asignados CO abr-2026).
# Habímetro -27% (el más agresivo y acertado); WEB/Lead Forms -16%.
RECAL = {'WEB': 0.84, 'lead_forms': 0.84, 'Estudio Inmueble': 0.73}

# --- Proyección: factores por escenario y bloque de calendario ---
# bloque "mundial": semanas que se traslapan con 11-jun..19-jul (incluye 2a vuelta 21-jun y festivos).
# bloque "post":    semanas posteriores al 19-jul hasta fin de Q3 (sep).
# (demanda, cvr_mult, cpl_mult) relativo al run-rate de las ultimas 4 semanas completas.
SCEN = {
    'conservador': {'mundial': (0.88, 1.00, 1.20), 'post': (0.97, 1.00, 1.08)},
    'optimista':   {'mundial': (0.93, 1.02, 1.10), 'post': (1.05, 1.05, 0.98)},
}
MUNDIAL_INI = datetime.date(2026, 6, 11)
MUNDIAL_FIN = datetime.date(2026, 7, 19)
Q3_FIN = datetime.date(2026, 9, 30)


def iso_monday(d):
    return d - datetime.timedelta(days=d.weekday())


def wlabel(monday):
    sun = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%d/%m')} - {sun.strftime('%d/%m')}"


def main():
    updated = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else 'data.json'
    here = '/home/administrador/habi/tableros-marketing/diagnostico-performance-co/'

    inv = json.load(open(here + '_inversion.json'))
    fun = json.load(open(here + '_funnel.json'))
    for r in fun:
        r['registros'] = int(r['registros']); r['asignados'] = int(r['asignados'])
    hitos = json.load(open(here + 'hitos.json'))
    sheet = parse_sheet(here + '_co_sheet.csv', SOURCES_CO)

    # ---- Agregación semanal (ISO) por fuente: costos + funnel cohort ----
    wk = defaultdict(lambda: defaultdict(float))  # (monday_iso, fuente) -> metrics
    for r in inv:
        if r['dt'] < '2026-01-01':
            continue
        m = iso_monday(datetime.date.fromisoformat(r['dt'])).isoformat()
        k = (m, r['fuente'])
        for f in ('spend', 'impr', 'clicks'):
            wk[k][f] += float(r[f])
    for r in fun:
        if r['dt'] < '2026-01-01':
            continue
        m = iso_monday(datetime.date.fromisoformat(r['dt'])).isoformat()
        k = (m, r['fuente'])
        wk[k]['registros'] += r['registros']
        wk[k]['asignados_cohort'] += r['asignados']

    # ---- Metas oficiales (sheet) indexadas por lunes ISO ----
    sheet_by_monday = {}  # monday_iso -> {fuente: {meta,actual,prev}}
    for w in sheet['weeks']:
        if not w.get('_desde'):
            continue
        sheet_by_monday[w['_desde']] = w

    # ---- Construir series semanales por fuente ----
    semanal = {f: [] for f in PERF}
    all_mondays = sorted({k[0] for k in wk})
    for m in all_mondays:
        sw = sheet_by_monday.get(m, {})
        for f in PERF:
            d = wk[(m, f)]
            spend, impr, clicks = d['spend'], d['impr'], d['clicks']
            reg, asgc = d['registros'], d['asignados_cohort']
            sv = sw.get(f, {}) if sw else {}
            meta_orig = sv.get('meta')
            row = {
                'w': m, 'label': wlabel(datetime.date.fromisoformat(m)),
                'spend': round(spend), 'impr': round(impr), 'clicks': round(clicks),
                'cpm': round(spend / impr * 1000, 2) if impr else None,
                'cpc': round(spend / clicks, 2) if clicks else None,
                'cpl': round(spend / reg, 1) if reg else None,
                'registros': reg,
                'asignados_cohort': asgc,
                'cvr': round(asgc / reg * 100, 1) if reg else None,
                'meta_orig': meta_orig,
                'meta_recal': round(meta_orig * RECAL[f]) if meta_orig else None,
                'actual': sv.get('actual'),   # asignados oficiales (WBR/sheet)
                'prev': sv.get('prev'),
            }
            semanal[f].append(row)

    # ---- Series diarias desde DIARIO_DESDE ----
    dia = defaultdict(lambda: defaultdict(float))
    for r in inv:
        if r['dt'] >= DIARIO_DESDE:
            for f in ('spend', 'impr', 'clicks'):
                dia[(r['dt'], r['fuente'])][f] += float(r[f])
    for r in fun:
        if r['dt'] >= DIARIO_DESDE:
            dia[(r['dt'], r['fuente'])]['registros'] += r['registros']
    diario = {f: [] for f in PERF}
    all_days = sorted({k[0] for k in dia})
    for dt in all_days:
        for f in PERF:
            d = dia[(dt, f)]
            spend, impr, clicks, reg = d['spend'], d['impr'], d['clicks'], d['registros']
            diario[f].append({
                'd': dt,
                'spend': round(spend),
                'cpm': round(spend / impr * 1000, 2) if impr else None,
                'cpc': round(spend / clicks, 2) if clicks else None,
                'cpl': round(spend / reg, 1) if reg else None,
                'registros': int(reg),
            })

    # ---- Metas trimestrales completas (sheet) por fuente ----
    metas_q = {f: {} for f in PERF}
    for q in ('Q2', 'Q3'):
        qd = sheet['quarters'].get(q, {})
        for f in PERF:
            metas_q[f][q] = qd.get(f, {}).get('meta')

    # ---- Proyección Q2+Q3 por fuente y escenario ----
    proyeccion = build_projection(semanal)

    out = {
        'updated': updated,
        'fuentes': PERF,
        'recal': RECAL,
        'semanal': semanal,
        'diario': diario,
        'hitos': hitos,
        'metas_quarter': metas_q,
        'proyeccion': proyeccion,
        'scen_factores': SCEN,
    }
    json.dump(out, open(here + out_path, 'w'), ensure_ascii=False)
    print('OK ->', out_path)


def build_projection(semanal):
    """Proyecta asignados (y CPL narrativo) por fuente y escenario, semana a semana,
    desde la primera semana no-completa hasta fin de Q3. Reparte por trimestre."""
    today = datetime.date.fromisoformat(sys.argv[1])
    cur_monday = iso_monday(today)  # semana en curso (no completa)

    # Run-rate base: ultimas 4 semanas COMPLETAS (anteriores a cur_monday) con actual oficial.
    base_asg, base_cpl = {}, {}
    for f in PERF:
        complete = [r for r in semanal[f]
                    if r['w'] < cur_monday.isoformat() and r['actual'] is not None]
        last4 = complete[-4:]
        base_asg[f] = sum(r['actual'] for r in last4) / len(last4) if last4 else 0
        cpls = [r['cpl'] for r in last4 if r['cpl']]
        base_cpl[f] = sum(cpls) / len(cpls) if cpls else 0

    # Sumatorios oficiales Q2-a-la-fecha (asignados ya logrados, semanas completas dentro de Q2).
    q2_actual_todate = {}
    for f in PERF:
        q2_actual_todate[f] = sum(
            r['actual'] for r in semanal[f]
            if r['actual'] is not None and '2026-04-01' <= r['w'] < cur_monday.isoformat()
            and datetime.date.fromisoformat(r['w']) <= datetime.date(2026, 6, 30))

    # Genera semanas futuras (Mondays) desde cur_monday hasta que el lunes supere Q3_FIN.
    weeks = []
    m = cur_monday
    while m <= Q3_FIN:
        weeks.append(m)
        m += datetime.timedelta(days=7)

    def block(monday):
        wk_end = monday + datetime.timedelta(days=6)
        # se traslapa con el mundial?
        return 'mundial' if (monday <= MUNDIAL_FIN and wk_end >= MUNDIAL_INI) else 'post'

    def days_in_quarter(monday, q_ini, q_fin):
        cnt = 0
        for i in range(7):
            d = monday + datetime.timedelta(days=i)
            if q_ini <= d <= q_fin:
                cnt += 1
        return cnt

    Q2I, Q2F = datetime.date(2026, 4, 1), datetime.date(2026, 6, 30)
    Q3I, Q3F = datetime.date(2026, 7, 1), datetime.date(2026, 9, 30)

    result = {'fuentes': {}, 'totales': {}}
    for f in PERF:
        result['fuentes'][f] = {}
        for scen, blocks in SCEN.items():
            serie = []
            for monday in weeks:
                blk = block(monday)
                dem, cvrm, cplm = blocks[blk]
                asg_week = base_asg[f] * dem * cvrm
                cpl_week = base_cpl[f] * cplm
                serie.append({
                    'w': monday.isoformat(),
                    'label': wlabel(monday),
                    'asignados': round(asg_week),
                    'cpl': round(cpl_week, 1),
                    'block': blk,
                })
            result['fuentes'][f][scen] = serie

    # Totales por escenario: Q2 cierre (actual-a-fecha + proyectado prorrateado a Q2) y Q3.
    for scen in SCEN:
        q2_close = {f: q2_actual_todate[f] for f in PERF}
        q3_total = {f: 0.0 for f in PERF}
        for f in PERF:
            for monday in weeks:
                blk = block(monday)
                dem, cvrm, cplm = SCEN[scen][blk]
                asg_week = base_asg[f] * dem * cvrm
                d2 = days_in_quarter(monday, Q2I, Q2F)
                d3 = days_in_quarter(monday, Q3I, Q3F)
                q2_close[f] += asg_week * d2 / 7
                q3_total[f] += asg_week * d3 / 7
        result['totales'][scen] = {
            'q2_close': {f: round(q2_close[f]) for f in PERF},
            'q2_close_total': round(sum(q2_close.values())),
            'q3_total': {f: round(q3_total[f]) for f in PERF},
            'q3_total_total': round(sum(q3_total.values())),
        }

    # Metas de referencia (sheet, full quarter) para WEB/lead_forms/Estudio + total perfo.
    result['base_asg'] = {f: round(base_asg[f]) for f in PERF}
    result['base_cpl'] = {f: round(base_cpl[f], 1) for f in PERF}
    result['q2_actual_todate'] = {f: round(q2_actual_todate[f]) for f in PERF}
    return result


if __name__ == '__main__':
    main()
