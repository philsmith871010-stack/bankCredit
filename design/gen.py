# Generates the four artboards for the Counterparty canvas from real data captured 6 Sep 2026.
import html
NAVY="#0a2540"; NAVY_MID="#143659"; NAVY_LIGHT="#1a4775"; ORANGE="#fd7e14"; ORANGE_SOFT="#fff5e9"
TEXT="#243240"; MUTED="#6c757d"; LINE="#e9ecef"; LINE_SOFT="#f1f3f5"; BG="#f7f8fa"; WHITE="#ffffff"; GREEN="#28a745"; RED="#b04632"
GRAD="linear-gradient(180deg, #0a2540 0%, #143659 60%, #1a4775 100%)"
FONTS='<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap">'
BASE_CSS=f"""
body{{margin:0;background:{BG};color:{TEXT};font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;font-size:15.2px;line-height:1.45;-webkit-font-smoothing:antialiased}}
a{{color:{NAVY};text-decoration:none}} a:hover{{color:{ORANGE}}}
.mono{{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}}
"""
def ico(name, size=18, color="currentColor"):
    p={"grid":'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
       "trend":'<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
       "bank":'<path d="M3 10h18"/><path d="M5 10v8"/><path d="M9 10v8"/><path d="M15 10v8"/><path d="M19 10v8"/><path d="M3 18h18"/><path d="M12 3l9 7H3l9-7z"/>',
       "bell":'<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21h4"/>',
       "list":'<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
       "book":'<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
       "search":'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
       "star":'<path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9L12 3z"/>',
       "download":'<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
       "compare":'<path d="M9 3v18"/><path d="M15 3v18"/><path d="M3 9h18"/><path d="M3 15h18"/>',
       "activity":'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
       "doc":'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h8"/>',
       "chev":'<path d="M9 6l6 6-6 6"/>', "up":'<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>', "down":'<path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/>', "flat":'<path d="M5 12h14"/>',
       "info":'<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>', "link":'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
       "menu":'<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>', "back":'<path d="M15 18l-6-6 6-6"/>', "clock":'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'}[name]
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{p}</svg>'

def spark(series, w=92, h=28, color=NAVY, fill=True):
    s=series[::-1]  # oldest first
    lo,hi=min(s),max(s); rng=(hi-lo) or 1; pad=3
    pts=[(pad+i*(w-2*pad)/(len(s)-1), h-pad-(v-lo)/rng*(h-2*pad)) for i,v in enumerate(s)]
    poly=" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)
    area=f'<polygon points="{pad},{h-pad} {poly} {pts[-1][0]:.1f},{h-pad}" fill="{color}" fill-opacity="0.08"/>' if fill else ''
    ex,ey=pts[-1]
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">{area}<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><circle cx="{ex:.1f}" cy="{ey:.1f}" r="2.6" fill="{ORANGE}"/></svg>'

def ribbon(score, p25, p50, p75, w=96, h=10):
    # band ribbon: five-step scale, peer band shaded, marker at score
    steps=[(0,35,"#c9d3de"),(35,50,"#a9b8c9"),(50,65,"#7d93ad"),(65,80,"#3f5f85"),(80,100,NAVY)]
    x=lambda v: v/100*w
    rects="".join(f'<rect x="{x(a):.1f}" y="3" width="{x(b)-x(a):.1f}" height="{h-6}" fill="{c}"/>' for a,b,c in steps)
    band=f'<rect x="{x(p25):.1f}" y="0" width="{x(p75)-x(p25):.1f}" height="{h}" fill="{ORANGE}" fill-opacity="0.18"/>'
    med=f'<rect x="{x(p50)-0.5:.1f}" y="0" width="1" height="{h}" fill="{ORANGE}" fill-opacity="0.9"/>'
    mark=f'<circle cx="{x(score):.1f}" cy="{h/2}" r="4.5" fill="{WHITE}" stroke="{NAVY}" stroke-width="2"/>'
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">{band}{rects}{med}{mark}</svg>'

def chip(text, kind="rating"):
    styles={"rating":f"background:{LINE_SOFT};color:{NAVY};border:1px solid {LINE}", "warn":f"background:{ORANGE_SOFT};color:#b35900;border:1px solid #ffd9b3", "good":f"background:#e7f5ec;color:#1e7a3a;border:1px solid #cfe9d8", "bad":f"background:#f8e8e5;color:{RED};border:1px solid #f0cfc8", "muted":f"background:{WHITE};color:{MUTED};border:1px solid {LINE}", "navy":f"background:{NAVY};color:{WHITE};border:1px solid {NAVY}", "orange":f"background:{ORANGE};color:{WHITE};border:1px solid {ORANGE}"}[kind]
    return f'<span style="display:inline-flex;align-items:center;gap:4px;height:22px;padding:0 8px;border-radius:999px;font-size:12px;font-weight:600;letter-spacing:.01em;white-space:nowrap;{styles}">{text}</span>'

def agency_chips(rt):
    out=[]
    for ag,val in rt:
        out.append(f'<span style="display:inline-flex;align-items:center;gap:5px;height:21px;padding:0 6px 0 4px;border-radius:6px;background:{WHITE};border:1px solid {LINE};font-size:11.5px;white-space:nowrap"><span style="display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;border-radius:3px;background:{NAVY};color:{WHITE};font-size:9px;font-weight:700">{ag}</span><span class="mono" style="font-weight:600;color:{TEXT}">{val}</span></span>')
    return f'<div style="display:flex;gap:4px;flex-wrap:nowrap">{"".join(out)}</div>' if out else f'<span style="color:#adb5bd">—</span>'

