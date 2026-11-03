"""Cached static glass rim and shadow. No blur work during hover animations."""
from functools import lru_cache
try:
    from PIL import Image,ImageDraw,ImageFilter,ImageTk
except ImportError:
    Image=None


@lru_cache(maxsize=4)
def material(width,height,background,surface,border,light):
    image=Image.new('RGB',(width,height),background)
    shadow=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(shadow)
    draw.rounded_rectangle((5,8,width-4,height-2),radius=20,fill=(0,0,0,125 if not light else 35))
    image.paste(shadow.filter(ImageFilter.GaussianBlur(5)),(0,0),shadow.filter(ImageFilter.GaussianBlur(5)))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((2,2,width-7,height-8),radius=18,fill=surface,outline=border,width=1)
    # Static reflected edge: highlight falls away toward the lower rim.
    draw.arc((3,3,39,39),180,270,fill='#637594' if not light else '#FFFFFF',width=1)
    draw.line((21,3,width-26,3),fill='#485A79' if not light else '#FFFFFF',width=1)
    draw.line((22,5,width//2,5),fill='#263951' if not light else '#F4F7FF',width=1)
    return image


def photo(widget,width,height,tokens,mode):
    if Image is None:return None
    return ImageTk.PhotoImage(material(width,height,tokens['background'],tokens['surface'],tokens['border_subtle'],mode=='light'),master=widget)
