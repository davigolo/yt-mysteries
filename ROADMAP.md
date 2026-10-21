# Roadmap de mejora del canal

Revisión inicial: 21 de octubre de 2026. El objetivo es una publicación fiable y una mayor continuidad entre Shorts y
episodios, sin aumentar la producción ni cambiar de micronicho por una caída aislada.

## Punto de partida

YouTube Studio, 23 de septiembre–20 de octubre: 17.082 visualizaciones, 96,4 horas y 50 suscriptores netos ganados.
Los largos suman 314 visualizaciones, 1.906 impresiones y un CTR del 3,9%. En *Navy Blimp*, el CTR es del 4,6%, pero
solo el 41% permanece al segundo 30. En Shorts, el 52,9% decide seguir viendo y el 47,1% desliza.

Analytics, con corte al 18 de octubre: porcentaje medio visto del 24,09% en largos y del 70,81% en Shorts.
*The Cipher That Mourned a Living Woman* alcanza el 91,16% visto con 1.326 visualizaciones; *The Hillside Bodies Wearing
Eyeless Lead Masks*, el 30,79% con 784. No mezclar los totales de ambos cortes ni atribuir causalidad a estos ejemplos.

## Fase 1 — Publicación fiable

Prioridad inmediata:

- Generar los episodios domingo, martes y jueves con antelación; programar su salida exclusivamente lunes, miércoles
  y viernes a las 19:00 de Nueva York. Mantener el margen mínimo de 22 horas, el cambio automático de horario y la
  exclusión de franjas ocupadas. Si la generación llega tarde, usar el siguiente día permitido, nunca publicar fuera
  de calendario para recuperar una ejecución.
- Aplicar también los días permitidos a los episodios antiguos en oculto. Mantener los Shorts diarios a las 12:00 y
  19:30, siempre después del episodio al que apuntan.
- Detectar la verificación de identidad de Studio, detener los intentos inútiles y hacer que el fallo de enlaces sea
  visible en Actions. Comprobar cada enlace después de recargar; un aviso de guardado no basta.
- Permitir recuperar Shorts anteriores a los siete días habituales y asegurar que el modo de simulación no modifica
  Studio.

Aceptación: ninguna fecha nueva de episodio fuera de L/X/V en Nueva York; ninguna franja duplicada; cada enlace
se confirma al recargar o deja un fallo explícito. Una simulación no modifica el canal.

Incidencia inicial: Google pedía «Verifica que eres tú» al guardar desde el runner. Los enlaces pendientes se recuperaron
desde la sesión local autorizada y se comprobaron después desde Actions. Si vuelve a aparecer un desafío en futuras
subidas, la verificación debe hacerla el propietario; el código no la evita ni garantiza que exportar cookies lo elimine.

## Fase 2 — Aperturas y promesas

Primer lote de mejora editorial, sin generar vídeos durante la implementación:

- Reforzar la entrega de una evidencia tangible y la promesa del título en los primeros 20 segundos, sin presentación
  del canal, acumulación de nombres y fechas ni reinicio cronológico tras el gancho. La revisión del texto usa las
  primeras 50 palabras como aproximación editorial; no certifica el segundo exacto de la voz sintetizada.
- Mantener los Shorts centrados en una anomalía verificable, con un gancho concreto y una pequeña respuesta antes del
  CTA. Replicar estructuras narrativas, no casos ni afirmaciones de vídeos anteriores.
- Incluir la apertura en la revisión automática de packaging y regenerar los guiones que no cumplan, utilizando
  exclusivamente hechos respaldados por las fuentes.

Aceptación: el escritor y el revisor reciben las mismas reglas; un guion rechazado no llega a síntesis de voz ni imágenes.
Las comprobaciones se hacen sin llamadas pagadas. La aprobación automática no sustituye la revisión humana de fuentes.

## Fase 3 — Evaluación tras 3–4 publicaciones maduras

La instrumentación está implementada en `scripts/channel_report.py` y el workflow diario/manual `Channel Report`.
Consulta datos reales sin modificar el canal y guarda JSON y resumen de Actions. `reporting.rollout_id` distingue
los vídeos realmente generados por el nuevo pipeline de los que ya estaban programados: solo los primeros llevan
`pipeline_revision`. No se etiquetan retrospectivamente ni se cuentan guiones reutilizados como una nueva apertura.
La fecha inicial es el 21 de octubre de 2026 y el lote requiere cuatro muestras elegibles por formato.

