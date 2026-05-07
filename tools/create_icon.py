"""
创建默认应用图标
"""

from PIL import Image, ImageDraw

def create_app_icon():
    """创建应用图标"""
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    
    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 绘制圆角矩形背景
        margin = size // 8
        radius = size // 4
        
        # 背景
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=radius,
            fill=(70, 130, 180, 255)
        )
        
        # 绘制闪电符号
        center_x = size // 2
        center_y = size // 2
        bolt_size = size // 3
        
        points = [
            (center_x, center_y - bolt_size),
            (center_x - bolt_size // 2, center_y),
            (center_x, center_y),
            (center_x, center_y + bolt_size),
            (center_x + bolt_size // 2, center_y),
            (center_x, center_y),
        ]
        
        draw.polygon(points, fill=(255, 255, 255, 255))
        
        images.append(img)
    
    # 保存为ICO
    images[0].save(
        '../assets/app.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes]
    )
    print("图标已创建: assets/app.ico")


if __name__ == "__main__":
    import os
    os.makedirs('../assets', exist_ok=True)
    create_app_icon()