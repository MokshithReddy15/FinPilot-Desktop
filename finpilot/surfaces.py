"""FinPilot's native vector identity, animated metrics, and savings simulator."""
import math
import tkinter as tk
from tkinter import font as tkfont
from animations import lerp_color
from layout import RetainedCanvas
from models import format_indian_currency


def rounded(canvas, x, y, w, h, fill, outline='', radius=16):
    r = min(radius, w/2, h/2)
    return canvas.create_polygon(x+r,y,x+w-r,y,x+w,y,x+w,y+r,
        x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,
        x,y+r,x,y, smooth=True, splinesteps=24, fill=fill, outline=outline)


def icon(c, kind, x, y, color, size=20):
    s=size/24
    def line(points):
        c.create_line(*[v for i in range(0,len(points),2) for v in (x+points[i]*s,y+points[i+1]*s)], fill=color, width=1.7, capstyle='round', joinstyle='round')
    def rect(a,b,d,e): c.create_rectangle(x+a*s,y+b*s,x+d*s,y+e*s,outline=color,width=1.5)
    if kind=='dashboard':
        for a,b in [(3,3),(14,3),(3,14),(14,14)]: rect(a,b,a+7,b+7)
    elif kind=='transactions':
        rect(2,5,22,19);line([2,10,22,10]);line([6,15,10,15])
    elif kind=='analytics':
        line([3,3,3,21,22,21]);line([7,16,12,10,16,13,22,4])
    elif kind=='assistant':
        line([11,2,14,9,21,12,14,15,11,22,8,15,1,12,8,9,11,2])
        line([20,1,20,6]);line([18,3,22,3])
    elif kind=='budget':
        c.create_oval(x+3*s,y+3*s,x+21*s,y+21*s,outline=color,width=1.5)
        c.create_oval(x+8*s,y+8*s,x+16*s,y+16*s,outline=color,width=1.5)
        line([12,12,22,2])
    elif kind=='income': line([5,17,18,4,18,13]);line([9,4,18,4])
    elif kind=='expense': line([5,7,18,20,18,11]);line([9,20,18,20])
    else:
        line([3,16,8,7,13,13,21,3]);line([15,3,21,3,21,9])


class Surface(RetainedCanvas):
    def __init__(self,parent,theme,animator,height=180):
        super().__init__(parent,height=height,bd=0,highlightthickness=0,bg=theme.tokens['background'])
        self.theme,self.animator=theme,animator
        self.hover=0.0
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Enter>',lambda e:self._hover(1))
        self.bind('<Leave>',lambda e:self._hover(0))

    def _hover(self,target):
        self.animator.animate_value(f'surface_{id(self)}',self.hover,target,180,self._set_hover)

    def _set_hover(self,v): self.hover=v;self.draw()

    def text(self,x,y,text,size=13,color=None,bold=False,anchor='nw',width=None):
        family=self.theme.font_family
        if width:
            f=tkfont.Font(family=family,size=-size,weight='bold' if bold else 'normal')
            while size>11 and f.measure(text)>width:
                size-=1;f.configure(size=-size)
            if f.measure(text)>width:
                while text and f.measure(text+'…')>width:text=text[:-1]
                text+='…'
        return self.create_text(x,y,text=text,font=(family,-size,'bold' if bold else 'normal'),
                                fill=color or self.theme.tokens['text_primary'],anchor=anchor)

    def apply_theme(self):
        self.configure(bg=self.theme.tokens['background']);self.draw()


