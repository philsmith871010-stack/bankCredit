(function(){
  // ---- whose judgement this is -------------------------------------------------------------
  // The site publishes a number built from published regulatory figures and the agencies' own
  // ratings. How much each of those counts for is a policy judgement, not a fact, and it is the
  // reader's to make: the weights below are a starting point, they live in this browser, and every
  // score on the site is computed from whatever they are set to. Nothing here is a credit rating
  // and nothing here is advice.
  var WKEY='counterparty.weights';
  var PILLARS=[['capital','Capital',25,'CET1, leverage and total capital against Basel thresholds'],
               ['liquidity','Liquidity',15,'LCR and NSFR'],
               ['asset_quality','Asset quality',5,'non-performing loan ratio'],
               ['profitability','Profitability',5,'return on equity and assets, cost-income'],
               ['stability','Capital headroom',10,'CET1 over the overall requirement'],
               ['rating','Agency ratings',40,'the median long-term grade of the agencies that rate it']];
  var DEFAULTW={};PILLARS.forEach(function(p){DEFAULTW[p[0]]=p[2]});
  // the thresholds and caps the published method uses; the weights are the only part you set
  var SCORE_BANDS=[[80,'A'],[65,'B'],[50,'C'],[35,'D'],[0,'E']];   // not BANDS: this file already had one
  var GRADE_CAPS=[[7,100],[10,74.9],[17,64.9]];
  var UNRATED_CAP=74.9, OVERLAY_CAP=10, RATING_SCORE=[100,95,91,87,81,75,69,60,52,44,33,25,17,10,5,2,0];
  function weights(){
    var w={};try{w=JSON.parse(localStorage.getItem(WKEY)||'{}')||{}}catch(e){w={}}
    var out={},any=false;
    PILLARS.forEach(function(p){
      var v=Number(w[p[0]]);
      if(isFinite(v)&&v>=0&&v<=100){out[p[0]]=v;if(v!==p[2])any=true}else out[p[0]]=p[2];
    });
    out.__custom=any;
    return out;
  }
  function bandFor(v){for(var i=0;i<SCORE_BANDS.length;i++)if(v>=SCORE_BANDS[i][0])return SCORE_BANDS[i][1];return 'E'}
  function scoreCap(g){
    if(g==null)return UNRATED_CAP;
    var n=Math.round(g);
    for(var i=0;i<GRADE_CAPS.length;i++)if(n<=GRADE_CAPS[i][0])return GRADE_CAPS[i][1];
    return GRADE_CAPS[GRADE_CAPS.length-1][1];
  }
  // The published method, with the reader's weights in place of ours. A pillar the bank does not
  // report is not a zero: the ratio weight is shared out over what it does report, exactly as the
  // site's own figures are computed, and the coverage is carried so a thin name still says so.
  function rescore(e,w){
    var pw=e.pw; if(!pw)return {score:e.score,band:e.band,coverage:e.coverage};
    if(pw[0]==null||e.rating_grade==null)return {score:null,band:'',coverage:e.coverage};
    var total=0,used=0,weighted=0;
    for(var i=0;i<5;i++){
      var k=PILLARS[i][0]; total+=w[k];
      if(pw[i]!=null){used+=w[k];weighted+=pw[i]*w[k]}
    }
    var rw=w.rating, rs=pw[5];
    if(total+rw<=0)return {score:null,band:'',coverage:e.coverage};
    var ratios=used?weighted/used:0;
    var pub=(ratios*total+rs*rw)/(total+rw);
    var ov=Math.max(-OVERLAY_CAP,Math.min(OVERLAY_CAP,e.overlay||0));
    var cap=scoreCap(e.rating_grade);
    var fin=Math.min(cap,Math.max(0,Math.min(100,pub+ov)));
    return {score:Math.round(Math.min(pub,cap)*10)/10,band:(e.coverage>=0.5?bandFor(fin):'?'),
            coverage:e.coverage,final:Math.round(fin*10)/10};
  }
  function save(w){try{localStorage.setItem(WKEY,JSON.stringify(w))}catch(e){}}

  // A profile page is built with the starting weights, because it is built once for everyone. If
  // this reader has set their own, the number, the band and the pillar weights on it are redrawn
  // from theirs, so no page on the site shows a score the reader did not ask for.
  function dressProfile(){
    var card=document.querySelector('.score-card[data-pw]'); if(!card)return;
    var w=weights(); if(!w.__custom)return;
    var e;
    try{e={pw:JSON.parse(card.dataset.pw),overlay:+card.dataset.overlay||0,
           rating_grade:card.dataset.grade===''?null:+card.dataset.grade,
           coverage:+card.dataset.coverage||0}}catch(err){return}
    var r=rescore(e,w); if(r.score==null)return;
    var fig=card.querySelector('.score-fig .huge'); if(fig)fig.textContent=r.score.toFixed(0);
    var band=card.querySelector('.score-band .chip');
    if(band&&r.band&&r.band!=='?')band.textContent='Band '+r.band;
    card.querySelectorAll('.pillar[data-k]').forEach(function(el){
      var k=el.dataset.k, out=el.querySelector('.pw');
      if(out&&w[k]!=null)out.textContent='w '+w[k];
    });
    var head=card.querySelector('.score-head .tile-label');
    if(head&&!card.querySelector('.score-yours'))
      head.insertAdjacentHTML('afterend','<span class="score-yours" title="computed from the weights you set on the Policy page">your weights</span>');
  }
  window.CPW={PILLARS:PILLARS,DEFAULT:DEFAULTW,weights:weights,save:save,rescore:rescore,
              bandFor:bandFor,scoreCap:scoreCap};
  addEventListener('DOMContentLoaded',dressProfile);
  if(document.readyState!=='loading')dressProfile();
})();
(function(){
  var KEY='counterparty.watch';
  function watch(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
  function setWatch(w){try{localStorage.setItem(KEY,JSON.stringify(w))}catch(e){}}
  function paintWatch(){var w=watch();document.querySelectorAll('.watch,.watch-btn').forEach(function(b){var on=w.indexOf(b.dataset.id)>=0;b.classList.toggle('on',on);var s=b.querySelector('span');if(s)s.textContent=on?'Watching':'Watch'})}
  document.addEventListener('click',function(e){
    var b=e.target.closest('.watch,.watch-btn');if(b){e.preventDefault();var w=watch(),i=w.indexOf(b.dataset.id);if(i>=0)w.splice(i,1);else w.push(b.dataset.id);setWatch(w);paintWatch();applyFilter();return}
    var f=e.target.closest('.filter');if(f){document.querySelectorAll('.filter').forEach(function(x){x.classList.remove('active')});f.classList.add('active');applyFilter();return}
    var t=e.target.closest('.tab');var card=t&&t.closest('.tabs-card');if(t&&card){card.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active')});card.querySelectorAll('.panel').forEach(function(p){p.classList.toggle('active',p.dataset.panel===t.dataset.tab)});t.classList.add('active');if(location.hash.replace('#','').split('&')[0]!==t.dataset.tab)history.replaceState(null,'','#'+t.dataset.tab);loadPanel(card.querySelector('.panel[data-panel="'+t.dataset.tab+'"]'));return}
    var th=e.target.closest('th[data-sort]');if(th){sortBy(th.dataset.sort,th.cellIndex);return}
  });
  var q=document.getElementById('q');if(q)q.addEventListener('input',applyFilter);
  function applyFilter(){var tb=document.querySelector('#board tbody');if(!tb)return;var region=(document.querySelector('.filter.active')||{}).dataset||{};var term=(q&&q.value||'').toLowerCase();var w=watch();
    tb.querySelectorAll('tr').forEach(function(tr){var ok=true;if(region.region&&region.region!=='all'){ok=region.region==='watch'?w.indexOf(tr.dataset.id)>=0:tr.dataset.region===region.region}
      if(ok&&term)ok=tr.textContent.toLowerCase().indexOf(term)>=0;tr.style.display=ok?'':'none'})}
  var dir={};function sortBy(k,ci0){var tb=document.querySelector('#board tbody');if(!tb)return;if(k==='col')k='col'+ci0;dir[k]=dir[k]==='asc'?'desc':'asc';var rows=[].slice.call(tb.querySelectorAll('tr'));
    rows.sort(function(a,b){var av,bv;if(k==='name'){av=a.dataset.name;bv=b.dataset.name;return dir[k]==='asc'?av.localeCompare(bv):bv.localeCompare(av)}
      if(k.indexOf('col')===0){av=+((a.children[ci0]||{}).dataset||{}).v||0;bv=+((b.children[ci0]||{}).dataset||{}).v||0}else if(k==='score'){av=+a.dataset.score;bv=+b.dataset.score}else if(k==='rating'){av=-(+a.dataset.g);bv=-(+b.dataset.g);if(!dir.ratingInit){dir.ratingInit=1;dir[k]='desc'}}else if(k==='asof'){av=(a.querySelector('.age')||{}).textContent||'';bv=(b.querySelector('.age')||{}).textContent||'';return dir[k]==='asc'?av.localeCompare(bv):bv.localeCompare(av)}
      else{var ci={cet1:3,leverage:4,lcr:5}[k];av=parseFloat((a.children[ci].textContent||'').replace(/[^0-9.\-]/g,''))||-1;bv=parseFloat((b.children[ci].textContent||'').replace(/[^0-9.\-]/g,''))||-1}
      return dir[k]==='asc'?av-bv:bv-av});rows.forEach(function(r){tb.appendChild(r)})}
  paintWatch();
  // the board arrives with a panel, so its watch marks and the current filter are painted then
  (window.__panelInit=window.__panelInit||[]).push(function(){paintWatch();applyFilter()});
})();

// A tab nobody has opened is not worth its HTML in the page. The heavy panels are written as
// fragments and fetched the first time the tab is used - or when the pointer settles on it,
// which is usually a moment earlier. Everything a fragment needs is wired again on arrival.
function skeleton(n,cls){var s='';for(var i=0;i<(n||6);i++)s+='<span class="sk"></span>';
  return '<div class="'+(cls||'sk-rows')+'" aria-hidden="true">'+s+'</div>'}
// The bytes are warmed apart from the DOM: an idle browser fetches the text and holds it, and the
// click that follows only has to insert it. Nothing is built until a tab is actually opened.
var PANEL_TEXT={};
function warmPanel(p){
  if(!p||!p.dataset.src)return null;
  var src=p.dataset.src;
  if(!PANEL_TEXT[src]){
    var r=document.body.getAttribute('data-root'); r=(r==null?'../':r);
    PANEL_TEXT[src]=lowFetch(r+src).then(function(x){if(!x.ok)throw 0;return x.text()})
      .catch(function(e){delete PANEL_TEXT[src];throw e});
  }
  return PANEL_TEXT[src];
}
function loadPanel(p){
  if(!p||!p.dataset.src||p.dataset.loaded)return;
  p.dataset.loaded='1';
  var w=warmPanel(p); if(!w){p.dataset.loaded='';return}
  p.innerHTML=skeleton(8);
  w.then(function(html){
    p.innerHTML=html;
    (window.__panelInit||[]).forEach(function(f){try{f()}catch(e){}});
    // a panel may bring its own script; it runs once, after its markup is in place, and the
    // data behind it is asked for then rather than on every visit to the page
    if(p.dataset.js){var r=document.body.getAttribute('data-root'); r=(r==null?'../':r);
      var sc=document.createElement('script');sc.src=r+p.dataset.js;document.body.appendChild(sc);
      p.removeAttribute('data-js')}
  }).catch(function(){
    p.dataset.loaded='';
    p.innerHTML='<div class="empty">Could not load this panel. Reload the page.</div>';
  });
}
document.addEventListener('mouseover',function(e){
  var t=e.target.closest&&e.target.closest('.tab'); if(!t)return;
  var card=t.closest('.tabs-card'); if(!card)return;
  warmPanel(card.querySelector('.panel[data-panel="'+t.dataset.tab+'"]'));
},{passive:true});
// Warming waits for the page to have what the reader came for. Neither the load event nor an
// idle callback is enough on their own: load fires when the document's own subresources are done,
// which on a slow line is long before a 50 KB list has arrived, and the main thread is idle the
// whole time it waits for the network. Measured on a throttled line, warming from load pushed the
// list itself from two seconds to six by taking the pipe. So the page says when it is ready, and
// everything speculative is fetched at low priority behind it.
var READY=!document.getElementById('policy-body');     // a page with no list of its own is ready at load
addEventListener('cp:ready',function(){READY=1},{once:true});
function whenIdle(fn){
  var fired=false;
  var go=function(){
    if(fired)return; fired=true;
    window.requestIdleCallback?requestIdleCallback(fn,{timeout:8000}):setTimeout(fn,2000);
  };
  var when=function(){
    if(READY)return go();
    addEventListener('cp:ready',go,{once:true});
    setTimeout(go,12000);                              // the list never came; warm anyway
  };
  if(document.readyState==='complete')when(); else addEventListener('load',when,{once:true});
}
// a speculative fetch never competes with one the reader is waiting for
function lowFetch(u){try{return fetch(u,{priority:'low'})}catch(e){return fetch(u)}}
function sparingConnection(){var c=navigator.connection||{};return !!(c.saveData||/(^|-)2g$/.test(c.effectiveType||''))}
whenIdle(function(){
  if(sparingConnection())return;
  document.querySelectorAll('.panel[data-src]').forEach(warmPanel);
});

// Events page: type filter
function initEventFilter(){var f=document.getElementById('event-filters');if(!f||f.dataset.init)return;f.dataset.init='1';var q=document.getElementById('evq');
  function apply(){var a=(f.querySelector('.filter.active')||{}).dataset||{},t=(q&&q.value||'').trim().toLowerCase();
    document.querySelectorAll('#events .event').forEach(function(e){e.hidden=!((!a.type||a.type==='all'||e.dataset.type===a.type)&&(!t||e.textContent.toLowerCase().indexOf(t)>=0))});
    document.querySelectorAll('#events .ev-day').forEach(function(h){var n=h.nextElementSibling,any=false;while(n&&!n.classList.contains('ev-day')){if(!n.hidden)any=true;n=n.nextElementSibling}h.hidden=!any})}
  f.addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;f.querySelectorAll('button').forEach(function(x){x.classList.toggle('active',x===b)});apply()});
  if(q)q.addEventListener('input',apply);}
