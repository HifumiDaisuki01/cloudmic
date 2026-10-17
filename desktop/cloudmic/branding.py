"""Code-drawn brand mark shared by the title bar, tray and Windows EXE."""
from PIL import Image, ImageDraw


def make_mark(size=256):
    image=Image.new('RGBA',(256,256),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((0,0,255,255),radius=76,fill='#425DE8')
    for x,top,bottom in [(77,115,147),(128,70,186),(179,96,166)]:
        draw.line((x,top,x,bottom),fill='white',width=18)
        draw.ellipse((x-9,top-9,x+9,top+9),fill='white')
        draw.ellipse((x-9,bottom-9,x+9,bottom+9),fill='white')
    return image.resize((size,size),Image.Resampling.LANCZOS)