def shell(title, subtitle, content, active="board", width=1440, height=900, actions=""):
    nav=[("board","Board","grid"),("profile","Bank profiles","bank"),("events","Events","activity"),("brief","Brief","book"),("compare","Compare","compare"),("method","Method","list")]
    items="".join(f'<a href="#" style="display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;color:{"#ffffff" if k==active else "rgba(255,255,255,0.78)"};background:{"rgba(255,255,255,0.10)" if k==active else "transparent"};font-weight:{600 if k==active else 500};font-size:14px"><span style="display:inline-flex;color:{ORANGE if k==active else "rgba(255,255,255,0.7)"}">{ico(ic,17)}</span><span>{lab}</span></a>' for k,lab,ic in nav)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><script src="./support.js"></script></head><body><x-dc>
<helmet>{FONTS}<style>{BASE_CSS}</style></helmet>
<div style="width:{width}px;height:{height}px;background:{BG};display:flex;flex-direction:column;overflow:hidden;position:relative">
  <div style="height:60px;flex:0 0 60px;background:{WHITE};border-bottom:1px solid {LINE};display:flex;align-items:center;padding:0 20px 0 0;gap:0">
    <div style="width:220px;flex:0 0 220px;display:flex;align-items:center;gap:8px;padding-left:18px"><span style="width:10px;height:10px;border-radius:50%;background:{ORANGE};display:inline-block"></span><span style="font-weight:800;font-size:18px;letter-spacing:-0.02em;color:{NAVY}">PWLB<span style="color:{ORANGE}">today</span></span></div>
    <div style="display:flex;align-items:center;gap:10px;flex:1 1 auto"><span style="font-weight:600;font-size:16px;color:{TEXT}">Counterparty</span><span style="color:{LINE}">/</span><span style="font-size:15px;color:{MUTED}">{title}</span></div>
    <div style="display:flex;align-items:center;gap:10px">{actions}<span style="display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 12px;border:1px solid {LINE};border-radius:999px;font-size:13px;color:{TEXT};background:{WHITE}">{ico("bell",15,MUTED)} 3 alerts</span><span style="width:34px;height:34px;border-radius:50%;background:{NAVY};color:{WHITE};display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:13px">PS</span></div>
  </div>
  <div style="display:flex;flex:1 1 auto;min-height:0">
    <aside style="width:220px;flex:0 0 220px;background:{GRAD};color:{WHITE};padding:14px 9px 16px;display:flex;flex-direction:column;gap:4px;position:relative;overflow:hidden">
      <div style="position:absolute;top:-50px;right:-30px;width:240px;height:200px;background:radial-gradient(circle, rgba(253,126,20,0.10) 0%, transparent 70%);pointer-events:none"></div>
      <div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,0.55);padding:6px 12px 8px;font-weight:600">Counterparty</div>
      {items}
      <div style="flex:1 1 auto"></div>
      <div style="margin:0 4px;padding:12px;border-radius:10px;background:rgba(255,255,255,0.06);font-size:12px;color:rgba(255,255,255,0.75);line-height:1.4"><div style="display:flex;align-items:center;gap:6px;color:{WHITE};font-weight:600;margin-bottom:4px">{ico("clock",14,ORANGE)} Data status</div>Ratings 06:12 · Prices 06:05 · Pillar 3 sweep Mon · 2 sources late</div>
    </aside>
    <main style="flex:1 1 auto;min-width:0;padding:22px 28px 28px;display:flex;flex-direction:column;gap:18px;overflow:hidden">
      {content}
    </main>
  </div>
