"""Generate deterministic small protocol-authoring fixtures, without external media."""
import json
import math
import random
from pathlib import Path

from PyQt6.QtGui import QColor, QImage

root = Path(__file__).resolve().parents[3] / 'demo_assets'
(root / 'images').mkdir(parents=True, exist_ok=True)
(root / 'textures').mkdir(exist_ok=True)
size = 256
rng = random.Random(12)
images = {
    '01_gray_50': lambda x, y: (128,) * 3,
    '02_white': lambda x, y: (255,) * 3,
    '03_black': lambda x, y: (0,) * 3,
    '04_gradient': lambda x, y: (x,) * 3,
    '05_circle': lambda x, y: ((230 if (x-128)**2 + (y-128)**2 < 70**2 else 40),) * 3,
    '06_color_quadrants': lambda x, y: (220 if x < 128 else 30, 180 if y < 128 else 30, 160 if x >= 128 else 30),
}
textures = {
    'checkerboard': lambda x, y: ((230 if (x // 32 + y // 32) % 2 else 25),) * 3,
    'sine_grating': lambda x, y: (round(127.5 + 110 * math.sin(2*math.pi*x/64)),) * 3,
    'noise': lambda x, y: (rng.randrange(256),) * 3,
}
for category, patterns in [('images', images), ('textures', textures)]:
    for name, pixel in patterns.items():
        image = QImage(size, size, QImage.Format.Format_RGB888)
        for y in range(size):
            for x in range(size):
                image.setPixelColor(x, y, QColor(*pixel(x, y)))
        assert image.save(str(root / category / f'{name}.png'))
        if category == 'textures':
            (root / category / f'{name}.texture.json').write_text(json.dumps({
                'cephvr_asset_type': 'texture_design', 'kind': 'texture',
                'preview_file': f'{name}.png',
                'params': {'tile_width_mm': 40, 'tile_height_mm': 40},
            }, indent=2) + '\n')
(root / 'manifest.json').write_text(json.dumps({
    'purpose': 'Dummy media for local protocol authoring; not calibrated scientific stimuli.',
    'images': [f'images/{name}.png' for name in images],
    'textures': [f'textures/{name}.texture.json' for name in textures],
    'texture_tile_mm': [40, 40],
    'usage': 'Choose Image for images/*.png; choose Texture for textures/*.texture.json. Group repetitions repeat the full sequence.',
}, indent=2) + '\n')
print(root)
