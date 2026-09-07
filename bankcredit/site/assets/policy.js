// My policy: the user's approved counterparties and tenors, kept in this browser (or carried in a share link),
// checked every visit against the latest public standing, market signal and news. Nothing leaves the browser.
(function(){
  var KEY='counterparty.policy', ROOT=(document.body.dataset.root||'../');
  var TENORS=[[100,'100 days'],[182,'6 months'],[365,'12 months'],[730,'24 months'],[1825,'5 years']];
  var GRADES=['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC'];
  var data=null, byId={};
  function load(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
  function save(p){try{localStorage.setItem(KEY,JSON.stringify(p))}catch(e){}}
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function fmt(v,dp,suf){return v==null?'<span class="na">—</span>':'<span class="mono">'+Number(v).toFixed(dp==null?1:dp)+(suf||'')+'</span>'}
  function tenorLabel(d){for(var i=0;i<TENORS.length;i++)if(TENORS[i][0]===d)return TENORS[i][1];return d+' days'}
  function bandRank(b){return {A:1,B:2,C:3,D:4,E:5}[b]||9}
  function chip(t,k){return '<span class="chip chip-'+(k||'muted')+'">'+esc(t)+'</span>'}
  function mkt(m){if(!m||m.direction==='none')return '<span class="muted">no market data</span>';var k=m.direction==='down'?'bad':(m.direction==='up'?'good':'muted');return chip(m.label,k)}
  function ratings(r){return (r||[]).map(function(x){return '<span class="mono" title="'+esc(x.agency+' '+x.type+(x.outlook?' · '+x.outlook:''))+'">'+esc(x.letter)+' '+esc(x.value)+'</span>'}).join(' <span class="muted">·</span> ')||'<span class="muted">unrated</span>'}
  function shortR(r){return (r||[]).map(function(x){return '<span class="mono">'+esc(x.letter)+' '+esc(x.value)+'</span>'}).join(' <span class="muted">·</span> ')||'<span class="muted">—</span>'}
  function snapshot(e){return {score:e.score,band:e.band,grade:e.rating_grade,market:e.market&&e.market.direction,asof:e.asof}}
  function encode(p){try{return btoa(unescape(encodeURIComponent(JSON.stringify(p)))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')}catch(e){return ''}}
  function decode(s){try{s=s.replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';return JSON.parse(decodeURIComponent(escape(atob(s))))}catch(e){return null}}

  // ---- what changed since the name was approved, and what needs a look now
  function flags(item,e){
    var f=[], b=item.base||{};
    if(!e)return [['bad','No longer covered']];
    if(e.score==null)f.push(['warn','Not enough public data for a score']);
    if(b.score!=null&&e.score!=null&&e.score<=b.score-5)f.push(['bad','Score down '+(b.score-e.score).toFixed(1)+' since approved']);
    if(b.band&&e.band&&bandRank(e.band)>bandRank(b.band))f.push(['bad','Band '+b.band+' → '+e.band]);
    if(b.grade!=null&&e.rating_grade!=null&&e.rating_grade>b.grade+0.4)f.push(['bad','Ratings weaker: '+GRADES[Math.floor(b.grade+0.5)-1]+' → '+e.rating_composite]);
    (e.negative||[]).forEach(function(n){if(!item.added||n.date>=item.added)f.push(['bad',n.date+' '+n.title])});
    if(e.market&&e.market.direction==='down')f.push(['warn',e.market.label]);
    if(e.news30&&e.news30.bad)f.push(['warn',e.news30.bad+' adverse headline'+(e.news30.bad>1?'s':'')+' in 30 days']);
    if(e.age_days!=null&&e.age_days>180)f.push(['warn','Regulatory figures '+e.age_days+' days old']);
    if(e.inherited&&e.inherited.length)f.push(['muted','Some figures from the group or lead bank']);
    return f;
  }
  function worst(items){var w={band:null,grade:null,score:null};items.forEach(function(it){var e=byId[it.id];if(!e)return;
    if(e.band&&(w.band==null||bandRank(e.band)>bandRank(w.band)))w.band=e.band;
    if(e.rating_grade!=null&&(w.grade==null||e.rating_grade>w.grade))w.grade=e.rating_grade;
    if(e.score!=null&&(w.score==null||e.score<w.score))w.score=e.score});return w}

  function render(){
    var p=load(); var out=document.getElementById('policy-body'); if(!out||!data)return;
    var html='';
    if(!p.length){html+='<div class="empty">No counterparties yet. Add the names your policy approves and the longest tenor you accept for each.</div>'}
    else{
      var n_flag=0;
      var rows=p.slice().sort(function(a,b){return b.tenor-a.tenor||(byId[a.id]&&byId[a.id].short||'').localeCompare(byId[b.id]&&byId[b.id].short||'')}).map(function(it){
        var e=byId[it.id]; var fl=flags(it,e); if(fl.some(function(x){return x[0]!=='muted'}))n_flag++;
        if(!e)return '<tr><td class="b">'+esc(it.id)+'</td><td colspan="9">'+chip('No longer covered','bad')+'</td><td><button class="filter pol-rm" data-id="'+esc(it.id)+'">Remove</button></td></tr>';
        var recent=(e.recent||[]).slice(0,3).map(function(x){var t=x.title.length>90?x.title.slice(0,88)+'…':x.title;return '<div class="small"><span class="mono muted">'+x.date+'</span> '+chip(x.severity==='bad'?'adverse':x.severity==='warn'?'watch':'positive',x.severity==='bad'?'bad':x.severity==='warn'?'warn':'good')+' '+(x.url?'<a href="'+esc(x.url)+'" target="_blank" rel="noopener">':'')+esc(t)+(x.url?'</a>':'')+'</div>'}).join('')||'<span class="muted small">nothing notable in 90 days</span>';
        var fh=fl.map(function(x){return chip(x[1],x[0]==='muted'?'muted':x[0])}).join(' ')||chip('No change','good');
        return '<tr data-id="'+esc(e.id)+'"><td><a class="b" href="'+ROOT+'banks/'+esc(e.id)+'.html">'+esc(e.short)+'</a><div class="small muted">'+esc(e.name)+' · '+esc(e.country)+'</div></td>'+
          '<td class="mono">'+esc(tenorLabel(it.tenor))+'<div class="small muted">since '+esc(it.added||'?')+'</div></td>'+
          '<td>'+(e.score==null?'<span class="na">—</span>':'<span class="mono b">'+e.score.toFixed(1)+'</span> <span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>')+'<div class="small muted">'+(e.coverage!=null?Math.round(e.coverage*100)+'% of inputs':'')+'</div></td>'+
          '<td>'+ratings(e.ratings)+'<div class="small muted">ST: '+shortR(e.short_ratings)+'</div></td>'+
          '<td>'+fmt(e.cet1)+'<div class="small muted">CET1</div></td><td>'+fmt(e.leverage)+(e.leverage_basis==='us_tier1'?'<sup>T1</sup>':'')+'<div class="small muted">Lev.</div></td><td>'+fmt(e.lcr,0,'%')+'<div class="small muted">LCR · '+esc(e.asof||'')+'</div></td>'+
          '<td>'+mkt(e.market)+(e.market_detail&&e.market_detail.bond_change30!=null?'<div class="small muted">bonds vs peers '+(e.market_detail.bond_change30>0?'+':'')+Math.round(e.market_detail.bond_change30)+' bp</div>':'')+'</td>'+
          '<td>'+recent+'</td><td>'+fh+'</td><td><button class="filter pol-rm" data-id="'+esc(e.id)+'" title="Remove">×</button></td></tr>';
      }).join('');
      html+='<div class="pol-summary">'+(n_flag?chip(n_flag+' of '+p.length+' need a look','warn'):chip('All '+p.length+' names unchanged since approval','good'))+' <span class="small muted">Data built '+esc(data.generated.slice(0,16).replace('T',' '))+' UTC. Flags compare today with the day each name was approved.</span></div>';
      html+='<div class="table-wrap"><table class="plain pol"><thead><tr><th>Counterparty</th><th>Your max tenor</th><th>Score</th><th>Ratings (long / short)</th><th>CET1</th><th>Leverage</th><th>LCR</th><th>Market</th><th>Recent events</th><th>Since approved</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div>';
      // like-for-like: names at least as strong as the weakest you already accept at each tenor
      var tenors=[];p.forEach(function(it){if(tenors.indexOf(it.tenor)<0)tenors.push(it.tenor)});tenors.sort(function(a,b){return b-a});
      var ll='', shown={};
      tenors.forEach(function(t){var acc=p.filter(function(it){return it.tenor>=t});var w=worst(acc);if(w.grade==null&&w.score==null)return;
        var have={};p.forEach(function(it){have[it.id]=1});
        var cands=data.rows.filter(function(e){if(have[e.id]||e.score==null)return false;
          if(w.band&&bandRank(e.band)>bandRank(w.band))return false;
          if(w.grade!=null&&(e.rating_grade==null||e.rating_grade>w.grade))return false;
          if(w.score!=null&&e.score<w.score)return false;
          if(e.market&&e.market.direction==='down')return false;return !shown[e.id]}).sort(function(a,b){return b.score-a.score});
        cands.forEach(function(e){shown[e.id]=1});
        var names=acc.map(function(it){return byId[it.id]?byId[it.id].short:it.id});
        ll+='<h4>'+esc(tenorLabel(t))+' <span class="muted small">· you accept '+esc(names.join(', '))+' at this tenor; weakest of them: band '+esc(w.band||'?')+', ratings '+esc(GRADES[Math.floor((w.grade||1)+0.5)-1]||'?')+', score '+(w.score!=null?w.score.toFixed(1):'?')+'</span></h4>';
        ll+=(t!==tenors[0]?'<p class="small muted">In addition to the names already listed at longer tenors.</p>':'')+(cands.length?'<div class="ll-grid">'+cands.slice(0,24).map(function(e){return '<div class="ll"><a class="b" href="'+ROOT+'banks/'+esc(e.id)+'.html">'+esc(e.short)+'</a> <span class="small muted">'+esc(e.country)+'</span><div class="small"><span class="mono b">'+e.score.toFixed(1)+'</span> <span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span> · '+ratings(e.ratings)+'</div><div class="small">'+mkt(e.market)+' <button class="filter pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'">Add at '+esc(tenorLabel(t))+'</button></div></div>'}).join('')+'</div>':'<p class="small muted">No further covered name matches the weakest standing you accept at this tenor.</p>');
      });
      html+='<h3 style="margin-top:22px">Like-for-like</h3><p class="small muted">Names whose public standing is at least as strong as the weakest counterparty you already accept at each tenor: same or better band, ratings and score, and no market signal widening. This is a comparison of public information, not a recommendation; the tenor and the list remain your policy and your adviser\'s advice.</p>'+ll;
    }
    out.innerHTML=html;
    var link=document.getElementById('pol-link');if(link){link.value=p.length?location.href.split('#')[0]+'#p='+encode(p):''}
  }
  function add(id,tenor){var p=load();var e=byId[id];if(!e)return;var ex=p.filter(function(x){return x.id===id})[0];
    if(ex){ex.tenor=tenor}else{p.push({id:id,tenor:tenor,added:new Date().toISOString().slice(0,10),base:snapshot(e)})}save(p);render()}
  function init(){
    var sel=document.getElementById('pol-name');var dl=document.getElementById('pol-names');
    data.rows.forEach(function(e){byId[e.id]=e;var o=document.createElement('option');o.value=e.short+' — '+e.name;o.dataset.id=e.id;dl.appendChild(o)});
    var ten=document.getElementById('pol-tenor');TENORS.forEach(function(t){var o=document.createElement('option');o.value=t[0];o.textContent=t[1];if(t[0]===365)o.selected=true;ten.appendChild(o)});
    document.getElementById('pol-add').addEventListener('click',function(){var v=sel.value;var id=null;for(var i=0;i<dl.options.length;i++)if(dl.options[i].value===v){id=dl.options[i].dataset.id;break}
      if(!id){var q=v.toLowerCase();data.rows.some(function(e){if(e.short.toLowerCase()===q||e.name.toLowerCase()===q){id=e.id;return true}})}
      if(!id){sel.classList.add('err');return}sel.classList.remove('err');add(id,+ten.value);sel.value=''});
    document.addEventListener('click',function(ev){var b=ev.target.closest('.pol-rm');if(b){var p=load().filter(function(x){return x.id!==b.dataset.id});save(p);render();return}
      var a=ev.target.closest('.pol-add-ll');if(a){add(a.dataset.id,+a.dataset.tenor);return}
      if(ev.target.id==='pol-clear'){if(confirm('Remove every counterparty from this policy?')){save([]);render()}return}
      if(ev.target.id==='pol-copy'){var l=document.getElementById('pol-link');l.select();try{document.execCommand('copy')}catch(e){}ev.target.textContent='Copied';setTimeout(function(){ev.target.textContent='Copy link'},1500);return}
      if(ev.target.id==='pol-use-shared'){save(window.__shared);window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);render();return}
      if(ev.target.id==='pol-keep-mine'){window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);return}
    });
    var m=location.hash.match(/#p=([A-Za-z0-9_\-]+)/);if(m){var sh=decode(m[1]);if(sh&&sh.length){if(!load().length){save(sh);history.replaceState(null,'',location.pathname)}else{window.__shared=sh;var box=document.getElementById('pol-shared');box.hidden=false;box.querySelector('span').textContent='This link carries a policy of '+sh.length+' counterparties.'}}}
    render();
  }
  var box=document.getElementById('policy-body');if(!box)return;
  fetch(ROOT+'data/policy.json').then(function(r){return r.json()}).then(function(j){data=j;init()}).catch(function(){box.innerHTML='<div class="empty">Could not load the counterparty data.</div>'});
})();