</div>
</x-dc></body></html>"""

# ---------- data (real, captured 6 Sep 2026; scores and bands illustrative) ----------
rows=[
 # name, sub, ctry, score,p25,p50,p75, band, chg, cet1, lev, lcr, ratings, market(dir,label), events, asof
 ("Nationwide Building Society","Building society · UK","GB",82,58,68,79,"A","+1.4",18.6,5.2,174,[("F","AA-"),("S","A+"),("M","A1"),("D","A(H)")],("flat","Bond proxy"),3,"30 Jun 2026"),
 ("Skipton Building Society","Building society · UK","GB",79,58,68,79,"B","+0.6",27.9,None,177.5,[("F","A"),("M","A2")],("none","No CDS"),1,"30 Jun 2026"),
 ("Barclays PLC","Bank · UK","GB",71,55,66,76,"B","−0.8",14.3,None,None,[("F","AA-"),("S","A+"),("D","A(H)")],("down","Widening"),4,"30 Jun 2026"),
 ("HSBC Holdings plc","Bank · UK","GB",74,55,66,76,"B","−1.9",14.1,4.9,134,[("F","A+"),("S","A-"),("D","A(H)")],("flat","Stable"),5,"30 Jun 2026"),
 ("NatWest Bank plc","Bank · UK","GB",66,55,66,76,"B","−2.1",11.2,4.4,None,[("F","A+"),("M","A3"),("D","A")],("flat","Stable"),2,"30 Jun 2026"),
 ("Santander UK plc","Bank · UK","GB",70,55,66,76,"B","+0.3",None,None,None,[("F","AA-"),("S","A"),("M","A1")],("flat","Stable"),1,"30 Jun 2026"),
 ("Standard Chartered PLC","Bank · UK","GB",63,55,66,76,"C","+2.2",None,None,None,[("F","A"),("S","BBB+")],("up","Tightening"),3,"30 Jun 2026"),
 ("Banco Santander, S.A.","Bank · Spain","ES",69,52,64,74,"B","+0.4",13.5,4.9,None,[("F","A+")],("up","Tightening"),2,"31 Dec 2025"),
 ("ING Groep N.V.","Bank · Netherlands","NL",72,52,64,74,"B","0.0",None,None,None,[("F","A+"),("S","A-")],("flat","Stable"),1,"31 Dec 2025"),
 ("Coöperatieve Rabobank U.A.","Bank · Netherlands","NL",78,52,64,74,"B","+0.5",20.3,7.7,None,[],("up","Tightening"),0,"31 Dec 2025"),
 ("Danske Bank A/S","Bank · Denmark","DK",75,52,64,74,"B","+0.9",17.3,4.4,None,[],("up","Tightening"),1,"31 Dec 2025"),
 ("Nordea Bank Abp","Bank · Finland","FI",81,52,64,74,"A","+0.2",None,None,None,[("F","AA"),("S","AA-"),("M","Aa1"),("D","AA(L)")],("flat","Stable"),1,"31 Dec 2025"),
 ("ABN AMRO Bank N.V.","Bank · Netherlands","NL",70,52,64,74,"B","−0.3",15.4,5.3,None,[],("flat","Stable"),0,"31 Dec 2025"),
 ("Commerzbank AG","Bank · Germany","DE",64,52,64,74,"C","+1.1",14.7,4.3,None,[],("flat","Stable"),2,"31 Dec 2025"),
 ("Australia and New Zealand Banking Group","Bank · Australia","AU",76,60,70,80,"B","+0.1",None,None,None,[("F","AA-"),("D","AA")],("flat","Stable"),2,"30 Jun 2026"),
 ("Royal Bank of Canada","Bank · Canada","CA",80,60,70,80,"A","+0.4",None,None,None,[("F","AA-"),("D","AA(H)")],("flat","Stable"),0,"31 Jul 2026"),
 ("DBS Bank Ltd.","Bank · Singapore","SG",83,60,70,80,"A","+0.3",None,None,None,[("F","AA-"),("S","AA-"),("M","Aa1")],("flat","Stable"),1,"30 Jun 2026"),
]
def fmt(v,dp=1,suffix=""):
    return f'<span class="mono">{v:.{dp}f}{suffix}</span>' if v is not None else f'<span style="color:#adb5bd">—</span>'
def band_chip(b):
    col={"A":NAVY,"B":"#3f5f85","C":"#7d93ad","D":"#a9b8c9","E":"#c9d3de"}[b]
    return f'<span class="mono" style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:22px;border-radius:6px;background:{col};color:{WHITE};font-weight:600;font-size:12.5px">{b}</span>'
def market(m):
    d,l=m
    if d=="none": return f'<span title="{l}" style="display:inline-flex;width:26px;height:22px;align-items:center;justify-content:center;border-radius:6px;background:{LINE_SOFT};color:#adb5bd;font-size:12px">—</span>'
    c={"up":"#1e7a3a","down":RED,"flat":MUTED}[d]; bgc={"up":"#e7f5ec","down":"#f8e8e5","flat":LINE_SOFT}[d]
    return f'<span title="{l}" style="display:inline-flex;width:26px;height:22px;align-items:center;justify-content:center;border-radius:6px;background:{bgc};color:{c}">{ico(d,14,c)}</span>'
def chg(c):
    col=GREEN if c.startswith("+") else (RED if c.startswith("−") else MUTED)
    return f'<span class="mono" style="color:{col};font-weight:500">{c}</span>'

th=lambda t,al="left",w="": f'<th style="text-align:{al};padding:9px 8px;font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{ORANGE};white-space:nowrap;{w}">{t}</th>'
trs=[]
for i,(n,sub,cc,sc,p25,p50,p75,b,c,cet,lev,lcr,rt,mk,ev,asof) in enumerate(rows):
    bg=WHITE if i%2==0 else "#fbfcfd"
    evc=f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:13px"><span style="width:7px;height:7px;border-radius:50%;background:{ORANGE if ev else LINE};display:inline-block"></span><span class="mono">{ev}</span></span>'
    trs.append(f"""<tr style="background:{bg};border-bottom:1px solid {LINE_SOFT}">
<td style="padding:8px 8px 8px 10px;white-space:nowrap"><div style="display:flex;align-items:center;gap:8px"><span style="display:inline-flex;color:{LINE}">{ico("star",15,"#cbd3dc")}</span><div><div style="font-weight:600;color:{TEXT}">{html.escape(n)}</div><div style="font-size:12px;color:{MUTED}">{sub}</div></div></div></td>
<td style="padding:8px"><div style="display:flex;align-items:center;gap:8px"><span class="mono" style="font-weight:600;font-size:15px;width:22px;text-align:right">{sc}</span>{ribbon(sc,p25,p50,p75)}</div></td>
<td style="padding:8px 4px;text-align:center">{band_chip(b)}</td>
<td style="padding:8px;text-align:right">{chg(c)}</td>
<td style="padding:8px;text-align:right">{fmt(cet,1,"%")}</td>
<td style="padding:8px;text-align:right">{fmt(lev,1,"%")}</td>
<td style="padding:8px;text-align:right">{fmt(lcr,0,"%")}</td>
<td style="padding:8px">{agency_chips(rt)}</td>
<td style="padding:8px;text-align:center">{market(mk)}</td>
<td style="padding:8px">{evc}</td>
<td class="mono" style="padding:8px 10px 8px 8px;font-size:12px;color:{MUTED};white-space:nowrap">{asof}</td>
</tr>""")
filters="".join(f'<span style="display:inline-flex;align-items:center;height:32px;padding:0 13px;border-radius:999px;font-size:13px;font-weight:{600 if a else 500};background:{NAVY if a else WHITE};color:{WHITE if a else TEXT};border:1px solid {NAVY if a else LINE}">{t}</span>' for t,a in [("All · 132",True),("UK banks · 25",False),("Building societies · 20",False),("EU and EEA · 35",False),("Australia and Canada · 12",False),("Asia · 10",False),("Gulf · 6",False),("US and Swiss · 10",False),("My watchlist · 14",False)])
board=f"""
<div style="display:flex;align-items:flex-end;justify-content:space-between;gap:20px">
  <div><h1 style="margin:0 0 4px;font-size:22.4px;font-weight:600;color:{TEXT};letter-spacing:-0.01em">Board</h1><div style="font-size:14px;color:{MUTED}">132 banks and building societies · scores recomputed 06:12 today · Pillar 3 data as of the date shown on each row</div></div>
  <div style="display:flex;align-items:center;gap:10px">
    <span style="display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 12px;border:1px solid {LINE};border-radius:8px;background:{WHITE};color:{MUTED};font-size:14px;width:240px">{ico("search",16,MUTED)}Search bank or LEI</span>
    <span style="display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:8px;background:{NAVY};color:{WHITE};font-size:14px;font-weight:600">{ico("download",16,WHITE)}Export list</span>
  </div>
