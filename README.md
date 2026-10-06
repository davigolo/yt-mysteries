# yt-mysteries

Canal **long-form en inglés** (12-14 min) de misterios históricos y casos sin resolver, generado íntegramente con IA.
Hermano de `yt-autoshorts`, reutiliza la misma idea de pipeline:

**Gemini** (tema → investigación → guion por capítulos) → **ElevenLabs** (voz con tiempos por carácter) →
**Wikimedia Commons** (imágenes reales de archivo, con licencia libre) + **Pexels** (b-roll) + **Magnific** (reconstrucciones IA
y miniatura) → **ffmpeg** (1920x1080, Ken Burns, rótulos de capítulo, etalonaje, música con ducking) →
**YouTube Data API** (vídeo + miniatura + subtítulos SRT + capítulos en la descripción) → **GitHub Actions** (L/X/V 15:37 UTC).

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
| ElevenLabs | ~11.500 caracteres con `eleven_flash_v2_5` (0,5 créditos/carácter) = ~5.800 créditos. 3 vídeos/semana = ~75k/mes: cabe en **Creator** (121k). Con `eleven_multilingual_v2` (1 crédito/carácter) haría falta Pro |
| Magnific API | ~35-40 imágenes Flux 2 Turbo + 1 Mystic 2k (~2.000 créditos estimados; ~27k/mes, cabe en Premium+). **La API consume créditos aunque tu plan tenga uso "ilimitado" en la web** |
| Gemini | Capa gratuita. La búsqueda web (grounding) puede no tener cuota gratis; en ese caso investiga sin búsqueda y lo avisa en el log |
| Pexels / Wikimedia | 0 € |
| GitHub Actions | ~40-70 min por episodio; mejor repo público o tendrás que vigilar los 2.000 min/mes |

Ajusta `visuals.max_ai_images` para limitar el gasto en Magnific. `visuals.upscale_archive_below` (p. ej. `900`) y `max_upscales`
activan el upscaler de Magnific para las fotos de archivo de baja resolución.

## Publicación en oculto y paso a público

Episodios y Shorts se suben en **oculto** (`upload.privacy: "unlisted"`) para que YouTube los analice antes de enseñarlos,
y `.github/workflows/publish.yml` los pasa a **público al día siguiente**, en la misma franja en que se subieron
(13:17, 15:37, 18:17 y 23:17 UTC). `publish.py` publica los vídeos de `history.json` y `shorts_history.json` que llevan
al menos `publish.after_hours` (22 h) en oculto y ya están procesados. Un Short nunca se publica antes que su episodio:
si el episodio sigue oculto, espera a la siguiente ejecución. Como máximo `publish.max_per_run` vídeos por franja (si uno
lleva más de 44 h, se publica igualmente). No guarda estado: si una ejecución falla, los publica la siguiente. Los cron no
están en punto porque GitHub retrasa hasta 3 h los de `:00`.

- Ajusta los cron de `publish.yml` a las horas en que tu audiencia está conectada (Studio → Analytics → Audience →
  *When your viewers are on YouTube*).
- Para que un vídeo no se publique, pásalo a **privado** en Studio: solo se tocan los que siguen en oculto.
- `.venv/bin/python publish.py --dry-run` muestra qué se publicaría sin cambiar nada.
- Facebook, Instagram y TikTok se siguen publicando al momento (allí no existe el oculto).

Además, en cada subida: contenido sintético declarado, "no es para niños", contador de "me gusta" visible, máximo 5
hashtags (los del caso primero) y listas de reproducción (`playlists` en `config.yaml`, se crean públicas si no existen):
cada episodio va a la lista general y a la de su formato, y cada Short a *Mystery Shorts*. Mientras el vídeo está en
oculto conviene añadir a mano en Studio lo que la API no permite: **pantalla final** (suscribirse + "Mejor para el
espectador" o el episodio relacionado) y **tarjetas** a otros episodios. El vídeo relacionado de cada Short se pone solo
(ver más abajo).

## Políticas de YouTube a tener en cuenta

- `containsSyntheticMedia: true` va siempre activado (voz IA + reconstrucciones).
- Las imágenes IA tienen prohibido mostrar caras reconocibles de personas reales; las fotos reales salen de Commons y se acreditan
  en la descripción (CC BY / CC BY-SA lo exigen).
- El selector de temas evita casos con menores, violencia sexual o acusaciones a personas vivas no condenadas, y el guion no
  describe violencia explícita, para no caer en "contenido no apto para la mayoría de anunciantes".
- Para no ser marcado como contenido "producido en masa", conviene revisar los primeros episodios y variar formatos (`FORMATS` en
  `longform/script.py`); con 3 o más vídeos con datos, el pipeline aprende de las analíticas del canal.

## Shorts del canal (3 al día)

`short.py` genera Shorts verticales (~50 s) que promocionan los episodios ya publicados; `.github/workflows/shorts.yml`
los sube a las 13:17, 18:17 y 23:17 UTC (mañana, mediodía y tarde en EE. UU.).

- Elige el episodio con menos Shorts de los 5 últimos (uno recién publicado tiene prioridad) y Gemini escribe un teaser
  con un ángulo nuevo usando **solo los hechos del guion del episodio** (`episodes/<video_id>.json`, que `main.py` guarda al subir).
- Estructura: gancho de máximo 8 palabras, desarrollo rápido, punto de inflexión, CTA "Watch the full investigation, linked right here."
  con flecha animada y una última frase que enlaza con el gancho para que el vídeo haga bucle.
- Cortes de máximo 2,4 s con Ken Burns, etalonaje frío desaturado, subtítulos de 1-2 palabras (palabras clave en amarillo/rojo),
  música de tensión de `music/shorts/`, drone sub-bass y efectos de `sfx/` (golpes de graves, whoosh, riser, tape stop;
  si la carpeta no existe se sintetizan con ffmpeg).
- Coste por Short: ~400 créditos de ElevenLabs y hasta 4 imágenes de Magnific (`shorts.visuals.max_ai_images`). Si quedan menos de
  `shorts.reserve_credits` créditos, no se genera para no dejar sin voz a los episodios largos.
- Descripción del Short: resumen, enlace al episodio y hashtags; el enlace va también en un comentario. Pero en los Shorts esos enlaces no son clicables: el único
  enlace que funciona es el **"Vídeo relacionado"**, que no existe en la API de YouTube.
  `scripts/link_related_videos.py` lo pone automáticamente desde YouTube Studio con un Chrome sin ventana en GitHub Actions:
  lo ejecuta `publish.yml` antes de pasar nada a público, sobre los Shorts de los últimos 3 días (los ya enlazados se saltan).
  - La sesión de Studio es la del secret `STUDIO_STATE` (cookies de Google/YouTube, gzip + base64). Tras cada ejecución
    se guarda renovada y cifrada (`STUDIO_STATE_KEY`, AES-256) en la caché de Actions, así que no depende de ningún equipo.
  - Si la sesión caduca, el paso falla (GitHub te avisa por email) pero la publicación sigue. Para renovarla: inicia sesión
    en un Chrome con perfil vacío y Unsolved Archives activo, exporta las cookies de google.com/youtube.com con Playwright
    (`storage_state`) y súbelas con `gzip -9c state.json | base64 -w0 | gh secret set STUDIO_STATE`; borra la caché
    `studio-state-*` en Actions → Caches.
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