initEventFilter();
(window.__panelInit=window.__panelInit||[]).push(initEventFilter);

// Profile trends: a small multiple opens its full-size chart in a dialog
(function(){var d=document.createElement('dialog');d.className='chart-dialog';d.innerHTML='<div class="cd-head"><div><h3></h3><div class="small muted"></div></div><button class="cd-close" aria-label="Close">×</button></div><div class="cd-body"></div><div class="cd-def"></div>';
  // Clicking the backdrop closes any dialog. The click lands on the dialog element itself, so the
  // test is whether the point is outside its box; e.detail 0 is a keyboard activation, not a click.
  document.addEventListener('click',function(e){
    var dl=e.target.closest&&e.target.closest('dialog');
    if(!dl||!dl.open||!e.detail)return;
    var r=dl.getBoundingClientRect();
    if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dl.close();
  });
  document.addEventListener('click',function(e){var b=e.target.closest('.sm');if(b){if(!d.isConnected)document.body.appendChild(d);var t=b.querySelector('template');d.querySelector('h3').textContent=b.dataset.title||'';d.querySelector('.cd-head .small').textContent=b.dataset.sub||'';d.querySelector('.cd-body').innerHTML=t?t.innerHTML:'';
      var g=window.tipDef&&window.tipDef(b.dataset.def||'');            // what the measure is, beside the chart of it
      d.querySelector('.cd-def').innerHTML=g?'<b>'+g[1]+'</b> '+g[2]:'';
      d.showModal();return}
    if(e.target.closest('.cd-close')||(e.target===d))d.close()});
})();