</div>
<div style="display:flex;gap:8px;flex-wrap:wrap">{filters}</div>
<div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;box-shadow:0 6px 18px rgba(10,37,64,0.10);overflow:hidden;flex:1 1 auto;min-height:0;display:flex;flex-direction:column">
<div style="overflow:auto;flex:1 1 auto">
<table style="width:100%;border-collapse:collapse;font-size:13.5px">
<thead style="background:{GRAD};position:sticky;top:0"><tr>{th("Bank")}{th("Score · peers")}{th("Band","center")}{th("90d","right")}{th("CET1","right")}{th("Lev.","right")}{th("LCR","right")}{th("Ratings")}{th("Mkt","center")}{th("Events")}{th("As of")}</tr></thead>
<tbody>{"".join(trs)}</tbody>
</table></div>
<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-top:1px solid {LINE};font-size:12.5px;color:{MUTED}"><span>Showing 17 of 132 · sorted by score · <span style="color:{TEXT}">Ratings</span> from the ESMA register · <span style="color:{TEXT}">Mkt</span> is the 30-day direction of five-year CDS or bond spread, never the level</span><span style="display:flex;gap:14px"><span style="display:inline-flex;align-items:center;gap:6px">{ribbon(72,52,64,74,60,8)} peer 25th to 75th percentile, median in orange</span></span></div>
</div>"""
open("Main.dc.html","w").write(shell("Board","",board,"board"))

# ---------- Profile ----------
q=["Jun 25","Sep 25","Dec 25","Mar 26","Jun 26"]
S={"cet1":[18.6,19.1,18.9,18.4,18.8],"t1":[18.6,19.1,18.9,18.4,18.8],"tot":[23.5,23.8,24.0,23.2,24.4],"lcr":[174,169,166,163,166],"nsfr":[145,143,143,143,144],"rwa":[90308,87437,86701,86786,83232],"req":[17.5,17.5,17.5,17.5,18.2],"head":[11.5,11.8,12.0,11.2,11.6]}
def tile(label,val,unit,prev,series,peer,asof,dp=1,note=""):
    d=val-prev; col=GREEN if d>0 else (RED if d<0 else MUTED); sign="+" if d>0 else ("−" if d<0 else "")
    return f"""<div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;padding:14px 16px 12px;display:flex;flex-direction:column;gap:8px;min-width:0">
