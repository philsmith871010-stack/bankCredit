// Compare: a peer set against a measure, four ways. Charts fill their container and redraw on resize.
// Up to six names are pinned and carry fixed colours (assigned in pin order, kept while pinned); the rest
// are thin grey context. A crosshair reads every pinned series at one date. State lives in the URL hash.
(function(){
  var dash=document.getElementById('dash');if(!dash)return;
  // running as a tab, the state it writes has to keep the tab in front of it, or a reload
  // lands on the first tab with the analysis state in the address bar
  var panelId=((dash.closest&&dash.closest('.panel[data-panel]'))||{dataset:{}}).dataset.panel||'';var chart=null;var PANELS={rank:'c-rank',trend:'c-trend',bump:'c-bump',scatter:'c-scatter'};
  var ylab={hidden:false},side={innerHTML:''},pinsBar=document.getElementById('cp-pins'),tableEl=document.getElementById('c-table'),count=document.getElementById('cp-count'),sel=document.getElementById('cp-metric'),sel2=document.getElementById('cp-metric2'),q=document.getElementById('cp-q'),sugg=document.getElementById('cp-sugg');
  var NAVY='#0a2540',GREY='#d3dae3',MID='#7d93ad',INK='#243240',MUTED='#6c757d';
  var SLOTS=['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300'];   // validated categorical order; never cycled past six
  var D=null,byId={},state={set:'uk_large',extra:[],metric:'score',metric2:'cet1_ratio',view:'rank',pins:[],sort:'score',dir:'desc'},userPinned=false,tipEl=null;
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function ls(k){try{return JSON.parse(localStorage.getItem(k)||'[]')}catch(e){return[]}}
  function watchIds(){return ls('counterparty.watch')}
  function policyIds(){return ls('counterparty.policy').map(function(x){return x.id})}
  function readHash(){var h=location.hash.replace('#','');if(!h)return;h.split('&').forEach(function(kv){var p=kv.split('=');var k=p[0],v=decodeURIComponent(p[1]||'');if(k==='extra'||k==='pins'){state[k]=v?v.split(','):[];if(k==='pins')userPinned=true}else if(k in state&&k!=='pins'&&k!=='extra')state[k]=v})}
  function writeHash(){var parts=(panelId?[panelId]:[]).concat(['set='+state.set,'metric='+state.metric,'metric2='+state.metric2]);if(state.extra.length)parts.push('extra='+state.extra.join(','));if(userPinned&&state.pins.length)parts.push('pins='+state.pins.join(','));history.replaceState(null,'','#'+parts.join('&'))}
  // the definition marker beside the measure picker follows whatever is chosen
  var GK={score:'score',rating_grade:'composite',cet1_ratio:'cet1_ratio',leverage_ratio:'leverage_ratio',
          total_capital_ratio:'total_capital_ratio',lcr:'lcr',nsfr:'nsfr',roe:'roe',roa:'roa',nim:'nim',
          efficiency_ratio:'cost_to_income',npl_ratio:'npl_ratio',cost_of_risk:'cost_of_risk',total_assets:'total_assets'};
  function markMeasure(code){var b=document.getElementById('cp-def');if(!b)return;
    var k=GK[code];b.hidden=!k;if(k)b.dataset.t=k}
  function metric(code){for(var i=0;i<D.metrics.length;i++)if(D.metrics[i][0]===code)return D.metrics[i];return D.metrics[0]}
  function members(){var ids;
    if(state.set==='all')ids=D.rows.map(function(r){return r.id});
    else if(state.set==='watch')ids=watchIds();else if(state.set==='policy')ids=policyIds();
    else ids=D.rows.filter(function(r){return r.peer_group===state.set}).map(function(r){return r.id});
    state.extra.forEach(function(id){if(ids.indexOf(id)<0)ids.push(id)});
    return ids.map(function(id){return byId[id]}).filter(Boolean)}
  function marked(){var m={};watchIds().concat(policyIds()).forEach(function(id){m[id]=1});return m}
  function latest(r,code){if(code==='score')return r.score==null?null:{d:D.generated.slice(0,10),v:r.score};if(code==='rating_grade')return r.grade==null?null:{d:D.generated.slice(0,10),v:r.grade};var s=r.series[code];return s&&s.length?{d:s[s.length-1][0],v:s[s.length-1][1]}:null}
  function fmt(v,m){if(v==null)return '—';var dp=m[3];if(m[0]==='total_assets')return v>=1e6?(v/1e6).toFixed(2)+'tn':v>=1000?(v/1000).toFixed(0)+'bn':v.toFixed(0)+'m';return v.toFixed(dp)+(m[2]==='%'?'%':'')}
  function median(a){if(!a.length)return null;var s=a.slice().sort(function(x,y){return x-y}),n=s.length;return n%2?s[(n-1)/2]:(s[n/2-1]+s[n/2])/2}
  function niceTicks(lo,hi,n){if(lo===hi){lo-=1;hi+=1}var span=hi-lo,raw=span/(n-1),mag=Math.pow(10,Math.floor(Math.log10(raw))),norm=raw/mag,step=(norm<1.5?1:norm<3?2:norm<7?5:10)*mag;var t0=Math.floor(lo/step)*step,out=[];for(var v=t0;v<hi+step;v+=step)out.push(+v.toFixed(10));if(out[out.length-1]<hi)out.push(+(out[out.length-1]+step).toFixed(10));return out}
  function qEnd(d){var y=+d.slice(0,4),m=+d.slice(5,7),qm=Math.ceil(m/3)*3;var last=new Date(Date.UTC(y,qm,0)).getUTCDate();return y+'-'+(qm<10?'0':'')+qm+'-'+last}
  function daysBetween(a,b){return (Date.parse(b)-Date.parse(a))/864e5}
  function atBucket(r,code,b){var s=r.series[code]||[],best=null;for(var i=0;i<s.length;i++){if(s[i][0]<=b&&daysBetween(s[i][0],b)<=400)best=s[i][1]}return best}
  function buckets(rows,code,n){var set={};rows.forEach(function(r){(r.series[code]||[]).forEach(function(p){set[qEnd(p[0])]=1})});return Object.keys(set).sort().slice(-n)}
  function link(r){return '<a href="../banks/'+r.id+'.html">'+esc(r.short)+'</a>'}
  function W(){return Math.max(300,chart.clientWidth-2)}
  function svgOpen(w,h){return '<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" style="display:block;max-width:100%" font-family="inherit" font-size="12">'}
  function colourOf(id){var i=state.pins.indexOf(id);return i>=0&&i<SLOTS.length?SLOTS[i]:null}
  function swatch(id){var c=colourOf(id);return '<i class="sw" style="'+(c?'background:'+c:'border:1.5px solid #c3cbd5')+'"></i>'}
  function defaultPins(rows,m){if(userPinned)return;var mk=marked(),vals=rows.map(function(r){return{r:r,p:latest(r,m[0])}}).filter(function(x){return x.p&&x.p.v!=null});
    vals.sort(function(a,b){return m[4]?b.p.v-a.p.v:a.p.v-b.p.v});
    var pins=rows.filter(function(r){return mk[r.id]}).map(function(r){return r.id});
    vals.forEach(function(x){if(pins.length<3&&pins.indexOf(x.r.id)<0)pins.push(x.r.id)});
    state.pins=pins.slice(0,SLOTS.length)}
  function togglePin(id){var i=state.pins.indexOf(id);if(i>=0)state.pins.splice(i,1);else if(state.pins.length<SLOTS.length)state.pins.push(id);else{state.pins.shift();state.pins.push(id)}userPinned=true;render()}
  function xLabels(bs,X,y,w){var out='',lastX=-99;bs.forEach(function(b,i){var x=X(i);if((i%Math.ceil(bs.length/Math.max(4,Math.floor(w/110)))===0||i===bs.length-1)&&x-lastX>70){lastX=x;out+='<text x="'+x.toFixed(0)+'" y="'+y+'" text-anchor="middle" fill="'+MUTED+'" font-size="11">'+b.slice(0,7)+'</text>'}});return out}
  function tip(){var t=chart.querySelector('.cp-tip');if(!t){t=document.createElement('div');t.className='cp-tip';t.hidden=true;chart.appendChild(t)}return t}
  function placeTip(x,y,html){var t=tip();t.innerHTML=html;t.hidden=false;var r=chart.getBoundingClientRect();var left=x-r.left+14,top=y-r.top+12;if(left+t.offsetWidth>chart.clientWidth-8)left=x-r.left-t.offsetWidth-14;t.style.left=left+'px';t.style.top=top+'px'}
  function hideTip(){var t=chart&&chart.querySelector('.cp-tip');if(t)t.hidden=true}

  // ---------- ranking ----------
  function renderRank(rows,m){var vals=rows.map(function(r){return{r:r,p:latest(r,m[0])}}).filter(function(x){return x.p&&x.p.v!=null});
    vals.sort(function(a,b){return m[4]?b.p.v-a.p.v:a.p.v-b.p.v});
    if(!vals.length){chart.innerHTML='<div class="empty">No figures for this measure in the set.</div>';side.innerHTML='';return}
    var vs=vals.map(function(x){return x.p.v}),lo=Math.min(0,Math.min.apply(null,vs)),hi=Math.max.apply(null,vs),med=median(vs);
    var w=W(),rowH=26,left=Math.min(220,Math.max(140,w*0.22)),right=90,barW=w-left-right,H=vals.length*rowH+34;
    var sc=function(v){return left+(v-lo)/((hi-lo)||1)*barW};
    var out=svgOpen(w,H);
    out+='<line x1="'+sc(med).toFixed(0)+'" x2="'+sc(med).toFixed(0)+'" y1="20" y2="'+(H-8)+'" stroke="'+INK+'" stroke-dasharray="3 3" opacity=".5"/><text x="'+sc(med).toFixed(0)+'" y="13" text-anchor="middle" fill="'+INK+'" font-size="11">median '+fmt(med,m)+'</text>';
    vals.forEach(function(x,i){var y=26+i*rowH,c=colourOf(x.r.id);
      out+='<a href="../banks/'+x.r.id+'.html"><text data-id="'+x.r.id+'" class="cp-lbl" x="'+(left-10)+'" y="'+(y+14)+'" text-anchor="end" fill="'+(c||INK)+'" font-weight="'+(c?'700':'500')+'">'+esc(x.r.short.slice(0,28))+'</text></a>';
      out+='<rect class="cp-bar" data-id="'+x.r.id+'" x="'+sc(Math.max(lo,Math.min(0,x.p.v))).toFixed(0)+'" y="'+(y+4)+'" width="'+Math.max(1,Math.abs(sc(x.p.v)-sc(Math.max(lo,0)))).toFixed(0)+'" height="'+(rowH-9)+'" rx="4" fill="'+(c||MID)+'" fill-opacity="'+(c?1:0.55)+'"><title>'+esc(x.r.name)+': '+fmt(x.p.v,m)+' at '+x.p.d+'</title></rect>';
      out+='<text x="'+(sc(Math.max(x.p.v,0))+8).toFixed(0)+'" y="'+(y+14)+'" fill="'+INK+'" font-family="ui-monospace,monospace" font-size="12">'+fmt(x.p.v,m)+'</text>'});
    chart.innerHTML=out+'</svg>';
    }

  // ---------- legend / side list ----------
  function legend(items,m,hint){return '<div class="card pad cp-legend"><h4>Names <span class="muted small">· '+esc(hint)+'</span></h4>'+items.map(function(o){var c=colourOf(o.r.id);return '<div class="lg'+(c?' on':'')+'" data-id="'+o.r.id+'"><button class="pin" data-id="'+o.r.id+'" title="'+(c?'Unpin':'Pin')+'">'+swatch(o.r.id)+'</button><span class="nm">'+link(o.r)+'</span><span class="mono">'+fmt(o.v,m)+'</span><span class="small '+(o.cls||'muted')+'">'+(o.sub||'')+'</span></div>'}).join('')+'</div>'}

  // ---------- trends ----------
  function renderTrend(rows,m){var code=m[0],bs=buckets(rows,code,24);
    if(!bs.length){chart.innerHTML='<div class="empty">No history for this measure in the set.</div>';side.innerHTML='';return}
    var lines=rows.map(function(r){return{r:r,pts:bs.map(function(b){return atBucket(r,code,b)})}}).filter(function(l){return l.pts.some(function(v){return v!=null})});
    var med=bs.map(function(b,i){return median(lines.map(function(l){return l.pts[i]}).filter(function(v){return v!=null}))});
    var all=[];lines.forEach(function(l){l.pts.forEach(function(v){if(v!=null)all.push(v)})});
    var ticks=niceTicks(Math.min.apply(null,all),Math.max.apply(null,all),6),lo=ticks[0],hi=ticks[ticks.length-1];
    var w=W(),H=Math.max(340,Math.min(480,Math.round(w*0.36))),L=54,R=Math.min(170,Math.max(120,w*0.16)),T=16,B=32;
    var X=function(i){return L+i*(w-L-R)/Math.max(1,bs.length-1)},Y=function(v){return T+(hi-v)/(hi-lo)*(H-T-B)};
    var out=svgOpen(w,H);
    ticks.forEach(function(v){out+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+Y(v).toFixed(0)+'" y2="'+Y(v).toFixed(0)+'" stroke="#eef1f4"/><text x="'+(L-8)+'" y="'+(Y(v)+4).toFixed(0)+'" text-anchor="end" fill="'+MUTED+'" font-size="11">'+fmt(v,m)+'</text>'});
    out+=xLabels(bs,X,H-10,w);
    var path=function(pts){var d='',on=false;pts.forEach(function(v,i){if(v==null){on=false;return}d+=(on?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1);on=true});return d};
    lines.filter(function(l){return !colourOf(l.r.id)}).forEach(function(l){out+='<path class="cp-line" data-id="'+l.r.id+'" d="'+path(l.pts)+'" fill="none" stroke="'+GREY+'" stroke-width="1.4"/>'});
    out+='<path d="'+path(med)+'" fill="none" stroke="'+INK+'" stroke-width="2" stroke-dasharray="5 4" opacity=".75"/>';
    var labels=[];var mi=med.length-1;while(mi>0&&med[mi]==null)mi--;if(med[mi]!=null)labels.push({y:Y(med[mi]),t:'median',c:INK,w:'600'});
    lines.filter(function(l){return colourOf(l.r.id)}).forEach(function(l){var c=colourOf(l.r.id);out+='<path class="cp-line on" data-id="'+l.r.id+'" d="'+path(l.pts)+'" fill="none" stroke="'+c+'" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>';
      var li=l.pts.length-1;while(li>=0&&l.pts[li]==null)li--;if(li>=0){out+='<circle cx="'+X(li).toFixed(1)+'" cy="'+Y(l.pts[li]).toFixed(1)+'" r="4" fill="'+c+'" stroke="#fff" stroke-width="2"/>';labels.push({y:Y(l.pts[li]),t:l.r.short.slice(0,20),c:c,w:'600'})}});
    labels.sort(function(a,b){return a.y-b.y});var used=[];labels.forEach(function(lb){var y=lb.y;while(used.some(function(u){return Math.abs(u-y)<13}))y+=13;used.push(y);out+='<text x="'+(w-R+8)+'" y="'+(y+4).toFixed(0)+'" fill="'+lb.c+'" font-weight="'+lb.w+'" font-size="11.5">'+esc(lb.t)+'</text>'});
    out+='<line id="cp-hair" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+'" stroke="'+INK+'" stroke-width="1" opacity="0" pointer-events="none"/>';
    out+='<rect x="'+L+'" y="'+T+'" width="'+(w-L-R)+'" height="'+(H-T-B)+'" fill="transparent" id="cp-hit"/>';
    chart.innerHTML=out+'</svg>';
    var first=function(l){for(var i=0;i<l.pts.length;i++)if(l.pts[i]!=null)return l.pts[i];return null};
    var items=lines.map(function(l){var li=l.pts.length-1;while(li>=0&&l.pts[li]==null)li--;var f=first(l),ch=(f==null||li<0)?null:l.pts[li]-f;return{r:l.r,v:li>=0?l.pts[li]:null,ch:ch,sub:ch==null?'':((ch>=0?'+':'')+ch.toFixed(m[3])+' since '+bs[0].slice(0,4)),cls:ch==null?'muted':((ch>=0)===m[4]?'good':'bad')}}).sort(function(a,b){return (b.v||-1e9)-(a.v||-1e9)});
    lines._items=items;
    // crosshair and readout
    var hit=document.getElementById('cp-hit'),hair=document.getElementById('cp-hair'),byId2={};lines.forEach(function(l){byId2[l.r.id]=l});
    chart.onmousemove=function(e){var p=e.target.closest('.cp-line');var rect=chart.querySelector('svg').getBoundingClientRect();var sx=(e.clientX-rect.left)*(w/rect.width);
      if(p&&!p.classList.contains('on')){var l=byId2[p.dataset.id];document.querySelectorAll('.cp-line.hot').forEach(function(x){x.classList.remove('hot')});p.classList.add('hot');var li=l.pts.length-1;while(li>=0&&l.pts[li]==null)li--;placeTip(e.clientX,e.clientY,'<b>'+esc(l.r.short)+'</b> '+fmt(l.pts[li],m)+' <span class="muted">'+bs[li].slice(0,7)+'</span>');hair.setAttribute('opacity','0');return}
      document.querySelectorAll('.cp-line.hot').forEach(function(x){x.classList.remove('hot')});
      if(sx<L||sx>w-R){hideTip();hair.setAttribute('opacity','0');return}
      var i=Math.round((sx-L)/((w-L-R)/Math.max(1,bs.length-1)));i=Math.max(0,Math.min(bs.length-1,i));
      hair.setAttribute('x1',X(i).toFixed(1));hair.setAttribute('x2',X(i).toFixed(1));hair.setAttribute('opacity','.35');
      var rowsT=state.pins.map(function(id){return byId2[id]}).filter(function(l){return l&&l.pts[i]!=null}).sort(function(a,b){return b.pts[i]-a.pts[i]});
      var html='<div class="tt-h">'+bs[i].slice(0,7)+'</div>'+rowsT.map(function(l){return '<div><i class="sw" style="background:'+colourOf(l.r.id)+'"></i>'+esc(l.r.short)+'<span class="mono">'+fmt(l.pts[i],m)+'</span></div>'}).join('')+(med[i]!=null?'<div class="tt-med">median<span class="mono">'+fmt(med[i],m)+'</span></div>':'');
      placeTip(e.clientX,e.clientY,html)};
    chart.onmouseleave=function(){hideTip();hair.setAttribute('opacity','0');document.querySelectorAll('.cp-line.hot').forEach(function(x){x.classList.remove('hot')})}}

  // ---------- rank over time ----------
  function renderBump(rows,m){var code=m[0],bs=buckets(rows,code,16);if(bs.length<2){chart.innerHTML='<div class="empty">Not enough history in the set.</div>';side.innerHTML='';return}
    var lines=rows.map(function(r){return{r:r,pts:bs.map(function(b){return atBucket(r,code,b)}),rank:[]}}).filter(function(l){return l.pts.some(function(v){return v!=null})});
    bs.forEach(function(b,i){var have=lines.filter(function(l){return l.pts[i]!=null}).sort(function(a,b){return m[4]?b.pts[i]-a.pts[i]:a.pts[i]-b.pts[i]});lines.forEach(function(l){l.rank[i]=null});have.forEach(function(l,k){l.rank[i]=k+1})});
    var n=lines.length,w=W(),H=Math.max(260,Math.min(600,n*22+50)),L=36,R=Math.min(190,Math.max(130,w*0.17)),T=18,B=30,X=function(i){return L+i*(w-L-R)/(bs.length-1)},Y=function(rk){return T+(rk-1)/Math.max(1,n-1)*(H-T-B)};
    var out=svgOpen(w,H)+xLabels(bs,X,H-8,w);
    var path=function(rk){var d='',on=false;rk.forEach(function(v,i){if(v==null){on=false;return}d+=(on?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1);on=true});return d};
    var lastR=function(l){for(var i=l.rank.length-1;i>=0;i--)if(l.rank[i]!=null)return l.rank[i];return null};
    lines.filter(function(l){return !colourOf(l.r.id)}).concat(lines.filter(function(l){return colourOf(l.r.id)})).forEach(function(l){var c=colourOf(l.r.id),lr=lastR(l);
      out+='<path class="cp-line'+(c?' on':'')+'" data-id="'+l.r.id+'" d="'+path(l.rank)+'" fill="none" stroke="'+(c||GREY)+'" stroke-width="'+(c?2.4:1.4)+'" stroke-linejoin="round"><title>'+esc(l.r.name)+'</title></path>';
      l.rank.forEach(function(rk,i){if(rk!=null)out+='<circle cx="'+X(i).toFixed(1)+'" cy="'+Y(rk).toFixed(1)+'" r="'+(c?4:2.5)+'" fill="'+(c||GREY)+'"'+(c?' stroke="#fff" stroke-width="1.5"':'')+'><title>'+esc(l.r.short)+' #'+rk+' at '+bs[i]+' ('+fmt(l.pts[i],m)+')</title></circle>'});
      if(lr!=null&&(c||lr<=8||lr>n-2))out+='<text x="'+(w-R+8)+'" y="'+(Y(lr)+4).toFixed(0)+'" fill="'+(c||MUTED)+'" font-weight="'+(c?'600':'400')+'" font-size="11.5">#'+lr+' '+esc(l.r.short.slice(0,16))+'</text>'});
    chart.innerHTML=out+'</svg>';
    var moves=lines.map(function(l){var f=null,la=null;l.rank.forEach(function(v){if(v!=null){if(f==null)f=v;la=v}});return{r:l.r,v:la,sub:f!=null&&la!=null?('#'+f+' → #'+la+(f-la>0?' · up '+(f-la):f-la<0?' · down '+(la-f):' · level')):'',cls:f!=null&&la!=null?(f-la>0?'good':f-la<0?'bad':'muted'):'muted',ch:(f!=null&&la!=null)?f-la:0}}).sort(function(a,b){return (a.v||99)-(b.v||99)});
    }

  // ---------- two measures ----------
  function renderScatter(rows,m,m2){var pts=rows.map(function(r){return{r:r,a:latest(r,m2[0]),b:latest(r,m[0])}}).filter(function(p){return p.a&&p.b&&p.a.v!=null&&p.b.v!=null});
    if(pts.length<2){chart.innerHTML='<div class="empty">Fewer than two names carry both measures.</div>';side.innerHTML='';return}
    var xs=pts.map(function(p){return p.a.v}),ys=pts.map(function(p){return p.b.v});
    var tx=niceTicks(Math.min.apply(null,xs),Math.max.apply(null,xs),6),ty=niceTicks(Math.min.apply(null,ys),Math.max.apply(null,ys),6);
    var xlo=tx[0],xhi=tx[tx.length-1],ylo=ty[0],yhi=ty[ty.length-1];
    var w=W(),H=Math.max(360,Math.min(520,Math.round(w*0.42))),L=60,R=24,T=26,B=44,X=function(v){return L+(v-xlo)/(xhi-xlo)*(w-L-R)},Y=function(v){return T+(yhi-v)/(yhi-ylo)*(H-T-B)};
    var amax=Math.max.apply(null,pts.map(function(p){return p.r.assets||0}))||1;
    var out=svgOpen(w,H);
    ty.forEach(function(v){out+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+Y(v).toFixed(0)+'" y2="'+Y(v).toFixed(0)+'" stroke="#eef1f4"/><text x="'+(L-8)+'" y="'+(Y(v)+4).toFixed(0)+'" text-anchor="end" fill="'+MUTED+'" font-size="11">'+fmt(v,m)+'</text>'});
    // on a narrow chart six labels run into one another, so only those that clear the last one
    // are drawn: a gap is easier to read than a smudge
    var lastTx=-999;
    tx.forEach(function(u){var x=X(u);if(x-lastTx<46)return;lastTx=x;
      out+='<text x="'+x.toFixed(0)+'" y="'+(H-24)+'" text-anchor="middle" fill="'+MUTED+'" font-size="11">'+fmt(u,m2)+'</text>'});
    out+='<text x="'+((L+w-R)/2).toFixed(0)+'" y="'+(H-6)+'" text-anchor="middle" fill="'+INK+'" font-weight="600" font-size="12">'+esc(m2[1])+' →</text><text x="'+L+'" y="'+(T-3)+'" fill="'+INK+'" font-weight="600" font-size="12">↑ '+esc(m[1])+'</text>';
    var mx=median(xs),my=median(ys);out+='<line x1="'+X(mx).toFixed(0)+'" x2="'+X(mx).toFixed(0)+'" y1="'+T+'" y2="'+(H-B)+'" stroke="'+INK+'" stroke-dasharray="4 4" opacity=".35"/><line x1="'+L+'" x2="'+(w-R)+'" y1="'+Y(my).toFixed(0)+'" y2="'+Y(my).toFixed(0)+'" stroke="'+INK+'" stroke-dasharray="4 4" opacity=".35"/>';
    pts.sort(function(a,b){return (colourOf(a.r.id)?1:0)-(colourOf(b.r.id)?1:0)}).forEach(function(p){var c=colourOf(p.r.id),rad=p.r.assets?5+10*Math.sqrt(p.r.assets/amax):6;
      out+='<a href="../banks/'+p.r.id+'.html"><circle class="cp-dot" data-id="'+p.r.id+'" cx="'+X(p.a.v).toFixed(1)+'" cy="'+Y(p.b.v).toFixed(1)+'" r="'+rad.toFixed(1)+'" fill="'+(c||MID)+'" fill-opacity="'+(c?0.9:0.35)+'" stroke="#fff" stroke-width="1.5"><title>'+esc(p.r.name)+': '+esc(m2[1])+' '+fmt(p.a.v,m2)+', '+esc(m[1])+' '+fmt(p.b.v,m)+'</title></circle></a>';
      if(c||pts.length<=12){var right=X(p.a.v)>w-R-110;out+='<text x="'+(right?X(p.a.v)-rad-4:X(p.a.v)+rad+4).toFixed(0)+'" y="'+(Y(p.b.v)+4).toFixed(0)+'" text-anchor="'+(right?'end':'start')+'" fill="'+(c||MUTED)+'" font-weight="'+(c?'600':'400')+'" font-size="11.5">'+esc(p.r.short.slice(0,18))+'</text>'}});
    chart.innerHTML=out+'</svg>';
    }

  function pinsBarHtml(rows,m){var mk=marked();return '<span class="small muted">Pinned</span>'+state.pins.map(function(id){var r=byId[id];if(!r)return '';var p=latest(r,m[0]);return '<span class="pinchip" data-id="'+id+'" style="--c:'+colourOf(id)+'"><i class="sw" style="background:'+colourOf(id)+'"></i>'+link(r)+'<span class="mono">'+fmt(p&&p.v,m)+'</span>'+(mk[id]?'<span title="watched or in My policy">★</span>':'')+'<button class="pin" data-id="'+id+'" title="Unpin">×</button></span>'}).join('')+(state.pins.length<SLOTS.length?'<span class="small muted">· click any name, bar, line or dot to pin (up to six)</span>':'')}
  var COLS=[['score','Score',1],['band','Band',0],['rating','Rating',0],['cet1_ratio','CET1',1],['leverage_ratio','Leverage',1],['lcr','LCR',0],['nsfr','NSFR',0],['roe','ROE',1],['efficiency_ratio','Cost/income',0],['npl_ratio','NPL',2],['total_assets','Assets',0]];
  function cell(r,code){if(code==='band')return '<td><span class="band mono band-'+esc(r.band||'x')+'">'+esc(r.band||'?')+'</span></td>';if(code==='rating')return '<td>'+(r.rating?'<b>'+esc(r.rating)+'</b>':'<span class="muted">unrated</span>')+'</td>';var p=latest(r,code),m=metric(code);return '<td class="num mono" data-v="'+(p?p.v:-1e9)+'">'+(p?fmt(p.v,m):'<span class="na">—</span>')+'</td>'}
  function sortVal(r,code){if(code==='name')return r.short.toLowerCase();if(code==='band')return r.band||'Z';if(code==='rating')return r.grade==null?99:r.grade;var p=latest(r,code);return p?p.v:-1e9}
  function renderTable(rows){var rs=rows.slice().sort(function(a,b){var x=sortVal(a,state.sort),y=sortVal(b,state.sort);if(typeof x==='string')return state.dir==='asc'?x.localeCompare(y):y.localeCompare(x);return state.dir==='asc'?x-y:y-x});
    var head='<tr><th data-sort="name">Name</th>'+COLS.map(function(c){return '<th class="'+(c[0]==='band'||c[0]==='rating'?'':'num')+(state.sort===c[0]?' sorted':'')+'" data-sort="'+c[0]+'">'+esc(c[1])+(state.sort===c[0]?(state.dir==='asc'?' ▲':' ▼'):'')+'</th>'}).join('')+'</tr>';
    var body=rs.map(function(r){var c=colourOf(r.id);return '<tr data-id="'+r.id+'"'+(c?' class="on" style="--c:'+c+'"':'')+'><td><button class="pin" data-id="'+r.id+'" title="'+(c?'Unpin':'Pin')+'">'+swatch(r.id)+'</button> '+link(r)+'<span class="small muted"> '+esc(r.country)+'</span></td>'+COLS.map(function(c2){return cell(r,c2[0])}).join('')+'</tr>'}).join('');
    tableEl.innerHTML='<table class="plain cp-table"><thead>'+head+'</thead><tbody>'+body+'</tbody></table>'}
  function render(){var rows=members(),m=metric(state.metric);if(state.metric2===state.metric){state.metric2=state.metric==='roe'?'cet1_ratio':'roe';sel2.value=state.metric2}var m2=metric(state.metric2);
    count.textContent=rows.length+' in the set';
    document.querySelectorAll('.cp-set').forEach(function(b){b.classList.toggle('active',b.dataset.set===state.set)});
    var ids={};rows.forEach(function(r){ids[r.id]=1});state.pins=state.pins.filter(function(id){return ids[id]});
    if(!rows.length){var msg='<div class="empty">'+(state.set==='watch'?'You are not watching anyone yet. The star on any profile or board row adds a name.':state.set==='policy'?'My policy is empty. Add counterparties there and they appear here.':'Nothing in this set.')+'</div>';Object.keys(PANELS).forEach(function(k){document.getElementById(PANELS[k]).innerHTML=msg});pinsBar.innerHTML='';tableEl.innerHTML='';writeHash();return}
    defaultPins(rows,m);
    pinsBar.innerHTML=pinsBarHtml(rows,m[0]==='score'?m:m);
    var draws={rank:function(){renderRank(rows,m)},trend:function(){renderTrend(rows,m)},bump:function(){renderBump(rows,m)},scatter:function(){renderScatter(rows,m,m2)}};
    Object.keys(PANELS).forEach(function(k){chart=document.getElementById(PANELS[k]);chart.onmousemove=null;chart.onmouseleave=null;chart.innerHTML='';draws[k]()});
    renderTable(rows);writeHash()}
  // hover sync: anything carrying data-id lights its counterparts in every panel and the table
  function hotAll(id,on){document.querySelectorAll('[data-id="'+id+'"]').forEach(function(el){el.classList.toggle('hot',on)})}
  document.addEventListener('mouseover',function(e){var el=e.target.closest('[data-id]');if(!el||!el.closest('.dash, #c-table, #cp-pins'))return;document.querySelectorAll('.hot').forEach(function(x){x.classList.remove('hot')});hotAll(el.dataset.id,true)});
  document.addEventListener('mouseout',function(e){var el=e.target.closest('[data-id]');if(!el)return;hotAll(el.dataset.id,false)});
  function counts(){var w=watchIds().length,p=policyIds().length;document.querySelectorAll('.cp-set').forEach(function(b){var k=b.dataset.set,n=k==='all'?D.rows.length:k==='watch'?w:k==='policy'?p:D.rows.filter(function(r){return r.peer_group===k}).length;b.querySelector('.cnt').textContent=n;b.disabled=!n})}
  function suggest(){var t=q.value.trim().toLowerCase();if(!t){sugg.hidden=true;return}var hits=D.rows.filter(function(r){return (r.name+' '+r.short+' '+r.id).toLowerCase().indexOf(t)>=0}).slice(0,8);
    sugg.innerHTML=hits.map(function(r){return '<button data-id="'+r.id+'">'+esc(r.short)+' <span class="muted small">'+esc(r.name)+'</span></button>'}).join('')||'<span class="muted small">No match</span>';sugg.hidden=false}
  fetch(((document.body.getAttribute('data-root')==null)?'../':document.body.getAttribute('data-root'))+'data/compare.json').then(function(r){return r.json()}).then(function(d){D=d;d.rows.forEach(function(r){byId[r.id]=r});
    d.metrics.forEach(function(m){sel.insertAdjacentHTML('beforeend','<option value="'+m[0]+'">'+esc(m[1])+'</option>');if(m[0]!=='score')sel2.insertAdjacentHTML('beforeend','<option value="'+m[0]+'">'+esc(m[1])+'</option>')});
    markMeasure(state.metric||(d.metrics[0]||[])[0]);
    readHash();sel.value=state.metric;sel2.value=state.metric2;counts();render();
    document.getElementById('cp-sets').addEventListener('click',function(e){var b=e.target.closest('.cp-set');if(!b||b.disabled)return;state.set=b.dataset.set;state.extra=[];state.pins=[];userPinned=false;render()});
    sel.addEventListener('change',function(){state.metric=sel.value;markMeasure(sel.value);if(!userPinned)state.pins=[];render()});sel2.addEventListener('change',function(){state.metric2=sel2.value;render()});
    document.addEventListener('click',function(e){var b=e.target.closest('.pin');if(b){togglePin(b.dataset.id);return}
      var x=e.target.closest('.pc-x');if(x){var pnl=document.getElementById('p-'+x.dataset.panel);var was=pnl.classList.contains('wide');document.querySelectorAll('.panel-c.wide').forEach(function(q2){q2.classList.remove('wide')});if(!was)pnl.classList.add('wide');render();return}
      var th=e.target.closest('#c-table th[data-sort]');if(th){var k=th.dataset.sort;if(state.sort===k)state.dir=state.dir==='asc'?'desc':'asc';else{state.sort=k;state.dir=(k==='name'||k==='band'||k==='rating'||k==='efficiency_ratio'||k==='npl_ratio')?'asc':'desc'}renderTable(members());return}
      var p=e.target.closest('.cp-line,.cp-bar,.cp-dot,.cp-lbl');if(p&&p.dataset.id&&!e.target.closest('a[href]')){togglePin(p.dataset.id)}else if(p&&p.dataset.id&&e.target.closest('a[href]')&&e.target.closest('svg')){e.preventDefault();togglePin(p.dataset.id)}});
    q.addEventListener('input',suggest);sugg.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;if(state.extra.indexOf(b.dataset.id)<0)state.extra.push(b.dataset.id);if(state.pins.length<SLOTS.length&&state.pins.indexOf(b.dataset.id)<0){state.pins.push(b.dataset.id);userPinned=true}q.value='';sugg.hidden=true;render()});
    document.addEventListener('click',function(e){if(!e.target.closest('.cp-add'))sugg.hidden=true});
    var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(render,150)});
  }).catch(function(e){chart.innerHTML='<div class="empty">The comparison data could not be loaded.</div>'});
})();
