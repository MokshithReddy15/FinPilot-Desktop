"""Homepage-only art direction. Cached artwork; retained, interactive foreground."""
from surfaces import HeroVault, MetricCard, rounded, icon
from models import format_indian_currency
from animations import lerp_color

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    Image = None



class BalanceHero(HeroVault):
    def __init__(self, *args):
        self._art_key = None
        self._art = None
        self._track = (24, 200, 200)
        super().__init__(*args)

    def _background(self, w, h):
        key = (w, h, self.theme.mode)
        if Image is None:
            rounded(self, 2, 2, w-4, h-6, '#22244B', '#6C639E', 24)
            return
        if key != self._art_key:
            small = Image.new('RGB', (160, 64))
            pixels = small.load()
            for y in range(64):
                for x in range(160):
                    glow = max(0, 1-((x-106)**2/6500+(y-8)**2/2500))
                    pixels[x,y] = (int(23+35*glow), int(29+19*glow), int(54+51*glow))
            panel = small.resize((w,h), Image.Resampling.BILINEAR)
            draw = ImageDraw.Draw(panel)
            for r in (105, 140, 178, 218, 260):
                cx, cy = int(w*.55), -32
                draw.ellipse((cx-r,cy-r,cx+r,cy+r), outline='#4A466B', width=1)
            mask = Image.new('L',(w,h));md = ImageDraw.Draw(mask)
            md.rounded_rectangle((2,2,w-3,h-7), radius=24, fill=255)
            result = Image.new('RGB',(w,h),self.theme.tokens['background'])
            result.paste(panel,(0,0),mask)
            rd = ImageDraw.Draw(result)
            rd.rounded_rectangle((2,2,w-3,h-7),radius=24,outline='#635C88',width=1)
            rd.line((27,3,w-28,3),fill='#8B81B5',width=1)
            self._art = ImageTk.PhotoImage(result,master=self)
            self._art_key = key
        self.create_image(0,0,image=self._art,anchor='nw')

    def drag(self, event):
        self.focus_set()
        left, right, y = self._track
        if abs(event.y-y) <= 22:
            self.target_pct = round(10+65*max(0,min(1,(event.x-left)/max(1,right-left))))
            self.draw()

    def draw(self):
        if not hasattr(self,'value'): return
        self.begin_frame()
        w,h = self.winfo_width(),self.winfo_height()
        if w < 50: return
        self._background(w,h)
        wide = w >= 680
        left_width = int(w*.57) if wide else w-32
        self.text(28,24,'Y O U R   M O N E Y',10,'#CEC5EC',True,width=left_width-40)
        self.text(28,53,self.title.replace('TOTAL NET BALANCE','Net balance'),15,'#DFD9F0',width=left_width-40)
        self.text(26,79,format_indian_currency(round(self.value),self.symbol),48 if wide else 38,'#FFFFFF',True,width=left_width-46)
        self.text(28,142,f'{self.count} recorded transactions',12,'#C0B8D7',width=left_width-40)
        if wide:
            self.text(28,177,'A little clarity. More possibility.',13,'#DDD5F5',width=left_width-40)
        sx, sy = (int(w*.61),26) if wide else (18,177)
        sw, sh = w-sx-18, 174 if wide else 146
        rounded(self,sx,sy,sw,sh,'#1C2540','#596381',18)
        self.text(sx+18,sy+16,'MAKE ROOM FOR YOUR FUTURE',10,'#B8C7D9',True,width=sw-36)
        self.text(sx+18,sy+42,'Savings simulator',15,'#F5F2FF',True,width=sw-95)
        self.text(sx+sw-18,sy+40,f'{self.target_pct}%',20,'#AAE6CE',True,'ne')
        ty = sy+87
        a,b = sx+20,sx+sw-20
        self._track = (a,b,ty)
        self.create_line(a,ty,b,ty,fill='#3F4B69',width=5,capstyle='round')
        x = a+(b-a)*(self.target_pct-10)/65
        self.create_line(a,ty,max(a+1,x),ty,fill='#B9A7F5',width=5,capstyle='round')
        self.create_oval(x-9,ty-9,x+9,ty+9,fill='#384561',outline='')
        self.create_oval(x-5,ty-5,x+5,ty+5,fill='#F4F0FF',outline='#FFFFFF' if self.focus_get()==self else '#C1B1F6',width=2)
        self.text(sx+18,sy+108,format_indian_currency(round(self.monthly*self.target_pct/100),self.symbol)+' / month',17,'#F5F2FF',True,width=sw-36)
        if wide:
            self.text(sx+18,sy+143,f'Illustration · Recorded savings: {self.actual:.1f}%',11,'#AFBCD0',width=sw-36)


class HomeMetric(MetricCard):
    def draw(self):
        if not hasattr(self,'value'): return
        self.begin_frame()
        w,h = self.winfo_width(),self.winfo_height()
        if w < 35: return
        t = self.theme.tokens; accent = t[self.accent_key]
        rounded(self,2,3,w-4,h-7,t['surface'],lerp_color(t['border'],accent,self.hover*.55),18)
        self.create_line(22,4,w-22,4,fill=t['surface_raised'])
        rounded(self,18,18,30,30,t['surface_raised'],radius=10)
        icon(self,self.card_id,24,24,accent,18)
        self.text(59,25,self.label,10,t['text_muted'],True,width=w-77)
        self.text(18,61,self.formatter(self.value),29,bold=True,width=w-36)
        self.text(18,102,self.badge,10,t[self.badge_color],True,width=w-36)
        self.text(18,127,self.subtitle,11,t['text_muted'],width=w-36)
