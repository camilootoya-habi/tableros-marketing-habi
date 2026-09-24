import json, re, sys

def redact(t):
    t = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '[email]', t)
    t = re.sub(r'\+?\d[\d\s().-]{8,}\d', lambda m: '[tel]' if len(re.sub(r'\D','',m.group())) >= 10 else m.group(), t)
    return t

def render(rows, only=None):
    for r in rows:
        if only and r['caso'] != only: continue
        print(f"\n{'='*72}\n{r['caso']} · deal {r['deal_id']} · {r['n']} chars\n{'='*72}")
        for turno in re.split(r'\n(?=Gabi:|Usuario:)', r['c']):
            turno = turno.strip()
            if not turno: continue
            m = re.search(r'HORA: ([\d\-T:.]+)', turno)
            hora = m.group(1)[:16].replace('T', ' ') if m else '?'
            texto = re.sub(r'\.?\s*HORA: [\d\-T:.]+\s*$', '', turno).strip()
            rol, _, cuerpo = texto.partition(':')
            print(f"\n[{hora}] {rol.strip().upper()}:")
            for line in redact(cuerpo.strip()).split('\n'):
                print(f"    {line}")

rows = json.load(open(sys.argv[1]))
render(rows, sys.argv[2] if len(sys.argv) > 2 else None)
