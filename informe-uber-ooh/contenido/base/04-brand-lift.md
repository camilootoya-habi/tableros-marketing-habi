# 4. Recordación: el estudio de Brand Lift de Meta

Sin llamado a la acción en los autos, la pregunta no es cuántos clics generó sino si la marca se
recuerda más. Eso se mide con un experimento: cada mes Meta encuesta a un grupo que vio la pauta y a
un grupo de control equivalente al que se le **retuvo** deliberadamente. La diferencia entre ambos —
el *lift* — es el efecto neto, limpio de la gente que ya conocía la marca.

La serie completa está disponible desde 2022, así que el desempeño de la campaña se puede leer contra
cuatro años de historia y no contra una expectativa.

```chart
metrica: brand_lift
pais: MX
vista: expuesto_control
pregunta: ad_recall
caption: Recordación del anuncio — grupo expuesto contra grupo de control
```

```chart
metrica: brand_lift
pais: MX
vista: lift
caption: Lift neto en puntos porcentuales, por pregunta de encuesta
```

## Qué muestran los datos

1. **Máximo histórico de recordación.** El grupo expuesto alcanzó
   **{{brand_lift.MX.ad_recall.exposed.max:pct1}}** y el lift neto llegó a
   **{{brand_lift.MX.ad_recall.lift.max:pts}}** en {{brand_lift.MX.ad_recall.lift.max:month}}. Los
   medios masivos potencian de forma medible el efecto de la pauta digital.
2. **El grupo de control también sube.** Gente que no fue impactada digitalmente aparece recordando
   la marca. Eso solo puede venir de fuera del canal digital: la presencia física en la calle y los
   Reels locales están elevando el piso de recordación donde la pauta no llega.
3. **Top of Mind acompaña.** El lift de Top of Mind está en
   **{{brand_lift.MX.toma.lift.latest:pts}}** al último corte. La diferencia con Ad Recall importa:
   una cosa es recordar haber visto un anuncio, otra es que la marca aparezca primero cuando alguien
   piensa en vender su casa. La segunda es más difícil y más valiosa.
4. **Sin señal de saturación.** El crecimiento es sostenido, no un pico que se desinfló. No hay
   evidencia de retornos marginales decrecientes que justificaría bajar la intensidad.
