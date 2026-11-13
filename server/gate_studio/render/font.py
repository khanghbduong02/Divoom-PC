"""A bundled 5x7 pixel font.

Panel text is drawn from this bitmap table rather than a system TrueType face so
glyphs stay crisp at any integer scale and the app keeps the device's pixel look.
Lowercase input is folded to uppercase, which is how the panel reads best.
"""

from __future__ import annotations

from PIL import ImageDraw

GLYPH_WIDTH = 5
GLYPH_HEIGHT = 7
DEFAULT_GAP = 1

_RAW: dict[str, str] = {
    " ": "..... ..... ..... ..... ..... ..... .....",
    "0": ".###. #...# #..## #.#.# ##..# #...# .###.",
    "1": "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
    "2": ".###. #...# ....# ...#. ..#.. .#... #####",
    "3": "##### ...#. ..##. ....# ....# #...# .###.",
    "4": "...#. ..##. .#.#. #..#. ##### ...#. ...#.",
    "5": "##### #.... ####. ....# ....# #...# .###.",
    "6": "..##. .#... #.... ####. #...# #...# .###.",
    "7": "##### ....# ...#. ..#.. .#... .#... .#...",
    "8": ".###. #...# #...# .###. #...# #...# .###.",
    "9": ".###. #...# #...# .#### ....# ...#. .##..",
    "A": ".###. #...# #...# ##### #...# #...# #...#",
    "B": "####. #...# #...# ####. #...# #...# ####.",
    "C": ".###. #...# #.... #.... #.... #...# .###.",
    "D": "###.. #..#. #...# #...# #...# #..#. ###..",
    "E": "##### #.... #.... ####. #.... #.... #####",
    "F": "##### #.... #.... ####. #.... #.... #....",
    "G": ".###. #...# #.... #.### #...# #...# .###.",
    "H": "#...# #...# #...# ##### #...# #...# #...#",
    "I": ".###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.",
    "J": "..### ...#. ...#. ...#. ...#. #..#. .##..",
    "K": "#...# #..#. #.#.. ##... #.#.. #..#. #...#",
    "L": "#.... #.... #.... #.... #.... #.... #####",
    "M": "#...# ##.## #.#.# #.#.# #...# #...# #...#",
    "N": "#...# ##..# #.#.# #.#.# #..## #...# #...#",
    "O": ".###. #...# #...# #...# #...# #...# .###.",
    "P": "####. #...# #...# ####. #.... #.... #....",
    "Q": ".###. #...# #...# #...# #.#.# #..#. .##.#",
    "R": "####. #...# #...# ####. #.#.. #..#. #...#",
    "S": ".#### #.... #.... .###. ....# ....# ####.",
    "T": "##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..",
    "U": "#...# #...# #...# #...# #...# #...# .###.",
    "V": "#...# #...# #...# #...# #...# .#.#. ..#..",
    "W": "#...# #...# #...# #.#.# #.#.# ##.## #...#",
    "X": "#...# #...# .#.#. ..#.. .#.#. #...# #...#",
    "Y": "#...# #...# .#.#. ..#.. ..#.. ..#.. ..#..",
    "Z": "##### ....# ...#. ..#.. .#... #.... #####",
    ".": "..... ..... ..... ..... ..... .##.. .##..",
    ",": "..... ..... ..... ..... .##.. .##.. ..#..",
    ":": "..... .##.. .##.. ..... .##.. .##.. .....",
    ";": "..... .##.. .##.. ..... .##.. .##.. ..#..",
    "-": "..... ..... ..... ##### ..... ..... .....",
    "+": "..... ..#.. ..#.. ##### ..#.. ..#.. .....",
    "=": "..... ..... ##### ..... ##### ..... .....",
    "_": "..... ..... ..... ..... ..... ..... #####",
    "/": "....# ....# ...#. ..#.. .#... #.... #....",
    "\\": "#.... #.... .#... ..#.. ...#. ....# ....#",
    "%": "##..# ##..# ...#. ..#.. .#... #..## #..##",
    "(": "...#. ..#.. .#... .#... .#... ..#.. ...#.",
    ")": ".#... ..#.. ...#. ...#. ...#. ..#.. .#...",
    "[": ".###. .#... .#... .#... .#... .#... .###.",
    "]": ".###. ...#. ...#. ...#. ...#. ...#. .###.",
    "!": "..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..",
    "?": ".###. #...# ....# ...#. ..#.. ..... ..#..",
    "#": ".#.#. .#.#. ##### .#.#. ##### .#.#. .#.#.",
    "*": "..... #.#.# .###. ##### .###. #.#.# .....",
    "'": "..#.. ..#.. ..... ..... ..... ..... .....",
    '"': ".#.#. .#.#. ..... ..... ..... ..... .....",
    "@": ".###. #...# #.### #.#.# #.### #.... .###.",
    "&": ".##.. #..#. #.#.. .#... #.#.# #..#. .##.#",
    ">": "#.... .#... ..#.. ...#. ..#.. .#... #....",
    "<": "....# ...#. ..#.. .#... ..#.. ...#. ....#",
    "|": "..#.. ..#.. ..#.. ..#.. ..#.. ..#.. ..#..",
    "~": "..... ..... .#... #.#.# ...#. ..... .....",
    "°": ".##.. #..#. .##.. ..... ..... ..... .....",
    "µ": "..... #...# #...# #...# #.##. #.... #....",
    "×": "..... #...# .#.#. ..#.. .#.#. #...# .....",
    "←": "..... ..#.. .#... ##### .#... ..#.. .....",
    "→": "..... ..#.. ...#. ##### ...#. ..#.. .....",
    "↑": "..#.. .###. #.#.# ..#.. ..#.. ..#.. .....",
    "↓": "..#.. ..#.. ..#.. ..#.. #.#.# .###. ..#..",
}

