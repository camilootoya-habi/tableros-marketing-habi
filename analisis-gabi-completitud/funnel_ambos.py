# Funnel comparado bot A vs bot B — small multiples (nunca doble eje), PNG para Word.
# Barras = % de la cohorte de cada bot (868 vs 9.076: en absolutos B aplastaría a A);
# el absoluto va en la etiqueta. Un solo hue por panel (una serie); el peor drop
# intermedio de cada bot va en el rojo reservado de estado. Datos: funnel_ambos.json.
import json
import matplotlib.pyplot as plt

J = json.load(open("/Users/Nicolas/habi/tableros-marketing-habi/analisis-gabi-completitud/funnel_ambos.json"))

NOMBRES = {
    "recibio_apertura": "Recibió apertura",
    "respondio_algo": "Respondió algo",
    "consintio_y_le_piden_direccion": "Consintió (ACEPTO) →\nle piden dirección",
    "dio_direccion_le_piden_antiguedad_precio": "Dio dirección →\nantigüedad y precio",
    "llego_a_tipo_m2_recamaras": "Llegó a tipo + m² +\nrecámaras",
    "llego_a_banos_estacionamiento": "Llegó a baños +\nestacionamiento",
    "completo_levantamiento": "Completó levantamiento",
    "llego_a_direccion": "Llegó a dirección",
    "le_piden_bloque_de_6": "Le piden el bloque de 6",
    "respondio_bloque": "Respondió el bloque",
    "completo_o_paso_repreguntas": "Completó / pasó\nre-preguntas",
}
DROP_TXT = {
    ("botA", 0): "−35,5% · 308 nunca respondieron",
    ("botA", 1): "−38,6% · 216 mueren en consentimiento",
    ("botA", 2): "−40,7% · 140 mueren en dirección",
    ("botA", 3): "−39,8% · 90 en antigüedad/precio",
    ("botA", 4): "−20,4% · 29 en tipo/m² (con sugerencias)",
    ("botA", 5): "−52,5% · 64 en baños/estacionamiento",
    ("botB", 0): "−58,7% · 5.325 nunca respondieron",
    ("botB", 1): "−14,2% · 532 mueren en tipo",
    ("botB", 2): "−48,8% · 1.571 mueren en dirección",
    ("botB", 3): "−26,4% · 448 mueren ante el bloque",
    ("botB", 4): "−11,9% · 147 en re-pregunta de m²",
}
PEOR = {"botA": 5, "botB": 2}  # índice del drop resaltado por panel

INK, MUTED, SERIOUS, BAR, SURFACE = "#1F2430", "#6B7280", "#B4232A", "#2F6FB4", "#FFFFFF"

fig, axes = plt.subplots(1, 2, figsize=(13.4, 6.2), dpi=200)
fig.patch.set_facecolor(SURFACE)

TITULOS = {"botA": "Bot A — \"de a uno\" (LLM con sugerencias) · 868 deals",
           "botB": "Bot B — guionado \"los 6 juntos\" · 9.076 deals"}

for ax, key in zip(axes, ("botA", "botB")):
    etapas = J[key]
    total = etapas[0]["deals"]
    n = len(etapas)
    ax.set_facecolor(SURFACE)
    for i, e in enumerate(etapas):
        y = n - 1 - i
        pct = e["deals"] / total * 100
        ax.barh(y, pct, height=0.42, color=BAR, zorder=3)
        ax.text(-2, y, NOMBRES[e["etapa"]], ha="right", va="center",
                fontsize=8.6, color=INK, linespacing=1.1)
        ax.text(pct + 1.2, y, f"{e['deals']:,}".replace(",", "."), ha="left",
                va="center", fontsize=9, color=INK, fontweight="bold")
        if i > 0:
            ax.text(pct + 1.2, y - 0.27, f"{pct:.1f}%".replace(".", ","),
                    ha="left", va="center", fontsize=7.6, color=MUTED)
        if i < n - 1:
            resaltado = (PEOR[key] == i)
            color = SERIOUS if resaltado else MUTED
            ax.text(99, y - 0.5, DROP_TXT[(key, i)] + " ↓", ha="right", va="center",
                    fontsize=7.8, color=color,
                    fontweight="bold" if resaltado else "normal")
    ax.set_xlim(0, 112)
    ax.set_ylim(-0.6, n - 0.4)
    ax.axis("off")
    ax.text(0, n - 0.15, TITULOS[key], fontsize=10.5, color=INK, fontweight="bold",
            transform=ax.transData, ha="left")

fig.text(0.055, 0.965, "Funnel de Gabi por bot — dónde se muere cada conversación",
         fontsize=14, color=INK, fontweight="bold", ha="left")
fig.text(0.055, 0.925, "jun–ago 2026 · barras = % de la cohorte de cada bot (etiqueta = deals) · etapas propias de cada bot, no comparables 1 a 1 · fuente: chatbots.mabi_mx",
         fontsize=8.6, color=MUTED, ha="left")
fig.text(0.055, 0.022, "Dirección mata ~40–49% en AMBOS bots (la fricción es el dato, no el guión). El % que entrega la mayoría de los datos es casi idéntico: 14,1% (A) vs 13,6% (B).",
         fontsize=8.8, color=SERIOUS, ha="left")

plt.subplots_adjust(left=0.135, right=0.985, top=0.855, bottom=0.075, wspace=0.55)
out = "/private/tmp/claude-501/-Users-Nicolas-habi-marketing-loop-sellers/d3ebf127-0590-42c5-ae38-e0bae0a26363/scratchpad/funnel_ambos.png"
fig.savefig(out, facecolor=SURFACE)
print(out)
