# yt-mysteries

Canal **long-form en inglés** (12-14 min) de misterios históricos y casos sin resolver, generado íntegramente con IA.
Hermano de `yt-autoshorts`, reutiliza la misma idea de pipeline:

**Gemini** (tema → investigación → guion por capítulos) → **ElevenLabs** (voz con tiempos por carácter) →
**Wikimedia Commons** (imágenes reales de archivo, con licencia libre) + **Pexels** (b-roll) + **Magnific** (reconstrucciones IA
y miniatura) → **ffmpeg** (1920x1080, Ken Burns, rótulos de capítulo, etalonaje, música con ducking) →
**YouTube Data API** (vídeo + miniatura + subtítulos SRT + capítulos en la descripción) → **GitHub Actions** (generación D/M/J
15:37 UTC; publicación L/X/V a las 19:00 de Nueva York).

## Probar en local (recomendado antes de activar el cron)

Requiere `ffmpeg`/`ffprobe` en el PATH.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
# Rellena las claves en .env (está en .gitignore); main.py lo carga solo

.venv/bin/python main.py --script-only                          # 1. solo guion -> build/script.json (gratis)
cp build/script.json episode.json                               #    revísalo/edítalo a mano si quieres
.venv/bin/python main.py --script episode.json --preview 12     # 2. primeras 12 escenas (~1,5 min, pocos créditos)
.venv/bin/python main.py --script episode.json --no-upload      # 3. episodio completo sin subir
```

Salida en `build/`: `video.mp4`, `thumbnail.jpg`, `description.txt`, `captions.srt`.
Voz, imágenes IA y descargas se guardan en `cache/`, así que repetir un render con el mismo guion **no vuelve a gastar créditos**.

## Puesta en marcha (canal nuevo)

1. Crea el canal de YouTube y **verifícalo por teléfono** (necesario para miniaturas personalizadas y vídeos >15 min).
2. Reutiliza el proyecto de Google Cloud de `yt-autoshorts` (o crea otro) y descarga `client_secret.json` aquí.
3. `.venv/bin/python scripts/get_token.py` y autoriza **con la cuenta del canal nuevo** (pide además el scope
   `youtube.force-ssl`, necesario para subir subtítulos).
4. Crea el repo en GitHub y añade los secrets: `GEMINI_API_KEY`, `PEXELS_API_KEY`, `ELEVENLABS_API_KEY`,
   `MAGNIFIC_API_KEY` y los de `.yt.env` (`gh secret set -f .yt.env`).
5. Música y efectos: `ELEVENLABS_API_KEY=... .venv/bin/python scripts/generate_music.py [longform|shorts]` genera 10 fondos
   documentales de 3 min en `music/` y 8 pistas de tensión de 90 s para Shorts en `music/shorts/`;
   `scripts/generate_sfx.py` genera impactos, whoosh, risers y tape stops en `sfx/`. Solo crea lo que falte, así que para
   añadir variedad basta con añadir prompts. También valen pistas de la Biblioteca de audio de YouTube. Haz commit de `music/` y `sfx/`.

## Coste estimado por episodio (~13 min)

| Servicio | Consumo |
|---|---|
| ElevenLabs | Voz **Connery** (narrador grave de documental, EE. UU.; elegida en una prueba a ciegas frente a otras 6) con `eleven_v4_turbo`, 0,5 créditos/carácter: ~11.500 caracteres = ~5.800 créditos por episodio. 3 vídeos/semana + 2 Shorts/día = ~100k/mes: cabe en **Creator** (236k). La voz está añadida a la biblioteca de la cuenta; si cambias de API key, añádela otra vez desde la Voice Library |
| Magnific API | Hasta 30 imágenes Flux 2 Klein con referencia + 1 Mystic 2k para la miniatura. **La API consume créditos aunque tu plan tenga uso "ilimitado" en la web** |
| Gemini | Guion, plan visual y filtrado de candidatos con Gemini Vision (~1 llamada por plano de stock o archivo). La búsqueda web (grounding) puede no tener cuota gratis; en ese caso investiga sin búsqueda y lo avisa en el log |
| Pexels / Wikimedia | 0 € |
| GitHub Actions | ~40-70 min por episodio; mejor repo público o tendrás que vigilar los 2.000 min/mes |

Ajusta `visuals.max_ai_images` para limitar el gasto en Magnific. `visuals.upscale_archive_below` (p. ej. `900`) y `max_upscales`
activan el upscaler de Magnific para las fotos de archivo de baja resolución.

## Publicación programada a hora de EE. UU.

El público principal es estadounidense, así que cada vídeo se sube en **privado con `publishAt`** y YouTube lo publica él
solo a la hora exacta, sin depender de los cron de GitHub (que se retrasan hasta 4-5 h). Franjas y margen en
`upload.schedule`; zona horaria y días de episodio en `publish`:

- Zona `publish.timezone: America/New_York`, con horario de verano automático. Episodios a las 19:00 exclusivamente
  lunes, miércoles y viernes (`publish.episode_weekdays: [0, 2, 4]`; lunes = 0); Shorts todos los días a las 12:00 y 19:30.
- Actions genera los largos domingo, martes y jueves para preparar su publicación al día siguiente. Si una ejecución
  llega tarde, se elige el siguiente día permitido; no se publica en martes, jueves o fin de semana para recuperar el retraso.
- Siempre al menos `min_hours` (22 h) después de la subida, para que YouTube procese el vídeo antes, y nunca dos vídeos en
  la misma franja: se busca la siguiente libre a partir de `publish_at` en `history.json` y `shorts_history.json`.
- Un Short siempre sale al menos 30 min después de su episodio.
- Para no usarla, quita `upload.schedule`: se vuelve a subir en oculto (`upload.privacy`) y `publish.py` lo pasa a público
  cuando cumple el margen y, para episodios, el día permitido (13:17, 15:37, 18:17 y 23:17 UTC,
  máximo `publish.max_per_run` por franja). `publish.yml` lo sigue
  ejecutando para los vídeos antiguos en oculto y para enlazar los Shorts con su episodio.
- La vía de vídeos antiguos en oculto también respeta los días de episodio en la zona de `publish.timezone`.
  Las fechas ya programadas en YouTube no cambian retroactivamente al editar la configuración.
- Para cancelar una publicación programada, quita la fecha en Studio o borra el vídeo.

- `.venv/bin/python publish.py --dry-run` muestra qué se publicaría sin cambiar nada.
- Facebook, Instagram y TikTok se siguen publicando al momento (allí no existe el oculto).

Además, en cada subida: contenido sintético declarado, "no es para niños", contador de "me gusta" visible, máximo 5
hashtags (los del caso primero) y listas de reproducción (`playlists` en `config.yaml`, se crean públicas si no existen):
cada episodio va a la lista general y a la de su formato, y cada Short a *Mystery Shorts*. Mientras el vídeo está en
oculto conviene añadir a mano en Studio lo que la API no permite: **pantalla final** (suscribirse + "Mejor para el
espectador" o el episodio relacionado) y **tarjetas** a otros episodios. El vídeo relacionado de cada Short se pone solo
(ver más abajo).

## Plan visual y continuidad

Antes había planos al azar: el stock y Wikimedia metían cosas modernas o sin relación con el caso (móviles, furgonetas,
dólares, metro…), y cada imagen de IA se generaba aislada. Ahora `longform/visual_plan.py` sigue lo que hacen los canales
virales del nicho:

1. **Gemini planifica todos los planos** de una vez a partir de la narración: una *biblia visual* (época, lugar, un look
   de película común y personajes recurrentes, siempre de espaldas o en silueta) y entre 2 y 8 **anclas** (los lugares y
   objetos que se repiten; el objeto del título siempre es una). Cada frase recibe un plano que muestra **literalmente**
   lo que se dice, con plano general primero y detalles después, y nunca la misma imagen dos veces seguidas.
2. **Magnific Flux 2 Klein** (`visuals.plan_model`) genera cada ancla y luego cada plano usando su ancla como
   **imagen de referencia**, así se mantienen el mismo lugar, la misma luz y la misma ropa. Si se acaba el presupuesto de
   imágenes (`max_ai_images`), se reutiliza el ancla con otro movimiento de cámara, nunca un plano al azar.
3. **Stock y Wikimedia pasan por Gemini Vision**: se descargan hasta 6 candidatos en miniatura y Gemini elige el que
   muestra lo pedido, o los rechaza todos si hay algo anacrónico, de otro paisaje o metafórico. En los Shorts el stock está
   desactivado (`shorts.visuals.plan_stock: false`).
4. Las imágenes demasiado oscuras se aclaran con una curva de gamma (sin quemar luces) y el etalonado final es común.
5. **Ambiente por plano** (`longform/looks.py`): Gemini asigna a cada frase un `mood` (dread, mystery, eerie, memory,
   revelation, investigation, grief) que aplica un etalonado propio (frío y oscuro, verde enfermizo, sepia desvaído,
   blanco y negro duro…).
6. **Look de película** en el pase final, para que no se note la imagen de IA: suavizado del exceso de nitidez, halo en
   las luces, ligera aberración cromática, negros lavados, grano animado y un parpadeo de proyector casi imperceptible.

Si Gemini no responde, se usan los visuales del guion como antes. Presupuesto de Magnific: 12 imágenes por Short y
30 por episodio. La API no devuelve el saldo de créditos, así que revisa el consumo en el panel de Magnific los primeros
días y baja `max_ai_images` si hace falta.

## Enfoque en EE. UU.

- `channel.language: "American English"`, y los prompts piden ortografía de EE. UU., millas, pies, libras, °F y fechas tipo
  "October 4, 1931".
- Selector de temas (`_country_rule` en `longform/script.py`): con `script.country_focus: "US"` todos los casos son de
  EE. UU. (un solo avatar de audiencia). Sin esa clave vuelve la regla anterior: 2 de cada 3 episodios de EE. UU. y, si no,
  UK, Canadá o Australia. El país se guarda en `history.json` (`country`).

## Señales para el algoritmo

Aplicado de "9 errores que el algoritmo de YouTube odia" (Mario Ruiz):

- **Micronicho, no caos de temas**: el canal mantiene una promesa concreta para el mismo espectador, no solo una categoría
  amplia como «desapariciones». No cambia automáticamente al llegar a seis episodios. El selector y el escritor reciben
  los límites del micronicho y los casos ya cubiertos; el dossier se revisa antes de escribir para rechazar casos fuera
  de alcance o repeticiones del mismo incidente con otro nombre.
- **Ángulo, no temas vagos**: el caso debe aportar un ángulo nuevo; los casos muy trillados solo valen con una prueba o
  documento poco conocido.
- **Personalidad en un canal faceless**: el narrador tiene carácter (`channel.host`) y da su opinión en primera persona una
  vez a mitad y otra al final. Lo manual: un tráiler de canal de 30-60 s con tu voz o tu cara.
- **Gancho y promesa**: apertura de 40-60 palabras en 3-5 planos, con una primera frase de máximo 12 palabras. Entrega
  una prueba concreta antes de plantear la pregunta; el primer capítulo continúa la investigación sin otra introducción,
  rebobinado cronológico ni pausa de título. Los capítulos incorporan pistas o pequeñas respuestas cada 30-45 s.
- **Packaging relevante y sin engaño**: tras cada guion, también en Shorts, Gemini contrasta la narración con su fuente
  (dossier o episodio) y comprueba que entrega la promesa. Corrige título, texto e idea visual de miniatura cuando procede.
  Si detecta afirmaciones sin respaldo o una promesa sin entregar, se regenera el guion con ese feedback, hasta tres
  intentos; una revisión inválida detiene la generación antes de gastar en voz o imágenes. Esta revisión automática no
  sustituye la comprobación humana de fuentes.
- **Apertura revisada**: escritor y revisor comprueban una prueba tangible y la promesa del título en las primeras
  50 palabras de los largos, difieren nombres y fechas innecesarios y rechazan un reinicio después del gancho. Es una
  aproximación editorial al objetivo de los primeros 20 segundos, no una medición del audio. En Shorts, el gancho
  tiene como máximo ocho palabras y el segundo beat entrega evidencia de la anomalía. `opening_valid` es obligatorio
  en ambos revisores; una apertura rechazada devuelve feedback para regenerar el guion.
- **Impacto de sesión**: la última frase enlaza con el episodio anterior de la misma serie, que va también como
  "Watch next" en la descripción, y el vídeo termina con `video.end_screen_seconds` (20) de cola para la **pantalla final**.
  La API no permite crearla: el log indica qué vídeo poner en Studio.
- **Aprender rápido**: las estadísticas que recibe Gemini marcan los vídeos con retención < 40 % (problema de gancho o
  guion). El CTR (< 5 % = problema de título/miniatura) no está en la API de Analytics: revísalo en Studio tras 3-4 vídeos.

## Continuidad de micronichos

`longform/series.py` define cuatro promesas editoriales acotadas y sus vecinos:

| Micronicho | Qué mantiene unido cada episodio |
|---|---|
| `last-messages` | Desapariciones reconstruidas a partir de una última nota, comunicación, diario o inscripción real |
| `empty-vessels` | Barcos o aeronaves recuperados sin su tripulación y con una desaparición sin resolver |
| `lost-expeditions` | Expediciones desaparecidas investigadas mediante sus campamentos, equipo o diarios recuperados |
| `missing-prospectors` | Buscadores de minas o tesoros desaparecidos que dejaron un mapa, campamento o pertenencias |

- El arranque editorial es `script.microniche.initial: last-messages`, manteniendo el enfoque en EE. UU. No se presenta
  como un ganador estadístico. Los episodios antiguos conservan sus datos: no se les atribuye retroactivamente un
  micronicho sin revisar el caso.
- Cada episodio nuevo guarda `microniche`, `series_id` y `series_reason` en su guion y en `history.json`. El último bloque
  etiquetado es la serie activa. Generar una prueba o usar `--no-upload` no cambia esa serie: se consolida al subir el
  episodio y guardar el historial. Los guiones antiguos siguen siendo compatibles.
- La revisión usa bloques de cuatro episodios, no una fecha de caducidad. Para un cambio por deterioro hacen falta
  **ocho episodios públicos y maduros de la misma serie, cada uno con al menos 100 vistas**: los cuatro últimos deben
  estar todos por debajo del 40% visto y su media debe caer al menos un 25% respecto a los cuatro anteriores, cuya media
  debía alcanzar el 40%. Sin datos suficientes, con datos sanos o con una caída aislada, se continúa. Estos umbrales son
  heurísticas editoriales configurables, no reglas conocidas del algoritmo ni prueba de causalidad.
- Si el selector dice que no encuentra otro caso, se hace una búsqueda web con fuentes y se vuelve a evaluar dentro
  de los mismos límites antes de considerar un cambio. Un primer fallo, una respuesta inválida o una búsqueda sin
  fuentes no autorizan saltar de tema. No se inventan casos para completar una cuota; si tampoco hay candidatos adecuados
  en los vecinos permitidos, la ejecución se detiene para revisión editorial.
- Los cambios solo van a micronichos vecinos, priorizando sus señales maduras cuando existen y evitando volver
  inmediatamente al que se acaba de abandonar. No se elige al azar entre todos los formatos.
- El aprendizaje prioriza los episodios y Shorts de la serie activa. Si todavía no hay señales elegibles, las del resto
  del canal se presentan únicamente como hipótesis de narrativa, nunca como permiso para salir del micronicho.
- «Watch next» y la recomendación final priorizan la misma serie y después el mismo micronicho. En el arranque solo puede
  usarse un episodio antiguo sin etiqueta del mismo formato como alternativa; no se enlaza otro micronicho etiquetado
  solo por compartir formato. Cada episodio nuevo se añade también a una playlist estable de su micronicho.
- Los Shorts automáticos promocionan exclusivamente el bloque activo y guardan sus identificadores. Si todos sus
  episodios alcanzaron el máximo de Shorts, esperan en vez de rellenar con temas de series anteriores. `--episode`
  sigue permitiendo una elección manual explícita.

La continuidad busca facilitar que un espectador quiera ver el siguiente episodio. No garantiza más recomendaciones:
hay que seguir revisando en Studio impresiones, CTR, retención y tráfico entre vídeos, sin confundir una caída de alcance
con el agotamiento de un micronicho.

## Aprendizaje de las analíticas

El pipeline consulta los últimos 90 días, detecta el último día disponible en Analytics y comprueba en YouTube qué vídeos
son públicos. Solo aprende de los publicados al menos tres días antes de ese corte; no usa la fecha de generación o subida
ni considera maduros los programados o privados. Los días se comparan en la zona horaria de los informes de YouTube.

- **Episodios** (`main.py`): incorpora señales desde 20 vistas, aunque solo haya un episodio, señalando que la muestra es
  preliminar. El objetivo de referencia es 40% visto, no un umbral que demuestre éxito. Sus señales se combinan con las de
  los casos y Shorts, en lugar de descartarlas si faltan tres episodios grandes. El feedback llega tanto al selector de
  temas como al escritor del guion.
- **Shorts** (`short.py`): exige cuatro ejemplos con al menos 100 vistas y 50 vistas interesadas (`engagedViews`). La
  puntuación combina retención (80%, limitada al 100%) y suscriptores por vista interesada (20%, saturado al 2%).
  Muestra hasta tres ejemplos con retención >=75%, dos de rendimiento en suscriptores y tres con retención <60%;
  no llama ganador a un Short solo porque haya recibido más distribución. Incluye título, ángulo o gancho, duración media
  vista y suscriptores; los Shorts nuevos guardan también el gancho, las palabras y la duración real en el historial.
- **Casos**: requieren al menos dos Shorts elegibles por caso; muestran mediana de vistas y retención ponderada por
  vistas interesadas. Sirven para aprender de los ángulos y no para forzar una rotación entre formatos. El resultado de
  un Short no se presenta como prueba de retención del episodio ni como conversión medida entre ambos.
- **Límites del diagnóstico**: sin impresiones, CTR o tasa de deslizamiento no se atribuyen pocas vistas al título o
  miniatura. `engagedViews / views` tampoco equivale a la tasa de personas que decidieron ver frente a deslizar.
- El selector de temas prioriza casos con **un detalle tangible e inquietante** (un código, una última nota, un objeto, un
  lugar vacío), y los títulos de episodio giran en torno a ese detalle (máximo 60 caracteres, sin el patrón "Caso: subtítulo").

Las subidas se reintentan desde cero hasta 3 veces si YouTube corta la sesión resumible (410/5xx), para no dejar vídeos
vacíos en el canal. `publish.py` avisa (`::warning::`) de los vídeos que siguen sin procesar o que han fallado.

El [roadmap de mejora](ROADMAP.md) recoge las prioridades, las métricas de partida y los criterios para revisar el
siguiente lote de 3–4 publicaciones maduras.

### Seguimiento automático del despliegue

`Channel Report` genera un informe diario a las 11:17 UTC y permite ejecución manual desde Actions. Solo consulta
YouTube: no genera contenido, no gasta créditos de IA ni cambia vídeos. Guarda `build/channel_report.json` como
artefacto y un resumen en la ejecución, con periodos de 28 y 90 días, corte disponible, muestras y formatos separados.
Consulta también la curva de retención de los largos a los 30 y 60 segundos cuando hay datos.

`reporting` identifica el lote de mejora iniciado el 21 de octubre de 2026. Los vídeos generados desde este despliegue
guardan `pipeline_revision` en el historial; los ya programados y los guiones reutilizados no se etiquetan
retroactivamente. La revisión del lote requiere la etiqueta coincidente, publicación desde `reporting.since` y
madurez y muestra suficientes; espera cuatro piezas por formato (`reporting.batch_size`) antes de cerrar el lote.
No mezcla el rendimiento de vídeos anteriores con el de las nuevas aperturas.

Las impresiones, CTR y tasa de deslizamiento siguen requiriendo revisión en Studio. El informe no inventa esos valores
ni atribuye conversiones entre Shorts y largos. Si aún no hay suficientes vídeos nuevos maduros, lo indica.

```bash
.venv/bin/python scripts/channel_report.py
.venv/bin/python scripts/channel_report.py --since 2026-10-21 --no-retention
```

## Políticas de YouTube a tener en cuenta

- `containsSyntheticMedia: true` va siempre activado (voz IA + reconstrucciones).
- Las imágenes IA tienen prohibido mostrar caras reconocibles de personas reales; las fotos reales salen de Commons y se acreditan
  en la descripción (CC BY / CC BY-SA lo exigen).
- El selector de temas evita casos con menores, violencia sexual o acusaciones a personas vivas no condenadas, y el guion no
  describe violencia explícita, para no caer en "contenido no apto para la mayoría de anunciantes".
- Conviene revisar los episodios y aportar evidencia, ángulos y narración distintos dentro de la serie, en lugar de
  publicar versiones casi idénticas o cambiar de formato por calendario. Mantener un micronicho no convierte el contenido
  repetitivo en original ni garantiza cumplir las políticas de monetización.

## Shorts del canal (2 al día)

`short.py` genera Shorts verticales con un objetivo de 40 s que promocionan los episodios ya publicados; `.github/workflows/shorts.yml`
los sube a las 13:17 y 18:17 UTC (GitHub los suele lanzar con 4-5 h de retraso).

- Elige el episodio con menos Shorts de los 5 últimos **de la serie activa** (uno recién publicado tiene prioridad).
  Antes de existir series etiquetadas conserva la selección anterior. Gemini escribe un teaser con un ángulo nuevo usando
  **solo los hechos del guion del episodio** (`episodes/<video_id>.json`, que `main.py` guarda al subir).
- Máximo `shorts.max_per_episode` (5) Shorts por caso, para no saturar con el mismo caso. Si todos los episodios
  recientes están completos, la ejecución no genera nada y espera al siguiente episodio.
- El título no puede parecerse a ninguno ya publicado en el canal (`shorts.title_similarity`, 0,75 con `difflib`): si se
  parece, se regenera.
- Estructura: 75-90 palabras en 12-14 beats, gancho de máximo 8 palabras, una sola pista o contradicción y un pequeño
  desenlace que entrega el detalle del título antes del CTA "Watch the full investigation, linked right here.", con flecha
  animada y una última frase que enlaza con el gancho. El misterio general puede quedar abierto, pero no se oculta la
  respuesta prometida para forzar un clic. Los límites incluyen CTA y bucle y se comprueban antes de sintetizar la voz.
- Tras sintetizar, se comprueba la duración real: si supera 45 s, se detiene antes de generar imágenes o publicar.
  No se recorta el audio ni se acelera la voz; hay que acortar el guion y volver a ejecutar.
- Cortes de máximo 2,4 s con Ken Burns, etalonaje frío desaturado, subtítulos de 1-2 palabras (palabras clave en amarillo/rojo),
  música de tensión de `music/shorts/`, drone sub-bass y efectos de `sfx/` (golpes de graves, whoosh, riser, tape stop;
  si la carpeta no existe se sintetizan con ffmpeg).
- Sin imágenes de Wikimedia ni stock (`shorts.visuals.archive: false`, `plan_stock: false`): todos los planos son
  reconstrucciones de Magnific con continuidad entre ellas.
- Coste por Short: ~400 créditos de ElevenLabs y hasta 12 imágenes de Magnific (`shorts.visuals.max_ai_images`); a
  partir del tope se reutilizan las anclas (ver *Plan visual y continuidad*). Si se acaban los créditos, los planos de IA pasan solos a vídeo de stock. Si quedan menos de
  `shorts.reserve_credits` créditos, no se genera para no dejar sin voz a los episodios largos.
- Descripción del Short: resumen, enlace al episodio y hashtags; el enlace va también en un comentario. Pero en los Shorts esos enlaces no son clicables: el único
  enlace que funciona es el **"Vídeo relacionado"**, que no existe en la API de YouTube.
  `scripts/link_related_videos.py` lo pone automáticamente desde YouTube Studio con un Chrome sin ventana en GitHub Actions:
  lo ejecuta `publish.yml` antes de pasar nada a público, sobre los Shorts de los últimos 7 días (los ya enlazados se saltan).
  Si Studio no confirma el guardado, recarga la página para comprobar si se guardó y, si no, deja en el log el texto de
  cualquier diálogo visible. Un fallo de enlaces marca la ejecución como fallida al terminar, aunque se ejecuta la
  publicación de vídeos antiguos en oculto. Si aparece «Verifica que eres tú», se detiene el lote: no tiene sentido
  repetir el guardado en todos los Shorts sin resolver primero la verificación.
  - La sesión de Studio es la del secret `STUDIO_STATE` (cookies de Google/YouTube, gzip + base64). Tras cada ejecución
    se guarda renovada y cifrada (`STUDIO_STATE_KEY`, AES-256) en la caché de Actions, así que no depende de ningún equipo.
  - Si la sesión caduca, la ejecución falla pero la publicación de vídeos antiguos se intenta igualmente. Para renovarla: inicia sesión
    en un Chrome con perfil vacío y Unsolved Archives activo, exporta las cookies de google.com/youtube.com con Playwright
    (`storage_state`) y súbelas con `gzip -9c state.json | base64 -w0 | gh secret set STUDIO_STATE`; borra la caché
    `studio-state-*` en Actions → Caches.
  - Una verificación adicional de Google requiere intervención del propietario. Renovar cookies no garantiza que
    desaparezca ese desafío en un runner distinto. No se intenta eludirlo.
  - Para recuperar pendientes antiguos, el workflow manual `Publish` acepta `days` (por defecto 7, siempre positivo).
    La ejecución con `dry_run` no accede a Studio ni renueva su sesión.
    En local: `.venv/bin/python scripts/link_related_videos.py --profile /ruta/al/perfil --remote --days 30`.
  - Requiere las funciones avanzadas del canal activadas (verificación ya hecha).

```bash
.venv/bin/python short.py --no-upload                     # genera build/short.mp4 sin subirlo
.venv/bin/python short.py --episode <video_id>            # fuerza el episodio a promocionar
.venv/bin/python short.py --script build/short_script.json --no-upload  # re-render sin gastar créditos (caché)
```

### Facebook, Instagram y TikTok (opcional)

Cada Short se publica también en las redes cuyos secrets existan (cuentas propias del canal, separadas de las de
yt-autoshorts). Si una plataforma falla, el resto sigue igual. El pie incluye el enlace al episodio de YouTube.

- **Facebook Reels**: `FB_PAGE_ID` y `FB_PAGE_TOKEN`. Crea la página, una app de Meta de tipo *Empresa*, genera en
  *Graph API Explorer* un *User Token* con `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
  `publish_video`, `instagram_basic` e `instagram_content_publish`, y ejecuta `scripts/get_fb_token.py`.
- **Instagram Reels**: `IG_USER_ID` (lo añade `get_fb_token.py` si la página tiene vinculada una cuenta profesional de
  Instagram). Usa el mismo token de página.
- **TikTok**: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` y `TIKTOK_REFRESH_TOKEN` (app con *Login Kit* y *Content
  Posting API*, scope `video.publish`; ejecuta `scripts/get_tiktok_token.py`). Hasta que TikTok audite la app, los
  vídeos se publican como privados.

```bash
gh secret set -f .fb.env && gh secret set -f .tiktok.env
```
