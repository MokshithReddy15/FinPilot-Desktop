"""Compact report metrics using the homepage's native visual language."""
from surfaces import MetricCard, rounded, icon


class ReportMetric(MetricCard):
    def draw(self):
        if not hasattr(self,'value'):return
        self.begin_frame();w=self.winfo_width();t=self.theme.tokens
        if w<40:return
        rounded(self,2,2,w-4,78,t['surface'],t['border'],16)
        rounded(self,14,20,34,34,t['surface_raised'],radius=10)
        icon(self,'income' if self.accent_key=='success' else 'expense' if self.accent_key=='danger' else 'analytics',21,27,t[self.accent_key],20)
        self.text(61,15,self.label,10,t['text_muted'],True,width=w-77)
        self.text(60,34,self.formatter(self.value),25,t['text_primary'],True,width=w-76)