class HeroVault(Surface):
    def __init__(self,parent,theme,animator):
        super().__init__(parent,theme,animator,260)
        self.value=0;self.target_pct=30;self.monthly=0;self.actual=0;self.symbol='₹';self.count=0
        self.title='TOTAL NET BALANCE'
        self.configure(takefocus=1)
        self.bind('<Button-1>',self.drag)
        self.bind('<B1-Motion>',self.drag)
        self.bind('<Left>',lambda e:self.step(-1))
        self.bind('<Right>',lambda e:self.step(1))
        self.bind('<FocusIn>',lambda e:self.draw())
        self.bind('<FocusOut>',lambda e:self.draw())

    def step(self,n): self.target_pct=max(10,min(75,self.target_pct+n));self.draw()
    def drag(self,e):
        self.focus_set()
        if 190<=e.y<=230:
            self.target_pct=round(10+65*max(0,min(1,(e.x-24)/max(1,self.winfo_width()-48))))
            self.draw()

    def update_vault(self,balance_paise,monthly_income_paise,actual_savings_rate,record_count,currency_symbol,scope_title='TOTAL NET BALANCE',animate=True):
        self.monthly=monthly_income_paise;self.actual=actual_savings_rate;self.count=record_count
        self.symbol=currency_symbol;self.title=scope_title
        self.animator.animate_value('vault_balance',self.value,balance_paise,520 if animate else 0,self._value)

    def _value(self,v):self.value=v;self.draw()

    def draw(self):
        if not hasattr(self,'value'):return
        self.begin_frame();w=self.winfo_width();h=self.winfo_height()
        if w<20:return
        rounded(self,1,2,w-2,h-4,lerp_color('#27215A','#352B76',self.hover),'#6555B8',20)
        # Deliberate orbital motif, clipped to the hero's upper right.
        for r in (38,59,80):
            self.create_arc(w-108-r,34-r,w-108+r,34+r,start=200,extent=155,style='arc',outline='#55478D',width=1)
        self.text(24,22,'F I N P I L O T   /   VAULT',11,'#BFB3F5',True)
        self.text(24,56,self.title,12,'#C4BDE5',width=w-48)
        self.text(24,77,format_indian_currency(round(self.value),self.symbol),38,'#FFFFFF',True,width=w-48)
        self.text(24,127,f'{self.count} transactions  ·  Your money, in perspective',12,'#BDB4DE',width=w-48)
        self.create_line(24,161,w-24,161,fill='#4B3F7C')
        self.text(24,176,'SAVINGS SIMULATOR',10,'#C4BDE5',True)
        self.text(w-24,173,f'{self.target_pct}%',17,'#D5FFB1',True,'ne')
        self.create_line(24,211,w-24,211,fill='#504579',width=5,capstyle='round')
        x=24+(w-48)*(self.target_pct-10)/65
        self.create_line(24,211,max(25,x),211,fill='#B7A2FF',width=5,capstyle='round')
        self.create_oval(x-7,204,x+7,218,fill='#FFFFFF',outline='#D5C8FF',width=2)
        self.text(24,231,f'Target {format_indian_currency(round(self.monthly*self.target_pct/100),self.symbol)}/mo',11,'#D3CBEA',width=w-120)
        self.text(w-24,231,f'Actual {self.actual:.0f}%',11,'#D5FFB1',anchor='ne')


class MetricCard(Surface):
    def __init__(self,parent,theme,animator,card_id,label,accent_key='primary',show_radial=False):
        super().__init__(parent,theme,animator,164)
        self.card_id=card_id;self.label=label;self.accent_key=accent_key;self.radial=show_radial
        self.value=0;self.formatter=lambda v:'0';self.subtitle='';self.badge='';self.badge_color=accent_key

    def set_value(self,target_value,formatter,subtitle='',badge_text='',badge_color_key=None,animate=True):
        self.formatter=formatter;self.subtitle=subtitle;self.badge=badge_text;self.badge_color=badge_color_key or self.accent_key
        self.animator.animate_value(f'metric_{self.card_id}',self.value,target_value,480 if animate else 0,self._value)

    def _value(self,v):self.value=v;self.draw()

    def draw(self):
        if not hasattr(self,'value'):return
        self.begin_frame();w=self.winfo_width();h=self.winfo_height();t=self.theme.tokens
        if w<20:return
        accent=t[self.accent_key]
        rounded(self,1,2,w-2,h-4,t['surface'],lerp_color(t['border'],accent,self.hover),16)
        rounded(self,18,18,32,32,t['surface_raised'],radius=10)
        icon(self,self.card_id,24,24,accent,20)
        self.text(60,27,self.label,10,t['text_muted'],True,width=w-76)
        self.text(18,66,self.formatter(self.value),26,bold=True,width=w-(82 if self.radial else 36))
        self.text(18,104,self.badge,10,t[self.badge_color],True,width=w-36)
        self.text(18,h-29,self.subtitle,11,t['text_muted'],width=w-36)
        if h>210 and getattr(self,'series',None):
            low,high=min(self.series),max(self.series)
            points=[]
            for i,value in enumerate(self.series):
                points.extend((20+i*(w-40)/max(1,len(self.series)-1),h-65-(value-low)/max(1,high-low)*34))
            self.create_line(*points,fill=accent,width=2,smooth=True)
            for i in range(0,len(points),2):
                x,y=points[i:i+2];self.create_oval(x-2,y-2,x+2,y+2,fill=accent,outline='')
        if self.radial:
            x=w-58;y=65
            self.create_oval(x,y,x+38,y+38,outline=t['surface_raised'],width=4)
            self.create_arc(x,y,x+38,y+38,start=90,extent=-max(0,min(100,self.value))*3.6,
                            style='arc',outline=accent,width=4)


