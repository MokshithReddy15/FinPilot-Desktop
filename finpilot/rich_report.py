"""Safe Markdown presentation: no HTML, scripts or generated-code execution."""
import re
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont


def cells(line):
    return [v.strip().replace(r'\|','|') for v in re.split(r'(?<!\\)\|',line.strip().strip('|'))]


def blocks(text):
    lines=text.splitlines();i=0
    while i<len(lines):
        if i+1<len(lines) and '|' in lines[i] and all(re.fullmatch(r':?-{3,}:?',v.replace(' ','')) for v in cells(lines[i+1])):
            header=cells(lines[i]);rows=[];i+=2
            while i<len(lines) and '|' in lines[i] and lines[i].strip():
                row=cells(lines[i])
                # Preserve extra cells rather than silently dropping malformed data.
                if len(row)>len(header):row=row[:len(header)-1]+[' | '.join(row[len(header)-1:])]
                rows.append(row+['']*(len(header)-len(row)));i+=1
            yield 'table',(header,rows)
        else:
            yield 'text',lines[i];i+=1


def plain(value):return re.sub(r'\*\*(.*?)\*\*|`([^`]+)`',lambda m:m.group(1) or m.group(2),value)


class ReportTable(tk.Frame):
    """Wrapped cells with shared column widths, horizontal scroll and bounded pages."""
    def __init__(self,parent,theme,header,rows):
        super().__init__(parent,bg=theme.tokens['surface'])
        self.pack_propagate(False)
        self.theme,self.header,self.rows=theme,header,rows;self.page=0
        self.canvas=tk.Canvas(self,height=100,width=max(200,parent.winfo_width()-32),highlightthickness=0)
        self.canvas.pack(fill='x')
        self.scroll=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
        self.scroll.pack(fill='x');self.canvas.configure(xscrollcommand=self.scroll.set)
        self.controls=tk.Frame(self,bg=theme.tokens['surface']);self.controls.pack(fill='x')
        self.previous=ttk.Button(self.controls,text='Previous',command=lambda:self.turn(-1));self.previous.pack(side='left')
        self.caption=ttk.Label(self.controls);self.caption.pack(side='left',padx=10)
        self.next=ttk.Button(self.controls,text='Next',command=lambda:self.turn(1));self.next.pack(side='right')
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.draw()

    def turn(self,step):
        self.page=max(0,min(max(0,(len(self.rows)-1)//12),self.page+step));self.draw()

    def draw(self):
        t=self.theme.tokens;c=self.canvas;c.configure(bg=t['surface']);c.delete('all')
        n=len(self.header);width=max(320,self.winfo_width());col=max(135,min(260,width/max(1,n)))
        y=0
        data=[self.header]+self.rows[self.page*12:(self.page+1)*12]
        for index,row in enumerate(data):
            items=[];h=40
            for j,value in enumerate(row):
                value=plain(value);numeric=index>0 and bool(re.fullmatch(r'[₹$€£+−\-\d,.% ()]+',value))
                item=c.create_text(j*col+(col-12 if numeric else 12),y+12,text=value,
                    anchor='ne' if numeric else 'nw',justify='right' if numeric else 'left',width=col-24,
                    font=self.theme.fonts['body_bold' if index==0 else 'body'],fill=t['text_primary'])
                box=c.bbox(item);h=max(h,box[3]-y+12 if box else 40);items.append(item)
            bg=c.create_rectangle(0,y,n*col,y+h,fill=t['surface_raised'] if index==0 or index%2==0 else t['surface'],outline=t['border'])
            c.tag_lower(bg)
            for j in range(1,n):c.create_line(j*col,y,j*col,y+h,fill=t['border'])
            y+=h
        c.configure(height=y,scrollregion=(0,0,n*col,y))
        self.configure(height=y+(52 if len(self.rows)>12 else 20))
        self.caption.configure(text=f'{len(self.rows)} rows · Page {self.page+1}/{max(1,(len(self.rows)+11)//12)}')
        self.previous.configure(state='disabled' if self.page==0 else 'normal')
        self.next.configure(state='disabled' if (self.page+1)*12>=len(self.rows) else 'normal')
        if len(self.rows)<=12:self.controls.pack_forget()


class RichTranscript(tk.Text):
    def __init__(self,parent,theme,**kwargs):
        super().__init__(parent,**kwargs);self.theme=theme;self.tables=[]
        self.bind('<Configure>',self.resize_tables)
        self.apply_theme()

    def resize_tables(self,event=None):
        for table in self.tables:
            table.configure(width=max(200,self.winfo_width()-32))
            table.canvas.configure(width=max(200,self.winfo_width()-32))

    def add_message(self,role,text):
        follow=self.yview()[1]>=.98;position=self.yview()[0]
        self.configure(state='normal')
        role_tag='user_role' if role.lower().startswith('you') else 'role'
        self.insert('end',role.upper()+'\n',role_tag)
        for kind,value in blocks(text):
            if kind=='table':
                table=ReportTable(self,self.theme,*value);self.tables.append(table)
                table.configure(width=max(200,self.winfo_width()-32))
                self.window_create('end',window=table,stretch=False);self.insert('end','\n')
            else:
                heading=re.match(r'^#{1,6}\s+(.*)',value)
                if heading:self.insert('end',plain(heading.group(1))+'\n','heading')
                else:
                    value=re.sub(r'^\s*[-*]\s+','• ',value)
                    paragraph_tag='bullet' if value.startswith('• ') or re.match(r'^\d+[.)]\s',value) else 'body'
                    for part in re.split(r'(\*\*.*?\*\*)',value):
                        self.insert('end',plain(part),(paragraph_tag,'strong') if part.startswith('**') else paragraph_tag)
                    self.insert('end','\n')
        self.insert('end','\n');self.configure(state='disabled')
        if follow:self.see('end')
        else:self.yview_moveto(position)

    def clear(self):
        for table in self.tables:table.destroy()
        self.tables.clear();self.configure(state='normal');self.delete('1.0','end');self.configure(state='disabled')

    def apply_theme(self):
        t=self.theme.tokens
        self.configure(bg=t['surface'],fg=t['text_primary'],insertbackground=t['primary'],selectbackground=t['primary'],selectforeground=t['background'])
        self.tag_configure('role',foreground=t['primary'],font=self.theme.fonts['caption_bold'],spacing1=20,spacing3=10)
        self.tag_configure('user_role',foreground=t['text_muted'],font=self.theme.fonts['caption_bold'],spacing1=20,spacing3=8)
        self.tag_configure('heading',foreground=t['text_primary'],font=self.theme.fonts['subtitle'],spacing1=18,spacing3=8)
        self.tag_configure('strong',font=self.theme.fonts['body_bold'])
        self.tag_configure('body',spacing1=2,spacing2=3,spacing3=5)
        self.tag_configure('bullet',spacing1=4,spacing2=3,spacing3=6,lmargin1=8,lmargin2=23)
        for table in self.tables:table.draw()
