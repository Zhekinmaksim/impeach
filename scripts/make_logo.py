#!/usr/bin/env python3
"""Build the logo files from the typeface, so the wordmark is outlines and
renders the same everywhere, with no font installed.

    pip install fonttools brotli uharfbuzz
    python3 scripts/make_logo.py

The mark is two ovals from the answer sheet: one pencilled in, one answered with
the old answer. The wordmark is Barlow Condensed SemiBold (OFL 1.1), shaped with
its own kerning and converted to paths.

web/assets/logo.svg        mark + wordmark, for light backgrounds
web/assets/logo-dark.svg   the same for dark backgrounds
web/assets/logo-mono.svg   one colour, takes currentColor
web/assets/logo-mark.svg   the mark alone
"""

import io
import os

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "web", "assets")
FONT = os.path.join(ASSETS, "fonts", "barlow-condensed-latin-600-normal.woff2")

FORM = "#1e6a4b"
GRAPHITE = "#26292b"
VOID = "#b3202e"
PAPER = "#eef3ec"
VOID_ON_DARK = "#d9404d"

WORD = "Impeach"


def wordmark():
    """Returns (path data, advance width, cap height) in font units, y down,
    baseline at y = cap height."""
    font = TTFont(FONT)
    buf = io.BytesIO()
    font.flavor = None
    font.save(buf)
    face = hb.Face(buf.getvalue())
    hfont = hb.Font(face)
    hbuf = hb.Buffer()
    hbuf.add_str(WORD)
    hbuf.guess_segment_properties()
    hb.shape(hfont, hbuf, {"kern": True})

    cap = font["OS/2"].sCapHeight
    glyphs = font.getGlyphSet()
    order = font.getGlyphOrder()
    pen = SVGPathPen(glyphs, ntos=lambda v: ("%.1f" % v).rstrip("0").rstrip("."))
    x = 0
    for info, pos in zip(hbuf.glyph_infos, hbuf.glyph_positions):
        name = order[info.codepoint]
        # flip y, put the cap line at 0
        glyphs[name].draw(TransformPen(pen, (1, 0, 0, -1, x + pos.x_offset, cap)))
        x += pos.x_advance
    desc = -font["OS/2"].sTypoDescender
    return pen.getCommands(), x, cap, desc


def mark(top: str, bottom: str, height: float, x: float = 0, y: float = 0, outline: bool = False) -> tuple:
    """Two stacked ovals filling `height`. Returns (svg, width). With `outline`
    the lower oval is drawn empty, for one-colour use."""
    gap = height * 0.14
    oval = (height - gap) / 2
    width = oval * 2.5
    f = lambda v: ("%.1f" % v).rstrip("0").rstrip(".")
    svg = '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"/>' % (
        f(x), f(y), f(width), f(oval), f(oval / 2), top)
    y2 = y + oval + gap
    if outline:
        w = oval * 0.13
        svg += '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="none" stroke="%s" stroke-width="%s"/>' % (
            f(x + w / 2), f(y2 + w / 2), f(width - w), f(oval - w), f((oval - w) / 2), bottom, f(w))
    else:
        svg += '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"/>' % (
            f(x), f(y2), f(width), f(oval), f(oval / 2), bottom)
    return svg, width


def lockup(word_fill: str, top: str, bottom: str, outline: bool = False) -> str:
    path, advance, cap, desc = wordmark()
    m, mw = mark(top, bottom, cap, outline=outline)
    space = cap * 0.34
    pad = cap * 0.12
    width = mw + space + advance
    height = cap + desc          # room for the p
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="%d %d %d %d" role="img" aria-label="Impeach">'
        "<title>Impeach</title>%s"
        '<path transform="translate(%.1f 0)" fill="%s" d="%s"/></svg>\n'
        % (-pad, -pad, round(width + 2 * pad), round(height + 2 * pad), m, mw + space, word_fill, path)
    )


def main() -> int:
    files = {
        "logo.svg": lockup(FORM, GRAPHITE, VOID),
        "logo-dark.svg": lockup(PAPER, PAPER, VOID_ON_DARK),
        # in one colour the second oval is an outline: marked, but not pencilled in
        "logo-mono.svg": lockup("currentColor", "currentColor", "currentColor", outline=True),
    }
    m, mw = mark(GRAPHITE, VOID, 400)
    files["logo-mark.svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-40 -40 %d 480" role="img" aria-label="Impeach">'
        "<title>Impeach</title>%s</svg>\n" % (round(mw + 80), m)
    )
    for name, svg in files.items():
        open(os.path.join(ASSETS, name), "w", encoding="utf-8").write(svg)
        print("%-16s %5d bytes" % (name, len(svg)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