_GLYPHS: dict[str, tuple[str, ...]] = {
    char: tuple(pattern.split(" ")) for char, pattern in _RAW.items()
}
_MISSING = _GLYPHS["?"]


def normalize(text: str) -> str:
    return text.upper()


def glyph(char: str) -> tuple[str, ...]:
    return _GLYPHS.get(char.upper(), _MISSING)


def advance(scale: int = 1, gap: int = DEFAULT_GAP) -> int:
    return (GLYPH_WIDTH + gap) * scale


def text_width(text: str, scale: int = 1, gap: int = DEFAULT_GAP) -> int:
    if not text:
        return 0
    return len(text) * advance(scale, gap) - gap * scale


def text_height(scale: int = 1) -> int:
    return GLYPH_HEIGHT * scale


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    scale: int = 1,
    color: str = "#FFFFFF",
    gap: int = DEFAULT_GAP,
) -> tuple[int, int]:
    """Draw ``text`` with its top-left at ``xy``; returns the drawn size."""
    scale = max(1, int(scale))
    x0, y0 = xy
    cursor = x0
    for char in normalize(text):
        rows = glyph(char)
        for row_index, row in enumerate(rows):
            for col_index, pixel in enumerate(row):
                if pixel != "#":
                    continue
                left = cursor + col_index * scale
                top = y0 + row_index * scale
                draw.rectangle(
                    (left, top, left + scale - 1, top + scale - 1),
                    fill=color,
                )
        cursor += advance(scale, gap)
    return text_width(text, scale, gap), text_height(scale)


def fit_scale(
    text: str,
    max_width: int,
    preferred: int,
    max_height: int | None = None,
    gap: int = DEFAULT_GAP,
) -> int:
    """Largest integer scale <= ``preferred`` whose line fits the layer box."""
    scale = max(1, int(preferred))
    while scale > 1:
        too_wide = text_width(text, scale, gap) > max_width
        too_tall = max_height is not None and text_height(scale) > max_height
        if not too_wide and not too_tall:
            break
        scale -= 1
    return scale
