"""Approximate sRGB labels without extra dependencies or network access."""
from functools import lru_cache


# Keep these references stable: saved universal-name exports must resume with
# the same sequence names. Different TVPaint groups are never merged by name.
PALETTE = (
    ("Black", (0, 0, 0)), ("White", (255, 255, 255)),
    ("Grey", (128, 128, 128)), ("Dark Grey", (64, 64, 64)), ("Light Grey", (192, 192, 192)),
    ("Red", (255, 0, 0)), ("Dark Red", (128, 0, 0)),
    ("Orange", (255, 128, 0)), ("Yellow", (255, 255, 0)),
    ("Green", (0, 255, 0)), ("Dark Green", (0, 128, 0)), ("Lime", (191, 255, 0)),
    ("Cyan", (0, 255, 255)), ("Teal", (0, 128, 128)),
    ("Blue", (0, 0, 255)), ("Navy", (0, 0, 128)),
    ("Purple", (128, 0, 128)), ("Violet", (128, 0, 255)),
    ("Magenta", (255, 0, 255)), ("Pink", (255, 128, 176)),
    ("Brown", (139, 69, 19)), ("Beige", (224, 192, 160)),
)


@lru_cache(maxsize=256)
def oklab(rgb):
    """sRGB decoding and Björn Ottosson's public-domain Oklab equations.

    Reference: https://bottosson.github.io/posts/oklab/
    Compare perceptual coordinates rather than hex strings or raw RGB distance.
    """
    linear = [v / 255 / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in rgb]
    r, g, b = linear
    l = (0.4122214708*r + 0.5363325363*g + 0.0514459929*b) ** (1/3)
    m = (0.2119034982*r + 0.6806995451*g + 0.1073969566*b) ** (1/3)
    s = (0.0883024619*r + 0.2817188376*g + 0.6299787005*b) ** (1/3)
    return (0.2104542553*l + 0.7936177850*m - 0.0040720468*s,
            1.9779984951*l - 2.4285922050*m + 0.4505937099*s,
            0.0259040371*l + 0.7827717662*m - 0.8086757660*s)


def universal_colour_name(rgb):
    if not isinstance(rgb, (list, tuple)) or len(rgb) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in rgb):
        raise ValueError("RGB colour information is unavailable. Refresh the layers or choose a different sequence naming option.")
    colour = oklab(tuple(rgb))
    return min(PALETTE, key=lambda entry: sum((a-b)**2 for a, b in zip(colour, oklab(entry[1]))))[0]