class NavButton(Surface):
    def __init__(self,parent,theme,animator,key,label,command):
        super().__init__(parent,theme,animator,46)
        self.key=key;self.label=label;self.command=command;self.active=False;self.compact=False
        self.configure(cursor='hand2',takefocus=1)
        self.bind('<ButtonRelease-1>',lambda e:command())
        self.bind('<Return>',lambda e:command())
        self.bind('<space>',lambda e:command())
        self.bind('<FocusIn>',lambda e:self._hover(1))
        self.bind('<FocusOut>',lambda e:self._hover(0))

    def set_active(self,active):self.active=active;self.draw()
    def draw(self):
        if not hasattr(self,'key'):return
        self.begin_frame();t=self.theme.tokens;w=self.winfo_width()
        self.configure(bg=t['surface'])
        color=t['primary'] if self.active else t['text_muted']
        if self.active or self.hover:
            rounded(self,7,3,w-14,40,t['surface_raised'],t['border'] if self.active else '',11)
        icon(self,self.key,22,13,color,20)
        if not self.compact:self.text(55,15,self.label,13,t['text_primary'] if self.active else t['text_muted'],self.active)
        if self.active:self.create_oval(w-21,21,w-17,25,fill=t['primary'],outline='')


class ScenarioSlider(Surface):
    """Keyboard-accessible, vector slider using the same theme as the dashboard."""
    def __init__(self,parent,theme,animator,variable,command):
        super().__init__(parent,theme,animator,44)
        self.variable=variable;self.command=command
        self.configure(takefocus=1,cursor='hand2')
        self.bind('<Button-1>',self.drag)
        self.bind('<B1-Motion>',self.drag)
        self.bind('<Left>',lambda e:self.set(self.variable.get()-1))
        self.bind('<Right>',lambda e:self.set(self.variable.get()+1))
        self.bind('<Home>',lambda e:self.set(0))
        self.bind('<End>',lambda e:self.set(50))
        self.bind('<FocusIn>',lambda e:self.draw())
        self.bind('<FocusOut>',lambda e:self.draw())
        self._trace=self.variable.trace_add('write',lambda *_:self.draw())
        self.bind('<Destroy>',self._cleanup,add='+')

    def _cleanup(self,event):
        if event.widget is self:self.variable.trace_remove('write',self._trace)

    def set(self,value):
        self.variable.set(max(0,min(50,round(value))));self.command()

    def drag(self,event):
        self.focus_set();self.set((event.x-12)/max(1,self.winfo_width()-24)*50)

    def draw(self):
        if not hasattr(self,'variable'):return
        self.begin_frame();t=self.theme.tokens;w=self.winfo_width()
        if w<25:return
        self.configure(bg=t['surface'])
        y=17;x=12+(w-24)*self.variable.get()/50
        self.create_line(12,y,w-12,y,fill=t['surface_raised'],width=6,capstyle='round')
        self.create_line(12,y,max(13,x),y,fill=t['primary'],width=6,capstyle='round')
        self.create_oval(x-8,y-8,x+8,y+8,fill=t['primary'],outline=t['text_primary'] if self.focus_get()==self else t['primary'],width=2)
        self.text(12,30,'0%',10,t['text_muted'])
        self.text(w/2,30,'25%',10,t['text_muted'],anchor='n')
        self.text(w-12,30,'50%',10,t['text_muted'],anchor='ne')
