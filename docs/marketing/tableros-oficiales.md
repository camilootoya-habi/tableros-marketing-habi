# Tableros oficiales — el código de color del hub

En el hub, las cards con **borde verde neón** y el badge **oficial** son los tableros
oficiales. La leyenda que va debajo de las pestañas dice lo mismo para quien entre sin
contexto: *si dos tableros muestran lo mismo, manda el verde.*

## Qué significa que un tablero sea oficial

Un tablero verde cumple las cuatro:

1. **Es la fuente de verdad de su indicador.** No hay otro tablero que reporte lo mismo
   con distinta cifra y siga considerándose válido.
2. **Está al día.** Su `data.json` se refresca por workflow, no a mano.
3. **Es el que se cita** en el WBR y el OKR.
4. **Sus definiciones están documentadas** — cada indicador con su `?` explicando tabla,
   filtros y gotchas, o una nota en `docs/marketing/`.

Un tablero que no cumple las cuatro no es peor: es exploratorio, un análisis cerrado o un
diagnóstico puntual. Esos van sin resaltar, y esa es justamente la señal.

## Cómo se marca

Un solo campo en el `meta.json` del tablero:

```json
{
  "title": "Marketing Sellers",
  "order": 0,
  "featured": true
}
```

`scripts/build_hub.py` lo lee y le pone la clase `card featured` más el badge. El color
sale de las variables `--neon*` del template, definidas **por separado para tema claro y
oscuro** (`scripts/templates/hub.html`): el neón puro `#39ff88` no contrasta sobre blanco,
así que en claro baja a `#06c167` con el texto en `#04703c`.

El `index.html` del hub es **generado** — no se edita a mano. Después de tocar un
`meta.json` hay que correr:

```powershell
python scripts/build_hub.py
```

## Reglas de uso

- **El verde se gana, no se pide.** Marcar todo de verde lo vuelve invisible: si la mitad
  del hub está resaltada, el resaltado no comunica nada.
- **`order: 0`** para el que deba ir primero en su sección. Los demás van de 10 en 10 para
  que quede hueco donde insertar.
- Al **degradar** un tablero (ya no es la fuente de verdad), quitarle el `featured` el
  mismo día, no cuando alguien se queje de que dos tableros no cuadran.

## Estado actual

| tablero | oficial | por qué |
|---|---|---|
| `marketing-sellers` | ✅ | Funnel y asignación de sellers MM vs Inmo. Es el que se cita en el WBR. |

Cuando se marque otro, agregarlo a esta tabla con el motivo. Si la tabla crece a más de
cuatro o cinco, revisar si el criterio se está aflojando.