// Ratings grid: band tiles, grade bars and the "moved" chip filter the rows alongside region and search
function initRatingGrid(){var tb=document.querySelector('table.rgrid tbody');if(!tb||tb.dataset.init)return;tb.dataset.init='1';var grade=null,band=null,cnt=document.getElementById('rg-count'),clear=document.querySelector('.gclear');
  function apply(){var region=(document.querySelector('.filter.active[data-region]')||{}).dataset||{},term=((document.getElementById('q')||{}).value||'').toLowerCase(),w=[];try{w=JSON.parse(localStorage.getItem('counterparty.watch')||'[]')}catch(e){}
    var n=0;tb.querySelectorAll('tr').forEach(function(tr){var d=tr.dataset,ok=true;
      if(region.region&&region.region!=='all'){ok=region.region==='watch'?w.indexOf(d.id)>=0:region.region==='moved'?d.moved==='1':d.region===region.region}
      if(ok&&grade)ok=d.grade===grade;if(ok&&band)ok=d.band===band;if(ok&&term)ok=tr.textContent.toLowerCase().indexOf(term)>=0;tr.style.display=ok?'':'none';if(ok)n++});
    if(cnt)cnt.textContent=n+' shown';document.querySelectorAll('.gfilter').forEach(function(b){b.classList.toggle('active',b.dataset.grade===grade)});document.querySelectorAll('.bfilter').forEach(function(b){b.classList.toggle('active',b.dataset.band===band)});if(clear)clear.hidden=!grade&&!band}
  document.addEventListener('click',function(e){var g=e.target.closest('.gfilter');if(g){grade=grade===g.dataset.grade?null:g.dataset.grade;band=null;apply();return}var b=e.target.closest('.bfilter');if(b){band=band===b.dataset.band?null:b.dataset.band;grade=null;apply();return}if(e.target.closest('.gclear')){grade=null;band=null;apply();return}if(e.target.closest('.filter[data-region]'))setTimeout(apply,0)});
  var q=document.getElementById('q');if(q)q.addEventListener('input',apply);apply()}