<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:11.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{NAVY}">{label}</span><span style="display:inline-flex;color:{LINE}">{ico("info",14,"#b8c2cc")}</span></div>
<div style="display:flex;align-items:flex-end;justify-content:space-between;gap:10px"><div><span class="mono" style="font-size:30px;font-weight:600;letter-spacing:-0.02em;color:{TEXT};line-height:1">{val:.{dp}f}</span><span class="mono" style="font-size:14px;color:{MUTED};margin-left:2px">{unit}</span></div>{spark(series)}</div>
<div style="display:flex;justify-content:space-between;font-size:12px;color:{MUTED}"><span class="mono" style="color:{col};font-weight:500">{sign}{abs(d):.{dp}f} vs prior</span><span>peer median <span class="mono" style="color:{TEXT}">{peer}</span></span></div>
<div style="font-size:11.5px;color:{MUTED};display:flex;justify-content:space-between"><span>{note}</span><span class="mono">{asof}</span></div>
</div>"""
tiles="".join([
 tile("CET1 ratio",18.6,"%",19.1,S["cet1"],"22.4%","30 Jun 26",1,"requirement 12.3%"),
 tile("Leverage ratio",5.2,"%",5.3,[5.3,5.3,5.3,5.3,5.2],"5.6%","30 Jun 26",1,"requirement 4.3%, binding"),
 tile("Total capital",23.5,"%",23.8,S["tot"],"25.1%","30 Jun 26",1,"overall requirement 17.5%"),
 tile("LCR",174,"%",169,S["lcr"],"181%","30 Jun 26",0,"12-month average"),
 tile("NSFR",145,"%",143,S["nsfr"],"146%","30 Jun 26",0,"4-quarter average"),
 tile("Risk-weighted assets",90.3,"£bn",87.4,S["rwa"],"—","30 Jun 26",1,"+3.3% in the quarter"),
])
# trend chart (CET1 with requirement line), 12 quarters: only 5 real, so draw 5 real points on a wider axis honestly
def chart(series, req, labels, w=560, h=200, ymin=10, ymax=22, unit="%", step=3, evlabel="Virgin Money integration", band=(20.5,24.5)):
    padl,padr,padt,padb=40,16,14,26; s=series[::-1]; n=len(s)
    X=lambda i: padl+i*(w-padl-padr)/(n-1); Y=lambda v: padt+(ymax-v)/(ymax-ymin)*(h-padt-padb)
    grid="".join(f'<line x1="{padl}" x2="{w-padr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{LINE}" stroke-width="1"/><text x="{padl-8}" y="{Y(v)+4:.1f}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="11" fill="{MUTED}">{v}{unit}</text>' for v in range(ymin,ymax+1,step))
    bandr=f'<rect x="{padl}" y="{Y(band[1]):.1f}" width="{w-padl-padr}" height="{Y(band[0])-Y(band[1]):.1f}" fill="{ORANGE}" fill-opacity="0.10"/>'
    reqline=f'<line x1="{padl}" x2="{w-padr}" y1="{Y(req):.1f}" y2="{Y(req):.1f}" stroke="{ORANGE}" stroke-width="1.5" stroke-dasharray="4 4"/><text x="{padl+6}" y="{Y(req)-6:.1f}" text-anchor="start" font-family="Inter, sans-serif" font-size="11" fill="#b35900">Requirement {req}%</text>'
    pts=" ".join(f"{X(i):.1f},{Y(v):.1f}" for i,v in enumerate(s))
    area=f'<polygon points="{X(0):.1f},{Y(ymin):.1f} {pts} {X(n-1):.1f},{Y(ymin):.1f}" fill="{NAVY}" fill-opacity="0.06"/>'
    dots="".join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3.2" fill="{WHITE}" stroke="{NAVY}" stroke-width="2"/>' for i,v in enumerate(s))
    end=f'<circle cx="{X(n-1):.1f}" cy="{Y(s[-1]):.1f}" r="4" fill="{ORANGE}"/><text x="{X(n-1)-10:.1f}" y="{Y(s[-1])-10:.1f}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="12" font-weight="600" fill="{TEXT}">{s[-1]}%</text>'
    xl="".join(f'<text x="{X(i):.1f}" y="{h-8}" text-anchor="middle" font-family="Inter, sans-serif" font-size="11" fill="{MUTED}">{l}</text>' for i,l in enumerate(labels))
    ev=f'<line x1="{X(3):.1f}" x2="{X(3):.1f}" y1="{padt}" y2="{h-padb}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="2 3"/><text x="{X(3)-5:.1f}" y="{padt+10}" text-anchor="end" font-family="Inter, sans-serif" font-size="10.5" fill="{MUTED}">{evlabel}</text>'
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="max-width:100%">{grid}{bandr}{ev}{reqline}{area}<polyline points="{pts}" fill="none" stroke="{NAVY}" stroke-width="2" stroke-linejoin="round"/>{dots}{end}{xl}</svg>'
tabs="".join(f'<span style="padding:12px 4px;margin-right:22px;font-size:14px;font-weight:{600 if a else 500};color:{NAVY if a else MUTED};border-bottom:2px solid {ORANGE if a else "transparent"}">{t}</span>' for t,a in [("Trends",True),("Ratings",False),("Market",False),("News and events",False),("Documents",False),("Peers",False)])
ratings_rows=[("Fitch","Long-term Issuer Default","AA-","Stable","12 May 2026"),("Fitch","Short-term Issuer Default","F1+","","12 May 2026"),("S&P","Issuer Credit Rating","A+","Stable","10 Sep 2025"),("S&P","Resolution Counterparty","AA-","","10 Sep 2025"),("Moody's","Long-term Deposit","A1","Stable","2 Mar 2026"),("Moody's","Counterparty Risk","Aa3","","2 Mar 2026"),("DBRS","Issuer Rating","A (high)","","25 Mar 2026")]
rtable="".join(f'<tr style="border-bottom:1px solid {LINE_SOFT}"><td style="padding:8px 10px;font-weight:600">{a}</td><td style="padding:8px 10px;color:{MUTED}">{t}</td><td class="mono" style="padding:8px 10px;font-weight:600">{v}</td><td style="padding:8px 10px;color:{MUTED}">{o}</td><td class="mono" style="padding:8px 10px;color:{MUTED};font-size:12.5px">{d}</td></tr>' for a,t,v,o,d in ratings_rows)
docs=[("Pillar 3 disclosures Q1 2026/27","30 Jun 2026","nationwide.co.uk","KM1 extracted · 14 figures · validated"),("Pillar 3 disclosures FY 2025/26","31 Mar 2026","nationwide.co.uk","KM1 extracted · validated"),("Interim MREL and buffer statement","16 Apr 2026","Bank of England","MREL 9.7% of leverage exposure"),("Pillar 3 disclosures Q3 2025/26","31 Dec 2025","nationwide.co.uk","KM1 extracted · validated")]
dlist="".join(f'<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid {LINE_SOFT}"><span style="display:inline-flex;color:{NAVY}">{ico("doc",18,NAVY)}</span><div style="flex:1 1 auto;min-width:0"><div style="font-weight:600;font-size:14px">{t}</div><div style="font-size:12.5px;color:{MUTED}">{src} · {n}</div></div><span class="mono" style="font-size:12.5px;color:{MUTED}">{d}</span><span style="display:inline-flex;color:{MUTED}">{ico("chev",16,"#b8c2cc")}</span></div>' for t,d,src,n in docs)
profile=f"""
<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:20px">
  <div style="display:flex;gap:14px;align-items:flex-start">
    <span style="width:44px;height:44px;border-radius:10px;background:{NAVY};color:{WHITE};display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;letter-spacing:.02em">NW</span>
    <div><div style="display:flex;align-items:center;gap:10px"><h1 style="margin:0;font-size:22.4px;font-weight:600;color:{TEXT};letter-spacing:-0.01em">Nationwide Building Society</h1>{chip("Building society","muted")}{chip("UK · PRA","muted")}</div>
    <div style="font-size:13.5px;color:{MUTED};margin-top:4px;display:flex;gap:14px;align-items:center"><span>Group consolidated · includes Virgin Money UK</span><span class="mono">LEI 549300XFX12G42QIKN82</span><a href="#" style="display:inline-flex;align-items:center;gap:4px;color:{NAVY}">{ico("link",13,NAVY)}Disclosure page</a></div></div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <span style="display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:8px;background:{WHITE};border:1px solid {LINE};font-size:14px;font-weight:500">{ico("star",16,ORANGE)}Watching</span>
    <span style="display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:8px;background:{WHITE};border:1px solid {LINE};font-size:14px;font-weight:500">{ico("compare",16,NAVY)}Compare</span>
    <span style="display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:8px;background:{NAVY};color:{WHITE};font-size:14px;font-weight:600">{ico("download",16,WHITE)}Counterparty report</span>
  </div>
