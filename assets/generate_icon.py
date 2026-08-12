#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Generate the application icon.

The icon is committed as `app.ico`, but it is produced by this script so it can
be regenerated or restyled without any binary editing. It is deliberately
brand-neutral: two image tiles and an arrow, standing for "replace this picture
with that one".

Usage:
    python assets/generate_icon.py            # writes ../app.ico
    python assets/generate_icon.py out.ico
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

#: Rendering happens at this size and is downsampled, so curves stay smooth.
CANVAS = 1024

#: Sizes embedded in the .ico file. 16 and 32 are what Windows actually shows in
#: the title bar and taskbar, so the shapes must survive that reduction.
ICO_SIZES = [(size, size) for size in (16, 24, 32, 48, 64, 128, 256)]

BACKGROUND = "#3365ae"
BACKGROUND_DEEP = "#28508a"
TILE_BACK = "#a8c4e8"
TILE_FRONT = "#ffffff"
ACCENT = "#ffffff"
GLYPH = "#3365ae"


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=0):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


#: Below this pixel size the detailed drawing turns to mush, so a simplified
#: variant is drawn instead of downsampling the detailed one.
SIMPLIFY_BELOW = 32


def draw_icon(size: int = CANVAS) -> Image.Image:
    """Draw the detailed icon on a transparent square canvas of `size` pixels."""
    scale = size / 1024
    def s(value: float) -> float:
        return value * scale

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded background plate, with a slightly darker base for a little depth.
    _rounded(draw, (s(16), s(24), s(1008), s(1008)), s(200), BACKGROUND_DEEP)
    _rounded(draw, (s(16), s(16), s(1008), s(992)), s(200), BACKGROUND)

    # Back tile: the picture being replaced, pushed behind and dimmed.
    _rounded(draw, (s(170), s(300), s(560), s(720)), s(48), TILE_BACK)

    # Front tile: the new picture.
    _rounded(draw, (s(330), s(390), s(830), s(830)), s(48), TILE_FRONT)

    # A minimal "photo" glyph inside the front tile: horizon plus sun.
    draw.ellipse((s(410), s(470), s(490), s(550)), fill=GLYPH)
    draw.polygon(
        [(s(370), s(770)), (s(540), s(580)), (s(660), s(700)),
         (s(720), s(640)), (s(790), s(770))],
        fill=GLYPH,
    )
    _rounded(draw, (s(330), s(760), s(830), s(830)), s(10), GLYPH)

    # Arrow across the top: the replacement action itself.
    _rounded(draw, (s(300), s(170), s(680), s(230)), s(30), ACCENT)
    draw.polygon(
        [(s(650), s(110)), (s(650), s(290)), (s(810), s(200))],
        fill=ACCENT,
    )

    return image


def draw_small_icon(size: int) -> Image.Image:
    """
    Simplified icon for tiny sizes (16/24 px).

    At those sizes the two tiles, the photo glyph and the arrow cannot all
    survive: the back tile and the horizon detail are dropped, and the arrow is
    drawn thick enough to stay a recognisable shape.
    """
    # Drawn at 8x and reduced once, which anti-aliases the edges without
    # smearing the shapes the way a reduction from 1024 px does.
    factor = 8
    canvas = size * factor
    scale = canvas / 64

    def s(value: float) -> float:
        return value * scale

    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    _rounded(draw, (s(1), s(1), s(63), s(63)), s(13), BACKGROUND)

    # One tile only, large and centred low.
    _rounded(draw, (s(12), s(26), s(52), s(53)), s(4), TILE_FRONT)
    draw.polygon([(s(15), s(50)), (s(28), s(34)), (s(38), s(44)),
                  (s(44), s(38)), (s(50), s(50))], fill=GLYPH)

    # Thick arrow occupying the whole upper band.
    draw.rectangle((s(14), s(14), s(40), s(20)), fill=ACCENT)
    draw.polygon([(s(38), s(8)), (s(38), s(26)), (s(52), s(17))], fill=ACCENT)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def icon_for(size: int) -> Image.Image:
    """Best rendering of the icon at a given pixel size."""
    if size <= SIMPLIFY_BELOW:
        return draw_small_icon(size)
    return draw_icon(CANVAS).resize((size, size), Image.Resampling.LANCZOS)


def main(argv: list[str]) -> int:
    destination = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.ico"
    )

    # Each embedded size is drawn at the resolution that suits it, rather than
    # letting Pillow downsample one master for all of them.
    renderings = [icon_for(size) for size, _ in ICO_SIZES]
    largest = renderings[-1]
    largest.save(destination, format="ICO", sizes=ICO_SIZES,
                 append_images=renderings[:-1])
    print(f"Icon written to {destination} ({len(renderings)} sizes)")

    preview = os.path.splitext(destination)[0] + "_preview.png"
    draw_icon(CANVAS).resize((256, 256), Image.Resampling.LANCZOS).save(preview)
    print(f"Preview written to {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
