# 6. Validación: qué dice la gente al registrarse

El capítulo anterior mide comportamiento. Este mide **lo que la gente declara**: a cada persona que
se registra se le pregunta dónde nos conoció. Es una fuente distinta e independiente, con sus propias
limitaciones, y por eso vale como contraste.

## 6.1 ¿Es una muestra confiable?

```chart
metrica: exit_poll
pais: MX
vista: tasa
plaza: MTY
caption: Tasa de respuesta del exit poll en Monterrey, sobre registros web
```

La participación es alta y estable: **{{exit_poll.MX.MTY.tasa.latest:pct1}}** al último corte. No es
una muestra marginal de gente especialmente motivada, es la mayoría de quienes se registran.

## 6.2 Atribución declarada a Uber

```chart
metrica: exit_poll
pais: MX
vista: share
plaza: MTY
caption: Share de canales declarados en Monterrey. La encuesta es de selección múltiple
```

- **Punto de partida en cero.** Antes de la campaña, nadie mencionaba los autos de Uber. No es que
  fuera bajo: no existía.
- **Crecimiento sostenido.** En Monterrey la mención llega a
  **{{exit_poll.MX.MTY.uber_share.latest:pct2}}** de quienes responden, contra
  **{{exit_poll.MX.uber_share.latest:pct2}}** a nivel nacional. La plaza donde circulan los autos
  declara casi el doble que el promedio del país, que es exactamente la firma que uno esperaría si la
  causa fueran los autos.

## 6.3 Tres advertencias de lectura, y una corrección

**La encuesta es de selección múltiple.** Una persona marca varios canales, así que los porcentajes
suman más de 100%. El share de Uber no es "el 3% de los registros vino de Uber": es "el 3% de quienes
responden mencionan haber visto los autos", que es una afirmación sobre recordación, no sobre origen.

**El catálogo de respuestas cambió a inicios de 2026.** Algunas opciones se renombraron, así que unas
series se cortan y otras arrancan ahí. No es un cambio de comportamiento del público.

**El texto libre no se conserva.** La opción "Otro" permite escribir, y la gente escribió datos
personales. Como este informe y su tablero son públicos, ese texto se descarta y solo se registra que
la respuesta fue "Otro".

**Corrección respecto a la versión anterior de este informe.** La edición manual de Q1 reportó que la
atribución declarada a Uber alcanzaba 2% en marzo de 2026. Recalculada con la definición canónica que
ahora usa el tablero, marzo da 1.62% en Monterrey y Guadalajara, y 0.63% a nivel nacional; el 2% se
alcanza en mayo. La cifra anterior correspondía a otro corte. Se publica la serie reproducible, que
además sostiene mejor el argumento: sigue subiendo hasta el último dato disponible.
