#!/usr/bin/env python3
"""Genera una versión autocontenida del informe (data.json incrustado, sin fetch)
para abrir directo como archivo en Windows. Re-ejecutar tras cada cambio para afinar.

Uso: python make_standalone.py [destino.html]
"""
import json, sys

HERE = '/home/administrador/habi/tableros-marketing/diagnostico-performance-co/'
DEST = sys.argv[1] if len(sys.argv) > 1 else \
    '/mnt/c/Users/Administrador/Downloads/diagnostico-performance-co.html'

html = open(HERE + 'index.html', encoding='utf-8').read()
data = json.load(open(HERE + 'data.json', encoding='utf-8'))
embed = json.dumps(data, ensure_ascii=False)

needle = "fetch('./data.json').then(r => r.json()).then(D => {"
repl = "const __EMBEDDED__ = " + embed + ";\nPromise.resolve(__EMBEDDED__).then(D => {"
assert needle in html, "no se encontró la línea de fetch; revisa index.html"
html = html.replace(needle, repl)

open(DEST, 'w', encoding='utf-8').write(html)
print('Standalone ->', DEST, f'({len(html)//1024} KB)')