</div>
<div style="display:grid;grid-template-columns:repeat(12, minmax(0, 1fr));gap:16px">
  <div style="grid-column:span 4;background:{GRAD};border-radius:12px;box-shadow:0 6px 18px rgba(10,37,64,0.10);color:{WHITE};padding:18px 20px;position:relative;overflow:hidden">
    <div style="position:absolute;top:-40%;right:-25%;width:75%;height:160%;background:radial-gradient(circle, rgba(253,126,20,0.16) 0%, transparent 70%);pointer-events:none"></div>
    <div style="position:relative;display:flex;flex-direction:column;gap:12px">
      <div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:11.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,0.72)">Counterparty score</span>{chip("Band A","orange")}</div>
      <div style="display:flex;align-items:flex-end;gap:14px"><span class="mono" style="font-size:56px;font-weight:700;line-height:.95;color:{ORANGE};letter-spacing:-0.02em">82</span><div style="padding-bottom:6px;font-size:13px;color:rgba(255,255,255,0.75);line-height:1.35"><div><span class="mono" style="color:{WHITE};font-weight:600">+1.4</span> in 90 days</div><div><span class="mono" style="color:{WHITE};font-weight:600">+3.0</span> in 12 months</div></div></div>
      <div><div style="display:flex;justify-content:space-between;font-size:11.5px;color:rgba(255,255,255,0.65);margin-bottom:6px"><span>UK building societies, 20 peers</span><span>84th percentile</span></div>{ribbon(82,58,68,79,376,12)}</div>
      <div style="font-size:13px;line-height:1.45;color:rgba(255,255,255,0.86);border-top:1px solid rgba(255,255,255,0.14);padding-top:10px">CET1 eased to 18.6% on higher risk-weighted assets after the Virgin Money integration; liquidity strengthened, ratings unchanged. Market overlay <span class="mono" style="color:{WHITE}">+2</span>.</div>
    </div>
  </div>
  <div style="grid-column:span 8;display:grid;grid-template-columns:repeat(3, minmax(0, 1fr));gap:12px">{tiles}</div>
</div>
<div style="display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));gap:12px">
  <div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:8px"><span style="font-size:11.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{NAVY}">Ratings</span>{agency_chips([("F","AA-"),("S","A+"),("M","A1"),("D","A(H)")])}<span style="font-size:12px;color:{MUTED}">All stable · last action 12 May 2026</span></div>
  <div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:8px"><span style="font-size:11.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{NAVY}">Market signal</span><span style="display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:600;color:{MUTED}">{ico("flat",15,MUTED)}Stable</span><span style="font-size:12px;color:{MUTED}">No CDS market · senior bond spread proxy, 30 days</span></div>
  <div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:8px"><span style="font-size:11.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{NAVY}">Equity</span><span style="font-size:14px;font-weight:600;color:{MUTED}">Not listed</span><span style="font-size:12px;color:{MUTED}">Mutual · core capital deferred shares only</span></div>
  <div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:8px"><span style="font-size:11.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{NAVY}">Events, 90 days</span><span style="display:inline-flex;align-items:center;gap:8px;font-size:14px;font-weight:600"><span style="width:8px;height:8px;border-radius:50%;background:{ORANGE};display:inline-block"></span>3 credit-relevant</span><span style="font-size:12px;color:{MUTED}">New disclosure · Fitch affirmation · MREL statement</span></div>
</div>
<div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;box-shadow:0 6px 18px rgba(10,37,64,0.10);overflow:hidden">
  <div style="display:flex;padding:0 18px;border-bottom:1px solid {LINE}">{tabs}</div>
  <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:24px;padding:18px 18px 8px">
    <div><div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px"><span style="font-size:13.5px;font-weight:600">CET1 ratio</span><span style="font-size:12px;color:{MUTED}">Requirement from KM1 row 12 · peer band shaded</span></div>{chart(S["cet1"],17.5,q)}</div>
    <div><div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px"><span style="font-size:13.5px;font-weight:600">Liquidity coverage ratio</span><span style="font-size:12px;color:{MUTED}">12-month average, per KM1</span></div>{chart(S["lcr"],100,q,ymin=100,ymax=190,step=30,band=(165,195))}</div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:24px;padding:8px 18px 18px">
    <div><div style="font-size:13.5px;font-weight:600;margin-bottom:6px">Ratings</div><table style="width:100%;border-collapse:collapse;font-size:13.5px"><thead><tr style="border-bottom:1px solid {LINE}"><th style="text-align:left;padding:6px 10px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};font-weight:600">Agency</th><th style="text-align:left;padding:6px 10px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};font-weight:600">Type</th><th style="text-align:left;padding:6px 10px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};font-weight:600">Rating</th><th style="text-align:left;padding:6px 10px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};font-weight:600">Outlook</th><th style="text-align:left;padding:6px 10px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};font-weight:600">Date</th></tr></thead><tbody>{rtable}</tbody></table><div style="font-size:12px;color:{MUTED};margin-top:8px">Source: ESMA European Rating Platform, checked daily. Symbols shown with agency attribution; histories are not redistributed.</div></div>
    <div><div style="font-size:13.5px;font-weight:600;margin-bottom:6px">Documents and source trail</div>{dlist}<div style="margin-top:10px;padding:10px 12px;border-radius:8px;background:{ORANGE_SOFT};font-size:12.5px;color:#7a4a12;display:flex;gap:8px;align-items:flex-start"><span style="display:inline-flex;flex:0 0 auto">{ico("info",15,"#b35900")}</span><span>Hover any figure on this page to see its document, page and extraction check. Example: CET1 18.6% comes from Pillar 3 Q1 2026/27, table UK KM1, row 5, page 6, extracted 12 Aug 2026 and validated against the prior quarter.</span></div></div>
  </div>
