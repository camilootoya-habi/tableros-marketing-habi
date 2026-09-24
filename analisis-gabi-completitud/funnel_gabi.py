# Funnel de Gabi (bot B) con drops entre etapas — PNG para pegar en Word.
# Forma: barras horizontales (magnitud por etapa ordenada) + anotación del drop
# entre cada par de barras. Un solo hue secuencial (una serie, sin leyenda);
# el texto va en tinta, nunca en el color de la serie; el peor drop se marca
# con el color "serious" reservado + negrita (estado, no serie).
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ETAPAS = [
    ("Recibió apertura", 9076),
    ("Respondió algo", 3751),
    ("Llegó a dirección", 3219),
    ("Le piden el bloque de 6", 1695),
    ("Respondió el bloque", 1237),
    ("Completó / pasó re-preguntas", 1060),
]
DROPS = [  # (texto, ¿es el peor?)
    ("−58,7% · 5.325 nunca respondieron", False),
    ("−14,2% · 532 mueren en tipo", False),
    ("−48,8% · 1.571 mueren en dirección", True),
    ("−26,4% · 448 mueren ante el bloque", False),
    ("−11,9% · 147 mueren en re-pregunta de m²", False),
]

INK, MUTED, SERIOUS = "#1F2430", "#6B7280", "#B4232A"
BAR = "#2F6FB4"          # un solo hue (serie única): sin leyenda
SURFACE = "#FFFFFF"

fig, ax = plt.subplots(figsize=(9.2, 5.4), dpi=200)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

n = len(ETAPAS)
ys = [n - 1 - i for i in range(n)]           # de arriba hacia abajo
vals = [v for _, v in ETAPAS]
maxv = vals[0]

for (label, v), y in zip(ETAPAS, ys):
    # barra delgada, extremos redondeados 4px (~0.02 en ejes), anclada a 0
    ax.barh(y, v, height=0.42, color=BAR, zorder=3)
    ax.text(-150, y, label, ha="right", va="center", fontsize=10.5, color=INK)
    ax.text(v + 90, y, f"{v:,}".replace(",", "."), ha="left", va="center",
            fontsize=10.5, color=INK, fontweight="bold")
    pct = v / maxv * 100
    if v != maxv:
        ax.text(v + 90, y - 0.26, f"{pct:.1f}%".replace(".", ","), ha="left",
                va="center", fontsize=8.5, color=MUTED)

for i, (texto, peor) in enumerate(DROPS):
    y_mid = ys[i] - 0.5
    color = SERIOUS if peor else MUTED
    peso = "bold" if peor else "normal"
    ax.annotate("", xy=(maxv * 0.985, y_mid - 0.14), xytext=(maxv * 0.985, y_mid + 0.14),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.4))
    ax.text(maxv * 0.975, y_mid, texto, ha="right", va="center",
            fontsize=9.5, color=color, fontweight=peso)

ax.set_xlim(0, maxv * 1.12)
ax.set_ylim(-0.6, n - 0.4)
ax.axis("off")
fig.text(0.06, 0.955, "Funnel de Gabi (bot B) — dónde se muere cada conversación",
         fontsize=13.5, color=INK, fontweight="bold", ha="left")
fig.text(0.06, 0.905, "9.076 deals · jun–ago 2026 · fuente: chatbots.mabi_mx (desenlace: gabi_mx / gabi_inmo_mx)",
         fontsize=9, color=MUTED, ha="left")
fig.text(0.125, 0.02, "El drop en rojo es la mayor oportunidad: 48,8% de quienes llegan a dirección mueren ahí (~524/mes).",
         fontsize=9, color=SERIOUS)

plt.subplots_adjust(left=0.26, right=0.97, top=0.84, bottom=0.08)
out = "/private/tmp/claude-501/-Users-Nicolas-habi-marketing-loop-sellers/d3ebf127-0590-42c5-ae38-e0bae0a26363/scratchpad/funnel_gabi.png"
fig.savefig(out, facecolor=SURFACE)
print(out)