No aumentar la frecuencia antes de revisar el primer lote:

- Separar largos y Shorts; registrar el periodo, el último día disponible y el tamaño de muestra. Esperar al menos
  tres días completos desde la publicación antes de comparar.
- Largos: revisar permanencia al segundo 30 y 60, porcentaje medio visto, impresiones y CTR. Contrastar las aperturas
  con el 41% al segundo 30 de *Navy Blimp*, sin tratarlo como una comparación controlada entre temas distintos.
- Shorts: revisar porcentaje que sigue viendo frente a deslizar, porcentaje medio visto y suscriptores por vista
  interesada. No confundir estas métricas ni llamar ganador al que recibe más distribución.
- Usar 40% visto en largos y 75% en Shorts como referencias editoriales de diagnóstico, no como reglas conocidas del
  algoritmo ni garantías de crecimiento.
- Si la apertura mejora pero el CTR sigue débil con suficiente muestra, preparar una prueba de título o miniatura
  cambiando una sola variable. No cambiar packaging y guion simultáneamente para atribuir después la mejora a uno solo.
- Revisar en Studio el tráfico entre Shorts y largos una vez reparados los enlaces. No atribuirles conversiones que
  los informes no midan. Añadir manualmente pantallas finales a episodios relacionados.

Decisión al cerrar el lote: mantener lo que muestre una mejora consistente, corregir el siguiente cuello de botella y
continuar dentro del micronicho activo salvo que se cumplan sus criterios de cambio.

## Despliegue y estado

| Entrega | Estado |
|---|---|
| Calendario L/X/V y generación anticipada | Desplegado en `main` el 21/10; simulación de Actions correcta |
| Detección de desafíos, fallo visible y recuperación por ventana | Desplegado; 34/34 Shorts de la ventana de 14 días confirmados en Studio |
| Aperturas revisadas en largos y Shorts | Desplegado; se aplica a los nuevos guiones, no reescribe vídeos existentes |
| Informe diario/manual y cohorte del despliegue | Activo; primera consulta real y artefacto de Actions correctos |
| Evaluación del siguiente lote | Automatizada la recopilación; decisión pendiente de cuatro muestras elegibles por formato |

El despliegue en `main` fue solicitado el 21 de octubre de 2026. Las fases 1 y 2 y la instrumentación de la fase 3
se activan al subir el código; su comprobación operativa utiliza `Publish` en simulación y `Channel Report` real.
No hace falta generar vídeos adicionales para comprobar el despliegue.
Las publicaciones ya programadas no se reescriben retroactivamente. En la comprobación previa no había largos privados
programados fuera del nuevo calendario; se conservaron las fechas de los Shorts pendientes.

Comprobación del 21/10:

- Código desplegado: `706f9c8`.
- [Informe real correcto](https://github.com/davigolo/yt-mysteries/actions/runs/39581222564):
  corte del 18/10 y cero vídeos maduros de la nueva cohorte, sin comparación prematura.
- [Publicación en simulación correcta](https://github.com/davigolo/yt-mysteries/actions/runs/39581226198):
  no accede a Studio, no renueva la sesión y no publica vídeos.
- Recuperados los enlaces pendientes y confirmados tras recargar los 34 Shorts de la ventana de 14 días, incluidos
  los programados para hoy y mañana. Sin cambiar títulos, privacidad ni fechas.
- [Publicación real correcta](https://github.com/davigolo/yt-mysteries/actions/runs/39581824687):
  Actions reconoce como ya enlazados los 14 Shorts de los últimos siete días; no publicó vídeos adicionales.
- Los cuatro workflows están activos. La primera nueva franja de largo disponible desde este despliegue es el viernes
  23 de octubre a las 19:00 de Nueva York; no se reduce el margen de 22 horas para forzar un estreno el miércoles.
- Pantalla final del último episodio, *The Gold Cavern That Sparked a Secret Military Dig*: añadido el episodio
  *The Carving on the Tree That Left No Cross* previsto en su guion y el elemento de suscripción durante los últimos
  20 segundos. Guardado y comprobado tras recargar Studio. Las pantallas finales de futuros episodios siguen
  requiriendo Studio; la API de subida no las crea.

La fase 3 queda pendiente de publicaciones nuevas y datos maduros. No se presentará una mejora editorial como una mejora
estadística hasta observarla.
