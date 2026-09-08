// My policy: the user's approved counterparties and tenors, kept in this browser (or carried in a share link),
// checked every visit against the latest public standing, market signal and news. Nothing leaves the browser.
(function(){
  // An empty data-root is the site root, not a missing one: the home page sets it to "" and
  // a falsy test would send every fetch to ../, which escapes the project directory on Pages.
  var _r=document.body.getAttribute('data-root');
  var KEY='counterparty.policy', ROOT=(_r==null?'../':_r);
  var TENORS=[[100,'100 days'],[182,'6 months'],[365,'12 months'],[730,'24 months'],[1825,'5 years']];
  var GRADES=['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC'];
  var data=null, byId={};
  function load(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
  function save(p){try{localStorage.setItem(KEY,JSON.stringify(p))}catch(e){}}
  // the definition marker, drawn from the glossary every page carries
  function mk(k){return window.tipMark?window.tipMark(k):''}
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function fmt(v,dp,suf){return v==null?'<span class="na">—</span>':'<span class="mono">'+Number(v).toFixed(dp==null?1:dp)+(suf||'')+'</span>'}
  function tenorLabel(d){for(var i=0;i<TENORS.length;i++)if(TENORS[i][0]===d)return TENORS[i][1];return d+' days'}
  function bandRank(b){return {A:1,B:2,C:3,D:4,E:5}[b]||9}
  function chip(t,k){return '<span class="chip chip-'+(k||'muted')+'">'+esc(t)+'</span>'}
  var TYPE_LABEL={holding:'Holding company',bank:'Bank',building_society:'Building society',subsidiary:'Subsidiary'};
  function typeTag(e){
    if(!e||e.type!=='holding')return '';
    return '<span class="tag-hold" title="A holding company, not the entity a deposit is placed with. '+
           'Its figures are the group\u2019s.">Holding company</span>';
  }
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
    var t=[['CET1',e.cet1,1,'','cet1_ratio'],['Leverage',e.leverage,1,e.leverage_basis==='us_tier1'?'\u2020':'','leverage_ratio'],['LCR',e.lcr,0,'%','lcr']];
    return '<div class="cp-kpis">'+t.map(function(k){
      return '<div class="cp-kpi"><b>'+(k[1]==null?'<span class="na">\u2014</span>':Number(k[1]).toFixed(k[2])+k[3])+'</b><span>'+k[0]+mk(k[4])+'</span></div>';
    }).join('')+'</div>';
  }
  function mkt(m,terse){if(!m||m.direction==='none')return terse?'<span class="na">\u2014</span>'  :'<span class="muted">no market data</span>';var k=m.direction==='down'?'bad':(m.direction==='up'?'good':'muted');return chip(m.label,k)}
  function ratings(r){return (r||[]).map(function(x){return '<span class="mono" title="'+esc(x.agency+' '+x.type+(x.outlook?' · '+x.outlook:''))+'">'+esc(x.letter)+' '+esc(x.value)+'</span>'}).join(' <span class="muted">·</span> ')||'<span class="muted">unrated</span>'}
  function shortR(r){return (r||[]).map(function(x){return '<span class="mono">'+esc(x.letter)+' '+esc(x.value)+'</span>'}).join(' <span class="muted">·</span> ')||'<span class="muted">—</span>'}
  function snapshot(e){return {score:e.score,band:e.band,grade:e.rating_grade,market:e.market&&e.market.direction,asof:e.asof}}
  function encode(p){try{return btoa(unescape(encodeURIComponent(JSON.stringify(p)))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')}catch(e){return ''}}
  function decode(s){try{s=s.replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';return JSON.parse(decodeURIComponent(escape(atob(s))))}catch(e){return null}}

  // ---- what changed since the name was approved, and what needs a look now
  function flags(item,e){
    var f=[], b=item.base||{};
    if(!e)return [['bad','No longer covered']];
    // [kind, what happened, and a short form for the collapsed row, where a chip has one line]
    if(e.score==null)f.push(['warn','Not enough public data for a score','Not scored']);
    if(b.score!=null&&e.score!=null&&e.score<=b.score-5)f.push(['bad','Score down '+(b.score-e.score).toFixed(1)+' since approved','Score \u2212'+(b.score-e.score).toFixed(1)]);
    if(b.band&&e.band&&bandRank(e.band)>bandRank(b.band))f.push(['bad','Band '+b.band+' → '+e.band,'Band '+b.band+'\u2192'+e.band]);
    if(b.grade!=null&&e.rating_grade!=null&&e.rating_grade>b.grade+0.4)f.push(['bad','Ratings weaker: '+GRADES[Math.floor(b.grade+0.5)-1]+' → '+e.rating_composite,'Rating weaker']);
    (e.negative||[]).forEach(function(n){if(!item.added||n.date>=item.added)f.push(['bad',n.date+' '+n.title,'Adverse action'])});
    if(e.market&&e.market.direction==='down')f.push(['warn',e.market.label,e.market.label]);
    if(e.news30&&e.news30.bad)f.push(['warn',e.news30.bad+' adverse headline'+(e.news30.bad>1?'s':'')+' in 30 days',e.news30.bad+' adverse headline'+(e.news30.bad>1?'s':'')]);
    if(e.age_days!=null&&e.age_days>180)f.push(['warn','Regulatory figures '+e.age_days+' days old','Figures '+e.age_days+'d old']);
    if(e.inherited&&e.inherited.length)f.push(['muted','Some figures from the group or lead bank','Group figures']);
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

  function scoreHist(mine,all,solo){
    // The universe is the context and your names are the point, so this is emphasis: the
    // distribution in grey behind, each of your names marked on it. Two bar series scaled to
    // their own maxima would put one name at the same height as forty.
    var bins=20,w=260,h=52,base=h-14,ax=[];
    for(var i=0;i<bins;i++)ax.push(0);
    all.forEach(function(e){if(e.score!=null)ax[Math.min(bins-1,Math.floor(e.score/100*bins))]++});
    var amax=Math.max.apply(null,ax)||1, bw=w/bins, inner='';
    for(var j=0;j<bins;j++){
      var ah=ax[j]/amax*(base-4);
      if(ah>0)inner+='<rect x="'+(j*bw+.6).toFixed(1)+'" y="'+(base-ah).toFixed(1)+'" width="'+(bw-1.2).toFixed(1)+'" height="'+ah.toFixed(1)+'" rx="1.5" fill="'+(solo?'#c3ced9':'#e9ecef')+'"/>';
    }
    inner+='<line x1="0" x2="'+w+'" y1="'+base+'" y2="'+base+'" stroke="#dee2e6" stroke-width="1"/>';
    mine.forEach(function(e){
      if(e.score==null)return;
      var x=e.score/100*w;
      inner+='<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+(base-13)+'" y2="'+(base+4)+'" stroke="#fff" stroke-width="3.4"/>'+
             '<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+(base-13)+'" y2="'+(base+4)+'" stroke="#fd7e14" stroke-width="2"><title>'+esc(e.short)+' '+e.score.toFixed(1)+'</title></line>';
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
        '<figure><figcaption>Band mix'+mk('band')+'</figcaption>'+bandMix(es)+'</figure>'+
        '<figure><figcaption>Against every name'+mk('score')+'</figcaption>'+scoreHist(es,data.rows)+'</figure>'+
        '<figure><figcaption>Composite rating'+mk('composite')+'</figcaption>'+ratingHist(es)+'</figure>'+
        '<figure><figcaption>Score by tenor accepted'+mk('tenor')+'</figcaption>'+tenorScore(items)+'</figure>'+
      '</div></div>';
  }


  // ---- detail without leaving the page ----------------------------------------------
  // The bank's own JSON already carries its series, every rating, the score make-up and its
  // place among peers, so a card opens all of it here rather than sending the reader away.
  var MCACHE={}, PEERS=null;
  var AGN={fitch:'Fitch',sp:'S&P',moodys:"Moody's",dbrs:'DBRS',kbra:'KBRA',scope:'Scope',jcr:'JCR',creditreform:'Creditreform'};
  var TRENDS=[['cet1_ratio','CET1 ratio','%','cet1_ratio'],['tier1_ratio','Tier 1 ratio','%','tier1_ratio'],
              ['total_capital_ratio','Total capital','%','total_capital_ratio'],
              ['leverage_ratio','Leverage','%','leverage_ratio'],['lcr','LCR','%','lcr'],['nsfr','NSFR','%','nsfr'],
              ['npl_ratio','Non-performing','%','npl_ratio'],['roe','Return on equity','%','roe'],
              ['efficiency_ratio','Cost to income','%','cost_to_income']];
  // The bank's own path, with its peer group's current quartile band behind it. The band is
  // where the peers stand today, not a peer history, so it is drawn flat and labelled as such:
  // it answers "is this bank ahead of its peers now", which the line alone cannot.
  function trend(pts,label,unit,pq,gk){
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
    return '<figure class="mt"><figcaption>'+esc(label)+mk(gk)+' <b>'+last.v.toFixed(1)+unit+'</b> '+vs+'</figcaption>'+
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
    var charts=TRENDS.map(function(t){return trend(s[t[0]],t[1],t[2],pg[t[0]],t[3])}).filter(Boolean).join('')
               ||(b.series?'<div class="muted small">Only one period held, so there is nothing to plot yet.</div>'
                          :'<div class="md-wait">'+[0,1,2,3,4,5].map(function(){return '<div class="md-sk"></div>'}).join('')+'</div>');
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
    var ev=(b.events||(e&&e.recent)||[]).slice(0,6).map(function(x){
      var k=x.severity==='bad'?'bad':(x.severity==='warn'?'warn':'good');
      return '<div><span class="dot dot-'+k+'"></span><span class="mono muted">'+esc(x.date)+'</span><span class="hd">'+esc(x.title)+'</span></div>';
    }).join('')||'<div class="muted small">Nothing recorded in the window.</div>';
    return '<div class="md-grid">'+
      '<section><h4>Trends</h4><div class="md-trends" id="md-trends">'+charts+'</div>'+
        (Object.keys(pg).length?'<p class="small muted"><span class="mt-key"></span>Peer group today, quartile to quartile, median dashed.</p>':'')+
      '</section>'+
      '<section><h4>Ratings'+mk('rating')+'</h4><table class="plain md-rt"><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup><tbody>'+rt+'</tbody></table>'+
        (extra>0?'<p class="small muted">'+extra+' further rating'+(extra>1?'s':'')+' by type on the full profile.</p>':'')+
        (pill?'<h4>Score make-up'+mk('pillar')+'</h4><div class="md-pills">'+pill+'</div>':'')+
        (b.percentile!=null?'<p class="small muted">Stronger than '+Math.round(b.percentile)+'% of its peer group'+mk('percentile')+' ('+esc(String(b.peer_group||'').replace(/_/g,' '))+').</p>':'')+
      '</section>'+
      '<section><h4>Events</h4><div class="cp-news md-news">'+ev+'</div></section></div>';
  }
  function openModal(id,tenor){
    var dlg=document.getElementById('pol-modal');if(!dlg)return;
    var e=byId[id]||{};
    var act=tenor?'<button class="filter active pol-add-ll" data-id="'+esc(id)+'" data-tenor="'+tenor+'">Add at '+esc(tenorLabel(tenor))+'</button>':'';
    dlg.innerHTML='<div class="md-head"><div><div class="md-nm">'+esc(e.short||id)+'</div>'+
      '<div class="small muted">'+esc(e.name||'')+' \u00b7 '+esc(e.country||'')+typeTag(e)+'</div></div>'+
      '<div class="md-sc">'+(e.score==null?'<span class="na">—</span>':'<span class="cp-score">'+e.score.toFixed(0)+'</span> <span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>')+'</div>'+
      act+'<a class="filter" href="'+ROOT+'banks/'+esc(id)+'.html">Full profile</a>'+
      '<button class="filter" id="md-close" aria-label="Close">Close</button></div>'+
      '<div id="md-body"><div class="empty">Loading…</div></div>';
    if(!dlg.open)dlg.showModal();
    var put=function(b){var t=document.getElementById('md-body');if(t)t.innerHTML=modalBody(b,e)};
    if(MCACHE[id])return put(MCACHE[id]);
    detail(id).then(put).catch(function(){
      var t=document.getElementById('md-body');if(t)t.innerHTML='<div class="empty">Could not load this bank’s detail.</div>'});
  }

  // Opening a bank costs one small file, and on Pages a first byte for a file nobody has asked for
  // yet can take the better part of a second. So the request starts at the first sign of intent -
  // the pointer settling on a row, a finger touching it, a key focusing it - and the click usually
  // finds it already in flight or done. One promise per bank, so intent and click never fetch twice.
  var INFLIGHT={};
  function detail(id){
    if(MCACHE[id])return Promise.resolve(MCACHE[id]);
    if(INFLIGHT[id])return INFLIGHT[id];
    INFLIGHT[id]=fetch(ROOT+'data/detail/'+id+'.json')
      .then(function(r){if(!r.ok)throw 0;return r.json()})
      .then(function(b){MCACHE[id]=b;delete INFLIGHT[id];return b})
      .catch(function(err){delete INFLIGHT[id];throw err});
    return INFLIGHT[id];
  }
  function warm(el){
    var row=el&&el.closest&&el.closest('[data-id]'); if(!row)return;
    var id=row.dataset.id; if(!id||MCACHE[id]||INFLIGHT[id])return;
    detail(id).catch(function(){});
  }
  ['mouseover','focusin','touchstart','mousedown'].forEach(function(ev){
    document.addEventListener(ev,function(e){warm(e.target)},{passive:true,capture:true});
  });


  // ---- the whole universe on the same page -------------------------------------------
  // The board, the bank list and the ratings grid all showed slices of this. One table with
  // filters and the same dialog on click does the lot, and a name can be added where it is read.
  var REGION_LABEL={uk:'United Kingdom',eu:'Europe',us:'United States',us_ch:'US and Switzerland',
                    asia:'Asia',gulf:'Gulf',aus_can:'Australia and Canada',ch:'Switzerland'};
  var uniSort={key:'score',dir:-1};
  function uniRows(){
    var q=(document.getElementById('uni-q').value||'').trim().toLowerCase();
    var reg=document.getElementById('uni-region').value, typ=document.getElementById('uni-type').value;
    var bnd=document.getElementById('uni-band').value, only=document.getElementById('uni-scored').checked;
    var have={}; load().forEach(function(it){have[it.id]=it.tenor});
    return data.rows.filter(function(e){
      if(reg&&e.region!==reg)return false;
      if(typ&&e.type!==typ)return false;
      if(bnd&&e.band!==bnd)return false;
      if(only&&e.score==null)return false;
      if(q&&(e.short+' '+e.name+' '+(e.country||'')+' '+(e.lei||'')).toLowerCase().indexOf(q)<0)return false;
      return true;
    }).map(function(e){return {e:e,tenor:have[e.id]}}).sort(function(a,b){
      var k=uniSort.key, va=a.e[k], vb=b.e[k];
      if(va==null&&vb==null)return 0; if(va==null)return 1; if(vb==null)return -1;
      if(typeof va==='string')return uniSort.dir*va.localeCompare(vb);
      return uniSort.dir*(va-vb);
    });
  }
  function renderUni(){
    var body=document.getElementById('uni-body'); if(!body||!data)return;
    var rows=uniRows(), t=+document.getElementById('uni-tenor').value;
    document.getElementById('uni-count').textContent=rows.length+' of '+data.rows.length+' names';
    body.innerHTML=rows.slice(0,400).map(function(r){
      var e=r.e;
      return '<tr class="uni-row" data-id="'+esc(e.id)+'">'+
        '<td><span class="b">'+esc(e.short)+'</span>'+typeTag(e)+'<div class="small muted">'+esc(e.name)+'</div></td>'+
        '<td class="mono small">'+esc(e.country||'')+'</td>'+
        '<td class="num">'+(e.score==null?'<span class="na">—</span>':
            // the number and its band already say where the name stands, and the table sorts on it;
            // a bar in every one of 152 rows only adds weight
            '<span class="mono b">'+e.score.toFixed(1)+'</span> <span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>')+
          (e.score==null&&e.unscored?'<div class="small muted">'+esc(e.unscored)+'</div>':'')+'</td>'+
        '<td class="mono">'+esc(e.rating_composite||'—')+'</td>'+
        '<td class="num mono">'+(e.cet1==null?'—':e.cet1.toFixed(1))+'</td>'+
        '<td class="num mono">'+(e.lcr==null?'—':Math.round(e.lcr)+'%')+'</td>'+
        '<td class="mono small muted">'+esc(e.asof||'—')+'</td>'+
        '<td>'+mkt(e.market,1)+'</td>'+
        '<td class="num">'+(r.tenor!=null
            ? '<span class="chip chip-good" title="already in your policy">'+esc(tenorLabel(r.tenor))+'</span>'
            : '<button class="filter pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'">Add</button>')+'</td></tr>';
    }).join('')||'<tr><td colspan="9" class="empty">No name matches those filters.</td></tr>';
  }
  function initUni(){
    var reg=document.getElementById('uni-region'), typ=document.getElementById('uni-type'),
        ten=document.getElementById('uni-tenor');
    if(!reg)return;
    var regions={},types={};
    data.rows.forEach(function(e){if(e.region)regions[e.region]=1;if(e.type)types[e.type]=1});
    Object.keys(regions).sort().forEach(function(r){var o=document.createElement('option');o.value=r;o.textContent=REGION_LABEL[r]||r;reg.appendChild(o)});
    Object.keys(types).sort().forEach(function(x){var o=document.createElement('option');o.value=x;o.textContent=TYPE_LABEL[x]||x;typ.appendChild(o)});
    TENORS.forEach(function(x){var o=document.createElement('option');o.value=x[0];o.textContent='Add at '+x[1];if(x[0]===365)o.selected=true;ten.appendChild(o)});
    ['uni-q','uni-region','uni-type','uni-band','uni-scored','uni-tenor'].forEach(function(id){
      var el=document.getElementById(id); if(el)el.addEventListener('input',renderUni);
    });
    document.querySelectorAll('#uni-table th[data-sort]').forEach(function(th){
      th.addEventListener('click',function(){
        var k=th.dataset.sort;
        uniSort.dir=(uniSort.key===k)?-uniSort.dir:(k==='short'||k==='country'||k==='asof'?1:-1);
        uniSort.key=k;
        document.querySelectorAll('#uni-table th[data-sort]').forEach(function(x){x.removeAttribute('aria-sort')});
        th.setAttribute('aria-sort',uniSort.dir>0?'ascending':'descending');
        renderUni();
      });
    });
    renderUni();
  }

  function render(){
    var p=load(); var out=document.getElementById('policy-body'); if(!out||!data)return;
    var html='';
    // nothing approved yet: say what to do and open the door to the table, rather than showing an
    // empty box and a share bar with nothing to share
    var share=document.getElementById('pol-share'); if(share)share.hidden=!p.length;
    if(!p.length){
      // the space beside the instruction is worth more as real data than as white: the strongest
      // published standing today, addable in one click, so the page does something on arrival
      var top=data.rows.filter(function(e){return e.score!=null}).sort(function(a,b){return b.score-a.score}).slice(0,5);
      html+='<div class="pol-empty"><div><p>Type a name above, or add one from any row of the table below. '+
        'Every name is re-checked each night against its regulatory filings, its agency ratings and the news.</p>'+
        '<button class="filter active" id="pol-browse">Browse all '+data.rows.length+' names</button>'+
        '<figure class="pe-fig"><figcaption>Where the '+data.rows.filter(function(e){return e.score!=null}).length+
        ' scored names sit'+mk('score')+'</figcaption>'+scoreHist([],data.rows,1)+'</figure></div>'+
        '<div class="pe-top"><h5>Strongest published standing today</h5>'+top.map(function(e){
          return '<div class="pe-row" data-id="'+esc(e.id)+'"><span class="pe-nm">'+esc(e.short)+'</span>'+
                 '<span class="pe-sc mono">'+e.score.toFixed(1)+'</span>'+
                 '<span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>'+
                 '<button class="filter pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="365">Add</button></div>';
        }).join('')+'</div></div>'}
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
        // a name that has moved since approval carries an edge, so a long list scans in one pass
        var moved=fl.some(function(x){return x[0]!=='muted'&&x[0]!=='good'});
        // one row of figures per name, and the rest behind an expander: a policy of twenty names is
        // read down a column of numbers, not by scrolling through twenty cards of prose.
        var worst_fl=fl.filter(function(x){return x[0]!=='muted'})[0];
        var kv=function(v,l,cls){return '<div class="ck'+(cls?' '+cls:'')+'"><b>'+v+'</b><span>'+l+'</span></div>'};
        var num=function(v,dp,suf){return v==null?'<span class="na">\u2014</span>':Number(v).toFixed(dp)+(suf||'')};
        return '<div class="pol-card'+(moved?' pol-card-flag':'')+'" data-id="'+esc(e.id)+'">'+
          '<div class="cp-top">'+
            '<button class="cp-exp" data-id="'+esc(e.id)+'" aria-expanded="false" aria-label="Show detail for '+esc(e.short)+'"></button>'+
            '<div class="cp-id"><a class="cp-nm" href="'+ROOT+'banks/'+esc(e.id)+'.html">'+esc(e.short)+'</a>'+typeTag(e)+
              '<div class="cp-sub">'+esc(e.name)+' \u00b7 '+esc(e.country)+'</div></div>'+
            kv((e.score==null?'<span class="na">\u2014</span>':e.score.toFixed(0))+
               (e.band?' <span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>':''),'score','ck-score')+
            kv(esc(e.rating_composite||'\u2014'),'rating')+
            kv(num(e.cet1,1),'CET1')+
            kv(num(e.leverage,1)+(e.leverage_basis==='us_tier1'?'\u2020':''),'leverage')+
            kv(e.lcr==null?'<span class="na">\u2014</span>':Math.round(e.lcr)+'%','LCR')+
            kv(esc(tenorLabel(it.tenor)),'tenor','ck-tenor')+
            '<div class="cp-tags">'+(worst_fl?chip(worst_fl[2]||worst_fl[1],worst_fl[0])
              :((e.market&&e.market.direction!=='none')?mkt(e.market):''))+'</div>'+
            '<button class="pol-rm" data-id="'+esc(e.id)+'" title="Remove from policy" aria-label="Remove '+esc(e.short)+'">\u00d7</button>'+
          '</div>'+
          '<div class="cp-detail" hidden>'+
            '<div class="cp-body">'+
              '<div class="cp-cell"><h5>Counterparty score'+mk('score')+'</h5>'+
                (e.score==null
                  ? '<div class="cp-score-row"><span class="na big">\u2014</span></div><div class="small muted">'+esc(e.unscored||'not scored')+'</div>'
                  : '<div class="cp-score-row"><span class="cp-score">'+e.score.toFixed(0)+'</span>'+
                    '<span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span></div>'+
                    meter(e.score,e.band)+
                    '<div class="small muted">'+(e.coverage!=null?Math.round(e.coverage*100)+'% of the method\u2019s inputs':'')+'</div>')+
              '</div>'+
              '<div class="cp-cell"><h5>Key ratios</h5>'+kpis(e)+
                '<div class="cp-asof">as of'+mk('as_at')+' '+esc(e.asof||'\u2014')+
                (e.leverage_basis==='us_tier1'?' \u00b7 \u2020 Tier 1 leverage, US basis':'')+'</div></div>'+
              '<div class="cp-cell"><h5>Ratings'+mk('rating')+'</h5>'+ratingGrid(e.ratings,e.short_ratings)+'</div>'+
              '<div class="cp-cell cp-side"><h5>Market and changes'+mk('market_signal')+'</h5>'+
                mkt(e.market)+
                (e.market_detail&&e.market_detail.bond_change30!=null
                  ? '<div class="small muted">bonds vs peers '+(e.market_detail.bond_change30>0?'+':'')+Math.round(e.market_detail.bond_change30)+' bp</div>':'')+
                fh+'<div class="small muted">approved '+esc(it.added||'?')+'</div></div>'+
            '</div>'+
            '<div class="cp-news">'+recent+'</div></div></div>';
      }).join('');
      html+='<div class="pol-summary">'+(n_flag?chip(n_flag+' of '+p.length+' need a look','warn'):chip('All '+p.length+' names unchanged since approval','good'))+' <span class="small muted">Flags compare today with the day you approved each name.</span></div>';
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
        ll+='<h4>'+esc(tenorLabel(t))+' <span class="muted small">· weakest you accept: band '+esc(w.band||'?')+', ratings '+esc(GRADES[Math.floor((w.grade||1)+0.5)-1]||'?')+', score '+(w.score!=null?w.score.toFixed(1):'?')+'</span></h4>';
        ll+=(t!==tenors[0]?'<p class="small muted">Beyond those listed at longer tenors.</p>':'')+(cands.length?'<div class="ll-grid">'+cands.slice(0,24).map(function(e){
          var vs=(w.score!=null)?(e.score-w.score):null;
          // four rows and no meter: the action and the market read on the title line, and the score
          // says what a bar under it would repeat. A shortlist is scanned, not studied.
          var mp=(e.market&&e.market.direction!=='none')?mkt(e.market):'';
          return '<div class="ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'" tabindex="0" role="button" aria-label="'+esc(e.short)+', open detail">'+
            '<div class="ll-top"><span class="ll-nm">'+esc(e.short)+typeTag(e)+'</span>'+
              '<span class="ll-act">'+mp+'<button class="filter ll-add pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'">Add</button></span></div>'+
            '<div class="ll-co">'+esc(e.name)+' \u00b7 '+esc(e.country)+'</div>'+
            '<div class="ll-score"><b>'+e.score.toFixed(1)+'</b><span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span>'+
              (vs!=null&&vs>0?'<span class="ll-vs">+'+vs.toFixed(1)+'</span>':'')+'</div>'+
            '<div class="ll-rt">'+ratings(e.ratings)+'</div></div>';
        }).join('')+'</div>':'<p class="small muted">No further covered name matches the weakest standing you accept at this tenor.</p>');
      });
      html+='<div class="ll-sec"><h3>Like-for-like</h3><p class="small muted">Covered names at least as strong as the weakest you already accept at each tenor \u2014 same or better band, ratings and score, and no widening market signal.</p>'+ll+'</div>';
    }
    out.innerHTML=html;
    renderUni();
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
      var card=ev.target.closest('.pol-card,.ll,.uni-row');
      if(card&&!ev.target.closest('a,button')){
        var tn=card.dataset.tenor?+card.dataset.tenor:(card.classList.contains('uni-row')?+document.getElementById('uni-tenor').value:0);
        openModal(card.dataset.id,tn);return}
      if(ev.target.id==='pol-clear'){if(confirm('Remove every counterparty from this policy?')){save([]);render()}return}
      if(ev.target.id==='pol-copy'){var l=document.getElementById('pol-link');l.select();try{document.execCommand('copy')}catch(e){}ev.target.textContent='Copied';setTimeout(function(){ev.target.textContent='Copy link'},1500);return}
      if(ev.target.id==='pol-use-shared'){save(window.__shared);window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);render();return}
      if(ev.target.id==='pol-keep-mine'){window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);return}
    });
    // the chevron opens the detail in place; a click anywhere else on the row still opens the dialog
    document.addEventListener('click',function(ev){
      var x=ev.target.closest('.cp-exp'); if(!x)return;
      ev.preventDefault(); ev.stopPropagation();
      var card=x.closest('.pol-card'), d=card&&card.querySelector('.cp-detail'); if(!d)return;
      d.hidden=!d.hidden; x.setAttribute('aria-expanded',d.hidden?'false':'true');
      card.classList.toggle('cp-open',!d.hidden);
    },true);
    document.addEventListener('click',function(ev){
      if(!ev.target.closest('#pol-browse'))return;
      var t=document.querySelector('.tab[data-tab="universe"]'); if(t&&!t.classList.contains('active'))t.click();
      var q=document.getElementById('uni-q'); if(q)q.focus({preventScroll:true});
      var box=document.getElementById('browse'); if(box)box.scrollIntoView({behavior:'smooth',block:'start'});
    });
    document.addEventListener('keydown',function(ev){
      if(ev.key!=='Enter'&&ev.key!==' ')return;
      var card=ev.target.closest&&ev.target.closest('.ll,.pol-card');
      if(card&&!ev.target.closest('a,button')){ev.preventDefault();openModal(card.dataset.id,card.dataset.tenor?+card.dataset.tenor:0)}
    });
    var m=location.hash.match(/#p=([A-Za-z0-9_\-]+)/);if(m){var sh=decode(m[1]);if(sh&&sh.length){if(!load().length){save(sh);history.replaceState(null,'',location.pathname)}else{window.__shared=sh;var box=document.getElementById('pol-shared');box.hidden=false;box.querySelector('span').textContent='This link carries a policy of '+sh.length+' counterparties.'}}}
    render();
    initUni();
  }
  var box=document.getElementById('policy-body');if(!box)return;
  fetch(ROOT+'data/peers.json').then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(j){PEERS=j}).catch(function(){});
  function failed(){
    box.innerHTML='<div class="empty">Could not load the counterparty data. Reload the page.</div>';
    var u=document.getElementById('uni-body');
    if(u)u.innerHTML='<tr><td colspan="9" class="empty">Could not load the counterparty data. Reload the page.</td></tr>';
  }
  fetch(ROOT+'data/policy.json').then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(j){data=j;init()}).catch(failed);
})();
