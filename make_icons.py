from PIL import Image, ImageDraw
import os
os.makedirs('www/icons', exist_ok=True)
for size in [192, 512]:
    img = Image.new('RGB', (size, size), color='#000000')
    draw = ImageDraw.Draw(img)
    draw.rectangle([0,0,size-1,size-1], outline='#00ff00', width=max(2,size//64))
    m = size//6
    draw.text((m, size//3), 'MS78', fill='#00ff00')
    draw.text((m, size//2), 'ARDOSIA', fill='#00ff00')
    img.save(f'www/icons/icon-{size}.png')
