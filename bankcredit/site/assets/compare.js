// Compare: a peer set against a measure, four ways. Data from ../data/compare.json; state in the URL hash.
(function(){
  var chart=document.getElementById('cp-chart');if(!chart)return;
  var side=document.getElementById('cp-side'),count=document.getElementById('cp-count'),sel=document.getElementById('cp-metric'),sel2=document.getElementById('cp-metric2'),ylab=document.querySelector('.cp-y'),q=document.getElementById('cp-q'),sugg=document.getElementById('cp-sugg');
  var NAVY='#0a2540',ORANGE='#fd7e14',GREY='#c3cbd5',MID='#7d93ad';
  var D=null,byId={},state={set:'uk_large',extra:[],metric:'score',metric2:'cet1_ratio',view:'rank'};
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function ls(k){try{return JSON.parse(localStorage.getItem(k)||'[]')}catch(e){return[]}}
  function watchIds(){return ls('counterparty.watch')}
  function policyIds(){return ls('counterparty.policy').map(function(x){return x.id})}
  function readHash(){var h=location.hash.replace('#','');if(!h)return;h.split('&').forEach(function(kv){var p=kv.split('=');var k=p[0],v=decodeURIComponent(p[1]||'');if(k==='extra')state.extra=v?v.split(','):[];else if(k in state)state[k]=v})}
  function writeHash(){var parts=['set='+state.set,'metric='+state.metric,'view='+state.view];if(state.view==='scatter')parts.push('metric2='+state.metric2);if(state.extra.length)parts.push('extra='+state.extra.join(','));history.replaceState(null,'','#'+parts.join('&'))}
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
  function qEnd(d){var y=+d.slice(0,4),m=+d.slice(5,7),qm=Math.ceil(m/3)*3;var last=new Date(Date.UTC(y,qm,0)).getUTCDate();return y+'-'+(qm<10?'0':'')+qm+'-'+last}
  function daysBetween(a,b){return (Date.parse(b)-Date.parse(a))/864e5}
  function atBucket(r,code,b){var s=r.series[code]||[],best=null;for(var i=0;i<s.length;i++){if(s[i][0]<=b&&daysBetween(s[i][0],b)<=400)best=s[i][1]}return best}
  function buckets(rows,code,n){var set={};rows.forEach(function(r){(r.series[code]||[]).forEach(function(p){set[qEnd(p[0])]=1})});var ks=Object.keys(set).sort();return ks.slice(-n)}
  function link(r){return '<a href="../banks/'+r.id+'.html">'+esc(r.short)+'</a>'}
  function svgOpen(w,h){return '<svg viewBox="0 0 '+w+' '+h+'" width="100%" style="max-width:'+w+'px;display:block" font-family="inherit" font-size="11">'}

  function renderRank(rows,m,mark){var vals=rows.map(function(r){return{r:r,p:latest(r,m[0])}}).filter(function(x){return x.p&&x.p.v!=null});
    var hib=m[4];vals.sort(function(a,b){return hib?b.p.v-a.p.v:a.p.v-b.p.v});
    if(!vals.length){chart.innerHTML='<div class="empty">No figures for this measure in the set.</div>';side.innerHTML='';return}
    var vs=vals.map(function(x){return x.p.v}),lo=Math.min(0,Math.min.apply(null,vs)),hi=Math.max.apply(null,vs),med=median(vs);
    var W=560,rowH=22,left=170,barW=W-left-70,H=vals.length*rowH+30;
    var sc=function(v){return left+(v-lo)/((hi-lo)||1)*barW};
    var out=svgOpen(W,H);
    out+='<line x1="'+sc(med)+'" x2="'+sc(med)+'" y1="18" y2="'+(H-8)+'" stroke="'+ORANGE+'" stroke-dasharray="3 3"/><text x="'+sc(med)+'" y="12" text-anchor="middle" fill="'+ORANGE+'">median '+fmt(med,m)+'</text>';
    vals.forEach(function(x,i){var y=24+i*rowH,hl=mark[x.r.id];
      out+='<a href="../banks/'+x.r.id+'.html"><text x="'+(left-8)+'" y="'+(y+14)+'" text-anchor="end" fill="'+(hl?ORANGE:'#243240')+'" font-weight="'+(hl?'700':'500')+'">'+esc(x.r.short.slice(0,26))+'</text></a>';
      out+='<rect x="'+sc(Math.max(lo,Math.min(0,x.p.v)))+'" y="'+(y+3)+'" width="'+Math.max(1,Math.abs(sc(x.p.v)-sc(Math.max(lo,0))))+'" height="'+(rowH-8)+'" rx="3" fill="'+(hl?ORANGE:(i<3?NAVY:MID))+'"><title>'+esc(x.r.name)+': '+fmt(x.p.v,m)+' at '+x.p.d+'</title></rect>';
      out+='<text x="'+(sc(Math.max(x.p.v,0))+6)+'" y="'+(y+14)+'" fill="#243240" font-family="ui-monospace,monospace">'+fmt(x.p.v,m)+'</text>'});
    chart.innerHTML=out+'</svg>';
    var mine=vals.map(function(x,i){return{x:x,i:i}}).filter(function(o){return mark[o.x.r.id]});
    side.innerHTML='<div class="rtile"><div class="rtile-n">'+vals.length+'</div><div class="rtile-l">names with a figure</div></div><div class="rtile"><div class="rtile-n">'+fmt(med,m)+'</div><div class="rtile-l">set median</div></div><div class="rtile"><div class="rtile-n">'+fmt(vals[0].p.v,m)+'</div><div class="rtile-l">best: '+esc(vals[0].r.short)+'</div></div>'+
      (mine.length?'<div class="card pad cp-mine"><h4>Your names</h4>'+mine.map(function(o){return '<div><span>'+link(o.x.r)+'</span><span class="mono">'+fmt(o.x.p.v,m)+'</span><span class="muted small">#'+(o.i+1)+' of '+vals.length+'</span></div>'}).join('')+'</div>':'<p class="small muted">Watch a bank or add it to My policy and it is picked out here.</p>')}

  function renderTrend(rows,m,mark){var code=m[0];
    var bs=buckets(rows,code,24);if(!bs.length){chart.innerHTML='<div class="empty">No history for this measure in the set.</div>';side.innerHTML='';return}
    var lines=rows.map(function(r){return{r:r,pts:bs.map(function(b){return atBucket(r,code,b)})}}).filter(function(l){return l.pts.some(function(v){return v!=null})});
    var med=bs.map(function(b,i){return median(lines.map(function(l){return l.pts[i]}).filter(function(v){return v!=null}))});
    var all=[];lines.forEach(function(l){l.pts.forEach(function(v){if(v!=null)all.push(v)})});var lo=Math.min.apply(null,all),hi=Math.max.apply(null,all);if(lo===hi){lo-=1;hi+=1}
    var W=640,H=300,L=50,R=110,T=14,B=30,X=function(i){return L+i*(W-L-R)/Math.max(1,bs.length-1)},Y=function(v){return T+(hi-v)/(hi-lo)*(H-T-B)};
    var out=svgOpen(W,H);
    for(var g=0;g<5;g++){var v=lo+(hi-lo)*g/4;out+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(v)+'" y2="'+Y(v)+'" stroke="#eef1f4"/><text x="'+(L-6)+'" y="'+(Y(v)+4)+'" text-anchor="end" fill="#6c757d">'+fmt(v,m)+'</text>'}
    var lastX=-99;bs.forEach(function(b,i){if((i%Math.ceil(bs.length/8)===0||i===bs.length-1)&&X(i)-lastX>60){lastX=X(i);out+='<text x="'+X(i)+'" y="'+(H-10)+'" text-anchor="middle" fill="#6c757d">'+b.slice(0,7)+'</text>'}});
    var path=function(pts){var d='',on=false;pts.forEach(function(v,i){if(v==null){on=false;return}d+=(on?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1);on=true});return d};
    var ordered=lines.filter(function(l){return !mark[l.r.id]}).concat(lines.filter(function(l){return mark[l.r.id]}));
    ordered.forEach(function(l){var hl=mark[l.r.id];out+='<path class="cp-line" data-id="'+l.r.id+'" d="'+path(l.pts)+'" fill="none" stroke="'+(hl?ORANGE:GREY)+'" stroke-width="'+(hl?2.4:1.2)+'" opacity="'+(hl?1:0.8)+'"><title>'+esc(l.r.name)+'</title></path>'});
    out+='<path d="'+path(med)+'" fill="none" stroke="'+NAVY+'" stroke-width="2.6"/>';
    var last=[];lines.forEach(function(l){for(var i=l.pts.length-1;i>=0;i--)if(l.pts[i]!=null){last.push({l:l,i:i,v:l.pts[i]});break}});
    last.sort(function(a,b){return b.v-a.v});var used=[];var mi=med.length-1;var labels=[{y:Y(med[mi]),t:'median',c:NAVY,w:'700'}];
    last.forEach(function(o){var hl=mark[o.l.r.id],rank=last.indexOf(o);if(!hl&&rank>=6&&rank<last.length-2)return;labels.push({y:Y(o.v),t:o.l.r.short.slice(0,16),c:hl?ORANGE:'#6c757d',w:hl?'700':'400'})});
    labels.sort(function(a,b){return a.y-b.y});labels.forEach(function(lb){var y=lb.y;while(used.some(function(u){return Math.abs(u-y)<11}))y+=11;used.push(y);out+='<text x="'+(W-R+6)+'" y="'+(y+4)+'" fill="'+lb.c+'" font-weight="'+lb.w+'">'+esc(lb.t)+'</text>'});
    chart.innerHTML=out+'</svg><div class="cp-tip" id="cp-tip" hidden></div>';
    side.innerHTML='<div class="card pad cp-mine"><h4>Set, latest and change <span class="muted small">· hover a line or a name</span></h4>'+last.slice(0,40).map(function(o){var first=null;for(var i=0;i<o.l.pts.length;i++)if(o.l.pts[i]!=null){first=o.l.pts[i];break}var ch=first==null?null:o.v-first;return '<div data-id="'+o.l.r.id+'"><span>'+link(o.l.r)+'</span><span class="mono">'+fmt(o.v,m)+'</span><span class="small '+(ch==null?'muted':(ch>=0)===m[4]?'good':'bad')+'">'+(ch==null?'':(ch>=0?'+':'')+ch.toFixed(m[3])+' since '+bs[0].slice(0,4))+'</span></div>'}).join('')+'</div>';
    hoverWire(lines,m,bs)}
  function hoverWire(lines,m,bs){var tip=document.getElementById('cp-tip'),byId2={};lines.forEach(function(l){byId2[l.r.id]=l});
    function hot(id,on){document.querySelectorAll('.cp-line[data-id="'+id+'"]').forEach(function(p){p.classList.toggle('hot',on)});document.querySelectorAll('.cp-mine [data-id="'+id+'"]').forEach(function(d){d.classList.toggle('hot',on)})}
    chart.addEventListener('mousemove',function(e){var p=e.target.closest('.cp-line');if(!p){tip.hidden=true;document.querySelectorAll('.hot').forEach(function(x){x.classList.remove('hot')});return}
      var l=byId2[p.dataset.id];if(!l)return;document.querySelectorAll('.hot').forEach(function(x){x.classList.remove('hot')});hot(p.dataset.id,true);
      var last=null,li=-1;for(var i=l.pts.length-1;i>=0;i--)if(l.pts[i]!=null){last=l.pts[i];li=i;break}
      tip.innerHTML='<b>'+esc(l.r.short)+'</b> '+fmt(last,m)+' <span class="muted">'+(li>=0?bs[li].slice(0,7):'')+'</span>';var r=chart.getBoundingClientRect();tip.style.left=(e.clientX-r.left+12)+'px';tip.style.top=(e.clientY-r.top-28)+'px';tip.hidden=false});
    chart.addEventListener('mouseleave',function(){tip.hidden=true;document.querySelectorAll('.hot').forEach(function(x){x.classList.remove('hot')})});
    side.addEventListener('mouseover',function(e){var d=e.target.closest('[data-id]');if(!d)return;document.querySelectorAll('.hot').forEach(function(x){x.classList.remove('hot')});hot(d.dataset.id,true)});
    side.addEventListener('mouseleave',function(){document.querySelectorAll('.hot').forEach(function(x){x.classList.remove('hot')})})}

  function renderBump(rows,m,mark){var code=m[0];
    var bs=buckets(rows,code,16);if(bs.length<2){chart.innerHTML='<div class="empty">Not enough history in the set.</div>';side.innerHTML='';return}
    var lines=rows.map(function(r){return{r:r,pts:bs.map(function(b){return atBucket(r,code,b)}),rank:[]}}).filter(function(l){return l.pts.some(function(v){return v!=null})});
    bs.forEach(function(b,i){var have=lines.filter(function(l){return l.pts[i]!=null}).sort(function(a,b){return m[4]?b.pts[i]-a.pts[i]:a.pts[i]-b.pts[i]});lines.forEach(function(l){l.rank[i]=null});have.forEach(function(l,k){l.rank[i]=k+1})});
    var n=lines.length,W=640,H=Math.max(220,Math.min(520,n*18+40)),L=30,R=120,T=16,B=28,X=function(i){return L+i*(W-L-R)/(bs.length-1)},Y=function(rk){return T+(rk-1)/Math.max(1,n-1)*(H-T-B)};
    var out=svgOpen(W,H);
    var lastX=-99;bs.forEach(function(b,i){if((i%Math.ceil(bs.length/8)===0||i===bs.length-1)&&X(i)-lastX>60){lastX=X(i);out+='<text x="'+X(i)+'" y="'+(H-8)+'" text-anchor="middle" fill="#6c757d">'+b.slice(0,7)+'</text>'}});
    var path=function(rk){var d='',on=false;rk.forEach(function(v,i){if(v==null){on=false;return}d+=(on?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1);on=true});return d};
    var ordered=lines.filter(function(l){return !mark[l.r.id]}).concat(lines.filter(function(l){return mark[l.r.id]}));
    ordered.forEach(function(l){var hl=mark[l.r.id],lastR=null;for(var i=l.rank.length-1;i>=0;i--)if(l.rank[i]!=null){lastR=l.rank[i];break}var top=lastR!=null&&lastR<=3;
      out+='<path d="'+path(l.rank)+'" fill="none" stroke="'+(hl?ORANGE:top?NAVY:GREY)+'" stroke-width="'+(hl||top?2.4:1.2)+'" stroke-linejoin="round"><title>'+esc(l.r.name)+'</title></path>';
      l.rank.forEach(function(rk,i){if(rk!=null)out+='<circle cx="'+X(i)+'" cy="'+Y(rk)+'" r="'+(hl||top?3:2)+'" fill="'+(hl?ORANGE:top?NAVY:GREY)+'"><title>'+esc(l.r.short)+' #'+rk+' at '+bs[i]+' ('+fmt(l.pts[i],m)+')</title></circle>'});
      if(lastR!=null&&(hl||lastR<=8||lastR>n-2))out+='<text x="'+(W-R+6)+'" y="'+(Y(lastR)+4)+'" fill="'+(hl?ORANGE:top?NAVY:'#6c757d')+'" font-weight="'+(hl||top?'700':'400')+'">#'+lastR+' '+esc(l.r.short.slice(0,14))+'</text>'});
    chart.innerHTML=out+'</svg>';
    var moves=lines.map(function(l){var f=null,la=null;l.rank.forEach(function(v){if(v!=null){if(f==null)f=v;la=v}});return{l:l,f:f,la:la,ch:(f!=null&&la!=null)?f-la:null}}).filter(function(o){return o.ch!=null}).sort(function(a,b){return b.ch-a.ch});
    side.innerHTML='<div class="card pad cp-mine"><h4>Rank moves since '+bs[0].slice(0,7)+'</h4>'+moves.slice(0,6).concat(moves.slice(-6)).filter(function(o,i,a){return a.indexOf(o)===i}).map(function(o){return '<div><span>'+link(o.l.r)+'</span><span class="mono">#'+o.f+' → #'+o.la+'</span><span class="small '+(o.ch>0?'good':o.ch<0?'bad':'muted')+'">'+(o.ch>0?'up '+o.ch:o.ch<0?'down '+(-o.ch):'level')+'</span></div>'}).join('')+'</div>'}

  function renderScatter(rows,m,m2,mark){var pts=rows.map(function(r){return{r:r,a:latest(r,m2[0]),b:latest(r,m[0])}}).filter(function(p){return p.a&&p.b&&p.a.v!=null&&p.b.v!=null});
    if(pts.length<2){chart.innerHTML='<div class="empty">Fewer than two names carry both measures.</div>';side.innerHTML='';return}
    var xs=pts.map(function(p){return p.a.v}),ys=pts.map(function(p){return p.b.v}),xlo=Math.min.apply(null,xs),xhi=Math.max.apply(null,xs),ylo=Math.min.apply(null,ys),yhi=Math.max.apply(null,ys);
    if(xlo===xhi){xlo-=1;xhi+=1}if(ylo===yhi){ylo-=1;yhi+=1}
    var px=(xhi-xlo)*0.06,py=(yhi-ylo)*0.08;xlo-=px;xhi+=px;ylo-=py;yhi+=py;var W=640,H=360,L=54,R=20,T=14,B=40,X=function(v){return L+(v-xlo)/(xhi-xlo)*(W-L-R)},Y=function(v){return T+(yhi-v)/(yhi-ylo)*(H-T-B)};
    var amax=Math.max.apply(null,pts.map(function(p){return p.r.assets||0}))||1;
    var out=svgOpen(W,H);
    for(var g=0;g<5;g++){var v=ylo+(yhi-ylo)*g/4,u=xlo+(xhi-xlo)*g/4;out+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(v)+'" y2="'+Y(v)+'" stroke="#eef1f4"/><text x="'+(L-6)+'" y="'+(Y(v)+4)+'" text-anchor="end" fill="#6c757d">'+fmt(v,m)+'</text><text x="'+X(u)+'" y="'+(H-22)+'" text-anchor="middle" fill="#6c757d">'+fmt(u,m2)+'</text>'}
    out+='<text x="'+((L+W-R)/2)+'" y="'+(H-6)+'" text-anchor="middle" fill="#243240" font-weight="600">'+esc(m2[1])+' →</text>';
    var mx=median(xs),my=median(ys);out+='<line x1="'+X(mx)+'" x2="'+X(mx)+'" y1="'+T+'" y2="'+(H-B)+'" stroke="'+ORANGE+'" stroke-dasharray="3 3" opacity=".6"/><line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(my)+'" y2="'+Y(my)+'" stroke="'+ORANGE+'" stroke-dasharray="3 3" opacity=".6"/>';
    pts.forEach(function(p){var hl=mark[p.r.id],rad=p.r.assets?4+9*Math.sqrt(p.r.assets/amax):5;
      out+='<a href="../banks/'+p.r.id+'.html"><circle cx="'+X(p.a.v)+'" cy="'+Y(p.b.v)+'" r="'+rad.toFixed(1)+'" fill="'+(hl?ORANGE:NAVY)+'" fill-opacity="'+(hl?0.9:0.45)+'" stroke="#fff"><title>'+esc(p.r.name)+': '+esc(m2[1])+' '+fmt(p.a.v,m2)+', '+esc(m[1])+' '+fmt(p.b.v,m)+'</title></circle></a>';
      if(hl||pts.length<=12){var right=X(p.a.v)>W-R-90;out+='<text x="'+(right?X(p.a.v)-rad-3:X(p.a.v)+rad+3)+'" y="'+(Y(p.b.v)+4)+'" text-anchor="'+(right?'end':'start')+'" fill="'+(hl?ORANGE:'#6c757d')+'" font-weight="'+(hl?'700':'400')+'">'+esc(p.r.short.slice(0,16))+'</text>'}});
    chart.innerHTML=out+'</svg>';
    side.innerHTML='<p class="small muted">Dashed lines are the set medians; the top-right quadrant is strong on both measures when both read higher-is-better. Bubble size follows total assets where known.</p>'}

  function render(){var rows=members(),mark=marked(),m=metric(state.metric);if(state.metric2===state.metric){state.metric2=state.metric==='roe'?'cet1_ratio':'roe';sel2.value=state.metric2}var m2=metric(state.metric2);
    count.textContent=rows.length+' in the set';ylab.hidden=state.view!=='scatter';
    document.querySelectorAll('.cp-set').forEach(function(b){b.classList.toggle('active',b.dataset.set===state.set)});
    document.querySelectorAll('.cp-views .tab').forEach(function(t){t.classList.toggle('active',t.dataset.view===state.view)});
    if(!rows.length){chart.innerHTML='<div class="empty">'+(state.set==='watch'?'You are not watching anyone yet. The star on any profile or board row adds a name.':state.set==='policy'?'My policy is empty. Add counterparties there and they appear here.':'Nothing in this set.')+'</div>';side.innerHTML='';writeHash();return}
    if(state.view==='rank')renderRank(rows,m,mark);else if(state.view==='trend')renderTrend(rows,m,mark);else if(state.view==='bump')renderBump(rows,m,mark);else renderScatter(rows,m,m2,mark);
    writeHash()}
  function counts(){var w=watchIds().length,p=policyIds().length;document.querySelectorAll('.cp-set').forEach(function(b){var k=b.dataset.set,n=k==='all'?D.rows.length:k==='watch'?w:k==='policy'?p:D.rows.filter(function(r){return r.peer_group===k}).length;b.querySelector('.cnt').textContent=n;b.disabled=!n})}
  function suggest(){var t=q.value.trim().toLowerCase();if(!t){sugg.hidden=true;return}var hits=D.rows.filter(function(r){return (r.name+' '+r.short+' '+r.id).toLowerCase().indexOf(t)>=0}).slice(0,8);
    sugg.innerHTML=hits.map(function(r){return '<button data-id="'+r.id+'">'+esc(r.short)+' <span class="muted small">'+esc(r.name)+'</span></button>'}).join('')||'<span class="muted small">No match</span>';sugg.hidden=false}
  fetch('../data/compare.json').then(function(r){return r.json()}).then(function(d){D=d;d.rows.forEach(function(r){byId[r.id]=r});
    d.metrics.forEach(function(m){sel.insertAdjacentHTML('beforeend','<option value="'+m[0]+'">'+esc(m[1])+'</option>');if(m[0]!=='score')sel2.insertAdjacentHTML('beforeend','<option value="'+m[0]+'">'+esc(m[1])+'</option>')});
    readHash();sel.value=state.metric;sel2.value=state.metric2;counts();render();
    document.getElementById('cp-sets').addEventListener('click',function(e){var b=e.target.closest('.cp-set');if(!b||b.disabled)return;state.set=b.dataset.set;state.extra=[];render()});
    document.querySelector('.cp-views').addEventListener('click',function(e){var t=e.target.closest('.tab');if(!t)return;state.view=t.dataset.view;render()});
    sel.addEventListener('change',function(){state.metric=sel.value;render()});sel2.addEventListener('change',function(){state.metric2=sel2.value;render()});
    q.addEventListener('input',suggest);sugg.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;if(state.extra.indexOf(b.dataset.id)<0)state.extra.push(b.dataset.id);q.value='';sugg.hidden=true;render()});
    document.addEventListener('click',function(e){if(!e.target.closest('.cp-add'))sugg.hidden=true});
  }).catch(function(e){chart.innerHTML='<div class="empty">The comparison data could not be loaded.</div>'});
})();
