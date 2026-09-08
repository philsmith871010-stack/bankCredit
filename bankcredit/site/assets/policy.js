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
  var BANDC={A:'#0a2540',B:'#3f5f85',C:'#7d93ad',D:'#a9b8c9',E:'#c9d3de'};
  // A score is a ratio against a scale, so it reads as a meter on the band ramp - one hue,
  // light to dark - rather than as a one-bar chart. The track carries no meaning of its own.
  function meter(score,band,cls){
    if(score==null)return '';
    var w=Math.max(0,Math.min(100,score));
    return '<div class="meter'+(cls?' '+cls:'')+'" role="img" aria-label="score '+w.toFixed(0)+' of 100">'+
           '<i style="width:'+w.toFixed(1)+'%;background:'+(BANDC[band]||'#7d93ad')+'"></i></div>';
  }
  // One line per agency so they line up down the card, long-term rating first with the
  // short-term beside it; the title keeps the type and outlook that the line cannot show.
  function ratingGrid(r,sr){
    if(!(r||[]).length)return '<div class="cp-rt-none">unrated</div>';
    var st={};(sr||[]).forEach(function(x){st[x.letter]=x.value});
    return '<div class="cp-rt">'+r.map(function(x){
      return '<span class="ag" title="'+esc(x.agency)+'">'+esc(x.letter)+'</span>'+
             '<span class="lt" title="'+esc(x.agency+' '+x.type+(x.outlook?' \u00b7 '+x.outlook:''))+'">'+esc(x.value)+'</span>'+
             '<span class="st">'+(st[x.letter]?esc(st[x.letter]):'')+'</span>';
    }).join('')+'</div>';
  }
  function kpis(e){
    var t=[['CET1',e.cet1,1,''],['Leverage',e.leverage,1,e.leverage_basis==='us_tier1'?'\u2020':''],['LCR',e.lcr,0,'%']];
    return '<div class="cp-kpis">'+t.map(function(k){
      return '<div class="cp-kpi"><b>'+(k[1]==null?'<span class="na">\u2014</span>':Number(k[1]).toFixed(k[2])+k[3])+'</b><span>'+k[0]+'</span></div>';
    }).join('')+'</div>';
  }
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


  // ---- compact charts for the policy as a whole -------------------------------------
  // Small multiples, each answering one question. Band and rating are ordered scales, so
  // they take the band ramp - one hue, light to dark - and never a categorical palette.
  var BANDS=['A','B','C','D','E'];
  function svg(w,h,inner,cls){return '<svg viewBox="0 0 '+w+' '+h+'" width="100%" height="'+h+'" class="pv-svg'+(cls?' '+cls:'')+'" preserveAspectRatio="none" aria-hidden="true">'+inner+'</svg>'}

  function bandMix(es){
    var n={},tot=0;BANDS.forEach(function(b){n[b]=0});
    es.forEach(function(e){if(e.band&&n[e.band]!=null){n[e.band]++;tot++}});
    if(!tot)return '<div class="muted small">no scored names</div>';
    var w=260,h=16,x=0,parts='',key='';
    BANDS.forEach(function(b){
      if(!n[b])return;
      var seg=n[b]/tot*w;
      parts+='<rect x="'+x.toFixed(1)+'" y="0" width="'+Math.max(0,seg-2).toFixed(1)+'" height="'+h+'" rx="3" fill="'+BANDC[b]+'"><title>'+n[b]+' in band '+b+'</title></rect>';
      x+=seg;
      key+='<span class="pv-key"><i style="background:'+BANDC[b]+'"></i>'+b+' <b>'+n[b]+'</b></span>';
    });
    return svg(w,h,parts)+'<div class="pv-keys">'+key+'</div>';
  }

  function scoreHist(mine,all){
    // The universe is the context and your names are the point, so this is emphasis: the
    // distribution in grey behind, each of your names marked on it. Two bar series scaled to
    // their own maxima would put one name at the same height as forty.
    var bins=20,w=260,h=52,base=h-14,ax=[];
    for(var i=0;i<bins;i++)ax.push(0);
    all.forEach(function(e){if(e.score!=null)ax[Math.min(bins-1,Math.floor(e.score/100*bins))]++});
    var amax=Math.max.apply(null,ax)||1, bw=w/bins, inner='';
    for(var j=0;j<bins;j++){
      var ah=ax[j]/amax*(base-4);
      if(ah>0)inner+='<rect x="'+(j*bw+.6).toFixed(1)+'" y="'+(base-ah).toFixed(1)+'" width="'+(bw-1.2).toFixed(1)+'" height="'+ah.toFixed(1)+'" rx="1.5" fill="#e9ecef"/>';
    }
    inner+='<line x1="0" x2="'+w+'" y1="'+base+'" y2="'+base+'" stroke="#dee2e6" stroke-width="1"/>';
    mine.forEach(function(e){
      if(e.score==null)return;
      var x=e.score/100*w;
      inner+='<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+(base-13)+'" y2="'+(base+4)+'" stroke="#fff" stroke-width="3.4"/>'+
             '<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+(base-13)+'" y2="'+(base+4)+'" stroke="'+(BANDC[e.band]||'#0a2540')+'" stroke-width="1.8"><title>'+esc(e.short)+' '+e.score.toFixed(1)+'</title></line>';
    });
    inner+='<text x="1" y="'+h+'" class="pv-ax">0</text><text x="'+(w/2)+'" y="'+h+'" text-anchor="middle" class="pv-ax">50</text><text x="'+w+'" y="'+h+'" text-anchor="end" class="pv-ax">100</text>';
    return svg(w,h,inner);
  }

  function ratingHist(es){
    // the composite rating is an ordered scale, so the bars stay in grade order
    var n={},tot=0;
    es.forEach(function(e){if(e.rating_composite){n[e.rating_composite]=(n[e.rating_composite]||0)+1;tot++}});
    var present=GRADES.filter(function(g){return n[g]});
    if(!present.length)return '<div class="muted small">no rated names</div>';
    var w=260,h=52,bw=w/present.length,bar=Math.min(bw-3,26),mx=Math.max.apply(null,present.map(function(g){return n[g]})),inner='';
    present.forEach(function(g,i){
      var bh=Math.max(4,n[g]/mx*(h-16));
      inner+='<rect x="'+(i*bw+(bw-bar)/2).toFixed(1)+'" y="'+(h-16-bh).toFixed(1)+'" width="'+bar.toFixed(1)+'" height="'+bh.toFixed(1)+'" rx="2" fill="#143659"><title>'+n[g]+' rated '+g+'</title></rect>'+
             '<text x="'+(i*bw+bw/2).toFixed(1)+'" y="'+h+'" text-anchor="middle" class="pv-ax">'+g+'</text>';
    });
    return svg(w,h,inner);
  }

  function tenorScore(items){
    // the question this answers: are the longest tenors on the weakest names?
    var pts=items.map(function(it){var e=byId[it.id];return e&&e.score!=null?{t:it.tenor,s:e.score,n:e.short,b:e.band}:null}).filter(Boolean);
    if(!pts.length)return '<div class="muted small">no scored names</div>';
    var w=260,h=52,pad=14;
    var maxT=Math.max.apply(null,pts.map(function(p){return p.t}));
    var X=function(t){return maxT<=0?w/2:8+(t/maxT)*(w-20)};
    var Y=function(s){return (h-pad)-(s/100)*(h-pad-6)};
    var inner='<line x1="0" x2="'+w+'" y1="'+Y(50).toFixed(1)+'" y2="'+Y(50).toFixed(1)+'" stroke="#e9ecef" stroke-width="1"/>';
    pts.forEach(function(p){
      inner+='<circle cx="'+X(p.t).toFixed(1)+'" cy="'+Y(p.s).toFixed(1)+'" r="4.5" fill="'+(BANDC[p.b]||'#7d93ad')+'" stroke="#fff" stroke-width="1.5"><title>'+esc(p.n)+': '+p.s.toFixed(1)+' at '+tenorLabel(p.t)+'</title></circle>';
    });
    inner+='<text x="0" y="'+h+'" class="pv-ax">short</text><text x="'+w+'" y="'+h+'" text-anchor="end" class="pv-ax">'+tenorLabel(maxT)+'</text>';
    return svg(w,h,inner);
  }

  function overview(items){
    var es=items.map(function(it){return byId[it.id]}).filter(Boolean);
    var sc=es.map(function(e){return e.score}).filter(function(v){return v!=null}).sort(function(a,b){return a-b});
    var med=sc.length?(sc.length%2?sc[(sc.length-1)/2]:(sc[sc.length/2-1]+sc[sc.length/2])/2):null;
    var w=worst(items);
    var stale=es.filter(function(e){return e.age_days!=null&&e.age_days>180}).length;
    var tile=function(v,l,k){return '<div class="pv-tile'+(k?' '+k:'')+'"><b>'+v+'</b><span>'+l+'</span></div>'};
    return '<div class="pv">'+
      '<div class="pv-tiles">'+
        tile(items.length,'counterparties')+
        tile(w.score!=null?w.score.toFixed(1):'—','weakest score')+
        tile(w.band||'—','weakest band')+
        tile(med!=null?med.toFixed(1):'—','median score')+
        tile(sc.length+'/'+items.length,'scored')+
        tile(stale,'figures over 180 days',stale?'pv-warn':'')+
      '</div>'+
      '<div class="pv-charts">'+
        '<figure><figcaption>Band mix</figcaption>'+bandMix(es)+'</figure>'+
        '<figure><figcaption>Score against every covered name</figcaption>'+scoreHist(es,data.rows)+'</figure>'+
        '<figure><figcaption>Composite rating</figcaption>'+ratingHist(es)+'</figure>'+
        '<figure><figcaption>Score by tenor accepted</figcaption>'+tenorScore(items)+'</figure>'+
      '</div></div>';
  }


  // ---- detail without leaving the page ----------------------------------------------
  // The bank's own JSON already carries its series, every rating, the score make-up and its
  // place among peers, so a card opens all of it here rather than sending the reader away.
  var MCACHE={}, PEERS=null;
  var AGN={fitch:'Fitch',sp:'S&P',moodys:"Moody's",dbrs:'DBRS',kbra:'KBRA',scope:'Scope',jcr:'JCR',creditreform:'Creditreform'};
  var TRENDS=[['cet1_ratio','CET1 ratio','%'],['tier1_ratio','Tier 1 ratio','%'],['total_capital_ratio','Total capital','%'],
              ['leverage_ratio','Leverage','%'],['lcr','LCR','%'],['nsfr','NSFR','%'],
              ['npl_ratio','Non-performing','%'],['roe','Return on equity','%'],['efficiency_ratio','Cost to income','%']];
  // The bank's own path, with its peer group's current quartile band behind it. The band is
  // where the peers stand today, not a peer history, so it is drawn flat and labelled as such:
  // it answers "is this bank ahead of its peers now", which the line alone cannot.
  function trend(pts,label,unit,pq){
    if(!pts||pts.length<2)return '';
    var w=150,h=46,pad=5,vals=pts.map(function(p){return p.v});
    var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals);
    if(pq){lo=Math.min(lo,pq.p25);hi=Math.max(hi,pq.p75)}
    var rng=(hi-lo)||1; lo-=rng*0.08; hi+=rng*0.08; rng=hi-lo;
    var X=function(i){return pad+i*(w-2*pad)/(pts.length-1)};
    var Y=function(v){return h-12-((v-lo)/rng)*(h-12-pad)};
    var d='M'+pts.map(function(p,i){return X(i).toFixed(1)+' '+Y(p.v).toFixed(1)}).join('L');
    var last=pts[pts.length-1], band='', vs='';
    if(pq){
      var y1=Y(pq.p75),y2=Y(pq.p25);
      band='<rect x="0" y="'+Math.min(y1,y2).toFixed(1)+'" width="'+w+'" height="'+Math.abs(y2-y1).toFixed(1)+'" fill="#adb5bd" fill-opacity="0.16"/>'+
           '<line x1="0" x2="'+w+'" y1="'+Y(pq.p50).toFixed(1)+'" y2="'+Y(pq.p50).toFixed(1)+'" stroke="#adb5bd" stroke-width="1" stroke-dasharray="3 2"/>';
      var diff=last.v-pq.p50;
      if(Math.abs(diff)<0.05)diff=0;
      vs='<span class="mt-vs '+(diff>0?'up':diff<0?'dn':'lv')+'">'+(diff>0?'+':'')+diff.toFixed(1)+' vs peers</span>';
    }
    return '<figure class="mt"><figcaption>'+esc(label)+' <b>'+last.v.toFixed(1)+unit+'</b> '+vs+'</figcaption>'+
      '<svg viewBox="0 0 '+w+' '+h+'" width="100%" height="'+h+'" aria-hidden="true">'+band+
      '<path d="'+d+'V'+(h-12)+'H'+pad+'Z" fill="#0a2540" fill-opacity="0.07"/>'+
      '<path d="'+d+'" fill="none" stroke="#0a2540" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'+
      '<circle cx="'+X(pts.length-1).toFixed(1)+'" cy="'+Y(last.v).toFixed(1)+'" r="3" fill="#fd7e14"/>'+
      '<text x="'+pad+'" y="'+h+'" class="pv-ax">'+esc(pts[0].d.slice(0,7))+'</text>'+
      '<text x="'+(w-pad)+'" y="'+h+'" text-anchor="end" class="pv-ax">'+esc(last.d.slice(0,7))+'</text></svg></figure>';
  }
  function modalBody(b,e){
    var s=b.series||{};
    var pg=(PEERS&&PEERS[b.peer_group||(e&&e.peer_group)])||{};
    var charts=TRENDS.map(function(t){return trend(s[t[0]],t[1],t[2],pg[t[0]])}).filter(Boolean).join('')
               ||'<div class="muted small">Only one period held, so there is nothing to plot yet.</div>';
    // the headline rating per agency, with its short-term beside it; the rest are on the profile
    var st={};((e&&e.short_ratings)||[]).forEach(function(x){st[x.letter]=x.value});
    var head=(e&&e.ratings)||[];
    var rt=head.map(function(x){
      return '<tr><td class="ag">'+esc(AGN[x.agency]||x.agency)+'</td><td class="b">'+esc(x.value)+'</td>'+
             '<td class="mono muted">'+esc(st[x.letter]||'')+'</td>'+
             '<td class="muted">'+esc(x.outlook||'')+'</td></tr>';
    }).join('')||'<tr><td colspan="5" class="muted">No agency rates this entity.</td></tr>';
    var extra=(b.ratings_all||[]).length-head.length;
    // pillars come through as [score, weight]
    var sd=(b.score_detail&&b.score_detail.pillars)||null;
    var pill=sd?Object.keys(sd).map(function(k){var v=sd[k]||[];var pc=v[0],wt=v[1];
      return '<div class="md-pill"><span>'+esc(k.replace(/_/g,' '))+'</span>'+meter(pc,b.band||(e&&e.band),'sm')+
             '<b>'+(pc==null?'—':pc.toFixed(0))+'</b><i>w'+(wt==null?'':wt)+'</i></div>'}).join(''):'';
    var ev=(b.events||[]).slice(0,6).map(function(x){
      var k=x.severity==='bad'?'bad':(x.severity==='warn'?'warn':'good');
      return '<div><span class="dot dot-'+k+'"></span><span class="mono muted">'+esc(x.date)+'</span><span class="hd">'+esc(x.title)+'</span></div>';
    }).join('')||'<div class="muted small">Nothing recorded in the window.</div>';
    return '<div class="md-grid">'+
      '<section><h4>Trends</h4><div class="md-trends">'+charts+'</div>'+
        (Object.keys(pg).length?'<p class="small muted"><span class="mt-key"></span>The band is where this bank\u2019s peer group stands today, quartile to quartile, with the median dashed \u2014 not a peer history.</p>':'')+
      '</section>'+
      '<section><h4>Ratings</h4><table class="plain md-rt"><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup><tbody>'+rt+'</tbody></table>'+
        (extra>0?'<p class="small muted">'+extra+' further rating'+(extra>1?'s':'')+' by type on the full profile.</p>':'')+
        (pill?'<h4>Score make-up</h4><div class="md-pills">'+pill+'</div>':'')+
        (b.percentile!=null?'<p class="small muted">Stronger than '+Math.round(b.percentile)+'% of its peer group ('+esc(String(b.peer_group||'').replace(/_/g,' '))+').</p>':'')+
      '</section>'+
      '<section><h4>Events</h4><div class="cp-news md-news">'+ev+'</div></section></div>';
  }
  function openModal(id,tenor){
    var dlg=document.getElementById('pol-modal');if(!dlg)return;
    var e=byId[id]||{};
    var act=tenor?'<button class="filter active pol-add-ll" data-id="'+esc(id)+'" data-tenor="'+tenor+'">Add at '+esc(tenorLabel(tenor))+'</button>':'';
    dlg.innerHTML='<div class="md-head"><div><div class="md-nm">'+esc(e.short||id)+'</div>'+
      '<div class="small muted">'+esc(e.name||'')+' · '+esc(e.country||'')+'</div></div>'+
      '<div class="md-sc">'+(e.score==null?'<span class="na">—</span>':'<span class="cp-score">'+e.score.toFixed(0)+'</span> <span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>')+'</div>'+
      act+'<a class="filter" href="'+ROOT+'banks/'+esc(id)+'.html">Full profile</a>'+
      '<button class="filter" id="md-close" aria-label="Close">Close</button></div>'+
      '<div id="md-body"><div class="empty">Loading…</div></div>';
    if(!dlg.open)dlg.showModal();
    var put=function(b){var t=document.getElementById('md-body');if(t)t.innerHTML=modalBody(b,e)};
    if(MCACHE[id])return put(MCACHE[id]);
    fetch(ROOT+'data/detail/'+id+'.json').then(function(r){return r.json()}).then(function(b){MCACHE[id]=b;put(b)})
      .catch(function(){var t=document.getElementById('md-body');if(t)t.innerHTML='<div class="empty">Could not load this bank’s detail.</div>'});
  }

  function render(){
    var p=load(); var out=document.getElementById('policy-body'); if(!out||!data)return;
    var html='';
    if(!p.length){html+='<div class="empty">No counterparties yet. Add the names your policy approves and the longest tenor you accept for each.</div>'}
    else{
      var n_flag=0;
      var rows=p.slice().sort(function(a,b){return b.tenor-a.tenor||(byId[a.id]&&byId[a.id].short||'').localeCompare(byId[b.id]&&byId[b.id].short||'')}).map(function(it){
        var e=byId[it.id]; var fl=flags(it,e); if(fl.some(function(x){return x[0]!=='muted'}))n_flag++;
        if(!e)return '<div class="pol-row"><div class="pr-name"><span class="b">'+esc(it.id)+'</span></div><div class="pr-flags">'+chip('No longer covered','bad')+'</div><button class="pol-rm" data-id="'+esc(it.id)+'" title="Remove">×</button></div>';
        var recent=(e.recent||[]).slice(0,3).map(function(x){
          var k=x.severity==='bad'?'bad':(x.severity==='warn'?'warn':'good');
          var w=x.severity==='bad'?'adverse':(x.severity==='warn'?'watch':'positive');
          return '<div><span class="dot dot-'+k+'" title="'+w+'"></span>'+
                 '<span class="mono muted">'+esc(x.date)+'</span>'+
                 '<span class="hd">'+(x.url?'<a href="'+esc(x.url)+'" target="_blank" rel="noopener">':'')+esc(x.title)+(x.url?'</a>':'')+'</span></div>';
        }).join('')||'<div class="muted">Nothing notable in the last 90 days.</div>';
        var fh=fl.map(function(x){return chip(x[1],x[0]==='muted'?'muted':x[0])}).join(' ')||chip('Unchanged since approval','good');
        return '<div class="pol-card" data-id="'+esc(e.id)+'">'+
          '<div class="cp-top">'+
            '<div class="cp-id"><a class="cp-nm" href="'+ROOT+'banks/'+esc(e.id)+'.html">'+esc(e.short)+'</a>'+
              '<div class="cp-sub">'+esc(e.name)+' \u00b7 '+esc(e.country)+'</div></div>'+
            '<div class="cp-tenor"><div class="cp-t">'+esc(tenorLabel(it.tenor))+'</div>'+
              '<div class="small">approved '+esc(it.added||'?')+'</div></div>'+
            '<button class="pol-rm" data-id="'+esc(e.id)+'" title="Remove from policy" aria-label="Remove '+esc(e.short)+'">\u00d7</button>'+
          '</div>'+
          '<div class="cp-body">'+
            '<div class="cp-cell"><h5>Counterparty score</h5>'+
              (e.score==null
                ? '<div class="cp-score-row"><span class="na big">\u2014</span></div><div class="small muted">'+esc(e.unscored||'not scored')+'</div>'
                : '<div class="cp-score-row"><span class="cp-score">'+e.score.toFixed(0)+'</span>'+
                  '<span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span></div>'+
                  meter(e.score,e.band)+
                  '<div class="small muted">'+(e.coverage!=null?Math.round(e.coverage*100)+'% of the method\u2019s inputs':'')+'</div>')+
            '</div>'+
            '<div class="cp-cell"><h5>Key ratios</h5>'+kpis(e)+
              '<div class="cp-asof">as of '+esc(e.asof||'\u2014')+
              (e.leverage_basis==='us_tier1'?' \u00b7 \u2020 Tier 1 leverage, US basis':'')+'</div></div>'+
            '<div class="cp-cell"><h5>Ratings</h5>'+ratingGrid(e.ratings,e.short_ratings)+'</div>'+
            '<div class="cp-cell cp-side"><h5>Market and since approval</h5>'+
              mkt(e.market)+
              (e.market_detail&&e.market_detail.bond_change30!=null
                ? '<div class="small muted">bonds vs peers '+(e.market_detail.bond_change30>0?'+':'')+Math.round(e.market_detail.bond_change30)+' bp</div>':'')+
              fh+'</div>'+
          '</div>'+
          '<div class="cp-news">'+recent+'</div></div>';
      }).join('');
      html+='<div class="pol-summary">'+(n_flag?chip(n_flag+' of '+p.length+' need a look','warn'):chip('All '+p.length+' names unchanged since approval','good'))+' <span class="small muted">Data built '+esc(data.generated.slice(0,16).replace('T',' '))+' UTC. Flags compare today with the day each name was approved.</span></div>';
      html+=overview(p.filter(function(it){return byId[it.id]}));
      html+='<div class="pol-list">'+rows+'</div>';
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
        ll+=(t!==tenors[0]?'<p class="small muted">In addition to the names already listed at longer tenors.</p>':'')+(cands.length?'<div class="ll-grid">'+cands.slice(0,24).map(function(e){
          var vs=(w.score!=null)?(e.score-w.score):null;
          return '<div class="ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'" tabindex="0" role="button" aria-label="'+esc(e.short)+', open detail">'+
            '<div class="ll-nm">'+esc(e.short)+'</div><div class="ll-co">'+esc(e.name)+' \u00b7 '+esc(e.country)+'</div>'+
            '<div class="ll-score"><b>'+e.score.toFixed(1)+'</b><span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>'+
              (vs!=null&&vs>0?'<span class="ll-vs">+'+vs.toFixed(1)+' vs weakest</span>':'')+'</div>'+
            meter(e.score,e.band,'sm')+
            '<div class="ll-rt">'+ratings(e.ratings)+'</div>'+
            '<div class="ll-foot">'+mkt(e.market)+'<button class="filter pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'">Add</button></div></div>';
        }).join('')+'</div>':'<p class="small muted">No further covered name matches the weakest standing you accept at this tenor.</p>');
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
      var a=ev.target.closest('.pol-add-ll');if(a){add(a.dataset.id,+a.dataset.tenor);var d=document.getElementById('pol-modal');if(d&&d.open)d.close();return}
      if(ev.target.id==='md-close'){document.getElementById('pol-modal').close();return}
      // a card opens its detail; a link inside it still navigates
      var card=ev.target.closest('.pol-card,.ll');
      if(card&&!ev.target.closest('a,button')){openModal(card.dataset.id,card.dataset.tenor?+card.dataset.tenor:0);return}
      if(ev.target.id==='pol-clear'){if(confirm('Remove every counterparty from this policy?')){save([]);render()}return}
      if(ev.target.id==='pol-copy'){var l=document.getElementById('pol-link');l.select();try{document.execCommand('copy')}catch(e){}ev.target.textContent='Copied';setTimeout(function(){ev.target.textContent='Copy link'},1500);return}
      if(ev.target.id==='pol-use-shared'){save(window.__shared);window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);render();return}
      if(ev.target.id==='pol-keep-mine'){window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);return}
    });
    document.addEventListener('keydown',function(ev){
      if(ev.key!=='Enter'&&ev.key!==' ')return;
      var card=ev.target.closest&&ev.target.closest('.ll,.pol-card');
      if(card&&!ev.target.closest('a,button')){ev.preventDefault();openModal(card.dataset.id,card.dataset.tenor?+card.dataset.tenor:0)}
    });
    var m=location.hash.match(/#p=([A-Za-z0-9_\-]+)/);if(m){var sh=decode(m[1]);if(sh&&sh.length){if(!load().length){save(sh);history.replaceState(null,'',location.pathname)}else{window.__shared=sh;var box=document.getElementById('pol-shared');box.hidden=false;box.querySelector('span').textContent='This link carries a policy of '+sh.length+' counterparties.'}}}
    render();
  }
  var box=document.getElementById('policy-body');if(!box)return;
  fetch(ROOT+'data/peers.json').then(function(r){return r.json()}).then(function(j){PEERS=j}).catch(function(){});
  fetch(ROOT+'data/policy.json').then(function(r){return r.json()}).then(function(j){data=j;init()}).catch(function(){box.innerHTML='<div class="empty">Could not load the counterparty data.</div>'});
})();
