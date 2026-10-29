#!/usr/bin/env python3
"""
Builds the animated SVG panels used by the README (.github/readme/*.svg).
Run from the repo root:  python3 .github/readme/build.py
Standard library only.
"""

import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- Sakhi palette: Meesho jamuni plum, mango, thread pink, rivet teal ---
BG = "#1B0A19"      # plum surface
DEEP = "#11050F"    # deepest plum
HERO = "#3B0F36"    # hero light centre
GLOW = "#9F2089"    # Meesho jamuni
MDEEP = "#4A1445"   # muted plum (fills)
ACC = "#E27BD0"     # orchid accent (labels, strokes)
LIGHT = "#F7C9EE"   # blush highlight
TEXT = "#FCF2F9"    # warm white
MUTE = "#C2A9BC"    # secondary text
CHIP = "#2B0F28"    # chip / tile fill
MANGO = "#FC8B16"   # Meesho aam
MANGO_L = "#FFBE76"
PINK = "#F43397"    # stitched thread
TEAL = "#42BC9E"    # success rivet

SERIF = 'Georgia, "Iowan Old Style", "Palatino Linotype", "Times New Roman", serif'
MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'


def fonts(p):
    return (f"    .{p}-serif {{ font-family: {SERIF}; }}\n"
            f"    .{p}-mono {{ font-family: {MONO}; }}\n"
            f"    .{p}-sans {{ font-family: {SANS}; }}")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write(name, svg):
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg.strip() + "\n")
    print(f"wrote .github/readme/{name} ({os.path.getsize(path):,} bytes)")


def frame(w, h, p):
    """Panel background, plum glow and the stitched inner border the app uses on Sakhi's bubbles."""
    return f"""  <rect width="{w}" height="{h}" rx="20" fill="url(#{p}-bg)"/>
  <rect width="{w}" height="{h}" rx="20" fill="url(#{p}-glow)"/>
  <rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="19.5" fill="none" stroke="{ACC}" stroke-opacity=".2"/>
  <rect x="10" y="10" width="{w - 20}" height="{h - 20}" rx="13" fill="none" stroke="{PINK}" stroke-opacity=".22" stroke-dasharray="5 6"/>"""


def defs(p, glow_at="80% 15%", strength=".55"):
    cx, cy = glow_at.split()
    return f"""    <linearGradient id="{p}-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG}"/><stop offset="1" stop-color="{DEEP}"/></linearGradient>
    <radialGradient id="{p}-glow" cx="{cx}" cy="{cy}" r="70%"><stop offset="0" stop-color="{GLOW}" stop-opacity="{strength}"/><stop offset="1" stop-color="{MDEEP}" stop-opacity="0"/></radialGradient>
    <filter id="{p}-glowf" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>"""


