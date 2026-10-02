# yt-mysteries

Canal **long-form en inglés** (12-14 min) de misterios históricos y casos sin resolver, generado íntegramente con IA.
Hermano de `yt-autoshorts`, reutiliza la misma idea de pipeline:

**Gemini** (tema → investigación → guion por capítulos) → **ElevenLabs** (voz con tiempos por carácter) →
**Wikimedia Commons** (imágenes reales de archivo, con licencia libre) + **Pexels** (b-roll) + **Magnific** (reconstrucciones IA
y miniatura) → **ffmpeg** (1920x1080, Ken Burns, rótulos de capítulo, etalonaje, música con ducking) →
**YouTube Data API** (vídeo + miniatura + subtítulos SRT + capítulos en la descripción) → **GitHub Actions** (L/X/V 15:00 UTC).

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
5. Música: `ELEVENLABS_API_KEY=... .venv/bin/python scripts/generate_music.py` genera 4 fondos dark-ambient de 3 min en
   `music/` (o añade pistas de la Biblioteca de audio de YouTube sin atribución). Haz commit de `music/`.

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

## Políticas de YouTube a tener en cuenta

- `containsSyntheticMedia: true` va siempre activado (voz IA + reconstrucciones).
- Las imágenes IA tienen prohibido mostrar caras reconocibles de personas reales; las fotos reales salen de Commons y se acreditan
  en la descripción (CC BY / CC BY-SA lo exigen).
- El selector de temas evita casos con menores, violencia sexual o acusaciones a personas vivas no condenadas, y el guion no
  describe violencia explícita, para no caer en "contenido no apto para la mayoría de anunciantes".
- Para no ser marcado como contenido "producido en masa", conviene revisar los primeros episodios y variar formatos (`FORMATS` en
  `longform/script.py`); con 3 o más vídeos con datos, el pipeline aprende de las analíticas del canal.