initRatingGrid();
(window.__panelInit=window.__panelInit||[]).push(initRatingGrid);

// Definitions: every number on the site can say what it is, in a sentence a first-time reader gets.
// The glossary is embedded once per page as JSON; a single popover is moved to whichever marker was
// asked. Fixed positioning, and inside an open dialog it is appended there, so nothing clips it.
(function(){
  var G=null, tip=null, open=null, hoverT=null;
  function gloss(){
    if(G)return G;
    var el=document.getElementById('gloss');
    try{G=JSON.parse(el?el.textContent:'{}')}catch(e){G={}}
    return G;
  }
  // Markers built in the browser use the same shape as the server's, and read their label from
  // the same glossary, so a definition is written once however the element got there.
  window.tipDef=function(key){return key?(gloss()[key]||null):null};
  window.tipMark=function(key,cls){
    var g=gloss()[key];if(!g)return '';
    return '<button type="button" class="i'+(cls?' '+cls:'')+'" data-t="'+key+'" aria-expanded="false" aria-label="What is '+
           g[0].replace(/"/g,'&quot;')+'?">i</button>';
  };
  function el(){
    if(tip)return tip;
    tip=document.createElement('div');
    tip.className='tip';tip.setAttribute('role','dialog');tip.hidden=true;
    return tip;
  }
  function place(btn){
    var t=el(), r=btn.getBoundingClientRect(), vw=innerWidth, vh=innerHeight;
    var host=btn.closest('dialog')||document.body;      // the top layer paints over anything below it
    if(t.parentNode!==host)host.appendChild(t);
    t.hidden=false;t.style.left='0px';t.style.top='0px';
    var w=Math.min(320,vw-24);
    t.style.width=w+'px';
    var h=t.offsetHeight;                                // measured at its final width, not before it
    var left=Math.max(12,Math.min(r.left+r.width/2-w/2, vw-w-12));
    var below=r.bottom+8, top=(below+h>vh-12&&r.top-h-8>12)?r.top-h-8:below;
    top=Math.max(12,Math.min(top,vh-h-12));            // never off the screen, however small the screen is
    t.style.left=left+'px';t.style.top=top+'px';
  }
  function show(btn){
    var g=gloss()[btn.dataset.t];if(!g)return;
    hide();
    var t=el();
    t.innerHTML='<h4>'+g[0]+'</h4><p class="lead">'+g[1]+'</p><p>'+g[2]+'</p>';
    open=btn;btn.setAttribute('aria-expanded','true');
    place(btn);
  }
  function hide(){
    if(open)open.setAttribute('aria-expanded','false');
    open=null;if(tip)tip.hidden=true;
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest('.i');
    if(b){e.preventDefault();e.stopPropagation();if(open===b)hide();else show(b);return}
    if(!e.target.closest('.tip'))hide();
  },true);
  document.addEventListener('mouseover',function(e){
    var b=e.target.closest('.i');if(!b||open===b)return;
    if(!matchMedia('(hover:hover)').matches)return;
    clearTimeout(hoverT);hoverT=setTimeout(function(){show(b)},160);
  });
  document.addEventListener('mouseout',function(e){
    if(e.target.closest&&e.target.closest('.i'))clearTimeout(hoverT);
  });
  // the same definitions read end to end, built from the payload already on the page
  document.addEventListener('click',function(e){
    if(!e.target.closest('#glink'))return;
    var d=document.getElementById('gloss-dlg');if(!d)return;
    if(!d.dataset.filled){
      var g=gloss(),sec='',out='<div class="gd-head"><h3>What the numbers mean</h3>'+
        '<input id="gd-q" type="search" placeholder="Search a term" autocomplete="off">'+
        '<button class="cd-close" aria-label="Close">\u00d7</button></div><div class="gd">';
      for(var k in g){
        if(g[k][3]!==sec){sec=g[k][3];out+='<h4>'+sec+'</h4>'}
        out+='<div class="gd-t" data-k="'+(g[k][0]+' '+g[k][1]).toLowerCase().replace(/"/g,'')+'">'+
             '<dt>'+g[k][0]+'</dt><dd><b>'+g[k][1]+'</b> '+g[k][2]+'</dd></div>';
      }
      d.innerHTML=out+'</div>';d.dataset.filled='1';
      d.querySelector('#gd-q').addEventListener('input',function(){
        var t=this.value.trim().toLowerCase();
        d.querySelectorAll('.gd-t').forEach(function(x){x.hidden=!!t&&x.dataset.k.indexOf(t)<0});
        d.querySelectorAll('.gd h4').forEach(function(h){                // a heading with nothing under it goes too
          var n=h.nextElementSibling,any=false;
          while(n&&n.tagName!=='H4'){if(!n.hidden)any=true;n=n.nextElementSibling}
          h.hidden=!any;
        });
      });
    }
    d.showModal();
  });
  document.addEventListener('click',function(e){
    var d=document.getElementById('gloss-dlg');
    if(d&&d.open&&(e.target===d||e.target.closest('.gd-head .cd-close')))d.close();
  });
  document.addEventListener('keydown',function(e){if(e.key==='Escape')hide()});
  addEventListener('scroll',hide,true);addEventListener('resize',hide);
})();

// The tab named in the address, opened last: a tab click reaches for the panel loader, which is
// defined further down this file, and a var is not its value until the line that assigns it.
// Also on every later change of the address, so a link to #ratings from elsewhere on the page
// opens that tab rather than only working on a fresh load.
function openNamedTab(){
  var h=location.hash.replace('#','').split('&')[0]; if(!h)return;
  var t=document.querySelector('.tab[data-tab="'+h+'"]');
  if(t&&!t.classList.contains('active'))t.click();
}
openNamedTab();
addEventListener('hashchange',openNamedTab);
