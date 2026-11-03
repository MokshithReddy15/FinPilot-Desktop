"""Date grouping and vector category badges for recent activity."""
from datetime import date, timedelta
import tkinter as tk
from surfaces import rounded, icon


def date_heading(value, today=None):
    today=today or date.today()
    day=date.fromisoformat(value)
    if day==today:return 'Today'
    if day==today-timedelta(days=1):return 'Yesterday'
    return day.strftime('%d %b %Y')


class CategoryBadge(tk.Canvas):
    def __init__(self,parent,theme):
        super().__init__(parent,width=36,height=36,bd=0,highlightthickness=0)
        self.theme=theme
        self.category='Other';self.income=False
        self.draw()

    def set_category(self,category,income=False):
        self.category=category;self.income=income;self.draw()

    def draw(self):
        self.delete('all');t=self.theme.tokens
        self.configure(bg=t['surface'])
        rounded(self,1,1,34,34,t['surface_raised'],radius=10)
        color=t['success'] if self.income else t['primary']
        def line(*xy):self.create_line(*xy,fill=color,width=1.6,capstyle='round',joinstyle='round')
        def rect(*xy):self.create_rectangle(*xy,outline=color,width=1.5)
        cat=self.category.lower()
        if cat in ('rent','housing'):
            line(8,17,18,8,28,17);line(11,15,11,28,25,28,25,15);rect(16,21,20,28)
        elif cat in ('groceries','shopping'):
            line(9,13,27,13,25,27,11,27,9,13);self.create_arc(13,7,23,20,start=0,extent=180,outline=color,width=1.5,style='arc')
        elif cat in ('health','medical'):
            line(18,9,18,27);line(9,18,27,18)
        elif cat in ('food','dining'):
            line(11,8,11,27);line(8,8,8,15,14,15,14,8);line(24,8,21,17,25,17,25,27)
        elif cat in ('bills','fuel'):
            line(21,7,12,20,18,20,15,29,25,15,19,15,21,7)
        elif cat in ('subscriptions','entertainment'):
            rect(8,10,28,26);line(16,14,22,18,16,22,16,14)
        elif cat in ('travel','transport'):
            rect(9,10,27,25);line(9,16,27,16);line(13,25,13,28);line(23,25,23,28)
        elif cat in ('salary','freelance'):
            rect(8,13,28,27);rect(14,8,22,13);line(8,19,28,19)
        else:
            icon(self,'income' if self.income else 'transactions',8,8,color,20)
