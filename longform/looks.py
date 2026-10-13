MOODS = {
    "dread": "eq=contrast=1.14:brightness=-0.03:saturation=0.7,colorbalance=rs=-0.04:bs=0.09:bm=0.05",
    "mystery": "eq=saturation=0.8,colorbalance=rs=-0.03:gs=0.03:bs=0.06:gm=0.03:bm=0.03",
    "eerie": "eq=contrast=1.08:saturation=0.65,colorbalance=rs=-0.04:gs=0.07:gm=0.05:bh=-0.03",
    "memory": "eq=saturation=0.5:contrast=0.96,colorbalance=rs=0.09:gs=0.04:bs=-0.08:rm=0.07:bm=-0.06:rh=0.04",
    "revelation": "hue=s=0.2,eq=contrast=1.3:brightness=-0.02",
    "investigation": "eq=saturation=0.78:contrast=1.05,colorbalance=bs=0.03",
    "grief": "eq=saturation=0.55:brightness=-0.02:contrast=0.98,colorbalance=bs=0.05:bm=0.03",
}
MOOD_GUIDE = (
    "dread (threat, death, danger: cold and dark), mystery (unknown, clues: teal), eerie (supernatural, wrongness: "
    "sickly green), memory (the past, archives, life before the event: warm faded sepia), revelation (shocking fact, "
    "twist: harsh near black and white), investigation (police, documents, procedure: neutral), grief (loss, victims, "
    "aftermath: muted blue)"
)


def mood_filter(mood: str) -> str:
    return f",{MOODS[mood]}" if mood in MOODS else ""


def film_look(width: int, height: int, grain: int) -> str:
    return (
        "unsharp=5:5:-0.35:5:5:0,format=gbrp,split[base][glow_src];"
        f"[glow_src]curves=all='0/0 0.62/0 1/1',scale={width // 4}:{height // 4},gblur=sigma=6,scale={width}:{height}[glow];"
        "[base][glow]blend=all_mode=screen:all_opacity=0.22,"
        "rgbashift=rh=-2:bh=2,"
        "curves=all='0/0.035 1/0.97',format=yuv420p,"
        f"noise=alls={grain}:allf=t+u,"
        "eq=brightness='0.012*sin(2*PI*t*6)+0.006*sin(2*PI*t*17)':eval=frame"
    )
