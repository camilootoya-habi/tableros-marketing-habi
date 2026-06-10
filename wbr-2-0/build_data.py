#!/usr/bin/env python3
"""
Builds wbr-2-0/data.json from DAILY BQ rows, bucketed two ways:
  - 'week'  : ISO week  (Monday → Sunday)
  - 'cycle' : ciclo comercial (Wednesday → Tuesday)

For each country the output is:
  { 'week':  {by_week, totals_by_week, by_week_channels, by_week_platforms},
    'cycle': {by_week, totals_by_week, by_week_channels, by_week_platforms} }

Inputs are DAILY (one row per day, keyed by 'day'):
  - BQ main JSON     : reg/cal/asg/spend by (day, fuente)
  - BQ channels JSON : reg/cal/asg/spend/clicks/impressions by (day, channel, fuente)
  - BQ platforms JSON: ... by (day, platform, channel, fuente)
  - Sheet CSV (OKR)  : DAILY meta per fuente (sección "Metas Diarias")

Usage:
  build_data.py <bq_co> <sheet_co> <bq_ch_co> <bq_pl_co> \
                <bq_mx> <sheet_mx> <bq_ch_mx> <bq_pl_mx> <output>
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta


SHEET_FUENTES_OFFSET_BY_COUNTRY = {
    'co': {
        'TOTAL': 7, 'Perfo': 14, 'WEB': 21, 'lead_forms': 28,
        'Estudio Inmueble': 35, 'CRM': 42, 'Broker': 49, 'Comercial': 56,
    },
    # MX: mismo layout de columnas; la columna que en CO es CRM (42) en MX es Propiedades.
    'mx': {
        'TOTAL': 7, 'Perfo': 14, 'WEB': 21, 'lead_forms': 28,
        'Estudio Inmueble': 35, 'Propiedades': 42, 'Broker': 49, 'Comercial': 56,
    },
}

FUENTES_ROW_BY_COUNTRY = {
    'co': ['WEB', 'Estudio Inmueble', 'lead_forms', 'CRM', 'Broker', 'Comercial'],
    'mx': ['WEB', 'Estudio Inmueble', 'lead_forms', 'Propiedades', 'Broker', 'Comercial'],
}

# How many buckets to keep (most recent complete) per granularity.
# Dropdown muestra los últimos 52; los ~30 más antiguos quedan como historia
# para que la gráfica apilada pueda mostrar 30 periodos atrás desde el seleccionado.
KEEP_BUCKETS = 82
GRANULARITIES = ('week', 'cycle')


def parse_num(s):
    s = (s or '').strip()
    if not s or s in ('#N/A', '-', '#REF!', '#VALUE!'):
        return None
    if s.endswith('%'):
        s = s[:-1]
    s = s.replace('.', '').replace(',', '')
    try:
        return int(s)
    except ValueError:
        return None


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, '%d/%m/%Y').date()
    except ValueError:
        return None


def bucket_start(d, gran):
    """Return the ISO string of the bucket start for date `d`.
       week  -> Monday (weekday 0).  cycle -> Wednesday (weekday 2)."""
    if gran == 'week':
        off = d.weekday()              # Mon=0 .. Sun=6
    else:                              # cycle Wed→Tue
        off = (d.weekday() - 2) % 7    # Wed=0
    return (d - timedelta(days=off)).isoformat()


def parse_sheet_daily(csv_path, country):
    """Read the 'Metas Diarias' section of the OKR sheet.
       Returns { 'YYYY-MM-DD': { fuente_name: meta, 'TOTAL':.., 'Perfo':.. } }."""
    offsets = SHEET_FUENTES_OFFSET_BY_COUNTRY[country]
    with open(csv_path, 'r', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    out = {}
    in_daily = False
    for row in rows:
        if not row:
            continue
        label = row[0].strip()
        if 'Diarias' in label:
            in_daily = True
            continue
        if not in_daily:
            continue
        if not label.isdigit():        # left the daily section
            break
        d = parse_date(row[2]) if len(row) > 2 else None
        if not d:
            continue
        metas = {}
        for fuente, off in offsets.items():
            if off < len(row):
                metas[fuente] = parse_num(row[off])
        out[d.isoformat()] = metas
    return out


def channel_to_fuente(ch):
    if ch.startswith('WEB ') or ch == 'WEB':
        return 'WEB'
    if ch.startswith('Estudio Inmueble'):
        return 'Estudio Inmueble'
    if ch.startswith('lead_forms') or ch.startswith('Lead Forms') or ch == 'lead_forms':
        return 'lead_forms'
    if ch.startswith('Broker'):
        return 'Broker'
    if ch.startswith('CRM'):
        return 'CRM'
    if ch.startswith('Propiedades'):
        return 'Propiedades'
    if ch.lower().startswith('comercial'):
        return 'Comercial'
    return None  # unclassified (long-tail UTM IDs)


def _int_or_none(v):
    return int(float(v)) if v is not None else None


def build_country(bq_json, sheet_csv, channels_json, platforms_json, traffic_json, country):
    fuentes_row = FUENTES_ROW_BY_COUNTRY[country]
    daily = json.load(open(bq_json))
    channels = json.load(open(channels_json))
    platforms = json.load(open(platforms_json))
    metas_daily = parse_sheet_daily(sheet_csv, country)
    # Tráfico web (visitantes únicos), ya bucketeado por SQL en ambos cortes: {gran: {bucket: visitantes}}
    traffic_by_gran = defaultdict(dict)
    for r in json.load(open(traffic_json)):
        traffic_by_gran[r['gran']][r['bucket']] = int(r['visitantes'])
    today = date.today()

    def complete_recent_buckets(bucket_keys):
        """Keep only buckets fully in the past, then the most recent KEEP_BUCKETS."""
        done = [b for b in bucket_keys
                if date.fromisoformat(b) + timedelta(days=7) <= today]
        return sorted(set(done))[-KEEP_BUCKETS:]

    def build_for(gran):
        # --- main: by (bucket, fuente) ---
        agg = defaultdict(lambda: defaultdict(
            lambda: {'reg': 0, 'cal': 0, 'asg': 0, 'spend': None,
                     'completos': 0, 'paso65': 0, 'paso65_calif': 0}))
        for r in daily:
            b = bucket_start(date.fromisoformat(r['day']), gran)
            cell = agg[b][r['fuente']]
            cell['reg'] += int(r['reg'])
            cell['cal'] += int(r['cal'])
            cell['asg'] += int(r['asg'])
            cell['completos'] += int(r.get('completos') or 0)
            cell['paso65'] += int(r.get('paso65') or 0)
            cell['paso65_calif'] += int(r.get('paso65_calif') or 0)
            sp = _int_or_none(r.get('spend'))
            if sp is not None:
                cell['spend'] = (cell['spend'] or 0) + sp

        # --- metas: by (bucket, fuente / TOTAL / Perfo) ---
        meta_agg = defaultdict(lambda: defaultdict(lambda: None))
        for day_iso, metas in metas_daily.items():
            b = bucket_start(date.fromisoformat(day_iso), gran)
            for k, v in metas.items():
                if v is not None:
                    meta_agg[b][k] = (meta_agg[b].get(k) or 0) + v

        keep = complete_recent_buckets(agg.keys())
        keep_set = set(keep)

        by_week = {}
        totals_by_week = {}
        for b in keep:
            cells = {}
            for fuente in fuentes_row:
                cell = dict(agg[b].get(fuente, {'reg': 0, 'cal': 0, 'asg': 0, 'spend': None,
                                                'completos': 0, 'paso65': 0, 'paso65_calif': 0}))
                cell['meta'] = meta_agg.get(b, {}).get(fuente)
                cells[fuente] = cell
            # Tráfico (visitantes únicos) es indicador WEB-only → va en la celda WEB.
            if 'WEB' in cells:
                cells['WEB']['traffic'] = traffic_by_gran.get(gran, {}).get(b)
            by_week[b] = cells
            totals_by_week[b] = {
                'TOTAL': {'meta': meta_agg.get(b, {}).get('TOTAL')},
                'Perfo': {'meta': meta_agg.get(b, {}).get('Perfo')},
            }

        # --- channels: by_week_channels[bucket] = { channel: {reg,cal,asg,spend,clicks,impressions,fuente} } ---
        by_week_channels = defaultdict(dict)
        for r in channels:
            b = bucket_start(date.fromisoformat(r['day']), gran)
            if b not in keep_set:
                continue
            ch = r['channel']
            cell = by_week_channels[b].get(ch)
            spend_val = _int_or_none(r.get('spend'))
            clicks_val = _int_or_none(r.get('clicks'))
            impr_val = _int_or_none(r.get('impressions'))
            if cell is None:
                by_week_channels[b][ch] = {
                    'reg': int(r['reg']), 'cal': int(r['cal']), 'asg': int(r['asg']),
                    'spend': spend_val, 'clicks': clicks_val, 'impressions': impr_val,
                    'fuente': channel_to_fuente(ch) or r['fuente'],
                }
            else:
                cell['reg'] += int(r['reg'])
                cell['cal'] += int(r['cal'])
                cell['asg'] += int(r['asg'])
                for k, v in (('spend', spend_val), ('clicks', clicks_val), ('impressions', impr_val)):
                    if v is not None:
                        cell[k] = (cell[k] or 0) + v

        # --- platforms: by_week_platforms[bucket] = list of dicts (aggregated by platform×channel×fuente) ---
        pl_agg = defaultdict(lambda: defaultdict(
            lambda: {'reg': 0, 'cal': 0, 'asg': 0, 'spend': None, 'clicks': None, 'impressions': None}))
        for r in platforms:
            b = bucket_start(date.fromisoformat(r['day']), gran)
            if b not in keep_set:
                continue
            key = (r['platform'], r['channel'], r['fuente'])
            cell = pl_agg[b][key]
            cell['reg'] += int(r['reg'])
            cell['cal'] += int(r['cal'])
            cell['asg'] += int(r['asg'])
            for k in ('spend', 'clicks', 'impressions'):
                v = _int_or_none(r.get(k))
                if v is not None:
                    cell[k] = (cell[k] or 0) + v
        by_week_platforms = {}
        for b, combos in pl_agg.items():
            by_week_platforms[b] = [
                {'platform': p, 'channel': c, 'fuente': f, **vals}
                for (p, c, f), vals in combos.items()
            ]

        return {
            'by_week': by_week,
            'totals_by_week': totals_by_week,
            'by_week_channels': dict(by_week_channels),
            'by_week_platforms': by_week_platforms,
        }

    return {gran: build_for(gran) for gran in GRANULARITIES}


def main():
    if len(sys.argv) != 12:
        print(f"Usage: {sys.argv[0]} <bq_co> <sheet_co> <bq_ch_co> <bq_pl_co> <traffic_co> "
              f"<bq_mx> <sheet_mx> <bq_ch_mx> <bq_pl_mx> <traffic_mx> <output>")
        sys.exit(1)

    (bq_co, sheet_co, bq_ch_co, bq_pl_co, traffic_co,
     bq_mx, sheet_mx, bq_ch_mx, bq_pl_mx, traffic_mx, output) = sys.argv[1:]

    data = {
        'updated': date.today().isoformat(),
        'co': build_country(bq_co, sheet_co, bq_ch_co, bq_pl_co, traffic_co, 'co'),
        'mx': build_country(bq_mx, sheet_mx, bq_ch_mx, bq_pl_mx, traffic_mx, 'mx'),
    }

    with open(output, 'w') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    def n(c, g):
        return len(data[c][g]['by_week'])
    size = len(json.dumps(data))
    print(f"OK: {output} ({size:,} bytes · "
          f"CO week={n('co','week')} cycle={n('co','cycle')} · "
          f"MX week={n('mx','week')} cycle={n('mx','cycle')})")


if __name__ == '__main__':
    main()