</div>
"""
open("Profile.dc.html","w").write(shell("Nationwide Building Society","",profile,"profile",1440,1400))

# ---------- Events ----------
events=[
 ("Today 08:41","Close Brothers Group","Provisions","medium","Motor finance provision doubled at full-year results; capital guidance maintained","Kalkine Media, results RNS","news"),
 ("Today 07:05","BNP Paribas","Rating action","low","Moody's affirms A1 issuer and deposit ratings, outlook stable","ESMA register · Moody's","primary"),
 ("Fri 4 Sep","Barclays PLC","Market","medium","Five-year senior CDS widened 6bp over the week to 52bp; sub at 93bp","DTCC prints · ICE settlement","primary"),
 ("Thu 3 Sep","DBS Bank","Rating action","low","Moody's affirms Aa1 deposit rating","ESMA register · Moody's","primary"),
 ("Thu 13 Aug","Standard Chartered PLC","New disclosure","info","Half-year 2026 Pillar 3 filed: PDF and RNS notice","FCA National Storage Mechanism","primary"),
 ("Wed 12 Aug","NatWest Group","New disclosure","info","H1 2026 Pillar 3 published; NatWest Bank plc CET1 11.2%, leverage 4.4%","FCA National Storage Mechanism · natwestgroup.com","primary"),
 ("Tue 11 Aug","HSBC Holdings","Rating action","low","Fitch affirms A+ long-term IDR, outlook stable","ESMA register · Fitch","primary"),
 ("Thu 23 Jul","Standard Chartered PLC","Rating action","positive","S&P revises outlook to positive on BBB+ issuer credit rating","ESMA register · S&P","primary"),
 ("Wed 8 Jul","Banco Santander","Rating action","low","Fitch affirms A+ long-term IDR, outlook stable","ESMA register · Fitch","primary"),
 ("Mon 8 Jun","Starling Bank","Rating action","positive","Moody's assigns first-time Baa2 issuer and deposit ratings, outlook stable","ESMA register · Moody's press release","primary"),
 ("Tue 26 May","HSBC Holdings","Rating action","positive","S&P revises outlook to positive on A- issuer credit rating","ESMA register · S&P","primary"),
 ("Tue 28 Apr","Barclays Bank PLC","New disclosure","info","Q1 2026 Pillar 3 published: CET1 12.3%, LCR 147.4%, UK leverage 5.4%","RNS via FCA National Storage Mechanism","primary"),
]
sev={"positive":("good","Positive"),"low":("muted","Low"),"medium":("warn","Medium"),"high":("bad","High"),"info":("navy","Disclosure")}
erows=[]
for when,bank,typ,s,txt,src,kind in events:
    k,l=sev[s]
    erows.append(f"""<div style="display:grid;grid-template-columns:110px 210px 1fr 260px;gap:14px;align-items:start;padding:12px 16px;border-bottom:1px solid {LINE_SOFT}">
<span class="mono" style="font-size:12.5px;color:{MUTED};padding-top:2px">{when}</span>
<div><div style="font-weight:600;font-size:14px">{bank}</div><div style="font-size:12px;color:{MUTED}">{typ}</div></div>
<div style="font-size:14px;line-height:1.4">{txt}</div>
<div style="display:flex;flex-direction:column;gap:6px;align-items:flex-start"><div style="display:flex;gap:6px">{chip(l,k)}{chip("Primary source" if kind=="primary" else "Press","muted")}</div><span style="font-size:12px;color:{MUTED}">{src}</span></div>
</div>""")
efilters="".join(f'<span style="display:inline-flex;align-items:center;height:32px;padding:0 13px;border-radius:999px;font-size:13px;font-weight:{600 if a else 500};background:{NAVY if a else WHITE};color:{WHITE if a else TEXT};border:1px solid {NAVY if a else LINE}">{t}</span>' for t,a in [("All",True),("Rating actions",False),("New disclosures",False),("Regulatory",False),("Results and capital",False),("Market moves",False),("Press",False),("My watchlist",False)])
ev=f"""
<div style="display:flex;align-items:flex-end;justify-content:space-between;gap:20px">
  <div><h1 style="margin:0 0 4px;font-size:22.4px;font-weight:600;color:{TEXT};letter-spacing:-0.01em">Events</h1><div style="font-size:14px;color:{MUTED}">Credit-relevant events across the universe · primary sources first · 41 items in 90 days, 2 today</div></div>
  <div style="display:flex;align-items:center;gap:10px"><span style="display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:8px;background:{WHITE};border:1px solid {LINE};font-size:14px;font-weight:500">{ico("bell",16,NAVY)}Alert rules</span><span style="display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:8px;background:{NAVY};color:{WHITE};font-size:14px;font-weight:600">{ico("book",16,WHITE)}Read today's brief</span></div>
