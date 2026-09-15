// The approved list. One fetch for the column, one small file per card, cached; the list itself
// lives in this browser only (counterparty.approved) and travels as a link.
(function(){
  'use strict';
  var KEY='counterparty.approved', WATCH='counterparty.watch';
  // An empty data-root is the site root, not a missing one: the home page sets it to "".
  var _r=document.body.getAttribute('data-root'), ROOT=(_r==null?'../':_r);
  var POLICY='counterparty.policy';
  var EXAMPLE=['barclays-bank','lloyds-bank','natwest-bank','hsbc-uk','santander-uk','nationwide','coventry-bs','leeds-bs','yorkshire-bs','skipton-bs','goldman-sachs-international-bank','handelsbanken-plc','close-brothers','standard-chartered','clydesdale-bank'];
  var AG={fitch:'Fitch',sp:'S&P',moodys:"Moody's",dbrs:'DBRS',kbra:'KBRA',scope:'Scope',jcr:'JCR',rni:'R&I'};
  var TYPE={bank:'Bank',holding:'Group holding company',building_society:'Building society',subsidiary:'Subsidiary'};
  var PILLAR={capital:'Capital',liquidity:'Liquidity',asset_quality:'Asset quality',profitability:'Profitability',stability:'Stability',rating:'Ratings'};
  var COUNTRY={GB:'United Kingdom',US:'United States',DE:'Germany',FR:'France',NL:'Netherlands',ES:'Spain',IT:'Italy',SE:'Sweden',DK:'Denmark',NO:'Norway',FI:'Finland',CH:'Switzerland',IE:'Ireland',BE:'Belgium',AT:'Austria',CA:'Canada',AU:'Australia',SG:'Singapore',HK:'Hong Kong',JP:'Japan',AE:'United Arab Emirates',QA:'Qatar',SA:'Saudi Arabia',KW:'Kuwait',CN:'China',IN:'India',KR:'South Korea'};

  var all=[], byId={}, cache={}, state={ids:[],sort:'mine',group:false,example:false,compare:false,sel:[]}, current=null, q='';
  // Six lines at most on one chart, in a fixed order, so a name keeps its colour while others come and go.
  var CMP=['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300'], MAXSEL=CMP.length;
  function swatch(id){ var i=state.sel.indexOf(id); return i<0?'':CMP[i]; }
  var $=function(s){return document.querySelector(s)};
  var list=$('#list'), detail=$('#detail'), app=$('#app'), qEl=$('#q');

  // ---------- storage ----------
  function load(){ try{ var s=JSON.parse(localStorage.getItem(KEY)||'null'); if(s&&Array.isArray(s.ids)){ state.ids=s.ids; state.sort=s.sort||'mine'; state.group=!!s.group; return true; } }catch(e){} return false; }
  function save(){ try{ localStorage.setItem(KEY,JSON.stringify({ids:state.ids,sort:state.sort,group:state.group})); }catch(e){} }
  // The list the home page already keeps, in its order; then the starred names; then the example.
  function policyIds(){ try{ var p=JSON.parse(localStorage.getItem(POLICY)||'[]'); return Array.isArray(p)?p.map(function(x){return x&&x.id}).filter(Boolean):[]; }catch(e){ return []; } }
  function watchIds(){ try{ var w=JSON.parse(localStorage.getItem(WATCH)||'[]'); return Array.isArray(w)?w:[]; }catch(e){ return []; } }
  function linkIds(){ var m=/[#&]list=([^&]+)/.exec(location.hash); return m?m[1].split(',').filter(Boolean):null; }

  // ---------- helpers ----------
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]}); }
  var MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fdate(s){ if(!s) return '\u2014'; var p=String(s).slice(0,10).split('-'); return p.length===3?(+p[2])+' '+MON[+p[1]-1]+' '+p[0]:s; }
  function fshort(s){ if(!s) return '\u2014'; var p=String(s).slice(0,10).split('-'); return p.length===3?(+p[2])+' '+MON[+p[1]-1]:s; }
  function n1(v){ return v==null||isNaN(v)?'\u2014':(Math.round(v*10)/10).toFixed(1); }
  function pct(v){ return v==null?'\u2014':n1(v)+'%'; }
  function bandClass(b){ return /^[ABCD]$/.test(b||'')?'band-'+b:'band-N'; }
  function attention(r){ var f=r.flags||[], s=0; if(f.indexOf('news')>-1)s+=3; if(f.indexOf('rating')>-1)s+=3; if(f.indexOf('score')>-1)s+=2; if(f.indexOf('stale')>-1)s+=1; if(f.indexOf('unscored')>-1)s+=1; return s; }

  // ---------- list ----------
  function rows(){
    var rs=state.ids.map(function(id){return byId[id]}).filter(Boolean);
    if(state.sort==='attention') rs.sort(function(a,b){return attention(b)-attention(a)||(b.score||0)-(a.score||0)});
    else if(state.sort==='score') rs.sort(function(a,b){return (b.score||-1)-(a.score||-1)});
    else if(state.sort==='name') rs.sort(function(a,b){return a.short.localeCompare(b.short)});
    return rs;
  }
  function rowHtml(r){
    var f=r.flags||[], flag='', sc, unsc=!!r.unscored||r.score==null;
    if(f.indexOf('news')>-1||f.indexOf('rating')>-1) flag='<span class="flag'+(f.indexOf('news')>-1?' bad':'')+'" title="Something happened this month"></span>';
    if(unsc) sc='<span class="na">not scored</span>';
    else sc=n1(r.score)+(r.delta!=null&&Math.abs(r.delta)>=1?'<small class="'+(r.delta>0?'up':'dn')+'">'+(r.delta>0?'\u25b2':'\u25bc')+n1(Math.abs(r.delta))+'</small>':'');
    var sw=swatch(r.id);
    return '<a class="row'+(sw?' sel':'')+'" role="option" href="#'+esc(r.id)+'" data-id="'+esc(r.id)+'" aria-selected="'+(current===r.id)+'"'+(sw?' style="--ap-sw:'+sw+'"':'')+' title="'+esc(r.name)+(unsc?'':' \u00b7 band '+esc(r.band))+'">'
      +'<span class="ck" aria-hidden="true"></span><span class="bdot '+bandClass(r.band)+'"></span><span class="nm"><span>'+esc(r.short||r.name)+'</span>'+flag+'</span>'
      +'<span class="rg">'+(r.rating_composite?esc(r.rating_composite):(r.unrated?'<span class="na">unrated</span>':'\u2014'))+'</span><span class="sc">'+sc+'</span></a>';
  }
  function renderList(){
    var rs=rows(), term=q.trim().toLowerCase(), html='', shown=rs;
    if(term) shown=rs.filter(function(r){return (r.name+' '+r.short+' '+r.id).toLowerCase().indexOf(term)>-1});
    if(state.group&&!term){
      var groups={}, order=['bank','building_society','holding','subsidiary'];
      shown.forEach(function(r){ (groups[r.type]=groups[r.type]||[]).push(r); });
      order.concat(Object.keys(groups).filter(function(k){return order.indexOf(k)<0})).forEach(function(k){
        if(!groups[k]) return; html+='<div class="grp">'+esc(TYPE[k]||k)+'</div>'+groups[k].map(rowHtml).join('');
      });
    } else html+=shown.map(rowHtml).join('');
    if(!shown.length&&!term) html+='<div class="empty-note">Nothing here yet. Search above to add a counterparty.</div>';
    if(term){
      var adds=all.filter(function(r){return state.ids.indexOf(r.id)<0&&(r.name+' '+r.short+' '+r.id).toLowerCase().indexOf(term)>-1}).slice(0,8);
      if(adds.length){ html+='<div class="grp">Not on your list</div>'+adds.map(function(r){
        return '<a class="row add" href="#" data-add="'+esc(r.id)+'"><span class="nm">'+esc(r.name)+'</span><span class="plus">+ Add</span></a>'; }).join(''); }
      if(!shown.length&&!adds.length) html+='<div class="empty-note">No counterparty called \u201c'+esc(q)+'\u201d.</div>';
    }
    list.innerHTML=(shown.length?'<div class="cols"><span></span><span></span><span>Counterparty</span><span>Rating</span><span>Score</span></div>':'')+html;
    var n=state.ids.length; $('#count').textContent=n?(n+' counterpart'+(n===1?'y':'ies')+(state.example?' \u00b7 example':'')):'No counterparties yet';
    var gen=window.__generated; $('#foot').innerHTML=(state.example?'<div class="banner">This is an <b>example list</b> so you can see how it works. Add your own names above, or <a href="#" data-clear>start from empty</a>.</div>':'')
      +'<div>Data as of <b>'+(gen?fdate(gen):'\u2014')+'</b> \u00b7 stored in this browser only \u00b7 <a href="'+ROOT+'index.html">every name covered</a></div>';
  }

  // ---------- card ----------
  function fetchBank(id){ if(cache[id]) return Promise.resolve(cache[id]); return fetch(ROOT+'data/approved/'+id+'.json').then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); }).then(function(d){ cache[id]=d; return d; }); }
  function prefetch(){ var rs=rows(), i=rs.findIndex(function(r){return r.id===current}); [i-1,i+1].forEach(function(j){ if(rs[j]&&!cache[rs[j].id]) fetchBank(rs[j].id).catch(function(){}); }); }

  function sparkline(d){
    var pts=(d.quarters||[]).map(function(p){return p[1]}).filter(function(v){return v!=null});
    if(d.score!=null) pts.push(d.score);
    if(pts.length<2) return '';
    var W=320,H=48,P=6, lo=Math.min.apply(null,pts), hi=Math.max.apply(null,pts); if(hi-lo<2){hi+=1;lo-=1}
    var x=function(i){return P+i*(W-2*P)/(pts.length-1)}, y=function(v){return P+(H-2*P)*(1-(v-lo)/(hi-lo))};
    var line=pts.map(function(v,i){return (i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)}).join(' ');
    var area=line+' L'+x(pts.length-1).toFixed(1)+' '+(H-P)+' L'+x(0).toFixed(1)+' '+(H-P)+' Z';
    var since=(d.quarters&&d.quarters[0])?d.quarters[0][0].slice(0,4):'';
    return '<div class="lbl">Score since '+esc(since)+', by quarter</div><svg class="spark" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" aria-label="Score history">'
      +'<path d="'+area+'" fill="var(--ap-accent)" fill-opacity=".10"/><path d="'+line+'" fill="none" stroke="var(--ap-accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
      +'<circle cx="'+x(pts.length-1).toFixed(1)+'" cy="'+y(pts[pts.length-1]).toFixed(1)+'" r="4" fill="var(--ap-accent)" stroke="var(--ap-surface)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>';
  }
  function pspark(vals){
    if(!vals||vals.length<2) return '';
    var W=220,H=44,P=5, lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals); if(hi===lo){hi+=1;lo-=1}
    var x=function(i){return P+i*(W-2*P)/(vals.length-1)}, y=function(v){return P+(H-2*P)*(1-(v-lo)/(hi-lo))};
    var line=vals.map(function(v,i){return (i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)}).join(' ');
    return '<svg class="pspark" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" aria-label="Share price, last 60 sessions"><path d="'+line+'" fill="none" stroke="var(--ap-ink-3)" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
      +'<circle cx="'+x(vals.length-1).toFixed(1)+'" cy="'+y(vals[vals.length-1]).toFixed(1)+'" r="3.5" fill="var(--ap-ink-2)" stroke="var(--ap-surface)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>';
  }
  function mspark(pts,minimum,color){
    if(!pts||pts.length<2) return '';
    var W=120,H=46,P=5, vals=pts.map(function(p){return p[1]}), lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
    if(minimum!=null&&minimum>lo-(hi-lo)*2&&minimum<hi){ lo=Math.min(lo,minimum); }
    if(hi-lo<0.5){hi+=0.5;lo-=0.5}
    var x=function(i){return P+i*(W-2*P)/(vals.length-1)}, y=function(v){return P+(H-2*P)*(1-(v-lo)/(hi-lo))};
    var line=vals.map(function(v,i){return (i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)}).join(' ');
    var area=line+' L'+x(vals.length-1).toFixed(1)+' '+(H-P)+' L'+x(0).toFixed(1)+' '+(H-P)+' Z';
    var min=(minimum!=null&&minimum>=lo&&minimum<=hi)?'<line x1="0" x2="'+W+'" y1="'+y(minimum).toFixed(1)+'" y2="'+y(minimum).toFixed(1)+'" stroke="var(--ap-bad)" stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>':'';
    return '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" aria-hidden="true">'+min
      +'<path d="'+area+'" fill="'+color+'" fill-opacity=".10"/><path d="'+line+'" fill="none" stroke="'+color+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
      +'<circle cx="'+x(vals.length-1).toFixed(1)+'" cy="'+y(vals[vals.length-1]).toFixed(1)+'" r="4" fill="'+color+'" stroke="var(--ap-surface)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>';
  }
  // What the figure means. The minimum is the regulator's floor; the rest is where it sits among peers.
  function fmin(m){ return m==null?'':String(Math.round(m*100)/100); }
  function verdict(v,pr,minimum,higherIsBetter){
    if(v==null) return {cls:'na',text:'Not published'};
    if(minimum!=null&&v<minimum) return {cls:'bad',text:'Below the '+fmin(minimum)+'% minimum'};
    if(!pr||pr.p50==null) return {cls:'na',text:minimum!=null?'Above the '+fmin(minimum)+'% minimum':'No peer figures'};
    var hi=higherIsBetter!==false;
    if(hi?v>=pr.p75:v<=pr.p25) return {cls:'good',text:'Top quarter of peers'};
    if(hi?v>=pr.p50:v<=pr.p50) return {cls:'good',text:'Above peer median'};
    if(hi?v>=pr.p25:v<=pr.p75) return {cls:'warn',text:'Below peer median'};
    return {cls:'warn',text:'Bottom quarter of peers'};
  }
  function tile(label,sub,v,unit,pr,pts,minimum,minNote){
    if(v==null) return '<div class="tile none"><div class="k">'+label+'<small>'+sub+'</small></div><div class="v"><b>not published</b></div><span class="vd na"><i></i>No figure</span></div>';
    var vd=verdict(v,pr,minimum,true), color=vd.cls==='bad'?'var(--ap-bad)':(vd.cls==='warn'?'var(--ap-warn)':'var(--ap-accent)');
    var prev=(pts&&pts.length>1)?pts[pts.length-2]:null, ch='';
    if(prev&&prev[1]!=null){ var dlt=v-prev[1], a=Math.abs(dlt); ch='<span class="ch '+(a<0.05?'':(dlt>0?'up':'dn'))+'">'+(a<0.05?'unchanged':(dlt>0?'\u25b2':'\u25bc')+' '+n1(a))+' since '+fshort(prev[0])+'</span>'; }
    var span=(pts&&pts.length>1)?pts[0][0].slice(0,4)+'\u2013'+pts[pts.length-1][0].slice(0,4):'';
    var peers=pr&&pr.p50!=null?'Peers: median '+n1(pr.p50)+unit+', middle half '+n1(pr.p25)+'\u2013'+n1(pr.p75)+unit+(pr.n?' ('+pr.n+' names)':'')+(minimum!=null?' \u00b7 minimum '+fmin(minimum)+unit+(minNote?' '+minNote:''):''):(minimum!=null?'Minimum '+fmin(minimum)+unit+(minNote?' '+minNote:''):'');
    return '<div class="tile"><div class="k">'+label+'<small>'+sub+'</small></div><div class="v"><b>'+n1(v)+'<small>'+unit+'</small></b>'+ch+'</div>'
      +'<span class="vd '+vd.cls+' verdict"><i></i>'+vd.text+'</span>'
      +'<div class="tr">'+mspark(pts,minimum,color)+(span?'<small>'+span+', quarterly</small>':'')+'</div>'
      +(peers?'<div class="peers">'+peers+'</div>':'')+'</div>';
  }

  // ---------- compare ----------
  function fdateQ(s){ var p=String(s).slice(0,10).split('-'); return p.length===3?MON[+p[1]-1]+' '+p[0].slice(2):s; }
  var charts={};
  function lineChart(key,series,opt){
    // series: [{name,color,pts:[[date,value],...]}]; one scale for all; hover reads the nearest date.
    opt=opt||{}; var W=opt.w||640,H=opt.h||220,L=34,R=opt.labels?96:16,T=12,B=22;
    var xs={}; series.forEach(function(sr){ sr.pts.forEach(function(p){ xs[p[0]]=1; }); });
    var dates=Object.keys(xs).sort(); if(dates.length<2) return '<div class="hint">Not enough history to draw.</div>';
    var vals=[]; series.forEach(function(sr){ sr.pts.forEach(function(p){ if(p[1]!=null) vals.push(p[1]); }); });
    var lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals), near=opt.minimum!=null&&opt.minimum>=lo-(hi-lo||1)&&opt.minimum<=hi;
    if(near) lo=Math.min(lo,opt.minimum);
    var pad=(hi-lo||1)*0.12; lo-=pad; hi+=pad;
    if(opt.floor!=null) lo=Math.max(opt.floor,lo);
    var x=function(d){return L+dates.indexOf(d)*(W-L-R)/(dates.length-1)}, y=function(v){return T+(H-T-B)*(1-(v-lo)/(hi-lo))};
    var ticks=[], step=niceStep((hi-lo)/4); for(var v=Math.ceil(lo/step)*step; v<=hi; v+=step) ticks.push(Math.round(v*100)/100);
    var g=ticks.map(function(v){ return '<line class="gl" x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v).toFixed(1)+'" y2="'+y(v).toFixed(1)+'"/><text class="ax" x="'+(L-6)+'" y="'+(y(v)+3.5).toFixed(1)+'" text-anchor="end">'+v+(opt.unit||'')+'</text>'; }).join('');
    var every=Math.max(1,Math.round(dates.length/6));
    var xa=dates.map(function(d,i){ return ((i%every===0&&i<dates.length-1-every/2)||i===dates.length-1)?'<text class="ax" x="'+x(d).toFixed(1)+'" y="'+(H-6)+'" text-anchor="middle">'+esc(fdateQ(d))+'</text>':''; }).join('');
    var minl=near?'<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(opt.minimum).toFixed(1)+'" y2="'+y(opt.minimum).toFixed(1)+'" stroke="var(--ap-bad)" stroke-width="1" stroke-dasharray="3 3"/><text class="ax" x="'+(W-R+4)+'" y="'+(y(opt.minimum)+3.5).toFixed(1)+'" fill="var(--ap-bad)">min</text>':'';
    var ends=[]; var paths=series.map(function(sr){
      var pts=sr.pts.filter(function(p){return p[1]!=null}); if(!pts.length) return '';
      var d=pts.map(function(p,i){return (i?'L':'M')+x(p[0]).toFixed(1)+' '+y(p[1]).toFixed(1)}).join(' ');
      var last=pts[pts.length-1]; ends.push({name:sr.name,color:sr.color,y:y(last[1]),x:x(last[0])});
      return '<path d="'+d+'" fill="none" stroke="'+sr.color+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        +'<circle cx="'+x(last[0]).toFixed(1)+'" cy="'+y(last[1]).toFixed(1)+'" r="4" fill="'+sr.color+'" stroke="var(--ap-surface)" stroke-width="2"/>';
    }).join('');
    // end labels, pushed apart so they never sit on each other
    var lab=''; if(opt.labels){ ends.sort(function(a,b){return a.y-b.y}); for(var i=1;i<ends.length;i++){ if(ends[i].y-ends[i-1].y<13) ends[i].y=ends[i-1].y+13; }
      lab=ends.map(function(e){ return '<text class="lbl-end" x="'+(W-R+8)+'" y="'+(e.y+4).toFixed(1)+'">'+esc(e.name)+'</text>'; }).join(''); }
    charts[key]={dates:dates,series:series,L:L,R:R,W:W,unit:opt.unit||''};
    return '<div class="chart" data-chart="'+key+'"><svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(opt.aria||'')+'">'+g+xa+minl+paths+lab
      +'<line class="xh" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+'"/></svg><div class="tip"></div></div>';
  }
  function niceStep(raw){ var p=Math.pow(10,Math.floor(Math.log(raw)/Math.LN10)), r=raw/p; return (r<1.5?1:r<3.5?2:r<7.5?5:10)*p; }
  detail.addEventListener('mousemove',function(e){
    var ch=e.target.closest('.chart'); if(!ch) return; var c=charts[ch.dataset.chart]; if(!c) return;
    var svg=ch.querySelector('svg'), box=svg.getBoundingClientRect(), fx=(e.clientX-box.left)/box.width*c.W;
    var n=c.dates.length, i=Math.round((fx-c.L)/((c.W-c.L-c.R)/(n-1))); i=Math.max(0,Math.min(n-1,i));
    var d=c.dates[i], px=c.L+i*(c.W-c.L-c.R)/(n-1);
    svg.querySelector('.xh').setAttribute('x1',px); svg.querySelector('.xh').setAttribute('x2',px);
    var rows=c.series.map(function(sr){ var p=sr.pts.filter(function(q){return q[0]===d})[0]; return p&&p[1]!=null?'<div><i style="background:'+sr.color+'"></i>'+esc(sr.name)+' '+n1(p[1])+c.unit+'</div>':''; }).join('');
    var tip=ch.querySelector('.tip'); tip.innerHTML='<b>'+esc(fdate(d))+'</b>'+rows; tip.style.left=(px/c.W*100)+'%'; ch.classList.add('on');
  });
  detail.addEventListener('mouseleave',function(){ detail.querySelectorAll('.chart.on').forEach(function(ch){ch.classList.remove('on')}); },true);
  detail.addEventListener('mouseout',function(e){ var ch=e.target.closest('.chart'); if(ch&&!ch.contains(e.relatedTarget)) ch.classList.remove('on'); });

  function compareHtml(banks){
    var names=banks.map(function(d,i){ return {d:d,color:CMP[i],name:d.short||d.name}; });
    var who='<div class="who"><h2>Side by side</h2>'+names.map(function(n){ return '<span class="nm" style="--ap-sw:'+n.color+'"><i></i>'+esc(n.name)+'<button type="button" data-unsel="'+esc(n.d.id)+'" title="Remove from the comparison">\u00d7</button></span>'; }).join('')+'</div>';
    var score=lineChart('score',names.map(function(n){ var pts=(n.d.quarters||[]).slice(); if(n.d.score!=null) pts=pts.concat([[window.__generated.slice(0,10),n.d.score]]); return {name:n.name,color:n.color,pts:pts}; }),
      {labels:true,aria:'Counterparty score by quarter',w:720,h:240});
    var metrics=[['cet1_ratio','CET1 ratio','%',4.5],['leverage_ratio','Leverage ratio','%',3.0],['lcr','Liquidity coverage','%',100],['nsfr','Stable funding','%',100]];
    var smalls='<div class="smalls">'+metrics.map(function(m){ return '<div><h4>'+m[1]+'<small>quarterly, %</small></h4>'+lineChart(m[0],names.map(function(n){ return {name:n.name,color:n.color,pts:(n.d.trend||{})[m[0]]||[]}; }),{minimum:m[3],aria:m[1],w:360,h:170})+'</div>'; }).join('')+'</div>';
    function cell(v,pr,min){ var vd=verdict(v,pr,min,true); return '<td class="'+(v==null?'na':vd.cls)+'" title="'+esc(vd.text)+'">'+(v==null?'\u2014':n1(v)+'%')+'</td>'; }
    var table='<div class="ctab-wrap"><table class="ctab"><thead><tr><th>Name</th><th>Band</th><th>Score</th><th>Rating</th><th>CET1</th><th>Leverage</th><th>LCR</th><th>NSFR</th><th>Figures</th></tr></thead><tbody>'
      +names.map(function(n){ var d=n.d, pr=d.peer_ratios||{}, un=!!d.unscored||d.score==null;
        return '<tr><td><span class="sw" style="background:'+n.color+'"></span>'+esc(n.name)+'</td><td>'+(un?'<span class="na">not scored</span>':'Band '+esc(d.band))+'</td>'
          +'<td>'+(un?'<span class="na">\u2014</span>':n1(d.score)+(d.delta!=null&&Math.abs(d.delta)>=1?'<span class="'+(d.delta>0?'up':'dn')+'">'+(d.delta>0?'\u25b2':'\u25bc')+n1(Math.abs(d.delta))+'</span>':''))+'</td>'
          +'<td>'+(d.rating_composite?esc(d.rating_composite):'<span class="na">\u2014</span>')+'</td>'
          +cell(d.cet1,pr.cet1_ratio,4.5)+cell(d.leverage,pr.leverage_ratio,d.country==='GB'?3.25:3.0)+cell(d.lcr,pr.lcr,100)+cell(d.nsfr,pr.nsfr,100)
          +'<td class="na">'+fshort(d.asof)+(d.asof?' '+String(d.asof).slice(0,4):'')+'</td></tr>'; }).join('')+'</tbody></table></div>';
    return '<div class="cmp">'+who
      +'<section class="sec"><h3>Counterparty score <span>by quarter, three years, today at the end</span></h3>'+score+'</section>'
      +'<section class="sec"><h3>Capital and liquidity <span>the dotted line is the regulator\u2019s minimum</span></h3>'+smalls+'</section>'
      +'<section class="sec"><h3>Today <span>shaded against the regulator\u2019s minimum, then the peer group</span></h3>'+table+'</section>'
      +'<div class="note">Peer groups differ between names, so two names shaded the same are each judged against their own peers. Ratios are as last published by each bank; the dates column says when.</div></div>';
  }
  function renderCompare(){
    if(state.sel.length<2){ detail.innerHTML='<div class="cmp"><div class="who"><h2>Side by side</h2></div><div class="hint">Tick two or more names on the left'+(state.sel.length?' \u2014 one so far':'')+'. Up to six.</div></div>'; return; }
    var ids=state.sel.slice(), bar=document.createElement('div'); bar.className='loading-bar on'; detail.prepend(bar);
    Promise.all(ids.map(fetchBank)).then(function(banks){
      if(!state.compare||ids.join()!==state.sel.join()) return;
      detail.innerHTML=compareHtml(banks); detail.scrollTop=0;
      history.replaceState(null,'','#cmp='+ids.join(','));
    }).catch(function(){ detail.innerHTML='<div class="cmp"><div class="hint">Could not load one of the names. Try again.</div></div>'; });
  }
  function setCompare(on){
    state.compare=!!on; app.classList.toggle('comparing',state.compare); $('#cmp').setAttribute('aria-pressed',String(state.compare));
    if(state.compare){ if(current&&state.sel.indexOf(current)<0&&state.sel.length<MAXSEL) state.sel.push(current); renderList(); renderCompare(); }
    else { state.sel=[]; renderList(); if(current) show(current); else show(null); }
  }
  function toggleSel(id){
    var i=state.sel.indexOf(id);
    if(i>-1) state.sel.splice(i,1);
    else if(state.sel.length>=MAXSEL){ toast('Six is the most one chart can hold. Untick one first.'); return; }
    else state.sel.push(id);
    renderList(); renderCompare();
  }

  function card(d){
    var band=d.band||'', unscored=!!d.unscored||d.score==null;
    var field='var(--'+((/^[ABCD]$/.test(band))?band:'N')+'-soft)';
    var delta='';
    if(!unscored&&d.delta!=null){ var a=Math.abs(d.delta); delta='<div class="delta '+(a<0.05?'flat':(d.delta>0?'up':'dn'))+'">'+(a<0.05?'No change':(d.delta>0?'\u25b2 ':'\u25bc ')+n1(a))+'<small>since '+fshort(d.delta_since)+'</small></div>'; }
    var stale=(d.age_days||0)>180;
    var html='<button class="back" type="button" data-back>\u2039 Approved list</button>';
    html+='<section class="hero" style="--ap-field:'+field+'"><div class="hd"><div>'
      +'<div class="eyebrow">'+esc(TYPE[d.type]||d.type||'')+' \u00b7 '+esc(COUNTRY[d.country]||d.country||'')+(d.peer_group?' \u00b7 peers: '+esc(d.peer_group.replace(/_/g,' ')):'')+'</div>'
      +'<h2>'+esc(d.name)+'</h2></div>'
      +'<span class="pill '+bandClass(band)+'"><i></i>'+(unscored?'Not scored':'Band '+esc(band))+'</span></div>';
    if(unscored){
      html+='<div class="unscored">'+esc(d.unscored||'Not enough published figures to score.')+' The ratings and whatever figures exist are below; treat this name on those alone.</div>';
    } else {
      html+='<div class="figures"><div><div class="lbl">Counterparty score</div><div class="score"><span class="n">'+n1(d.score)+'</span><span class="of">/ 100</span></div>'+delta+'</div><div>'+sparkline(d)+'</div></div>';
    }
    html+='<div class="asof"><span>Figures as of <b>'+fdate(d.asof)+'</b>'+(d.age_days!=null?' <span class="'+(stale?'stale':'')+'">('+d.age_days+' days old'+(stale?' \u2014 check for a newer disclosure':'')+')</span>':'')+'</span>'
      +(d.basis?'<span>'+esc(d.basis)+' basis</span>':'')+(d.coverage!=null&&d.coverage<1?'<span>coverage '+Math.round(d.coverage*100)+'%</span>':'')+'</div></section>';

    // ratings
    // The three agencies a treasury management strategy names. Others are in the full profile.
    var ORD=['fitch','sp','moodys'], rk=function(a){return ORD.indexOf(a.agency)};
    var rts=(d.ratings||[]).filter(function(r){return rk(r)>-1}).sort(function(a,b){return rk(a)-rk(b)});
    html+='<section class="sec"><h3>Ratings <span>'+(d.rating_composite?'composite '+esc(d.rating_composite)+(d.sovereign&&d.sovereign.composite?' \u00b7 sovereign '+esc(d.sovereign.composite):'')+' \u00b7 ':'')+(rts.length?'as published in the ESMA register':'')+'</span></h3>';
    if(!rts.length) html+='<div class="none">No public rating from Fitch, S&amp;P or Moody\u2019s.</div>';
    else html+='<div class="ratings">'+rts.map(function(r){ return '<div class="rt"><span class="ag">'+esc(AG[r.agency]||r.agency)+'</span><span class="v">'+esc(r.value)+'</span><span class="o">'+(r.outlook?esc(r.outlook)+' outlook':'&nbsp;')+'</span><span class="d">'+fdate(r.date)+'</span></div>'; }).join('')
      +'</div>';
    html+='</section>';

    // capital & liquidity
    var pr=d.peer_ratios||{}, pn=(pr.cet1_ratio&&pr.cet1_ratio.n)||(d.peer&&d.peer.n)||'';
    var tr=d.trend||{}, levMin=d.country==='GB'?3.25:3.0;
    html+='<section class="sec"><h3>Capital and liquidity <span>'+(pn?'against '+pn+' peers':'')+'</span></h3><div class="cap">'
      +tile('CET1 ratio','core capital as a share of risk-weighted assets',d.cet1,'%',pr.cet1_ratio,tr.cet1_ratio,4.5,'before buffers')
      +tile('Leverage ratio','capital as a share of all exposure, unweighted',d.leverage,'%',pr.leverage_ratio,tr.leverage_ratio,levMin,d.country==='GB'?'(UK)':'(Basel)')
      +tile('Liquidity coverage','liquid assets against 30 days of stress',d.lcr,'%',pr.lcr,tr.lcr,100,'')
      +tile('Stable funding','funding that will still be there in a year',d.nsfr,'%',pr.nsfr,tr.nsfr,100,'')
      +'</div><div class="capnote">Higher is better for all four. A figure is judged against the regulator\u2019s minimum first, then against the '+(pn?pn+' ':'')+'names in the same peer group. The dotted line on a trend is the minimum, where it is close enough to show.</div></section>';

    // what changed
    var evs=(d.events||[]).filter(function(e){ if(e.type!=='rating') return true; var s=String(e.title||'').toLowerCase(); return /fitch|s&p|standard ?& ?poor|moody/.test(s); }).slice(0,6);
    html+='<section class="sec"><h3>What has happened <span>rating actions and judged headlines</span></h3>';
    if(!evs.length) html+='<div class="none">Nothing recorded in the last year.</div>';
    else html+='<ul class="ev">'+evs.map(function(e){ var sev=e.severity||'info'; var t=e.url&&/^https?:/.test(e.url)?'<a href="'+esc(e.url)+'" target="_blank" rel="noopener">'+esc(e.title)+'</a>':esc(e.title);
      return '<li><span class="d">'+fdate(e.date)+'</span><span class="sev '+esc(sev)+'">'+esc(sev)+'</span><div><div class="t">'+t+'</div><div class="s">'+esc(e.type==='rating'?'Rating action':(e.source||''))+'</div></div></li>'; }).join('')+'</ul>';
    html+='</section>';

    // context
    html+='<section class="sec"><h3>Context</h3><div class="ctx">'
      +'<div class="kv"><div class="k">Sovereign</div><div class="v">'+(d.sovereign?esc(d.sovereign.name)+' <small>'+esc(d.sovereign.composite||'')+'</small>':'\u2014')+'</div></div>'
      +'<div class="kv"><div class="k">Within its peer group</div><div class="v">'+(d.percentile!=null&&!unscored?esc(d.percentile)+'<small>th percentile of '+esc((d.peer&&d.peer.n)||'')+'</small>':'\u2014')+'</div></div>'
      +'<div class="kv"><div class="k">Peer median score</div><div class="v">'+(d.peer&&d.peer.p50!=null?n1(d.peer.p50):'\u2014')+'</div></div>'
      +(d.group?'<div class="kv"><div class="k">Part of</div><div class="v">'+esc(d.group)+'</div></div>':'')+'</div></section>';

    // market, small
    var mp=d.market_public;
    if(mp&&(mp.vol30!=null||(d.spark&&d.spark.length>1))){
      html+='<section class="sec"><h3>Market signal <span>context, not an input to the score</span></h3><div class="mkt"><div class="stats">'
        +'<div class="kv"><div class="k">Read</div><div class="v">'+esc(mp.label||'\u2014')+'</div></div>'
        +(mp.vol30!=null?'<div class="kv"><div class="k">30-day volatility</div><div class="v">'+n1(mp.vol30)+'<small>%</small></div></div>':'')
        +(mp.drawdown52!=null?'<div class="kv"><div class="k">From 52-week high</div><div class="v">'+n1(mp.drawdown52)+'<small>%</small></div></div>':'')
        +(mp.bond_change30!=null?'<div class="kv"><div class="k">Bond spread, 30 days</div><div class="v">'+(mp.bond_change30>0?'+':'')+n1(mp.bond_change30)+'<small> bp</small></div></div>':'')
        +'</div><div>'+pspark(d.spark)+(mp.last_price_date?'<div class="lbl" style="margin-top:4px">'+(d.price_currency?esc(d.price_currency)+' \u00b7 ':'')+'to '+fdate(mp.last_price_date)+'</div>':'')+'</div></div></section>';
    }

    // how the score is built
    if(d.pillars&&!unscored){
      var order=['rating','capital','liquidity','asset_quality','profitability','stability'];
      html+='<details class="how"><summary>How the score is built</summary><div class="pil">'
        +order.filter(function(k){return d.pillars[k]}).map(function(k){ var p=d.pillars[k]; return '<div class="p"><span>'+esc(PILLAR[k])+'<small>'+p[1]+'% weight</small></span><div class="bar"><i style="width:'+Math.max(0,Math.min(100,p[0])).toFixed(0)+'%"></i></div><span class="n">'+Math.round(p[0])+'</span></div>'; }).join('')
        +'<div class="note">Each pillar is scored 0\u2013100 against the whole universe and weighted as shown. '+(d.overlay?'A market overlay of '+n1(d.overlay)+' points is applied on top. ':'')+(d.inherited&&d.inherited.length?'Inherited from the group: '+esc(d.inherited.join(', ').replace(/_/g,' '))+'.':'')+'</div></div></details>';
    }

    html+='<div class="afoot"><div class="src">Capital: Pillar 3 disclosure'+(d.asof?', '+fdate(d.asof):'')+' \u00b7 Ratings: ESMA European Rating Platform \u00b7 Prices: Yahoo Finance \u00b7 Headlines: Google News, judged by hand</div>'
      +'<div class="acts"><a href="'+ROOT+'banks/'+esc(d.id)+'.html">Full profile \u2192</a><button type="button" data-remove="'+esc(d.id)+'">Remove from list</button></div></div>';
    return html;
  }

  function welcome(){
    return '<div class="welcome"><h2>Build your approved list</h2><p>Add the counterparties your treasury management strategy allows. Each one gets a card: the score and how it has moved, the ratings as published, the capital figures against peers, and anything that has happened.</p>'
      +'<div class="cta"><button class="btn" type="button" data-focus-search>Add a counterparty</button><button class="btn ghost" type="button" data-example>Load an example list</button></div></div>';
  }

  function skelRows(n){ var s=''; for(var i=0;i<n;i++) s+='<div class="skel-row" aria-hidden="true"><span class="skel"></span><span class="skel" style="width:'+(55+((i*37)%35))+'%"></span><span class="skel" style="width:60%;justify-self:end"></span><span class="skel" style="width:70%;justify-self:end"></span></div>'; return s; }
  function skelCard(){
    return '<div class="sk-card" aria-busy="true" aria-label="Loading">'
      +'<div class="sk-hero"><span class="skel" style="width:38%;height:12px"></span><span class="skel" style="width:60%;height:34px"></span><span class="skel" style="width:120px;height:56px;margin-top:8px"></span><span class="skel" style="width:45%;height:12px"></span></div>'
      +'<div class="sk-sec"><span class="skel" style="width:120px;height:11px"></span><div class="sk-grid"><span class="skel"></span><span class="skel"></span><span class="skel"></span></div></div>'
      +'<div class="sk-sec"><span class="skel" style="width:180px;height:11px"></span><div class="sk-2"><span class="skel"></span><span class="skel"></span><span class="skel"></span><span class="skel"></span></div></div></div>';
  }
  var skelTimer=null;
  function show(id,push){
    current=id; renderList();
    if(state.compare){ renderCompare(); return; }
    clearTimeout(skelTimer);
    if(!id){ detail.innerHTML=welcome(); app.classList.remove('showing'); return; }
    app.classList.add('showing');
    var bar=detail.querySelector('.loading-bar'); if(!bar){ bar=document.createElement('div'); bar.className='loading-bar'; detail.prepend(bar); }
    var el=detail.querySelector('.acard'); if(el) el.classList.add('fade');
    if(!cache[id]){
      // A thin bar at once; the skeleton only if the fetch is slow enough to be noticed.
      bar.classList.add('on');
      skelTimer=setTimeout(function(){ if(current===id&&!cache[id]) detail.innerHTML='<div class="loading-bar on"></div>'+skelCard(); },180);
    }
    fetchBank(id).then(function(d){
      if(current!==id) return;
      clearTimeout(skelTimer);
      detail.innerHTML='<div class="loading-bar"></div><div class="acard fade">'+card(d)+'</div>';
      detail.scrollTop=0;
      requestAnimationFrame(function(){ var c=detail.querySelector('.acard'); if(c) c.classList.remove('fade'); });
      if(push!==false&&location.hash!=='#'+id) history.replaceState(null,'','#'+id);
      prefetch();
    }).catch(function(){ clearTimeout(skelTimer); detail.innerHTML='<div class="acard"><p class="none">Could not load '+esc(id)+'. Check the connection and try again.</p></div>'; });
  }

  // ---------- actions ----------
  function add(id){ if(!byId[id]||state.ids.indexOf(id)>-1) return; state.ids.push(id); state.example=false; save(); q=''; qEl.value=''; show(id); }
  function remove(id){ var i=state.ids.indexOf(id); if(i<0) return; state.ids.splice(i,1); state.example=false; save(); var rs=rows(); show(rs[Math.min(i,rs.length-1)]?rs[Math.min(i,rs.length-1)].id:null); }
  function move(dir){ var rs=rows(); if(!rs.length) return; var i=rs.findIndex(function(r){return r.id===current}); var j=Math.max(0,Math.min(rs.length-1,i+dir)); if(rs[j]&&rs[j].id!==current){ show(rs[j].id); var el=list.querySelector('[data-id="'+rs[j].id+'"]'); if(el) el.scrollIntoView({block:'nearest'}); } }
  function toast(msg,link){ var t=document.createElement('div'); t.className='toast'; t.innerHTML=esc(msg)+(link?'<input type="text" readonly value="'+esc(link)+'" aria-label="Link">':''); document.body.appendChild(t); if(link){ var i=t.querySelector('input'); i.focus(); i.select(); } setTimeout(function(){ t.remove(); }, link?9000:2200); }
  function share(){
    var url=location.href.split('#')[0]+'#list='+state.ids.join(',');
    if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(url).then(function(){ toast('Link copied. Anyone who opens it gets this list.'); },function(){ toast('Copy this link:',url); }); }
    else toast('Copy this link:',url);
  }

  list.addEventListener('click',function(e){
    var a=e.target.closest('a'); if(!a) return; e.preventDefault();
    if(a.dataset.add) add(a.dataset.add);
    else if(a.dataset.id){ if(state.compare) toggleSel(a.dataset.id); else show(a.dataset.id); }
  });
  $('#cmp').addEventListener('click',function(){ setCompare(!state.compare); });
  detail.addEventListener('click',function(e){
    var b=e.target.closest('[data-remove],[data-back],[data-focus-search],[data-example],[data-unsel]'); if(!b) return;
    if(b.dataset.unsel!=null){ toggleSel(b.dataset.unsel); }
    else if(b.dataset.remove!=null){ if(confirm('Remove '+(byId[b.dataset.remove]||{}).short+' from your approved list?')) remove(b.dataset.remove); }
    else if(b.dataset.back!=null){ app.classList.remove('showing'); }
    else if(b.dataset.focusSearch!=null){ qEl.focus(); }
    else if(b.dataset.example!=null){ state.ids=EXAMPLE.filter(function(id){return byId[id]}); state.example=true; save(); show(rows()[0].id); }
  });
  $('#foot').addEventListener('click',function(e){ var a=e.target.closest('[data-clear]'); if(!a) return; e.preventDefault(); state.ids=[]; state.example=false; save(); show(null); });
  qEl.addEventListener('input',function(){ q=qEl.value; renderList(); });
  qEl.addEventListener('keydown',function(e){
    if(e.key==='Escape'){ q=''; qEl.value=''; renderList(); qEl.blur(); }
    if(e.key==='Enter'){ var first=list.querySelector('.row'); if(first){ e.preventDefault(); if(first.dataset.add) add(first.dataset.add); else show(first.dataset.id); } }
    if(e.key==='ArrowDown'){ e.preventDefault(); var f=list.querySelector('.row'); if(f) f.focus(); }
  });
  $('#sort').addEventListener('change',function(){ state.sort=this.value; save(); renderList(); });
  $('#group').addEventListener('change',function(){ state.group=this.checked; save(); renderList(); });
  $('#share').addEventListener('click',share);
  document.addEventListener('keydown',function(e){
    var inField=/^(INPUT|TEXTAREA|SELECT)$/.test((e.target.tagName||''));
    if(e.key==='/'&&!inField){ e.preventDefault(); qEl.focus(); qEl.select(); }
    if((e.key==='ArrowDown'||e.key==='ArrowUp')&&!inField&&!state.compare){ e.preventDefault(); move(e.key==='ArrowDown'?1:-1); }
    if(e.key==='Escape'&&!inField&&window.innerWidth<=760){ app.classList.remove('showing'); }
  });
  window.addEventListener('hashchange',function(){ var id=location.hash.slice(1); if(byId[id]&&id!==current&&!state.compare) show(id,false); });

  // ---------- boot ----------
  list.innerHTML=skelRows(12); detail.innerHTML=skelCard();
  fetch(ROOT+'data/approved/list.json').then(function(r){return r.json()}).then(function(j){
    all=j.rows; window.__generated=j.generated; all.forEach(function(r){byId[r.id]=r});
    var had=load(), fromLink=linkIds();
    if(fromLink&&fromLink.length){
      var valid=fromLink.filter(function(id){return byId[id]});
      if(!had||!state.ids.length||confirm('This link carries a list of '+valid.length+' counterparties. Replace yours with it?')){ state.ids=valid; state.example=false; save(); }
      history.replaceState(null,'',location.pathname+location.search);
    }
    if(!state.ids.length&&!had){
      var w=policyIds().concat(watchIds()).filter(function(id,i,a){return byId[id]&&a.indexOf(id)===i});
      if(w.length){ state.ids=w; save(); }
      else { state.ids=EXAMPLE.filter(function(id){return byId[id]}); state.example=true; }
    }
    $('#sort').value=state.sort; $('#group').checked=state.group;
    var cm=/^#cmp=([^&]+)/.exec(location.hash);
    if(cm){ var cids=cm[1].split(',').filter(function(id){return byId[id]}).slice(0,MAXSEL);
      cids.forEach(function(id){ if(state.ids.indexOf(id)<0){ state.ids.push(id); state.example=false; } }); save();
      $('#sort').value=state.sort; $('#group').checked=state.group; current=cids[0]||null; state.sel=cids; setCompare(true); return; }
    var want=location.hash.slice(1);
    if(byId[want]&&state.ids.indexOf(want)<0){ state.ids.push(want); state.example=false; save(); }
    var first=rows()[0];
    if(byId[want]) show(want,false); else if(first){ show(first.id,false); if(window.innerWidth<=760) app.classList.remove('showing'); } else show(null);
  }).catch(function(){ $('#count').textContent='Could not load the data.'; detail.innerHTML='<div class="welcome"><h2>Could not load the data</h2><p>Reload the page to try again.</p></div>'; });
})();