def svg_open(w, h, p, title, desc=""):
    d = f'\n  <desc id="{p}-d">{esc(desc)}</desc>' if desc else ""
    lab = f"{p}-t {p}-d" if desc else f"{p}-t"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="{lab}">
  <title id="{p}-t">{esc(title)}</title>{d}"""


REDUCED = "@media (prefers-reduced-motion: reduce) {{ {sel} {{ animation: none !important; }} }}"


# ---- Hero ---------------------------------------------------------------
def hero():
    p = "hero"
    W, H = 1200, 480
    cx, cy = 905, 200
    agents = [("Catalog", 745, 92), ("Customer", 1062, 92), ("Growth", 1075, 300), ("Returns", 735, 300)]
    wires, nodes, dots = [], [], []
    for k, (name, x, y) in enumerate(agents):
        path = f"M{cx} {cy} Q {(cx + x) / 2 + (30 if x > cx else -30)} {(cy + y) / 2 - 30} {x} {y}"
        wires.append(f'<path d="{path}" fill="none" stroke="{ACC}" stroke-opacity=".35" stroke-dasharray="3 5"/>')
        w = len(name) * 8.4 + 34
        nodes.append(f"""<g transform="translate({x - w / 2:.0f} {y - 17})">
        <rect width="{w:.0f}" height="34" rx="17" fill="{CHIP}" stroke="{ACC}" stroke-opacity=".45">
          <animate attributeName="stroke-opacity" values=".45;1;.45;.45" keyTimes="0;.06;.2;1" dur="8s" begin="{1.6 + k * 2:.1f}s" repeatCount="indefinite"/>
          <animate attributeName="fill" values="{CHIP};{MDEEP};{CHIP};{CHIP}" keyTimes="0;.06;.2;1" dur="8s" begin="{1.6 + k * 2:.1f}s" repeatCount="indefinite"/>
        </rect>
        <text class="{p}-mono" x="{w / 2:.0f}" y="21.5" font-size="11.5" text-anchor="middle" fill="{TEXT}">{name}</text>
      </g>""")
        dots.append(f"""<circle r="3.5" fill="{MANGO_L}" filter="url(#{p}-glowf)" opacity="0">
        <animateMotion path="{path}" dur="8s" begin="{1 + k * 2:.1f}s" repeatCount="indefinite" keyPoints="0;1;1" keyTimes="0;.08;1" calcMode="linear"/>
        <animate attributeName="opacity" values="0;1;0;0" keyTimes="0;.02;.09;1" dur="8s" begin="{1 + k * 2:.1f}s" repeatCount="indefinite"/>
      </circle>""")
    bars = "".join(
        f'<rect class="{p}-bar" style="animation-delay:{-k * .11:.2f}s;animation-duration:{.6 + (k * 37 % 5) * .1:.2f}s" x="{-28 + k * 6.2:.1f}" y="{-h / 2}" width="3" height="{h}" rx="1.5" fill="{TEXT}"/>'
        for k, h in enumerate([10, 18, 28, 16, 34, 22, 12, 26, 14, 8]))
    rings = "".join(
        f'<circle class="{p}-ring" style="animation-delay:{k * 1.2:.1f}s" r="62" fill="none" stroke="{LIGHT}" stroke-opacity=".5"/>'
        for k in range(3))
    chip_names = ["LangGraph", "FastAPI", "Gemini", "Sarvam ASR · TTS", "pgvector"]
    chips, x = [], 72
    for k, c in enumerate(chip_names):
        w = len(c) * 7 + 24
        chips.append(f'<g class="{p}-rise" style="animation-delay:{1.3 + k * .08:.2f}s"><rect x="{x}" y="356" width="{w}" height="28" rx="14" fill="{CHIP}" stroke="{ACC}" stroke-opacity=".4"/>'
                     f'<text class="{p}-mono" x="{x + w / 2:g}" y="374.5" font-size="11.5" text-anchor="middle" fill="{LIGHT}">{esc(c)}</text></g>')
        x += w + 8

    return f"""{svg_open(W, H, p, "Sakhi — the AI business didi for every Meesho reseller",
                     "Sakhi is a voice-first, Hindi-first agentic AI co-pilot. Four specialist agents (Catalog, Customer, Growth and Returns), routed by a LangGraph orchestrator, run a reseller's business. Meesho ScriptedBy Her 2.0, Top 50 of 36,000+.")}
  <defs>
{defs(p, "78% 40%", ".7")}
    <radialGradient id="{p}-orb" cx="40%" cy="35%" r="70%"><stop offset="0" stop-color="#D24BBE"/><stop offset=".6" stop-color="{GLOW}"/><stop offset="1" stop-color="#5A1252"/></radialGradient>
    <radialGradient id="{p}-mango" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{MANGO}" stop-opacity=".22"/><stop offset="1" stop-color="{MANGO}" stop-opacity="0"/></radialGradient>
    <linearGradient id="{p}-name" gradientUnits="userSpaceOnUse" x1="60" y1="0" x2="330" y2="0"><stop offset="0" stop-color="{TEXT}"/><stop offset="1" stop-color="{LIGHT}"/></linearGradient>
    <linearGradient id="{p}-sheen" gradientUnits="userSpaceOnUse" x1="-240" y1="0" x2="-40" y2="0">
      <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".8"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
      <animateTransform attributeName="gradientTransform" type="translate" values="0 0;640 0;640 0" keyTimes="0;.3;1" dur="9s" begin="2.5s" repeatCount="indefinite"/>
    </linearGradient>
    <pattern id="{p}-dots" width="26" height="26" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.1" fill="{ACC}" fill-opacity=".14"/></pattern>
    <radialGradient id="{p}-fade" cx="75%" cy="45%" r="55%"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>
    <mask id="{p}-mask"><rect width="{W}" height="{H}" fill="url(#{p}-fade)"/></mask>
    <clipPath id="{p}-clip"><rect width="{W}" height="{H}" rx="20"/></clipPath>
  </defs>
  <style>
{fonts(p)}
    .{p}-rise {{ animation: {p}-rise 1.3s cubic-bezier(.16,1,.3,1) both; }}
    .{p}-fade {{ animation: {p}-fade 1.6s ease both; }}
    .{p}-ring {{ transform-origin: 0 0; animation: {p}-ring 3.6s cubic-bezier(.2,.6,.3,1) infinite; }}
    .{p}-bar {{ transform-box: fill-box; transform-origin: center; animation: {p}-bar 1s ease-in-out infinite alternate; }}
    .{p}-draw {{ stroke-dasharray: 700; stroke-dashoffset: 700; animation: {p}-draw 2.2s cubic-bezier(.65,0,.35,1) 1s forwards; }}
    @keyframes {p}-rise {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes {p}-fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
    @keyframes {p}-ring {{ from {{ transform: scale(1); opacity: .9; }} to {{ transform: scale(2.3); opacity: 0; }} }}
    @keyframes {p}-bar {{ from {{ transform: scaleY(.3); }} to {{ transform: scaleY(1); }} }}
    @keyframes {p}-draw {{ to {{ stroke-dashoffset: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .{p}-rise, .{p}-fade, .{p}-ring, .{p}-bar {{ animation: none; }} .{p}-draw {{ animation: none; stroke-dashoffset: 0; }} }}
  </style>
  <g clip-path="url(#{p}-clip)">
{frame(W, H, p)}
    <rect width="{W}" height="{H}" fill="url(#{p}-dots)" mask="url(#{p}-mask)"/>
    <ellipse cx="160" cy="470" rx="380" ry="200" fill="url(#{p}-mango)"/>

    <!-- Copy -->
    <g class="{p}-rise" style="animation-delay:.1s">
      <line x1="72" y1="78" x2="102" y2="78" stroke="{MANGO}"/>
      <text class="{p}-mono" x="114" y="82" font-size="12" letter-spacing="3" fill="{MANGO_L}">MEESHO SCRIPTEDBY{{HER}} 2.0 · TOP 50 OF 36,000+</text>
    </g>
    <g class="{p}-rise" style="animation-delay:.3s">
      <text class="{p}-serif" x="66" y="190" font-size="112" font-weight="300" letter-spacing="-3" fill="url(#{p}-name)">Sakhi</text>
      <text class="{p}-serif" x="66" y="190" font-size="112" font-weight="300" letter-spacing="-3" fill="url(#{p}-sheen)">Sakhi</text>
      <text class="{p}-sans" x="378" y="186" font-size="46" font-weight="300" fill="{MANGO}">सखी</text>
    </g>
    <path class="{p}-draw" d="M72 214 C 200 208, 380 220, 560 210" fill="none" stroke="{PINK}" stroke-width="1.6" stroke-dasharray="6 6" stroke-opacity=".8"/>
    <g class="{p}-rise" style="animation-delay:.55s">
      <text class="{p}-serif" x="72" y="262" font-size="26" font-style="italic" fill="{TEXT}">The AI business didi for every Meesho reseller.</text>
    </g>
    <g class="{p}-rise" style="animation-delay:.8s">
      <text class="{p}-sans" x="72" y="300" font-size="16" fill="{MUTE}">She speaks in Hindi. Four agents list her products, answer her buyers,</text>
      <text class="{p}-sans" x="72" y="324" font-size="16" fill="{MUTE}">coach her growth and save her returns, all grounded in real data.</text>
    </g>
    {"".join(chips)}

    <!-- Voice orb and the four agents it routes to -->
    <g class="{p}-fade" style="animation-delay:.6s">
      {"".join(wires)}
      {"".join(dots)}
      <g transform="translate({cx} {cy})">
        {rings}
        <circle r="62" fill="url(#{p}-orb)" stroke="{LIGHT}" stroke-opacity=".6"/>
        <circle r="62" fill="none" stroke="{PINK}" stroke-opacity=".7" stroke-dasharray="4 5" transform="scale(1.12)"/>
        {bars}
      </g>
      {"".join(nodes)}
      <text class="{p}-mono" x="{cx}" y="{cy + 98}" font-size="10" letter-spacing="2.2" text-anchor="middle" fill="{MUTE}">LANGGRAPH ORCHESTRATOR</text>
    </g>

    <!-- Hindi voice bubble -->
    <g class="{p}-rise" style="animation-delay:1.4s">
      <rect x="690" y="348" width="430" height="46" rx="16" fill="{TEXT}" fill-opacity=".06" stroke="{PINK}" stroke-opacity=".55" stroke-dasharray="5 4"/>
      <text class="{p}-sans" x="712" y="377" font-size="16" fill="{TEXT}">“मेरी नई साड़ी लिस्ट कर दो”</text>
      <text class="{p}-mono" x="1100" y="376" font-size="10" letter-spacing="1.6" text-anchor="end" fill="{MANGO_L}">VOICE · HI</text>
    </g>

    <!-- Meta strip -->
    <g class="{p}-fade" style="animation-delay:1.6s">
      <line x1="72" y1="428" x2="1128" y2="428" stroke="{ACC}" stroke-opacity=".18"/>
      <text class="{p}-mono" x="72" y="452" font-size="10.5" letter-spacing="2" fill="{MUTE}">VOICE-FIRST · VERNACULAR-FIRST · GROUNDED IN HER REAL CATALOG</text>
      <text class="{p}-mono" x="1128" y="452" font-size="10.5" letter-spacing="2" text-anchor="end" fill="{LIGHT}">LIVE · MEESHO-SAKHI-KOMAL25.VERCEL.APP</text>
    </g>
  </g>
</svg>"""


# ---- Section titles -----------------------------------------------------
def title(num, label, lead, italic, right):
    """Section heading on its own plum card, so it reads on GitHub's light and dark themes alike."""
    p = f"t{num}"
    W, H = 1200, 136
    return f"""{svg_open(W, H, p, f"{num} {label.title()}: {lead}{italic}")}
  <defs>
{defs(p, "10% 0%", ".5")}
    <linearGradient id="{p}-line" gradientUnits="userSpaceOnUse" x1="56" y1="0" x2="1144" y2="0"><stop offset="0" stop-color="{MANGO}"/><stop offset=".45" stop-color="{GLOW}"/><stop offset="1" stop-color="{GLOW}" stop-opacity="0"/></linearGradient>
  </defs>
  <style>
{fonts(p)}
    .{p}-draw {{ stroke-dasharray: 1200; stroke-dashoffset: 1200; animation: {p}-draw 1.8s cubic-bezier(.65,0,.35,1) .3s forwards; }}
    @keyframes {p}-draw {{ to {{ stroke-dashoffset: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .{p}-draw {{ animation: none; stroke-dashoffset: 0; }} }}
  </style>
{frame(W, H, p)}
  <text class="{p}-mono" x="56" y="46" font-size="12" letter-spacing="3" fill="{ACC}"><tspan fill="{MANGO_L}">{num}</tspan>   {esc(label)}</text>
  <text class="{p}-mono" x="1144" y="46" text-anchor="end" font-size="10.5" letter-spacing="2.4" fill="{MUTE}">{esc(right)}</text>
  <text class="{p}-serif" x="54" y="94" font-size="40" font-weight="300" letter-spacing="-1" fill="{TEXT}">{esc(lead)}<tspan font-style="italic" fill="{LIGHT}">{esc(italic)}</tspan></text>
  <path class="{p}-draw" d="M56 112 H1144" stroke="url(#{p}-line)" stroke-width="1"/>
</svg>"""


TITLES = [
    ("01", "PRODUCT", "Live, ", "not a recording.", "THE LAUNCH FILM · 1:32"),
    ("02", "HOW IT THINKS", "One message, ", "end to end.", "LANGGRAPH · 12 NODES"),
    ("03", "THE AGENTS", "Four specialists, ", "one didi.", "CATALOG · CUSTOMER · GROWTH · RETURNS"),
    ("04", "GUARDRAILS", "Grounded, gated, ", "resilient.", "BUILT FOR TRUST"),
]


# ---- Launch film preview ----------------------------------------------
def video_frames(video, times, width=1104):
    """Pull stills from the committed launch film with ffmpeg (needs ffmpeg on PATH)."""
    import subprocess
    import tempfile
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            jpg = os.path.join(tmp, f"{i}.jpg")
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(t), "-i", video,
                            "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "5", jpg], check=True)
            with open(jpg, "rb") as f:
                out.append(base64.b64encode(f.read()).decode())
    return out


def crossfade(i, n, slot, fade):
    """Opacity keyframes that hand frame i over to frame i+1, looping back to frame 0."""
    T = n * slot
    k = lambda t: f"{t / T:.4f}"
    if i == 0:
        return f'values="1;1;0;0;1;1" keyTimes="0;{k(slot + fade)};{k(slot + fade + .01)};{k(T - fade - .01)};{k(T - fade)};1"'
    a, b = i * slot, i * slot + fade
    if i == n - 1:
        return f'values="0;0;1;1;0" keyTimes="0;{k(a)};{k(b)};{k(T - fade)};1"'
    c = (i + 1) * slot + fade
    return f'values="0;0;1;1;0;0" keyTimes="0;{k(a)};{k(b)};{k(c)};{k(c + .01)};1"'


def film():
    p = "film"
    times = [4, 16, 20, 40, 52, 56, 76, 80, 88]
    frames = video_frames(os.path.join(HERE, "sakhi-launch.mp4"), times)
    n, SLOT, FADE = len(frames), 2.6, .7
    T = n * SLOT
    W, iw, ih = 1200, 1104, 622
    x0, y0 = 48, 48
    H = y0 + ih + 48
    imgs = "\n".join(
        f'      <image href="data:image/jpeg;base64,{b}" x="{x0}" y="{y0}" width="{iw}" height="{ih}" preserveAspectRatio="xMidYMid slice" opacity="{1 if i == 0 else 0}">'
        f'<animate attributeName="opacity" {crossfade(i, n, SLOT, FADE)} dur="{T:.1f}s" repeatCount="indefinite"/></image>'
        for i, b in enumerate(frames))
    cx, cy = W / 2, y0 + ih / 2
    return f"""{svg_open(W, H, p, "Sakhi launch film, 1 minute 32 seconds. Click to play.",
                     "A preview of the Sakhi launch film: Sunita's whole business on one phone, Sakhi the AI business didi, four specialist agents, the live app drafting a WhatsApp-ready listing, 12 LangGraph nodes, 3 approval gates, 5 Gemini models, and Top 50 of 36,000+.")}
  <defs>
{defs(p, "50% 0%", ".6")}
    <clipPath id="{p}-win"><rect x="{x0}" y="{y0}" width="{iw}" height="{ih}" rx="16"/></clipPath>
    <linearGradient id="{p}-shade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{DEEP}" stop-opacity=".9"/><stop offset=".3" stop-color="{DEEP}" stop-opacity="0"/><stop offset=".9" stop-color="{DEEP}" stop-opacity="0"/><stop offset="1" stop-color="{DEEP}" stop-opacity=".75"/></linearGradient>
  </defs>
  <style>
{fonts(p)}
    .{p}-ring {{ transform-origin: {cx}px {cy}px; animation: {p}-ring 2.4s cubic-bezier(.2,.6,.3,1) infinite; }}
    @keyframes {p}-ring {{ from {{ transform: scale(1); opacity: .9; }} to {{ transform: scale(1.9); opacity: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .{p}-ring {{ animation: none; opacity: 0; }} }}
  </style>
{frame(W, H, p)}
  <g clip-path="url(#{p}-win)">
{imgs}
    <rect x="{x0}" y="{y0}" width="{iw}" height="{ih}" fill="url(#{p}-shade)"/>
    <rect x="{x0 + 32}" y="{y0 + ih - 14}" width="{iw - 64}" height="3" rx="1.5" fill="{TEXT}" fill-opacity=".22"/>
    <rect x="{x0 + 32}" y="{y0 + ih - 14}" width="0" height="3" rx="1.5" fill="{MANGO}">
      <animate attributeName="width" values="0;{iw - 64}" dur="{T:.1f}s" repeatCount="indefinite"/>
    </rect>
  </g>
  <rect x="{x0 - .5}" y="{y0 - .5}" width="{iw + 1}" height="{ih + 1}" rx="16.5" fill="none" stroke="{ACC}" stroke-opacity=".5"/>
  <circle class="{p}-ring" cx="{cx}" cy="{cy}" r="46" fill="none" stroke="{MANGO_L}" stroke-width="2"/>
  <circle cx="{cx}" cy="{cy}" r="46" fill="{MANGO}"/>
  <path d="M{cx - 13} {cy - 19} L{cx + 21} {cy} L{cx - 13} {cy + 19} Z" fill="{DEEP}"/>
  <text class="{p}-serif" x="{x0 + 32}" y="{y0 + 58}" font-size="34" font-weight="300" fill="{TEXT}">Watch the launch film</text>
  <text class="{p}-mono" x="{x0 + 32}" y="{y0 + 86}" font-size="12" letter-spacing="2.4" fill="{MANGO_L}">1:32 · SOUND ON · CLICK TO PLAY</text>
  <text class="{p}-mono" x="{x0 + iw - 32}" y="{y0 + 86}" font-size="11" letter-spacing="2" text-anchor="end" fill="{MUTE}">PREVIEW</text>
</svg>"""


# ---- How one message flows ---------------------------------------------
def flow():
    p = "fl"
    W, H = 1200, 560
    DUR, BEGIN, SPEED = 8.6, 1.0, 280.0  # the travelling pulse covers the route at 280 px/s

    def pill(x, y, w, label, sub=None, tag=None, tag_col=None, t=None, mono=True, h=40):
        hl = ""
        if t is not None:
            b = BEGIN + t
            hl = (f'<animate attributeName="fill" values="{CHIP};{GLOW};{CHIP};{CHIP}" keyTimes="0;.03;.14;1" dur="{DUR}s" begin="{b:.2f}s" repeatCount="indefinite"/>'
                  f'<animate attributeName="stroke-opacity" values=".35;1;.35;.35" keyTimes="0;.03;.14;1" dur="{DUR}s" begin="{b:.2f}s" repeatCount="indefinite"/>')
        cls = f"{p}-mono" if mono else f"{p}-sans"
        out = (f'<g><rect x="{x}" y="{y - h / 2}" width="{w}" height="{h}" rx="10" fill="{CHIP}" stroke="{ACC}" stroke-opacity=".35">{hl}</rect>'
               f'<text class="{cls}" x="{x + 14}" y="{y + 4.5}" font-size="12" fill="{TEXT}">{esc(label)}</text>')
        if tag:
            tw = len(tag) * 6.6 + 14
            out += (f'<rect x="{x + w - tw - 8}" y="{y - 10}" width="{tw:.0f}" height="20" rx="10" fill="none" stroke="{tag_col}" stroke-opacity=".8"/>'
                    f'<text class="{p}-mono" x="{x + w - 8 - tw / 2:.0f}" y="{y + 4}" font-size="9.5" letter-spacing=".8" text-anchor="middle" fill="{tag_col}">{tag}</text>')
        if sub:
            out += f'<text class="{p}-mono" x="{x + w - 12}" y="{y + 4}" font-size="10" text-anchor="end" fill="{MUTE}">{esc(sub)}</text>'
        return out + "</g>"

    def colhead(x, n, word, note):
        return (f'<text class="{p}-mono" x="{x}" y="70" font-size="11" letter-spacing="2.4" fill="{MANGO_L}">{n} · {word}</text>'
                f'<text class="{p}-sans" x="{x}" y="90" font-size="12.5" fill="{MUTE}">{esc(note)}</text>')

    # Route: hear → think (down the gate rail) → act (catalog) → speak
    route = "M26 130 V350 H262 V130 H282 V410 H690 V130 H940 V290"
    cum = lambda px: px / SPEED
    rail = [("load_memory", None, None), ("check_pending_return", "HITL", MANGO_L), ("check_pending_approval", "HITL", MANGO_L),
            ("check_pending_selection", "HITL", MANGO_L), ("check_fresh_context_lock", "LOCK", TEAL), ("detect_intent", "GEMINI", LIGHT)]
    rail_svg = "".join(pill(290, 130 + i * 56, 380, n, tag=tg, tag_col=tc, t=cum(696 + i * 56)) for i, (n, tg, tc) in enumerate(rail))
    agents = [("Catalog agent", 1789), ("Customer agent", None), ("Growth agent", None), ("Returns funnel", None), ("General handler", None)]
    agent_svg = "".join(pill(710, 130 + i * 56, 210, n, t=(cum(t) if t else None), mono=False) for i, (n, t) in enumerate(agents))
    hear = [("Voice note", "WebM", 0), ("ffmpeg", "→ WAV", 160), ("Saarika v2.5", "ASR", 320)]
    hear_svg = "".join(pill(40, 130 + i * 80, 200, n, sub=s, t=cum(t)) for i, (n, s, t) in enumerate(hear))
    speak = [("assemble_reply", None, 1914), ("Bulbul v3 TTS", "priya", 1994), ("Voice reply", "HI", 2074)]
    speak_svg = "".join(pill(960, 130 + i * 80, 200, n, sub=s, t=cum(t)) for i, (n, s, t) in enumerate(speak))

    return f"""{svg_open(W, H, p, "How one message flows through Sakhi",
                     "A Hindi voice note is transcoded by ffmpeg and transcribed by Sarvam Saarika v2.5. The LangGraph orchestrator loads memory, passes three human-in-the-loop gates and a context lock, then classifies intent with Gemini structured output and routes to the Catalog, Customer or Growth agent, the Returns funnel or the general handler. The reply is assembled, spoken by Sarvam Bulbul v3 and every step streams to the Orchestrator's Brain over a WebSocket.")}
  <defs>
{defs(p, "50% 0%", ".45")}
  </defs>
  <style>
{fonts(p)}
    .{p}-draw {{ stroke-dasharray: 2000; stroke-dashoffset: 2000; animation: {p}-draw 3s cubic-bezier(.65,0,.35,1) .2s forwards; }}
    @keyframes {p}-draw {{ to {{ stroke-dashoffset: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .{p}-draw {{ animation: none; stroke-dashoffset: 0; }} .{p}-pulse {{ display: none; }} }}
  </style>
{frame(W, H, p)}
  {colhead(40, "01", "HEAR", "Hindi voice in")}
  {colhead(290, "02", "THINK", "LangGraph state machine")}
  {colhead(710, "03", "ACT", "route_decision")}
  {colhead(960, "04", "SPEAK", "Hindi voice out")}
  <rect x="276" y="98" width="408" height="340" rx="16" fill="none" stroke="{ACC}" stroke-opacity=".25"/>
  <path class="{p}-draw" d="{route}" fill="none" stroke="{ACC}" stroke-opacity=".45" stroke-width="1.4"/>
  {hear_svg}
  {rail_svg}
  {agent_svg}
  {speak_svg}
  <g class="{p}-mono" font-size="10.5" fill="{MUTE}">
    <text x="40" y="410">“मुझे पीली साड़ी दिखाओ”</text>
    <text x="40" y="430" font-size="9.5" letter-spacing="1.2">GEMINI MULTIMODAL IF ASR FAILS</text>
  </g>
  <g transform="translate(40 474)">
    <rect width="1120" height="50" rx="14" fill="{TEAL}" fill-opacity=".07" stroke="{TEAL}" stroke-opacity=".45" stroke-dasharray="5 5"/>
    <circle cx="26" cy="25" r="5" fill="{TEAL}"><animate attributeName="opacity" values="1;.3;1" dur="1.6s" repeatCount="indefinite"/></circle>
    <text class="{p}-mono" x="44" y="29.5" font-size="12" fill="{TEXT}">every node logs agent · action · latency_ms → <tspan fill="{TEAL}">/ws/agent-logs</tspan> → the Orchestrator's Brain panel, live</text>
  </g>
  <circle class="{p}-pulse" r="5" fill="{MANGO_L}" filter="url(#{p}-glowf)">
    <animateMotion path="{route}" dur="{DUR}s" begin="{BEGIN}s" repeatCount="indefinite" keyPoints="0;1;1" keyTimes="0;{2074 / SPEED / DUR:.4f};1" calcMode="linear"/>
  </circle>
</svg>"""


# ---- The four agents ----------------------------------------------------
ICONS = {
    "catalog": '<path d="M-11 -6 L0 -11 L11 -6 L11 7 L0 12 L-11 7 Z"/><path d="M-11 -6 L0 -1 L11 -6 M0 -1 V12" stroke-opacity=".8"/>',
    "customer": '<path d="M-12 -9 H12 V5 H-2 L-8 11 V5 H-12 Z"/><path d="M-6 -2 H6" stroke-opacity=".8"/>',
    "growth": '<path d="M-12 10 H12"/><path d="M-9 4 L-3 -2 L2 2 L10 -8"/><path d="M5 -8 H10 V-3"/>',
    "returns": '<path d="M-9 -3 A10 10 0 1 1 -6 7"/><path d="M-13 -9 L-9 -3 L-3 -6"/>',
}


def agents():
    p = "ag"
    W, H = 1200, 400
    cards = [
        ("catalog", "Catalog agent", "Lists a product in her words",
         ["Drafts a WhatsApp-ready listing", "with her real margin spelled", "out, then waits for her yes."], "HUMAN APPROVAL GATE"),
        ("customer", "Customer agent", "Answers buyers from the catalog",
         ["RAG over the pgvector catalog.", "Photos come from code; prices", "are checked before she replies."], "GROUNDED IN THE CATALOG"),
        ("growth", "Growth agent", "Coaches her on what sells",
         ["Revenue, profit, top seller and", "top category for any N days.", "Numbers computed in Python."], "SALES-DATA GROUNDED"),
        ("returns", "Returns funnel", "Turns a return into a sale",
         ["Hears the grievance, offers an", "exchange first. Starts from a", "complaint or a system event."], "EXCHANGE BEFORE REFUND"),
    ]
    out = []
    for k, (icon, name, role, lines, tag) in enumerate(cards):
        x = 40 + k * 285
        body = "".join(f'<text class="{p}-sans" x="24" y="{196 + i * 26}" font-size="14" fill="{MUTE}">{esc(l)}</text>' for i, l in enumerate(lines))
        out.append(f"""  <g class="{p}-in" style="animation-delay:{.15 + k * .15:.2f}s"><g transform="translate({x} 40)">
    <rect width="265" height="320" rx="16" fill="{BG}" stroke="{ACC}" stroke-opacity=".28"/>
    <rect x="8" y="8" width="249" height="304" rx="11" fill="none" stroke="{PINK}" stroke-opacity=".18" stroke-dasharray="4 5"/>
    <g transform="translate(24 28)">
      <rect width="52" height="52" rx="14" fill="{CHIP}" stroke="{ACC}" stroke-opacity=".5"/>
      <rect width="52" height="52" rx="14" fill="none" stroke="{MANGO_L}" stroke-opacity="0">
        <animate attributeName="stroke-opacity" values="0;1;0" dur="6s" begin="{1 + k * 1.5:.1f}s" repeatCount="indefinite"/>
      </rect>
      <g transform="translate(26 26)" fill="none" stroke="{LIGHT}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</g>
    </g>
    <text class="{p}-mono" x="241" y="48" font-size="10" letter-spacing="1.6" text-anchor="end" fill="{MUTE}">0{k + 1}</text>
    <text class="{p}-serif" x="24" y="126" font-size="27" font-weight="300" fill="{TEXT}">{name}</text>
    <text class="{p}-sans" x="24" y="152" font-size="13.5" fill="{MANGO_L}">{esc(role)}</text>
    <line x1="24" y1="170" x2="241" y2="170" stroke="{ACC}" stroke-opacity=".18"/>
    {body}
    <text class="{p}-mono" x="24" y="290" font-size="9.5" letter-spacing="1.6" fill="{TEAL}">● {tag}</text>
  </g></g>""")
    return f"""{svg_open(W, H, p, "Sakhi's four specialist agents",
                     "Catalog agent drafts WhatsApp-ready listings with the real margin and waits for approval. Customer agent answers buyers with RAG over the pgvector catalog; photos come from code and every stated price is checked against the catalog. Growth agent reports revenue, profit, top seller and top category for any number of days, computed in Python. Returns funnel offers an exchange first and starts from a buyer's complaint in chat or from a system event.")}
  <defs>
{defs(p, "10% 100%", ".4")}
  </defs>
  <style>
{fonts(p)}
    .{p}-in {{ animation: {p}-in 1s cubic-bezier(.16,1,.3,1) both; }}
    @keyframes {p}-in {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: none; }} }}
    @media (prefers-reduced-motion: reduce) {{ .{p}-in {{ animation: none; }} }}
  </style>
{frame(W, H, p)}
{chr(10).join(out)}
</svg>"""


# ---- Guardrails in numbers ----------------------------------------------
def numbers():
    p = "nm"
    W, H = 1200, 250
    stats = [
        ("12", "LangGraph nodes", "one compiled state machine"),
        ("3", "human-in-the-loop gates", "draft, picker, return"),
        ("5", "Gemini models", "fallback chain + key rotation"),
        ("100", "catalog SKUs", "RAG over Supabase pgvector"),
        ("560", "pytest tests", "on every push to main, in CI"),
    ]
    out = "\n".join(f"""  <g class="{p}-in" style="animation-delay:{.1 + k * .12:.2f}s"><g transform="translate({64 + k * 222} 66)">
    <circle r="4" fill="{MANGO}"/>
    <text class="{p}-serif" y="76" font-size="56" font-weight="300" fill="{TEXT}">{big}</text>
    <text class="{p}-mono" y="110" font-size="11" letter-spacing="2" fill="{ACC}">{lab.upper()}</text>
    <text class="{p}-sans" y="138" font-size="13" fill="{MUTE}">{esc(sub)}</text>
  </g></g>""" for k, (big, lab, sub) in enumerate(stats))
    return f"""{svg_open(W, H, p, "Sakhi in numbers",
                     "12 LangGraph nodes in one compiled state machine; 3 human-in-the-loop gates (draft approval, product picker, returns); 5 Gemini models in a fallback chain with API key rotation; 100 catalog SKUs for RAG over Supabase pgvector; 560 pytest tests run in CI on every push to main.")}
  <defs>
{defs(p, "50% 100%", ".45")}
  </defs>
  <style>
{fonts(p)}
    .{p}-in {{ animation: {p}-in 1s cubic-bezier(.16,1,.3,1) both; }}
    .{p}-draw {{ stroke-dasharray: 1200; stroke-dashoffset: 1200; animation: {p}-draw 2.4s cubic-bezier(.65,0,.35,1) .3s forwards; }}
    @keyframes {p}-in {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes {p}-draw {{ to {{ stroke-dashoffset: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .{p}-in {{ animation: none; }} .{p}-draw {{ animation: none; stroke-dashoffset: 0; }} }}
  </style>
{frame(W, H, p)}
  <path class="{p}-draw" d="M40 66 H1160" stroke="{ACC}" stroke-opacity=".35"/>
{out}
</svg>"""


# ---- Footer -------------------------------------------------------------
def footer():
    p = "ft"
    W, H = 1200, 210
    return f"""{svg_open(W, H, p, "Made by Komal Mittal for Bharat's 1.7 crore Meesho resellers")}
  <defs>
{defs(p, "50% 100%", ".6")}
    <linearGradient id="{p}-line" gradientUnits="userSpaceOnUse" x1="140" y1="0" x2="1060" y2="0"><stop offset="0" stop-color="{GLOW}" stop-opacity="0"/><stop offset=".5" stop-color="{MANGO}"/><stop offset="1" stop-color="{GLOW}" stop-opacity="0"/></linearGradient>
  </defs>
  <style>
{fonts(p)}
    .{p}-name {{ stroke: {MANGO_L}; stroke-width: 1; fill: {MANGO_L}; fill-opacity: 0; stroke-dasharray: 600; stroke-dashoffset: 600; animation: {p}-write 3.2s cubic-bezier(.65,0,.35,1) .3s forwards; }}
    .{p}-rule {{ stroke-dasharray: 920; stroke-dashoffset: 920; animation: {p}-draw 2.2s cubic-bezier(.65,0,.35,1) 1.4s forwards; }}
    .{p}-in {{ animation: {p}-in 1.2s ease 2.4s both; }}
    @keyframes {p}-write {{ 70% {{ stroke-dashoffset: 0; fill-opacity: 0; }} 100% {{ stroke-dashoffset: 0; fill-opacity: 1; }} }}
    @keyframes {p}-draw {{ to {{ stroke-dashoffset: 0; }} }}
    @keyframes {p}-in {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
    @media (prefers-reduced-motion: reduce) {{ .{p}-name {{ animation: none; stroke-dashoffset: 0; fill-opacity: 1; }} .{p}-rule {{ animation: none; stroke-dashoffset: 0; }} .{p}-in {{ animation: none; }} }}
  </style>
{frame(W, H, p)}
  <text class="{p}-sans {p}-name" x="600" y="96" text-anchor="middle" font-size="64" font-weight="300">सखी</text>
  <path class="{p}-rule" d="M140 124 H1060" stroke="url(#{p}-line)" stroke-dasharray="6 6"/>
  <g class="{p}-in">
    <text class="{p}-serif" x="600" y="160" text-anchor="middle" font-size="19" font-style="italic" fill="{TEXT}">Made by Komal Mittal for Bharat's 1.7 crore Meesho resellers.</text>
    <text class="{p}-mono" x="600" y="186" text-anchor="middle" font-size="10.5" letter-spacing="3" fill="{MUTE}">MEESHO SCRIPTEDBY{{HER}} 2.0 · AGENTIC AI FOR BHARAT</text>
  </g>
</svg>"""


if __name__ == "__main__":
    write("hero.svg", hero())
    for t in TITLES:
        write(f"title-{t[0]}.svg", title(*t))
    write("film.svg", film())
    write("flow.svg", flow())
    write("agents.svg", agents())
    write("numbers.svg", numbers())
    write("footer.svg", footer())