</div>
<div style="display:flex;gap:8px;flex-wrap:wrap">{efilters}</div>
<div style="background:{WHITE};border:1px solid {LINE};border-radius:12px;box-shadow:0 6px 18px rgba(10,37,64,0.10);overflow:hidden;flex:1 1 auto;min-height:0;display:flex;flex-direction:column">
<div style="display:grid;grid-template-columns:110px 210px 1fr 260px;gap:14px;padding:10px 16px;background:{GRAD}"><span style="font-size:11.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{ORANGE}">When</span><span style="font-size:11.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{ORANGE}">Bank · type</span><span style="font-size:11.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{ORANGE}">What happened</span><span style="font-size:11.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{ORANGE}">Severity · source</span></div>
<div style="overflow:auto;flex:1 1 auto">{"".join(erows)}</div>
<div style="padding:10px 16px;border-top:1px solid {LINE};font-size:12.5px;color:{MUTED}">Severity and type are assigned by the classifier and reviewed before the daily brief. Filtered out today: 31 press items with no credit relevance (sponsorships, product launches, broker notes issued by the bank).</div>
</div>"""
open("Events.dc.html","w").write(shell("Events","",ev,"events"))

# ---------- Mobile profile ----------
mtiles="".join(f"""<div style="background:{WHITE};border:1px solid {LINE};border-radius:10px;padding:12px 12px 10px;display:flex;flex-direction:column;gap:6px"><span style="font-size:10.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{NAVY}">{l}</span><div style="display:flex;align-items:flex-end;justify-content:space-between"><span><span class="mono" style="font-size:24px;font-weight:600;letter-spacing:-0.02em;line-height:1">{v}</span><span class="mono" style="font-size:12px;color:{MUTED}">{u}</span></span>{spark(s,64,22)}</div><span class="mono" style="font-size:11.5px;color:{GREEN if d.startswith('+') else (RED if d.startswith('−') else MUTED)}">{d} vs prior</span></div>""" for l,v,u,s,d in [("CET1","18.6","%",S["cet1"],"−0.5"),("Leverage","5.2","%",[5.3,5.3,5.3,5.3,5.2],"−0.1"),("LCR","174","%",S["lcr"],"+5"),("NSFR","145","%",S["nsfr"],"+2")])
mob=f"""<!doctype html><html><head><meta charset="utf-8"><script src="./support.js"></script></head><body><x-dc>
<helmet>{FONTS}<style>{BASE_CSS}</style></helmet>
<div style="width:390px;height:844px;background:{BG};display:flex;flex-direction:column;overflow:hidden">
  <div style="height:56px;flex:0 0 56px;background:{WHITE};border-bottom:1px solid {LINE};display:flex;align-items:center;justify-content:space-between;padding:0 12px;margin-top:44px">
    <span style="display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:15px;color:{NAVY}">{ico("back",20,NAVY)}Board</span>
    <span style="font-weight:800;font-size:16px;letter-spacing:-0.02em;color:{NAVY}">PWLB<span style="color:{ORANGE}">today</span></span>
    <span style="display:inline-flex;gap:14px">{ico("star",20,ORANGE)}{ico("download",20,NAVY)}</span>
  </div>
  <div style="padding:16px 16px 0;display:flex;flex-direction:column;gap:12px">
    <div><div style="display:flex;align-items:center;gap:8px"><span style="width:34px;height:34px;border-radius:8px;background:{NAVY};color:{WHITE};display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:12px">NW</span><div><div style="font-weight:600;font-size:17px;line-height:1.2">Nationwide Building Society</div><div style="font-size:12px;color:{MUTED}">Building society · UK · as of 30 Jun 2026</div></div></div></div>
    <div style="background:{GRAD};border-radius:12px;color:{WHITE};padding:14px 16px;display:flex;flex-direction:column;gap:10px;box-shadow:0 6px 18px rgba(10,37,64,0.10)">
      <div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,0.72)">Counterparty score</span>{chip("Band A","orange")}</div>
      <div style="display:flex;align-items:flex-end;gap:12px"><span class="mono" style="font-size:48px;font-weight:700;line-height:.95;color:{ORANGE};letter-spacing:-0.02em">82</span><span style="padding-bottom:5px;font-size:12.5px;color:rgba(255,255,255,0.75)"><span class="mono" style="color:{WHITE};font-weight:600">+1.4</span> in 90 days · 84th percentile of 20 societies</span></div>
      {ribbon(82,58,68,79,326,12)}
    </div>
    <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px">{mtiles}</div>
    <div style="background:{WHITE};border:1px solid {LINE};border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px"><div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:10.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{NAVY}">Ratings</span><span style="font-size:11.5px;color:{MUTED}">ESMA register</span></div>{agency_chips([("F","AA-"),("S","A+"),("M","A1"),("D","A(H)")])}</div>
    <div style="display:flex;align-items:flex-end;height:40px;border-bottom:1px solid {LINE};overflow:hidden">{"".join(f'<span style="padding:0 2px 9px;margin-right:16px;font-size:13.5px;font-weight:{600 if a else 500};color:{NAVY if a else MUTED};border-bottom:2px solid {ORANGE if a else "transparent"};white-space:nowrap">{t}</span>' for t,a in [("Trends",True),("Ratings",False),("Market",False),("Events",False),("Documents",False)])}</div>
    <div style="background:{WHITE};border:1px solid {LINE};border-radius:10px;padding:12px"><div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:13px;font-weight:600">CET1 ratio</span><span style="font-size:11.5px;color:{MUTED}">requirement 17.5%</span></div>{chart(S["cet1"],17.5,q,332,160,step=3,evlabel="VM integration")}</div>
  </div>
</div>
</x-dc></body></html>"""
open("MobileProfile.dc.html","w").write(mob)

import json
json.dump({"artboards":[
  {"file":"Main.dc.html","title":"Board","x":0,"y":0,"w":1440,"h":900},
  {"file":"Profile.dc.html","title":"Bank profile · Nationwide","x":1540,"y":0,"w":1440,"h":1400},
  {"file":"Events.dc.html","title":"Events","x":0,"y":1040,"w":1440,"h":900},
  {"file":"MobileProfile.dc.html","title":"Mobile profile","x":1540,"y":1540,"w":390,"h":844}],
 "annotations":[
  {"id":"note-data","x":0,"y":-150,"w":520,"text":"Figures are real, captured 6 Sep 2026: Nationwide from Pillar 3 Q1 2026/27 (KM1, page 6), Barclays, HSBC, NatWest and Skipton from their H1 2026 reports, EU banks from the EBA hub (Dec 2025), ratings from the ESMA register, CDS from ICE and DTCC.\nScores, bands, peer percentiles and the market overlay are illustrative until the method is built."},
  {"id":"note-design","x":1540,"y":-150,"w":420,"text":"Matches PWLBtoday tokens: navy gradient shell, orange accent, Inter, IBM Plex Mono for every number, radii 6/10/14, navy table heads with orange labels, metric cards on the navy gradient.\nBand ribbon = five-step navy scale, peer 25th to 75th percentile in orange tint, median line, marker at the score."}],
 "launch":{"view":"canvas"}}, open("canvas.json","w"), indent=1)
print("written", [len(open(f).read()) for f in ["Main.dc.html","Profile.dc.html","Events.dc.html","MobileProfile.dc.html"]])
