// My policy: the user's approved counterparties and tenors, kept in this browser (or carried in a share link),
// checked every visit against the latest public standing, rating actions and market signal. Nothing leaves the browser.
(function(){
  // An empty data-root is the site root, not a missing one: the home page sets it to "" and
  // a falsy test would send every fetch to ../, which escapes the project directory on Pages.
  var _r=document.body.getAttribute('data-root');
  var KEY='counterparty.policy', ROOT=(_r==null?'../':_r);
  // The tenors a name can be accepted for, in days: from overnight to ten years, with the 100 days
  // the advisers' lists use. Any other length can be typed in on Choose names (Other), and is shown
  // in the plainest unit it divides into.
  var TENORS=[[1,'1 day'],[7,'1 week'],[30,'1 month'],[91,'3 months'],[100,'100 days'],[182,'6 months'],[365,'12 months'],
    [547,'18 months'],[730,'24 months'],[1095,'3 years'],[1825,'5 years'],[3650,'10 years']];
  var GRADES=['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC'];
  var data=null, byId={};

  // The weighting model lives in app.js, because a profile page carries no policy.js and must
  // still show the reader's own weights rather than ours.
  var CPW=window.CPW, PILLARS=CPW.PILLARS;
  // the score parts by the names the Weightings page gives them, so every view uses the same words
  var PLABEL={}; PILLARS.forEach(function(p){PLABEL[p[0]]=p[1]});
  // the peer groups by name, as the summaries write them
  var PEER_LABEL={uk_large:'UK majors',uk_mid:'UK mid-sized banks',uk_small:'UK small banks',uk_bs:'UK building societies',
    eu_large:'EU and Nordic banks',us:'US banks',ch:'Swiss banks',aus:'Australian banks',can:'Canadian banks',asia:'Asian banks',gulf:'Gulf banks'};
  function weights(){return CPW.weights()}
  function saveWeights(w){CPW.save(w)}
  function rescore(e,w){return CPW.rescore(e,w)}
  // Every score the site shows is read off e.score, so the weights are applied once, here, and
  // every table, card, shortlist and dialog follows without knowing about them.
  function applyWeights(){
    var w=weights();
    (data&&data.rows||[]).forEach(function(e){
      if(e.pw0===undefined){e.pw0=e.score;e.band0=e.band}
      var r=rescore(e,w);
      e.score=r.score; e.band=r.band;
    });
    return w;
  }

  function load(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
  // The names a reader follows without holding them. The profile's star writes the same list, so
  // a star here and a star there are one thing.
  var WKEY='counterparty.watch';
  function watchIds(){try{var v=JSON.parse(localStorage.getItem(WKEY)||'[]');return Array.isArray(v)?v:[]}catch(e){return[]}}
  function saveWatch(w){try{localStorage.setItem(WKEY,JSON.stringify(w))}catch(e){}}
  function toggleWatch(id){var w=watchIds(),i=w.indexOf(id);if(i>=0)w.splice(i,1);else w.push(id);saveWatch(w)}
  function starBtn(id,cls){var on=watchIds().indexOf(id)>=0;
    return '<button type="button" class="uni-star'+(on?' on':'')+(cls?' '+cls:'')+'" data-id="'+esc(id)+'" title="'+(on?'Stop watching':'Watch this name')+'" aria-pressed="'+on+'" aria-label="'+(on?'Stop watching':'Watch')+'">'+(on?'\u2605':'\u2606')+'</button>'}
  // Cards or a table: a policy of twenty names is a column of figures to some readers and a set of
  // cards to others, so the choice is theirs and kept. The table sorts on any of its columns.
  var VIEW=KEY+'.view', polSort={key:'tenor',dir:-1};
  function polView(){try{return localStorage.getItem(VIEW)==='table'?'table':'cards'}catch(e){return 'cards'}}
  function setPolView(v){try{localStorage.setItem(VIEW,v)}catch(e){}}
  function polVal(it,e,k){
    if(k==='tenor')return it.tenor; if(k==='short')return (e&&e.short)||it.id;
    if(k==='rating_grade')return e&&e.rating_grade!=null?-e.rating_grade:null;
    return e?e[k]:null;
  }
  function polTable(p,flagsOf){
    var items=p.slice().sort(function(a,b){
      var k=polSort.key, va=polVal(a,byId[a.id],k), vb=polVal(b,byId[b.id],k);
      if(va==null&&vb==null)return 0; if(va==null)return 1; if(vb==null)return -1;
      var d=typeof va==='string'?va.localeCompare(vb):va-vb; return polSort.dir*d||((byId[a.id]||{}).short||'').localeCompare((byId[b.id]||{}).short||'');
    });
    var th=function(k,l,cls){return '<th data-k="'+k+'"'+(cls?' class="'+cls+'"':'')+(polSort.key===k?' aria-sort="'+(polSort.dir>0?'ascending':'descending')+'"':'')+'>'+l+'</th>'};
    var rows=items.map(function(it){
      var e=byId[it.id];
      if(!e)return '<tr class="pol-tr"><td colspan="12"><span class="b">'+esc(it.id)+'</span> '+chip('No longer covered','bad')+'</td><td><button class="pol-rm" data-id="'+esc(it.id)+'" title="Remove">×</button></td></tr>';
      var fl=flagsOf(it,e), worst=fl.filter(function(x){return x[0]!=='muted'})[0], moved=fl.some(function(x){return x[0]!=='muted'&&x[0]!=='good'});
      return '<tr class="pol-tr'+(moved?' pol-tr-flag':'')+'" data-id="'+esc(e.id)+'" data-tenor="'+it.tenor+'" tabindex="0"'+(e.blurb?' title="'+esc(e.blurb)+'"':'')+'>'+
        '<td class="pt-name"><a class="cp-nm" href="'+ROOT+'banks/'+esc(e.id)+'.html">'+esc(e.short)+'</a>'+typeTag(e)+'<div class="small muted">'+esc(e.name)+' · '+sovPill(e)+'</div></td>'+
        '<td class="num">'+scoreNum(e.score,e.band,'sc-1')+'</td>'+
        '<td class="mono"><b style="color:'+gradeColour(e.rating_composite)+'">'+esc(e.rating_composite||'—')+'</b></td>'+
        '<td class="num mono">'+(e.cet1==null?'—':e.cet1.toFixed(1)+'%')+'</td>'+
        '<td class="num mono">'+levTxt(e)+'</td>'+
        '<td class="num mono">'+(e.lcr==null?'—':Math.round(e.lcr)+'%')+'</td>'+
        '<td class="num mono">'+(e.nsfr==null?'—':Math.round(e.nsfr)+'%')+'</td>'+
        asofCell(e)+
        '<td>'+mkt(e.market,1)+'</td>'+
        '<td class="pt-ten">'+tenorPick(it)+'</td>'+
        '<td class="pt-flag">'+(worst?chip(worst[2]||worst[1],worst[0]):'<span class="na">—</span>')+'</td>'+
        '<td><button class="pol-rm" data-id="'+esc(e.id)+'" title="Remove from policy" aria-label="Remove '+esc(e.short)+'">×</button></td></tr>';
    }).join('');
    return '<div class="table-wrap"><table class="plain pol-t" id="pol-table"><thead><tr>'+
      th('short','Name')+th('score','Score','num')+th('rating_grade','Agency rating')+th('cet1','CET1','num')+th('leverage','Lev','num')+
      th('lcr','LCR','num')+th('nsfr','NSFR','num')+th('age_days','Figures')+'<th>Market</th>'+th('tenor','Tenor')+'<th>Since approval</th><th></th>'+
      '</tr></thead><tbody>'+rows+'</tbody></table></div>';
  }
  function save(p){try{localStorage.setItem(KEY,JSON.stringify(p))}catch(e){}}
  // the definition marker, drawn from the glossary every page carries
  function mk(k){return window.tipMark?window.tipMark(k):''}
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function fmt(v,dp,suf){return v==null?'<span class="na">—</span>':'<span class="mono">'+Number(v).toFixed(dp==null?1:dp)+(suf||'')+'</span>'}
  function tenorLabel(d){
    for(var i=0;i<TENORS.length;i++)if(TENORS[i][0]===d)return TENORS[i][1];
    var n=function(x,u){return x+' '+u+(x===1?'':'s')};
    if(d>=365&&d%365===0)return n(d/365,'year');
    var m=Math.round(d/(365/12)); if(d>=28&&Math.abs(m*365/12-d)<1)return n(m,'month');
    if(d%7===0)return n(d/7,'week');
    return n(d,'day');
  }
  // The tenor the Add buttons on Choose names use: one from the list, or Other, a number and a unit.
  function curTenor(){
    var sel=document.getElementById('uni-tenor'); if(!sel)return 365;
    if(sel.value!=='other')return +sel.value||365;
    var n=+(document.getElementById('uni-other-n')||{}).value, u=+(document.getElementById('uni-other-u')||{}).value;
    var d=Math.round(n*u);
    return d>=1&&d<=3650?d:365;
  }
  function bandRank(b){return {A:1,B:2,C:3,D:4,E:5}[b]||9}
  function chip(t,k,ti){return '<span class="chip chip-'+(k||'muted')+'"'+(ti?' title="'+esc(ti)+'"':'')+'>'+esc(t)+'</span>'}
  var TYPE_LABEL={holding:'Holding company',bank:'Bank',building_society:'Building society',subsidiary:'Subsidiary'};
  function typeTag(e){
    if(!e||e.type!=='holding')return '';
    return '<span class="tag-hold" title="A holding company, not the entity a deposit is placed with. '+
           'Its figures are the group\u2019s.">Holding company</span>';
  }
  var BANDC={A:'#0a2540',B:'#3f5f85',C:'#7d93ad',D:'#a9b8c9',E:'#c9d3de'};
  // The score carries its own colour, red through to green, instead of a chip beside it that was
  // the same shape and nearly the same colour for every name a policy usually holds. Every stop
  // clears 5:1 on white, and the band letter stays beside the number in words, so nothing here
  // depends on telling red from green.
  // Anchored to where scores actually fall - the universe runs 49 to 99, quartiles at 67, 73 and 78
  // - so the ramp turns over the range a reader is comparing, rather than spending most of itself
  // on scores no bank has.
  var RAMP=[[0,163,22,29],[0.267,184,69,26],[0.444,138,98,6],[0.6,79,122,31],[0.778,30,122,58],[1,20,102,58]];
  function rampColour(t){
    t=Math.max(0,Math.min(1,t));
    for(var i=1;i<RAMP.length;i++){
      if(t<=RAMP[i][0]){
        var a=RAMP[i-1],b=RAMP[i],k=(t-a[0])/((b[0]-a[0])||1);
        return 'rgb('+[1,2,3].map(function(j){return Math.round(a[j]+(b[j]-a[j])*k)}).join(',')+')';
      }
    }
    return 'rgb(20,102,58)';
  }
  // the counterparty score, anchored to where scores actually fall (49.5 to 99.4 across the universe)
  function scoreColour(v){return v==null?'#6c757d':rampColour((v-50)/45)}
  // a pillar is scored on its own nought-to-a-hundred, so it takes the whole ramp
  function pillarColour(v){return v==null?'#adb5bd':rampColour(v/100)}
  // Each agency writes the same standing differently, so one 0..16 scale carries the lot and a
  // Moody's Baa1 is placed and coloured beside an S&P BBB+. DBRS writes its notches (high)/(low).
  var MOODYS=['Aaa','Aa1','Aa2','Aa3','A1','A2','A3','Baa1','Baa2','Baa3','Ba1','Ba2','Ba3','B1','B2','B3','Caa'];
  function gradeIndex(v){
    v=String(v==null?'':v).trim().replace(/\s+/g,'').replace(/\(high\)/i,'+').replace(/\(H\)/,'+')
      .replace(/\(low\)/i,'-').replace(/\(L\)/,'-').replace(/\(hyb\)/i,'').replace(/u$/,'').split('/')[0];
    var i=MOODYS.indexOf(v); if(i>=0)return i;
    i=GRADES.indexOf(v); if(i>=0)return i;
    return /^(CCC|CC|C|D|RD|SD|Ca)/.test(v)?16:-1;
  }
  // a rating runs AAA to CCC; the turn sits at the investment-grade line rather than in the middle
  // Spread over 14 notches rather than 11, so the turn lands at the investment-grade line: two
  // notches inside investment grade are a small difference and should not look like a large one.
  function gradeColour(g){
    var i=gradeIndex(g);
    if(i<0)return '#6c757d';
    return rampColour(1-Math.min(1,i/14));
  }
  window.cpGradeColour=gradeColour;      // the Analysis table colours its ratings the same way
  // one number, one colour, one letter - used wherever a score is shown in a row or a card
  function scoreNum(v,band,cls){
    if(v==null)return '<span class="na">\u2014</span>';
    return '<span class="sc-n'+(cls?' '+cls:'')+'" style="color:'+scoreColour(v)+'">'+v.toFixed(0)+'</span>'+
           (band?'<span class="sc-b">'+esc(band)+'</span>':'');
  }
  // A score is a ratio against a scale, so it reads as a meter on the band ramp - one hue,
  // light to dark - rather than as a one-bar chart. The track carries no meaning of its own.
  function meter(score,band,cls){
    if(score==null)return '';
    var w=Math.max(0,Math.min(100,score));
    return '<div class="meter'+(cls?' '+cls:'')+'" role="img" aria-label="score '+w.toFixed(0)+' of 100">'+
           '<i style="width:'+w.toFixed(1)+'%;background:'+(BANDC[band]||'#7d93ad')+'"></i></div>';
  }
  // The country a bank sits in, with the state's own rating beside it - context, never a score input.
  // No agency is named against a rating anywhere: the site shows the average and the weakest
  // of the three main agencies, and how many of them hold each outlook. See composite.py.
  var NUMW={0:'none',1:'one',2:'two',3:'three'};
  function ofThree(n){return n===3?'all three':(NUMW[n]||n)+' of the three'}
  function toneWords(tones){
    var c={};(tones||[]).forEach(function(t){c[t||'']=(c[t||'']||0)+1});
    var parts=[];
    [['watch negative','on negative watch'],['negative','on a negative outlook'],['watch positive','on positive watch'],
     ['positive','on a positive outlook'],['stable','on a stable outlook'],['','with no outlook published']].forEach(function(k){
      if(c[k[0]])parts.push((NUMW[c[k[0]]]||c[k[0]])+' '+k[1])});
    return parts.length<2?(parts[0]||''):parts.slice(0,-1).join(', ')+' and '+parts[parts.length-1];
  }
  var TONE_GLYPH={'watch negative':['\u25c6','wn','negative watch'],'negative':['\u25bc','dn','negative outlook'],
                  'watch positive':['\u25c6','wp','positive watch'],'positive':['\u25b2','up','positive outlook'],
                  'stable':['\u25b6','lv','stable outlook'],'':['\u2013','lv','no outlook published']};
  // one rule for outlook marks in tables and the pop-up: shown when an outlook is not stable,
  // since three grey arrows on every row said nothing and hid the one that did
  function toneMarks(tones){
    var moving=(tones||[]).filter(function(t){return t&&t!=='stable'});
    return moving.length?toneGlyphs(moving):'';      // only the marks that say something
  }
  function toneGlyphs(tones){
    return '<span class="tones" title="'+esc(toneWords(tones)||'no outlook published')+'">'+(tones||[]).map(function(t){
      var g=TONE_GLYPH[t]||TONE_GLYPH[''];return '<span class="cr-o '+g[1]+'">'+g[0]+'</span>'}).join('')+'</span>';
  }
  function describeRating(r){
    if(!r)return 'no public rating from any of the three main agencies';
    var s=r.letter+' on average across '+ofThree(r.n);
    if(r.n>1&&r.worst_letter!==r.letter)s+=', the weakest of them at '+r.worst_letter;
    var tw=toneWords(r.tones);
    if(tw)s+=', '+(r.n>1?tw:tw.replace('one on','on'));
    return s;
  }
  function sovPill(e){
    // one entry a country, held once at the top of the file rather than copied onto every bank
    var sv=e&&((data&&data.sovereigns||{})[e.country]);
    if(!sv||!sv.composite)return esc((e&&e.country)||'');
    return '<span class="sov" title="'+esc(sv.name+' sovereign rating: '+describeRating({letter:sv.composite,worst_letter:sv.worst||sv.composite,n:sv.n,tones:sv.tones})+
           '. Context, not part of the score.')+'">'+esc(e.country||'')+'</span>';   // the state's rating is context: on hover, not beside every bank's own
  }
  // One rule everywhere: a market chip appears only when the market has moved; a quiet market,
  // or none, leaves the cell empty rather than saying "Stable" on half the rows
  function mkt(m,terse){if(!m||m.direction==='none'||(terse&&m.direction==='flat'))return terse?'':'<span class="muted">no market data</span>';var k=m.direction==='down'?'bad':(m.direction==='up'?'good':'muted');
    // one word on the chip; whether the signal is the group's own, and against what, is in its title
    var grp=/ \(group\)$/.test(m.label||''), shown=(m.label||'').replace(/ \(group\)$/,'').replace(/ \((with the market|bank-specific)\)$/,'');
    return chip(shown,k,m.label+(grp?': the signal is the group\u2019s, which carries the market prices':''))}
  function snapshot(e){return {score:e.score,band:e.band,grade:e.rating_grade,market:e.market&&e.market.direction,asof:e.asof}}
  // nothing makes a share link any more; a link already sent still opens one
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
    if(e.age_days!=null&&e.age_days>180)f.push(['warn','Regulatory figures '+e.age_days+' days old','Old figures']);
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


  // ---- tooltips on the overview charts ------------------------------------------------------
  // A mark is a few pixels of colour; the tooltip is where it says what it is. The content is
  // built with the chart and kept in a registry, so nothing has to be escaped into an attribute
  // and the DOM carries a key rather than a paragraph per mark.
  var TIPS={}, TIPN=0, DTIP=null;
  function tipd(html){var k='t'+(++TIPN);TIPS[k]=html;return ' data-tip="'+k+'"'}
  var BAND_RANGE={A:'80 and above',B:'65 to 79.9',C:'50 to 64.9',D:'35 to 49.9',E:'below 35'};
  function names(list,max){
    var n=list.slice(0,max||6).map(function(e){return esc(e.short)}).join(', ');
    return list.length>(max||6)?n+' and '+(list.length-(max||6))+' more':n;
  }
  function tipHead(t,s){return '<b>'+t+'</b>'+(s?'<span>'+s+'</span>':'')}
  function dtip(){
    if(DTIP)return DTIP;
    DTIP=document.createElement('div');DTIP.className='dtip';DTIP.hidden=true;document.body.appendChild(DTIP);
    return DTIP;
  }
  function showTip(el,ev){
    var k=el.getAttribute('data-tip'), html=TIPS[k]; if(!html)return;
    var t=dtip(); t.innerHTML=html; t.hidden=false;
    // A dialog is painted in the browser's top layer, above every z-index on the page, so a
    // tooltip left on the body sits behind it. It moves into the dialog while one is open; it
    // is positioned against the viewport either way, so the coordinates do not change.
    var host=el.closest('dialog')||document.body;
    if(t.parentNode!==host)host.appendChild(t);
    var w=t.offsetWidth, h=t.offsetHeight, vw=innerWidth, vh=innerHeight;
    var x=Math.max(10,Math.min(ev.clientX-w/2, vw-w-10));
    var y=ev.clientY-h-14; if(y<10)y=ev.clientY+18;
    t.style.left=x+'px'; t.style.top=Math.min(y,vh-h-10)+'px';
  }
  function hideTip(){if(DTIP)DTIP.hidden=true}
  document.addEventListener('mouseover',function(e){
    var el=e.target.closest&&e.target.closest('[data-tip]');
    if(el)showTip(el,e); else if(!e.target.closest('.dtip'))hideTip();
  });
  document.addEventListener('mousemove',function(e){
    var el=e.target.closest&&e.target.closest('[data-tip]');
    if(el&&DTIP&&!DTIP.hidden)showTip(el,e);
  });
  addEventListener('scroll',hideTip,true);

  // The band mix in the same form as the tenor rows beside it: one row a band, how many names
  // sit there and the weakest score among them. A single stacked bar filled a third of its panel
  // and needed a key to read; rows read straight off.
  function bandMix(es){
    var n={},who={},tot=0;BANDS.forEach(function(b){n[b]=0;who[b]=[]});
    es.forEach(function(e){if(e.band&&n[e.band]!=null){n[e.band]++;who[e.band].push(e);tot++}});
    if(!tot)return '<div class="muted small">no scored names</div>';
    var SHORT={A:'80+',B:'65\u201379',C:'50\u201364',D:'35\u201349',E:'under 35'};
    var most=Math.max.apply(null,BANDS.map(function(b){return n[b]}));
    return '<div class="tmix">'+BANDS.filter(function(b){return n[b]}).map(function(b){
      var sc=who[b].map(function(e){return e.score}).sort(function(a,c){return a-c});
      var tip=tipd(tipHead('Band '+b,n[b]+' of '+tot)+
        '<i>'+Math.round(n[b]/tot*100)+'% of your scored names \u00b7 score '+BAND_RANGE[b]+'</i>'+
        '<i>'+names(who[b])+'</i>');
      return '<div class="tm-r"'+tip+'><span class="tm-t"><b class="tm-band" style="background:'+BANDC[b]+'">'+b+'</b>'+SHORT[b]+'</span>'+
        '<span class="tm-b"><i style="width:'+(n[b]/most*100).toFixed(0)+'%;background:'+BANDC[b]+'"></i></span>'+
        '<span class="tm-n mono">'+n[b]+'</span>'+
        '<span class="tm-w mono" style="color:'+scoreColour(sc[0])+'" title="weakest score in this band">'+sc[0].toFixed(0)+'</span></div>';
    }).join('')+'</div>';
  }
  function ratingHist(es){
    // the composite rating is an ordered scale, so the bars stay in grade order
    var n={},who={},tot=0;
    es.forEach(function(e){if(e.rating_composite){n[e.rating_composite]=(n[e.rating_composite]||0)+1;
      (who[e.rating_composite]=who[e.rating_composite]||[]).push(e);tot++}});
    var present=GRADES.filter(function(g){return n[g]});
    if(!present.length)return '<div class="muted small">no rated names</div>';
    // how common that grade is across everything covered, so your mix has something to sit against
    var uni={},urated=0;
    (data&&data.rows||[]).forEach(function(e){if(e.rating_composite){uni[e.rating_composite]=(uni[e.rating_composite]||0)+1;urated++}});
    var w=260,h=72,bw=w/present.length,bar=Math.min(bw-3,26),mx=Math.max.apply(null,present.map(function(g){return n[g]})),inner='';
    present.forEach(function(g,i){
      var bh=Math.max(4,n[g]/mx*(h-30));
      var ig=GRADES.indexOf(g);
      var tip=tipd(tipHead(esc(g),n[g]+' of '+tot)+
        '<i>'+(ig<=3?'the top of investment grade':ig<=6?'the strong end of investment grade':ig<=9?'the middle of investment grade':'below investment grade')+
        ' \u00b7 '+Math.round(n[g]/tot*100)+'% of your rated names</i>'+
        (uni[g]?'<i><em>'+uni[g]+'</em> of the '+urated+' rated names covered carry '+esc(g)+'</i>':'')+
        '<i>'+names(who[g])+'</i>');
      inner+='<rect x="'+(i*bw+(bw-bar)/2).toFixed(1)+'" y="'+(h-16-bh).toFixed(1)+'" width="'+bar.toFixed(1)+'" height="'+bh.toFixed(1)+'" rx="2" fill="#143659"/>'+
             '<rect x="'+(i*bw).toFixed(1)+'" y="0" width="'+bw.toFixed(1)+'" height="'+(h-16)+'" fill="transparent"'+tip+'/>'+
             '<text x="'+(i*bw+bw/2).toFixed(1)+'" y="'+(h-19-bh).toFixed(1)+'" text-anchor="middle" class="pv-n">'+n[g]+'</text>'+
             '<text x="'+(i*bw+bw/2).toFixed(1)+'" y="'+h+'" text-anchor="middle" class="pv-ax">'+g+'</text>';
    });
    return svg(w,h,inner);
  }

  // How the list is spread across tenors: one row a tenor, shortest first, with how many names
  // are accepted there and the weakest score among them. The question it answers is whether the
  // longest tenors sit on the weakest names, and a row of words answers it at a glance where a
  // scatter of dots did not.
  function tenorMix(items){
    var by={};
    items.forEach(function(it){var e=byId[it.id];if(!e)return;var t=+it.tenor||0;(by[t]=by[t]||[]).push(e)});
    var ts=Object.keys(by).map(Number).sort(function(a,b){return a-b});
    if(!ts.length)return '<div class="muted small">no tenors set</div>';
    var most=Math.max.apply(null,ts.map(function(t){return by[t].length}));
    return '<div class="tmix tmix-t">'+ts.map(function(t){
      var es=by[t], sc=es.map(function(e){return e.score}).filter(function(v){return v!=null});
      var low=sc.length?Math.min.apply(null,sc):null;
      var tip=tipd(tipHead(esc(tenorLabel(t)),es.length+' name'+(es.length===1?'':'s'))+'<i>'+names(es)+'</i>');
      return '<div class="tm-r"'+tip+'><span class="tm-t">'+esc(tenorLabel(t))+'</span>'+
        '<span class="tm-b"><i style="width:'+(es.length/most*100).toFixed(0)+'%"></i></span>'+
        '<span class="tm-n mono">'+es.length+'</span>'+
        '<span class="tm-w mono" style="color:'+(low==null?'var(--muted)':scoreColour(low))+'" title="weakest score at this tenor">'+(low==null?'\u2014':low.toFixed(0))+'</span></div>';
    }).join('')+'</div>';
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
        tile(w.score!=null?w.score.toFixed(0):'—','weakest score')+
        tile(w.band||'—','weakest band')+
        tile(med!=null?med.toFixed(0):'—','median score')+
        tile(sc.length+'/'+items.length,'scored')+
        tile(stale,'figures over 180 days',stale?'pv-warn':'')+
      '</div>'+
      '<div class="pv-charts">'+
        '<figure><figcaption>Band mix'+mk('band')+'<span class="tm-key">names \u00b7 weakest</span></figcaption>'+bandMix(es)+'</figure>'+
        '<figure><figcaption>Composite rating'+mk('composite')+'<span class="tm-key">names</span></figcaption>'+ratingHist(es)+'</figure>'+
        '<figure><figcaption>By tenor'+mk('tenor')+'<span class="tm-key">names \u00b7 weakest</span></figcaption>'+tenorMix(items)+'</figure>'+
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
    var w=150,h=106,pad=5,vals=pts.map(function(p){return p.v});
    var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals);
    if(pq){lo=Math.min(lo,pq.p25);hi=Math.max(hi,pq.p75)}
    var rng=(hi-lo)||1; lo-=rng*0.08; hi+=rng*0.08; rng=hi-lo;
    var X=function(i){return pad+i*(w-2*pad)/(pts.length-1)};
    var Y=function(v){return h-12-((v-lo)/rng)*(h-12-pad)};
    var d='M'+pts.map(function(p,i){return X(i).toFixed(1)+' '+Y(p.v).toFixed(1)}).join('L');
    var last=pts[pts.length-1], band='', vs='';
    if(pq){
      var y1=Y(pq.p75),y2=Y(pq.p25);
      band='<rect x="0" y="'+Math.min(y1,y2).toFixed(1)+'" width="'+w+'" height="'+Math.abs(y2-y1).toFixed(1)+'" fill="#8fa3b8" fill-opacity="0.22"/>'+
           '<line x1="0" x2="'+w+'" y1="'+Y(pq.p50).toFixed(1)+'" y2="'+Y(pq.p50).toFixed(1)+'" stroke="#7d93ad" stroke-width="1" stroke-dasharray="3 2"/>';
      var diff=last.v-pq.p50;
      if(Math.abs(diff)<0.05)diff=0;
      vs='<span class="mt-vs '+(diff>0?'up':diff<0?'dn':'lv')+'">'+(diff>0?'+':'')+diff.toFixed(1)+' vs peers</span>';
    }
    // one tooltip for the whole spark: at 150 by 46 there is no room to point at a single quarter,
    // and the questions a reader has are about the run and the peer group, not one point
    var first=pts[0], chg=last.v-first.v;
    var tip=tipd(tipHead(esc(label),last.v.toFixed(1)+unit)+
      '<i>'+esc(first.d.slice(0,7))+' to '+esc(last.d.slice(0,7))+' \u00b7 '+pts.length+' periods</i>'+
      '<i>from '+first.v.toFixed(1)+unit+' \u00b7 '+(chg>=0?'+':'\u2212')+Math.abs(chg).toFixed(1)+' over the run</i>'+
      (pq?'<i>peer group today: 25th <em>'+pq.p25.toFixed(1)+'</em> \u00b7 median <em>'+pq.p50.toFixed(1)+
          '</em> \u00b7 75th <em>'+pq.p75.toFixed(1)+'</em></i>'+
          '<i>the shaded band is that middle half, the dashed line its median</i>':
          '<i>no peer band: fewer than four names in the group publish this</i>'));
    return '<figure class="mt"'+tip+'><figcaption><span class="mt-l">'+esc(label)+mk(gk)+'</span>'+
      '<b>'+last.v.toFixed(1)+unit+'</b></figcaption>'+(vs?'<div class="mt-sub">'+vs+'</div>':'')+
      '<svg viewBox="0 0 '+w+' '+h+'" width="100%" height="'+h+'" aria-hidden="true">'+band+
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
    var n=(TRENDS.map(function(t){return (s[t[0]]||[]).length>1}).filter(Boolean)).length;
    // pillars come through as [score, weight]
    var sd=(b.score_detail&&b.score_detail.pillars)||null;
    var pill=sd?Object.keys(sd).map(function(k){var v=sd[k]||[];var pc=v[0],wt=v[1];
      var col=pillarColour(pc);
      var lab=PLABEL[k]||k;
      var tip=tipd(tipHead(esc(lab),(pc==null?'not held':pc.toFixed(0)+' of 100'))+
        '<i>worth <em>'+(wt==null?'0':wt)+'%</em> of the score'+(pc==null?' \u2014 re-scaled away, since this bank does not publish it':'')+'</i>'+
        (pc!=null?'<i>'+(pc>=80?'strong':pc>=60?'middling':pc>=40?'weak':'very weak')+' against the method\u2019s thresholds</i>':''));
      return '<div class="md-pill"'+tip+'><span>'+esc(lab)+'</span>'+
             '<div class="meter meter-sm"><i style="width:'+(pc==null?0:Math.max(0,Math.min(100,pc)))+'%;background:'+col+'"></i></div>'+
             '<b style="color:'+col+'">'+(pc==null?'\u2014':pc.toFixed(0))+'</b><i>w'+(wt==null?'':wt)+'</i></div>'}).join(''):'';
    // The same panels the open card uses: a ruled heading on a white box on a tinted ground. The
    // trends and the standing; a name's events were dropped in November 2026, with the headlines. A dialog that looks like the row it came from is one thing to learn, not two.
    return '<div class="md-grid">'+
      sect('Trends','',
        '<div class="md-trends" id="md-trends">'+charts+'</div>'+
        (n&&Object.keys(pg).length?'<p class="mt-legend"><span class="mt-key"></span>The band is where this bank\u2019s peer group stands today, quartile to quartile, median dashed.</p>':''),
        'md-trend-panel')+
      '<div class="md-col">'+
        sect('Ratings'+mk('rating'),'',ratingCell(e)+ratingPath(b)+
          '')+
        sect('Score make-up'+mk('pillar'),(e.score==null?'':'score '+e.score.toFixed(0)),
          (pill?'<div class="md-pills">'+pill+'</div>':'<div class="muted small">No public score for this entity.</div>')+
          (b.percentile!=null?'<p class="md-foot">Stronger than <b>'+Math.round(b.percentile)+'%</b> of its peer group'+
            mk('percentile')+(PEER_LABEL[b.peer_group]?', '+esc(PEER_LABEL[b.peer_group]):'')+'.</p>':''))+
      '</div>'+
    '</div>';
  }
  function openModal(id,tenor){
    var dlg=document.getElementById('pol-modal');if(!dlg)return;
    var e=byId[id]||{};
    var act=tenor?'<button class="filter active pol-add-ll" data-id="'+esc(id)+'" data-tenor="'+tenor+'">Add at '+esc(tenorLabel(tenor))+'</button>':'';
    dlg.innerHTML='<div class="md-head">'+
      '<div class="md-id"><div class="md-nm">'+esc(e.short||id)+typeTag(e)+'</div>'+
        '<div class="md-sub">'+esc(e.name||'')+' \u00b7 '+sovPill(e)+'</div></div>'+
      '<div class="md-sc">'+(e.score==null
        ? '<span class="na big">\u2014</span><span class="md-scl">not scored</span>'
        : '<span class="md-scn"><span class="cp-score" style="color:'+scoreColour(e.score)+'">'+e.score.toFixed(0)+'</span>'+
          '<span class="band mono band-'+esc(e.band)+'">'+esc(e.band)+'</span></span>'+
          '<span class="md-scl">counterparty score</span>')+'</div>'+
      ((e.market&&e.market.direction!=='none'&&e.market.direction!=='flat')?'<div class="md-mkt">'+mkt(e.market)+'</div>':'')+
      '<div class="md-act">'+act+'<a class="filter" href="'+ROOT+'banks/'+esc(id)+'.html">Full profile</a>'+
      '<button class="filter" id="md-close" aria-label="Close">Close</button></div></div>'+
      '<div id="md-body"><div class="md-grid">'+
        sect('Trends','','<div class="md-wait">'+[0,1,2,3,4,5].map(function(){return '<div class="md-sk"></div>'}).join('')+'</div>','md-trend-panel')+
        '<div class="md-col">'+sect('Ratings','',sk(4))+sect('Score make-up','',sk(5))+'</div>'+
        '</div></div>';
    if(!dlg.open)dlg.showModal();
    var put=function(b){var t=document.getElementById('md-body');if(t)t.innerHTML=modalBody(b,e)};
    hideTip();
    if(MCACHE[id])return put(MCACHE[id]);
    detail(id,1).then(put).catch(function(){
      var t=document.getElementById('md-body');if(t)t.innerHTML='<div class="empty">Could not load this bank’s detail.</div>'});
  }

  // Opening a bank costs one small file, and on Pages a first byte for a file nobody has asked for
  // yet can take the better part of a second. So the request starts at the first sign of intent -
  // the pointer settling on a row, a finger touching it, a key focusing it - and the click usually
  // finds it already in flight or done. One promise per bank, so intent and click never fetch twice.
  var INFLIGHT={};
  function detail(id,eager){
    if(MCACHE[id])return Promise.resolve(MCACHE[id]);
    if(INFLIGHT[id])return INFLIGHT[id];
    // a click is waiting on this one; a warm-up is not
    INFLIGHT[id]=(eager||!window.lowFetch?fetch(ROOT+'data/detail/'+id+'.json'):lowFetch(ROOT+'data/detail/'+id+'.json'))
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
  // The names in your own policy are the ones you open. Their files are small - 5 KB each over
  // the wire - and an idle browser fetches them, so the dialog has nothing to wait for. Skipped
  // on a metered or slow connection, and never more than a dozen.
  (window.whenIdle||function(f){setTimeout(f,3000)})(function(){
    if(window.sparingConnection&&sparingConnection())return;
    load().slice(0,12).forEach(function(it){detail(it.id).catch(function(){})});
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
    var wl={}; watchIds().forEach(function(id){wl[id]=1});
    var top={}; if(uniChip==='top')topStanding().forEach(function(e){top[e.id]=1});
    return data.rows.filter(function(e){
      if(uniChip==='top'&&!top[e.id])return false;
      if(uniChip==='mine'&&have[e.id]==null)return false;
      if(uniChip==='watch'&&!wl[e.id])return false;
      if(reg&&e.region!==reg)return false;
      if(typ&&e.type!==typ)return false;
      if(bnd&&e.band!==bnd)return false;
      if(only&&e.score==null)return false;
      if(q&&(e.short+' '+e.name+' '+(e.country||'')+' '+(e.lei||'')).toLowerCase().indexOf(q)<0)return false;
      return true;
    }).map(function(e){return {e:e,tenor:have[e.id]}}).sort(function(a,b){
      var k=uniSort.key, isx=XCOLS.some(function(c){return c[0]===k});
      var va=isx?xval(a.e,k):a.e[k], vb=isx?xval(b.e,k):b.e[k];
      if(va==null&&vb==null)return 0; if(va==null)return 1; if(vb==null)return -1;
      if(typeof va==='string')return uniSort.dir*va.localeCompare(vb);
      return uniSort.dir*(va-vb);
    });
  }
  var PEEK=8;    // rows a scrolling window shows before there is anything below its fold
  // One chip at a time, or none: the five strongest standings, the names held, the names followed.
  var uniChip='';
  function topStanding(){return data.rows.filter(function(e){return e.score!=null}).sort(function(a,b){return b.score-a.score}).slice(0,5)}
  // Columns the universe table shows on request. The four a policy is written around are always
  // there; these are the rest of what is held, brought in without widening the default for
  // everyone, and the choice is kept in this browser.
  var XCOLS=[['tier1_ratio','Tier 1','%',1],['total_capital_ratio','Total cap.','%',1],['roe','ROE','%',1],['roa','ROA','%',2],
             ['nim','NIM','%',2],['efficiency_ratio','Cost/income','%',0],['npl_ratio','NPL','%',2],['cost_of_risk','Cost of risk','%',2],
             ['total_assets','Assets','m',0],['deposits','Deposits','m',0]];
  var XKEY=KEY.replace('policy','uni.cols');
  function xcols(){try{var v=JSON.parse(localStorage.getItem(XKEY)||'[]');return Array.isArray(v)?v.filter(function(k){return XCOLS.some(function(c){return c[0]===k})}):[]}catch(e){return[]}}
  function setXcols(v){try{localStorage.setItem(XKEY,JSON.stringify(v))}catch(e){}}
  function xval(e,k){return (e.x||{})[k]}
  function xfmt(v,unit,dp){
    if(v==null)return '\u2014';
    if(unit==='m')return v>=1e6?(v/1e6).toFixed(2)+'tn':v>=5000?(v/1000).toFixed(0)+'bn':v.toFixed(0)+'m';
    return Number(v).toFixed(dp)+(unit==='%'&&dp===0?'%':'');
  }
  function renderXhead(){
    var tr=document.querySelector('#uni-table thead tr'); if(!tr)return;
    tr.querySelectorAll('th.uni-x').forEach(function(th){th.remove()});
    var fig=tr.querySelector('th.uni-fig'); if(!fig)return;
    xcols().forEach(function(k){
      var c=XCOLS.filter(function(x){return x[0]===k})[0]; if(!c)return;
      var th=document.createElement('th'); th.className='num uni-x'; th.dataset.sort=k; th.textContent=c[1];
      if(uniSort.key===k)th.setAttribute('aria-sort',uniSort.dir>0?'ascending':'descending');
      tr.insertBefore(th,fig);
    });
  }
  function xcells(e){
    return xcols().map(function(k){var c=XCOLS.filter(function(x){return x[0]===k})[0];return '<td class="num uni-x">'+xfmt(xval(e,k),c[2],c[3])+'</td>'}).join('');
  }
  function renderColsMenu(){
    var m=document.getElementById('uni-cols-menu'); if(!m)return;
    var on=xcols();
    m.innerHTML='<div class="uni-cols-h">More columns <span class="small muted">latest reported figure</span></div>'+XCOLS.map(function(c){
      return '<label><input type="checkbox" data-col="'+c[0]+'"'+(on.indexOf(c[0])>-1?' checked':'')+'> '+esc(c[1])+'</label>';
    }).join('')+'<div class="uni-cols-f"><button class="filter" type="button" id="uni-cols-none">None</button></div>';
  }
  // A figure's date, and how old that makes it: past six months it is shown as such, because a
  // capital ratio from a year ago is a different fact from one published last quarter.
  function asofCell(e){
    var old=(e.age_days||0)>180;
    return '<td class="mono small asof '+(old?'stale':'muted')+'"'+(old?' title="'+e.age_days+' days old"':'')+'>'+esc(e.asof||'\u2014')+'</td>';
  }
  // "24 months" as "24m": the held tenor in a phone row leaves the name its width
  function tenorShort(t){return tenorLabel(t).replace(/ months?$/,'m').replace(/ years?$/,'y').replace(/ weeks?$/,'w').replace(/ days?$/,'d')}
  function renderUni(){
    var body=document.getElementById('uni-body'); if(!body||!data)return;
    var rows=uniRows(), t=curTenor();
    // Every row is here; the table scrolls inside a window rather than growing the page. Paging a
    // sorted list meant clicking through sixteen pages to read it, and the column headings went
    // off the top of the screen on the way. They stay put now, and the whole list is one scroll.
    renderXhead();
    var cnt=document.getElementById('uni-count');
    if(cnt)cnt.textContent=rows.length===data.rows.length?data.rows.length+' names'
      :rows.length+' of '+data.rows.length+' names match';
    var foot=document.getElementById('uni-count2');
    body.innerHTML=rows.map(function(r){
      var e=r.e;
      return '<tr class="uni-row'+(r.tenor!=null?' uni-mine':'')+'" data-id="'+esc(e.id)+'"'+(e.blurb?' title="'+esc(e.blurb)+'"':'')+'>'+
        '<td class="uni-st">'+(r.tenor!=null?'<span class="uni-own" title="in your list">\u2713</span>':starBtn(e.id))+'</td>'+
        // the action leads the row, so it is on screen however wide the table runs
        '<td class="uni-add">'+(r.tenor!=null
            ? '<span class="chip chip-good" title="already in your list at this tenor"><span class="tl-l">'+esc(tenorLabel(r.tenor))+'</span><span class="tl-s">'+esc(tenorShort(r.tenor))+'</span></span>'
            : '<button class="filter pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'" title="Add at '+esc(tenorLabel(t))+'">Add</button>')+'</td>'+
        '<td class="uni-nm"><span class="b">'+esc(e.short)+'</span>'+typeTag(e)+(mkt(e.market,1)?' '+mkt(e.market,1):'')+'<div class="small muted">'+esc(e.name)+'</div></td>'+
        '<td class="mono small">'+sovPill(e)+'</td>'+
        '<td class="num uni-sc">'+(e.score==null?'<span class="na">—</span>':
            // the number and its band already say where the name stands, and the table sorts on it;
            // a bar in every one of 152 rows only adds weight
            scoreNum(e.score,e.band,'sc-1'))+
          (e.score==null&&e.unscored?'<div class="small muted">'+esc(e.unscored)+'</div>':'')+'</td>'+
        // the same rating and ratio cells as Alternatives: one way to read a name across the tool
        '<td class="uni-rt ll-cpc"><b style="color:'+gradeColour(e.rating_composite)+'">'+esc(e.rating_composite||'—')+'</b>'+
          '<span class="ll-ags">'+(e.rating?toneMarks(e.rating.tones):'')+'</span></td>'+
        '<td class="num">'+(e.cet1==null?'—':e.cet1.toFixed(1)+'%')+'</td>'+
        '<td class="num">'+levTxt(e)+'</td>'+
        '<td class="num">'+(e.lcr==null?'—':Math.round(e.lcr)+'%')+'</td>'+
        '<td class="num">'+(e.nsfr==null?'—':Math.round(e.nsfr)+'%')+'</td>'+
        xcells(e)+
        asofCell(e)+'</tr>';
    }).join('')||'<tr><td colspan="13" class="empty">No name matches those filters.</td></tr>';
    // Measuring the box is no good here: renderUni first runs while this tab is still closed, a
    // hidden box measures nothing, and the answer would stick. The row count asks the same
    // question of the data rather than of the layout, and it cannot go stale.
    if(foot)foot.textContent=!rows.length?''
      :rows.length+(rows.length===1?' name':' names')+(rows.length>PEEK?' \u00b7 scroll for the rest':'');
  }
  function initUni(){
    var reg=document.getElementById('uni-region'), typ=document.getElementById('uni-type'),
        ten=document.getElementById('uni-tenor');
    if(!reg)return;
    var regions={},types={};
    data.rows.forEach(function(e){if(e.region)regions[e.region]=1;if(e.type)types[e.type]=1});
    Object.keys(regions).sort().forEach(function(r){var o=document.createElement('option');o.value=r;o.textContent=REGION_LABEL[r]||r;reg.appendChild(o)});
    Object.keys(types).sort().forEach(function(x){var o=document.createElement('option');o.value=x;o.textContent=TYPE_LABEL[x]||x;typ.appendChild(o)});
    TENORS.forEach(function(x){var o=document.createElement('option');o.value=x[0];o.textContent=x[1];if(x[0]===365)o.selected=true;ten.appendChild(o)});
    var oo=document.createElement('option');oo.value='other';oo.textContent='Other\u2026';ten.appendChild(oo);
    var other=document.getElementById('uni-other');
    ten.addEventListener('change',function(){if(other)other.hidden=ten.value!=='other';
      if(ten.value==='other'){var nb=document.getElementById('uni-other-n');if(nb)nb.focus()}});
    renderColsMenu();
    var cb=document.getElementById('uni-cols-btn'), cm=document.getElementById('uni-cols-menu');
    if(cb&&cm){
      cb.addEventListener('click',function(){var open=cm.hidden;cm.hidden=!open;cb.setAttribute('aria-expanded',String(open));cb.classList.toggle('active',open)});
      cm.addEventListener('change',function(ev){var i=ev.target.closest('input[data-col]');if(!i)return;var on=xcols().filter(function(k){return k!==i.dataset.col});if(i.checked)on.push(i.dataset.col);
        setXcols(XCOLS.map(function(c){return c[0]}).filter(function(k){return on.indexOf(k)>-1}));renderUni()});
      cm.addEventListener('click',function(ev){if(ev.target.id==='uni-cols-none'){setXcols([]);renderColsMenu();renderUni()}});
      document.addEventListener('click',function(ev){if(!cm.hidden&&!ev.target.closest('.uni-cols')){cm.hidden=true;cb.setAttribute('aria-expanded','false');cb.classList.remove('active')}});
    }
    ['uni-q','uni-region','uni-type','uni-band','uni-scored','uni-tenor','uni-other-n','uni-other-u'].forEach(function(id){
      var el=document.getElementById(id); if(el)el.addEventListener('input',renderUni);
    });
    var ft=document.getElementById('uni-ftoggle'), fr=document.getElementById('uni-row2');
    if(ft&&fr)ft.addEventListener('click',function(){var o=!fr.classList.contains('open');fr.classList.toggle('open',o);
      ft.setAttribute('aria-expanded',String(o));ft.classList.toggle('active',o)});
    var chips=document.getElementById('uni-chips');
    if(chips)chips.addEventListener('click',function(ev){
      var b=ev.target.closest('[data-uf]'); if(!b)return;
      uniChip=uniChip===b.dataset.uf?'':b.dataset.uf;
      chips.querySelectorAll('[data-uf]').forEach(function(x){x.classList.toggle('active',x.dataset.uf===uniChip)});
      renderUni();
    });
    // One listener on the row, not one per heading: the column chooser adds headings after
    // this runs, and a heading with no listener sorted nothing.
    var uhead=document.querySelector('#uni-table thead');
    if(uhead)uhead.addEventListener('click',function(ev){
        var th=ev.target.closest('th[data-sort]'); if(!th)return;
        var k=th.dataset.sort;
        uniSort.dir=(uniSort.key===k)?-uniSort.dir:(k==='short'||k==='country'||k==='asof'?1:-1);
        uniSort.key=k;
        document.querySelectorAll('#uni-table th[data-sort]').forEach(function(x){x.removeAttribute('aria-sort')});
        th.setAttribute('aria-sort',uniSort.dir>0?'ascending':'descending');
        renderUni();
    });
    renderUni();
  }


  // ---- an open card ----------------------------------------------------------------------
  // Four panels, one question each, on a tinted ground so the sections are told apart at a
  // glance. No figure is left bare: 14.3% CET1 is strong or thin depending on the company it
  // keeps, so every measure is drawn against the spread of the same measure across the covered
  // universe - middle half shaded, median marked, this bank in orange. That is the idiom the
  // profile trends already use for a peer group, at the size of a card.
  // US banks publish Tier 1 leverage on average assets, not the Basel ratio: shown, and named
  function levTxt(e){
    if(e.leverage!=null)return e.leverage.toFixed(1)+'%';
    if(e.lev_us!=null)return '<span class="lv-w" title="US Tier 1 leverage: Tier 1 capital over average assets, not the Basel exposure measure">'+e.lev_us.toFixed(1)+'%<sup class="lv-us">US</sup></span>';
    return '—';
  }
  var UNI=null;
  function qt(v,p){var i=(v.length-1)*p,a=Math.floor(i),b=Math.ceil(i);return v[a]+(v[b]-v[a])*(i-a)}
  function uni(k){
    if(!UNI){UNI={};['score','cet1','leverage','lcr','nsfr','rating_grade'].forEach(function(m){
      var v=data.rows.map(function(e){return e[m]}).filter(function(x){return x!=null}).sort(function(a,b){return a-b});
      // the axis runs the 5th to the 95th: one LCR of 400% should not flatten every other gauge
      UNI[m]=v.length>7?{v:v,lo:qt(v,.05),hi:qt(v,.95),p25:qt(v,.25),p50:qt(v,.5),p75:qt(v,.75),n:v.length}:null;
    })}
    return UNI[k];
  }
  function below(st,x){var n=0;for(var i=0;i<st.v.length;i++)if(st.v[i]<x)n++;return Math.round(n/st.v.length*100)}
  function sk(n){var s='';for(var i=0;i<n;i++)s+='<span class="sk"></span>';
    return '<div class="sk-rows" aria-hidden="true">'+s+'</div>'}
  function sect(title,meta,body,cls){
    return '<div class="cp-cell'+(cls?' '+cls:'')+'"><h5><span>'+title+'</span>'+
           (meta?'<em>'+meta+'</em>':'')+'</h5>'+body+'</div>';
  }



  // ratings: the composite, the agencies laid on the scale so any disagreement shows, then one
  // line each with its outlook - an agency on negative outlook is the thing a treasurer looks for
  var OUTLOOK={positive:['\u25b2','up','positive outlook'],negative:['\u25bc','dn','negative outlook'],
               stable:['\u2013','lv','stable outlook'],developing:['\u25c7','lv','developing outlook'],
               evolving:['\u25c7','lv','evolving outlook']};
  // ---- the path the ratings took, from the register's own action log ----
  // The dialog gets the composite only: one line, where it started, where it is, and what moved
  // it. Every agency's own steps are the ladder on the full profile.
  function gradeLetter(g){return GRADES[Math.min(16,Math.max(0,Math.round(g)-1))]}
  function ratingPath(e){
    var h=e.rating_history, c=h&&h.composite;
    if(!c||c.length<2)return '';
    var w=100, ht=34, pad=4, t0=+new Date(c[0][0]), t1=Date.now();
    if(t1<=t0)return '';
    var gs=c.map(function(p){return p[1]});
    var lo=Math.min.apply(null,gs)-0.6, hi=Math.max.apply(null,gs)+0.6;
    var X=function(d){return ((+new Date(d)-t0)/(t1-t0)*w).toFixed(2)};
    var Y=function(g){return (pad+(g-lo)/(hi-lo)*(ht-2*pad)).toFixed(2)};   // a lower grade is a stronger rating
    var d='', prev=null;
    c.forEach(function(p){
      var x=X(p[0]), y=Y(p[1]);
      d+=(prev===null?'M'+x+','+y:'H'+x+'V'+y); prev=y;
    });
    d+='H'+w;
    var dots=c.map(function(p,i){
      if(!i)return '';
      var up=p[1]<c[i-1][1];
      return '<circle cx="'+X(p[0])+'" cy="'+Y(p[1])+'" r="1.9" fill="'+(up?'#1e7a3a':'#b04632')+'"/>';
    }).join('');
    var a=gradeLetter(c[0][1]), b=gradeLetter(c[c.length-1][1]);
    var bits=[];
    if(h.ups)bits.push('<b class="rp-u">'+h.ups+'</b> upgrade'+(h.ups>1?'s':''));
    if(h.downs)bits.push('<b class="rp-d">'+h.downs+'</b> downgrade'+(h.downs>1?'s':''));
    var last=(h.moves||[])[0];
    return '<div class="rp"'+tipd(tipHead('The path it took',esc(a)+' → '+esc(b))+
        '<i>the average of the three main agencies on every day it changed, from the register’s own action log</i>'+
        (last?'<i>last move: '+(last.action==='new'?'a new rating from':last.action==='withdrawal'?'a withdrawal by':'a '+esc(last.action)+(last.notches?' of '+last.notches+' notch'+(last.notches>1?'es':''):'')+' by')+
          ' one of the three on '+esc(last.date)+'</i>':'')+
        '<i>green marks a step up, red a step down; nothing before July 2015 is on the platform</i>')+'>'+
      '<span class="rp-e" style="color:'+gradeColour(a)+'">'+esc(a)+'</span>'+
      '<svg viewBox="0 0 '+w+' '+ht+'" preserveAspectRatio="none" class="rp-svg" aria-hidden="true">'+
        '<path d="'+d+'" fill="none" stroke="#0a2540" stroke-width="2" stroke-opacity=".85" '+
        'vector-effect="non-scaling-stroke" stroke-linejoin="round"/>'+dots+'</svg>'+
      '<span class="rp-e" style="color:'+gradeColour(b)+'">'+esc(b)+'</span>'+
      '<span class="rp-t">'+(bits.join(' · ')||'no change')+'<span class="muted"> since '+
        esc(String(h.start||'').slice(0,4))+'</span></span></div>';
  }
  // The shortlist, one tenor and one page at a time. Kept apart from the pane around it so a
  // page change redraws the table and nothing else: the tenor chips, the counts and the bar
  // saying what the weakest accepted name is are all unchanged by turning a page.
  var llSets=[], llFirst=null;
  function llBody(x){
    var t=x.t, total=x.total;
    if(!total)
      return '<p class="ll-none">Nothing outside your policy is as strong as the weakest name you '+
        'already accept at '+esc(tenorLabel(t))+'.'+
        (llFirst!=null&&llFirst!==t?' Shorter tenors accept a weaker name, so <button class="linky '+
          'll-jump" data-t="'+llFirst+'">'+esc(tenorLabel(llFirst))+'</button> has matches.':'')+'</p>';
    return llTable(x.cands,x.w,t,0)+
      '<div class="tfoot small muted">'+total+(total===1?' name':' names')+' clear the bar at this tenor'+
      (total>PEEK?' \u00b7 scroll for the rest':'')+'</div>';
  }

  // ---- the shortlist ----
  // Twenty-four cards carrying the same eight figures in the same eight places is a table that has
  // been taken apart: nothing lines up, so nothing can be compared down a column, and the eye has
  // to find each number again in every card. One row a name, and the columns do the comparing.
  function llTable(cands,w,t,off){
    off=off||0;
    var span=1;
    cands.forEach(function(e){ if(w.score!=null&&e.score-w.score>span)span=e.score-w.score; });
    // a ratio is marked only where it is in the bottom quarter of every covered name: on a
    // shortlist of strong names, the useful colour says where the weak spot is
    var kpi=function(k,v,dp,suf){
      var st=uni(k), low=(v!=null&&st&&v<st.p25);
      return '<td class="ll-v'+(low?' ll-low':'')+'"'+(low?' title="in the bottom quarter of every covered name"':'')+'>'+
        (v==null?'<span class="na">—</span>':Number(v).toFixed(dp)+(suf||''))+'</td>';
    };
    var rows=cands.map(function(e,i){
      var vs=(w.score!=null)?(e.score-w.score):null;
      var mp=(e.market&&e.market.direction!=='none'&&e.market.direction!=='flat')?mkt(e.market):'';
      var bar=(vs!=null&&vs>0)?'<span class="ll-bar2" style="width:'+Math.max(3,vs/span*100).toFixed(0)+
        '%;background:'+(BANDC[e.band]||'#c9d3de')+'" title="'+vs.toFixed(1)+' points above the weakest name you accept at this tenor"></span>':'';
      return '<tr class="ll-r" data-id="'+esc(e.id)+'" data-tenor="'+t+'" tabindex="0" role="button" aria-label="'+
          esc(e.short)+', open detail" style="--band:'+(BANDC[e.band]||'#c9d3de')+'">'+
        '<td class="ll-rank mono">'+(off+i+1)+'</td>'+
        '<td class="ll-name"><span class="ll-nm">'+esc(e.short)+typeTag(e)+(mp?' '+mp:'')+'</span>'+
          '<span class="ll-co">'+esc(e.name)+' · '+sovPill(e)+'</span></td>'+
        '<td class="ll-sc">'+scoreNum(e.score,e.band,'sc-2')+
          '<span class="ll-track">'+bar+'</span></td>'+
        '<td class="ll-cpc"><b style="color:'+gradeColour(e.rating_composite)+'">'+esc(e.rating_composite||'—')+'</b>'+
          '<span class="ll-ags">'+(e.rating?toneMarks(e.rating.tones):'')+'</span></td>'+
        kpi('cet1',e.cet1,1,'%')+(e.leverage==null&&e.lev_us!=null?'<td class="ll-v">'+levTxt(e)+'</td>':kpi('leverage',e.leverage,1,'%'))+kpi('lcr',e.lcr,0,'%')+kpi('nsfr',e.nsfr,0,'%')+
        asofCell(e)+
        '<td class="ll-addc"><button class="filter ll-add pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'">Add</button></td></tr>';
    }).join('');
    return '<div class="table-wrap scrollbox"><table class="plain ll-t2"><thead><tr>'+
      '<th></th><th>Name</th><th>Score'+mk('score')+'</th><th>Agency rating</th>'+
      '<th>CET1</th><th>LEV</th><th>LCR</th><th>NSFR</th><th>Figures</th><th></th>'+
      '</tr></thead><tbody>'+rows+'</tbody></table></div>';
  }
  // The agencies' own ratings: fetched once from the members path, and absent (a build
  // without it, or a login in front of it later) the dialog simply shows the composite alone.
  var ATTR=null;
  fetch(ROOT+'members/ratings.json').then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(j){ATTR=j}).catch(function(){});
  function attrLine(e){
    var rows=ATTR&&ATTR.rows&&ATTR.rows[e.id]; if(!rows||!rows.length)return '';
    var G={positive:'\u25b2',negative:'\u25bc',stable:'\u25b6','watch negative':'\u25c6','watch positive':'\u25c6'};
    return '<div class="cr cr-attr" title="the agencies\u2019 own current ratings, quoted from the ESMA register">'+
      '<span class="cr-a">Agencies (quoted)</span><span class="cr-g cr-attr-l">'+rows.map(function(r){var o=r.outlook&&r.outlook!=='stable'?' <span class="cr-o '+(r.outlook==='positive'?'up':r.outlook==='negative'?'dn':'lv')+'">'+(G[r.outlook]||'')+'</span>':'';return '<span><b>'+esc(r.name)+'</b> <span class="tnum">'+esc(r.lt)+'</span>'+o+'</span>'}).join('')+'</span>'+
      '</div>';
  }
  function ratingCell(e){
    var r=e.rating;
    if(!r)return '<div class="cp-rt-none">None of the three main agencies rates this entity.</div>';
    var strip='';
    // the axis is the range the covered universe occupies, not AAA to default, so the notches
    // that separate one bank from another are the ones that get the width
    var st=uni('rating_grade');
    var ia=r.avg-1, iw=r.worst-1;
    var lo=Math.min(st?Math.floor(st.lo)-1:2,Math.floor(ia)), hi=Math.max(st?Math.ceil(st.hi)-1:12,iw);
    if(hi-lo<3)hi=lo+3;
    var X=function(i){return 6+Math.max(0,Math.min(1,(i-lo)/(hi-lo)))*88};   // inset, so an end mark is not hard on the edge
    var spread=r.worst-Math.round(r.avg);
    var tip=tipd(tipHead('On the scale','average '+esc(r.letter))+
      '<i>'+esc(describeRating(r))+'</i>'+
      '<i>the orange mark is the average, the hollow one the weakest'+(r.n>1?(spread>0?': they differ by <em>'+spread+' notch'+(spread>1?'es':'')+'</em>':': <em>the three agree</em>'):'')+'</i>'+
      '<i>the axis spans the covered names, '+esc(GRADES[Math.max(0,lo)])+' to '+esc(GRADES[Math.min(16,hi)])+'</i>');
    strip='<div class="cr-scale" style="height:25px"'+tip+'>'+
      '<span class="cr-ax" style="top:5px"></span>'+
      ((lo<=9&&hi>=10)?'<span class="cr-ig" style="left:'+X(9.5).toFixed(1)+'%;top:1px"></span>':'')+
      (r.n>1?'<span class="cr-dot cr-worst" style="left:'+X(iw).toFixed(1)+'%;top:2px;border-color:'+gradeColour(r.worst_letter)+'"></span>':'')+
      '<span class="cr-c" style="left:'+X(ia).toFixed(1)+'%;height:14px"></span>'+
      '<span class="cr-e cr-e1">'+esc(GRADES[Math.max(0,lo)])+'</span>'+
      '<span class="cr-e cr-e2">'+esc(GRADES[Math.min(16,hi)])+'</span></div>';
    var rows='<div class="cr" title="the lowest of the three main agencies\u2019 ratings">'+
        '<span class="cr-a">Weakest</span><b class="cr-g" style="color:'+gradeColour(r.worst_letter)+'">'+esc(r.worst_letter)+'</b>'+
        '<span></span><span class="cr-s small muted">'+(r.n>1&&r.worst_letter===r.letter?'the same':'')+'</span></div>'+
      '<div class="cr">'+
        // three stable outlooks are said in words alone; marks appear when one of them is not stable
        '<span class="cr-a">Outlooks</span><span class="cr-g">'+((r.tones||[]).every(function(t){return t==='stable'})?'':toneGlyphs(r.tones))+'</span>'+
        '<span></span><span class="cr-s small muted">'+esc(toneWords(r.tones)||'none published')+'</span></div>'+
      (r.date?'<div class="cr"><span class="cr-a">Last action</span><span class="cr-g tnum">'+esc(r.date)+'</span><span></span><span class="cr-s small muted">by any of the three</span></div>':'')+
      attrLine(e);
    return '<div class="cr-top"><span class="cr-comp" style="color:'+gradeColour(r.letter)+'">'+
      esc(r.letter)+'</span><span class="small muted">average of '+ofThree(r.n)+' main agencies</span></div>'+strip+'<div class="cr-rows">'+rows+'</div>';
  }


  // a tab says how much is behind it, so a reader knows whether it is worth the click
  function tabCount(id,n){var el=document.getElementById(id); if(el)el.textContent=n?String(n):''}
  // Weightings and Choose names are pages of the tool, beside Start here: a button that used to
  // open either as a dialog opens its page, the way the navigation does.
  function openPage(name){
    var t=document.querySelector('.tabs-card .tab[data-tab="'+name+'"]'); if(!t)return;
    if(!t.classList.contains('active'))t.click();
    window.scrollTo(0,0);
  }
  // The table every name is on: an add goes straight onto the list, so several can be chosen in
  // one sitting.
  function openUni(){
    openPage('universe');
    var q=document.getElementById('uni-q'); if(q)q.focus({preventScroll:true});
  }
  function uniBtn(label){return '<button class="filter filter-blue" id="uni-open" type="button">'+label+'</button>'}
  // The names followed but not held: a short table under the list, with the same figures and a
  // way to move one up into the list.
  function watchSection(p){
    var have={}; p.forEach(function(it){have[it.id]=1});
    var ws=watchIds().map(function(id){return byId[id]}).filter(function(e){return e&&!have[e.id]});
    if(!ws.length)return '';
    ws.sort(function(a,b){return (b.score||0)-(a.score||0)});
    var t=curTenor();
    var rows=ws.map(function(e){
      return '<tr class="pw-r" data-id="'+esc(e.id)+'"><td class="uni-st">'+starBtn(e.id)+'</td>'+
        '<td><a class="cp-nm" href="'+ROOT+'banks/'+esc(e.id)+'.html">'+esc(e.short)+'</a>'+typeTag(e)+'<div class="small muted">'+esc(e.name)+' \u00b7 '+sovPill(e)+'</div></td>'+
        '<td class="num">'+scoreNum(e.score,e.band,'sc-1')+'</td>'+
        '<td class="mono"><b style="color:'+gradeColour(e.rating_composite)+'">'+esc(e.rating_composite||'\u2014')+'</b></td>'+
        '<td class="num mono">'+(e.cet1==null?'\u2014':e.cet1.toFixed(1)+'%')+'</td>'+
        '<td class="num mono">'+(e.lcr==null?'\u2014':Math.round(e.lcr)+'%')+'</td>'+
        asofCell(e)+'<td>'+mkt(e.market,1)+'</td>'+
        '<td class="num"><button class="filter pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'">Add at '+esc(tenorLabel(t))+'</button></td></tr>';
    }).join('');
    return '<div class="pol-watch" id="pol-watch"><h4>Watching <span class="small muted">\u00b7 '+ws.length+(ws.length===1?' name':' names')+' you follow but do not hold; adding one moves it up</span></h4>'+
      '<div class="table-wrap"><table class="plain pw-t"><thead><tr><th></th><th>Name</th><th class="num">Score</th><th>Agency rating</th><th class="num">CET1</th><th class="num">LCR</th><th>Figures</th><th>Market</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div></div>';
  }
  // The Build-your-strategy panel: three steps, each saying where the reader has got to. Painted
  // with the list, so adding a name on the universe table moves step two the moment it happens.
  function paintStrategy(){
    var p=load(), w=weights();
    var el=function(id){return document.getElementById(id)};
    var n=p.length, names=el('st-names'), ten=el('st-tenors'), wt=el('st-weights');
    if(names)names.innerHTML=n?'<b>'+n+'</b> name'+(n===1?'':'s')+' on your list':'No names yet';
    if(ten){var ts=p.map(function(x){return +x.tenor||0}).filter(Boolean);
      ten.innerHTML=!n?'Set as you add each name':(!ts.length?'No tenor set yet':Math.min.apply(null,ts)===Math.max.apply(null,ts)?'Every name at <b>'+tenorLabel(ts[0])+'</b>':'Tenors from <b>'+tenorLabel(Math.min.apply(null,ts))+'</b> to <b>'+tenorLabel(Math.max.apply(null,ts))+'</b>')}
    if(wt)wt.innerHTML=w.__custom?'<b>Your own</b> weightings':'<b>Published</b> weightings';
    ['st-1','st-2','st-3'].forEach(function(id,i){var st=el(id); if(!st)return;
      st.classList.toggle('step-done',[!!w.__custom,n>0,n>0&&p.every(function(x){return +x.tenor>0})][i])});
  }
  function render(){
    paintStrategy();
    var p=load(); var out=document.getElementById('policy-body'); if(!out||!data)return;
    var llBox=document.getElementById('pol-ll'), llHtml='', llN=0;
    TIPS={}; hideTip();                       // the marks are about to be rebuilt
    var html='';
    // nothing approved yet: say what to do and open the door to the table, rather than showing an
    // empty box and a share bar with nothing to share
    var share=document.getElementById('pol-share'); if(share)share.hidden=!p.length;
    if(!p.length){
      // an instruction and the open table under it: the survey of the market is the empty state
      html+='<div class="pol-empty"><p><b>Your list is empty.</b> The button below opens every covered name: sort on any column, '+
        'filter by region, type or band, and press Add on a row. Every name you hold is re-checked each night '+
        'against its regulatory filings, its agency ratings and the market.</p>'+
        '<p class="small muted">Everything stays in this browser; nothing is sent anywhere. '+
        'To see the page with names on it, <button class="linky" id="pol-demo" type="button">load an example list</button>.</p>'+
        uniBtn('Choose from every covered name')+'</div>'+
        watchSection(p)}
    else{
      var n_flag=0;
      var rows=p.slice().sort(function(a,b){return b.tenor-a.tenor||(byId[a.id]&&byId[a.id].short||'').localeCompare(byId[b.id]&&byId[b.id].short||'')}).map(function(it){
        var e=byId[it.id]; var fl=flags(it,e); if(fl.some(function(x){return x[0]!=='muted'}))n_flag++;
        if(!e)return '<div class="pol-row"><div class="pr-name"><span class="b">'+esc(it.id)+'</span></div><div class="pr-flags">'+chip('No longer covered','bad')+'</div><button class="pol-rm" data-id="'+esc(it.id)+'" title="Remove">×</button></div>';
        // a name that has moved since approval carries an edge, so a long list scans in one pass
        var moved=fl.some(function(x){return x[0]!=='muted'&&x[0]!=='good'});
        // A row, not a card: the name, what it is worth, what it is rated, and how long you accept
        // it for. The four ratios and the events that used to sit here are all in the dialog a
        // click away, and a policy of twenty names is a column of numbers rather than a scroll.
        var worst_fl=fl.filter(function(x){return x[0]!=='muted'})[0];
        var kv=function(v,l,cls){return '<div class="ck'+(cls?' '+cls:'')+'"><b>'+v+'</b><span>'+l+'</span></div>'};
        return '<div class="pol-card'+(moved?' pol-card-flag':'')+'" data-id="'+esc(e.id)+'"'+(e.blurb?' title="'+esc(e.blurb)+'"':'')+'>'+
          '<div class="cp-top">'+
            // The country and its rating are drawn twice and shown once: on the second line with the
            // legal name where there is room for a second line, and up beside the name where there
            // is not, which is a card in a two-column list. A pill is a dozen bytes; a layout that
            // has to choose between the country and a third line of wrapping is not.
            '<div class="cp-id"><div class="cp-line"><a class="cp-nm" href="'+ROOT+'banks/'+esc(e.id)+'.html" title="'+esc(e.name)+'">'+esc(e.short)+'</a>'+
              '<span class="cp-sov">'+sovPill(e)+'</span></div>'+
              '<div class="cp-sub">'+esc(e.name)+' · '+sovPill(e)+'</div></div>'+
            '<div class="cp-stats">'+
              kv(scoreNum(e.score,e.band),'score','ck-score ck-sep')+
              kv('<span style="color:'+gradeColour(e.rating_composite)+'">'+esc(e.rating_composite||'—')+'</span>','agency rating')+
            '</div>'+
            tenorPick(it)+
            // a holding company says so beside the flag, where it does not take the name's room
            '<div class="cp-tags">'+typeTag(e)+(worst_fl?chip(worst_fl[2]||worst_fl[1],worst_fl[0],worst_fl[1])
              // a card speaks when the market moves; "Stable" on twelve cards of eighteen was noise
              :((e.market&&e.market.direction!=='none'&&e.market.direction!=='flat')?mkt(e.market):''))+'</div>'+
            '<button class="pol-rm" data-id="'+esc(e.id)+'" title="Remove from policy" aria-label="Remove '+esc(e.short)+'">×</button>'+
          '</div></div>';
      }).join('');
      if(isDemo(p))html='<div class="pol-demo">'+
        '<b>An example list.</b> Eighteen names shaped like a local authority\u2019s. Change it freely, or clear it and start your own.'+
        '<button class="filter" id="pol-demo-x">Clear it and start mine</button></div>'+html;
      var view=polView();
      html+='<div class="pol-summary">'+(n_flag?chip(n_flag+' of '+p.length+' need a look','warn'):chip('All '+p.length+' names unchanged since approval','good'))+' <span class="small muted">Flags compare today with the day you approved each name.</span>'+
        '<span class="pol-view" role="group" aria-label="Show as">'+uniBtn('Add names')+'<button class="filter'+(view==='cards'?' active':'')+'" id="pol-view-cards" type="button">Cards</button><button class="filter'+(view==='table'?' active':'')+'" id="pol-view-table" type="button">Table</button></span></div>';
      html+=overview(p.filter(function(it){return byId[it.id]}));
      html+=view==='table'?polTable(p,flags):'<div class="pol-list">'+rows+'</div>';
      html+=watchSection(p);
      // like-for-like: names at least as strong as the weakest you already accept at each tenor
      // One tenor at a time, chosen from a row of chips rather than four lists down a page. Each
      // one now stands alone: it shows every covered name that clears the bar at that tenor, not
      // the ones a longer tenor did not already list. A name that qualifies at 24 months qualifies
      // at 12, and reading the 12-month list should not depend on having read the other.
      var tenors=[];p.forEach(function(it){if(tenors.indexOf(it.tenor)<0)tenors.push(it.tenor)});tenors.sort(function(a,b){return b-a});
      var chips='', panes='', union={}, first=null, sets=[];
      tenors.forEach(function(t){
        var acc=p.filter(function(it){return it.tenor>=t}), w=worst(acc);
        if(w.grade==null&&w.score==null)return;
        var have={};p.forEach(function(it){have[it.id]=1});
        var cands=data.rows.filter(function(e){
          if(have[e.id]||e.score==null)return false;
          if(w.band&&bandRank(e.band)>bandRank(w.band))return false;
          if(w.grade!=null&&(e.rating_grade==null||e.rating_grade>w.grade))return false;
          if(w.score!=null&&e.score<w.score)return false;
          if(e.market&&e.market.direction==='down')return false;
          return true;
        }).sort(function(a,b){return b.score-a.score});
        // the tab badge counts every distinct name any tenor turns up, not just the ones drawn
        cands.forEach(function(e){union[e.id]=1});
        sets.push({t:t,w:w,total:cands.length,cands:cands});
      });
      // The longest tenor is the strictest, and on a strong list nothing clears it. Opening there
      // showed a page whose whole content was a sentence saying there was nothing to show, so the
      // tab opens on the longest tenor that actually turns something up.
      sets.forEach(function(x){if(first==null&&x.total)first=x.t});
      if(first==null&&sets.length)first=sets[0].t;
      llSets=sets; llFirst=first;
      sets.forEach(function(x){
        var t=x.t, w=x.w, total=x.total;
        var wg=GRADES[Math.floor((w.grade||1)+0.5)-1]||'?';
        chips+='<button class="filter ll-t'+(t===first?' active':'')+'" data-t="'+t+'">'+esc(tenorLabel(t))+
               '<span class="cnt">'+total+'</span></button>';
        panes+='<div class="ll-pane" data-t="'+t+'"'+(t===first?'':' hidden')+'>'+
          '<div class="ll-head">'+
          '<span class="ll-bar">the weakest you accept at '+esc(tenorLabel(t))+
            '<b class="band mono band-'+esc(w.band||'')+'">'+esc(w.band||'?')+'</b>'+
            '<b style="color:'+gradeColour(wg)+'">'+esc(wg)+'</b>'+
            '<b style="color:'+scoreColour(w.score)+'">'+(w.score!=null?w.score.toFixed(0):'?')+'</b></span></div>'+
          '<div class="ll-body">'+llBody(x)+'</div></div>';
      });
      ll=(tenors.length>1?'<div class="ll-tenors filters">'+chips+'</div>':'')+panes;
      llN=Object.keys(union).length;
      llHtml=ll;   // the panel head above says what this is
    }
    out.innerHTML=html;
    if(llBox)llBox.innerHTML=llHtml||'<div class="empty">Approve a name and this fills with the covered names that match the standing you accept.</div>';
    tabCount('tn-policy',p.length); tabCount('tn-ll',llN);
    renderUni();
    weightLine();
    // the list is on screen: anything speculative may start now
    if(!render.said){render.said=1;dispatchEvent(new Event('cp:ready'))}
  }
  // The tenor you accept a name for is the one thing on this list that is your decision rather
  // than a fact about the bank, and it was printed as if it were a fact: to change it you had to
  // remove the name and add it again. It is a select now, and choosing writes straight through.
  function tenorPick(it){
    var opts=TENORS.slice();
    if(!opts.some(function(t){return t[0]===it.tenor}))opts.push([it.tenor,tenorLabel(it.tenor)]);
    opts.sort(function(a,b){return a[0]-b[0]});
    return '<label class="cp-ten"><span>tenor</span><select data-id="'+esc(it.id)+'" aria-label="Longest tenor">'+
      opts.map(function(t){return '<option value="'+t[0]+'"'+(t[0]===it.tenor?' selected':'')+'>'+esc(t[1])+'</option>'}).join('')+
      '</select></label>';
  }
  // ---- an example portfolio -------------------------------------------------------------------
  // A list shaped like a local authority's - the clearing banks it settles through, a few building
  // societies, a few overseas names, tenors graded by standing - for showing the page with names
  // on it. It is loaded only by the link in the empty state, and the page says it is an example.
  var DEMO=[
    ['nwb-bank',1825],['bng-bank',1825],['rabobank',730],['handelsbanken-plc',730],
    ['dz-bank',730],['td-bank',730],
    ['yorkshire-bs',730],['skipton-bs',730],['leeds-bs',365],['coventry-bs',365],
    ['nationwide',365],['hsbc-uk',365],['barclays-bank-uk',365],['santander-uk',365],
    ['lloyds-bank',182],['natwest-bank',182],['bank-of-scotland',182],['close-brothers',100]
  ];
  function demoPolicy(){
    var out=[];
    DEMO.forEach(function(d){
      var e=byId[d[0]]; if(!e)return;
      out.push({id:d[0],tenor:d[1],added:new Date().toISOString().slice(0,10),base:snapshot(e)});
    });
    return out;
  }
  function isDemo(p){
    if(!p||p.length!==DEMO.length)return false;
    var want={};DEMO.forEach(function(d){want[d[0]]=d[1]});
    return p.every(function(x){return want[x.id]===x.tenor});
  }
  function add(id,tenor){var p=load();var e=byId[id];if(!e)return;var ex=p.filter(function(x){return x.id===id})[0];
    if(ex){ex.tenor=tenor}else{p.push({id:id,tenor:tenor,added:new Date().toISOString().slice(0,10),base:snapshot(e)});
      var w=watchIds(),wi=w.indexOf(id);if(wi>=0){w.splice(wi,1);saveWatch(w)}}
    save(p);render()}
  // ---- the weighting panel ------------------------------------------------------------------
  function pct(w){var t=0;PILLARS.forEach(function(p){t+=w[p[0]]});return t}
  function weightPanel(){
    var box=document.getElementById('pol-weights'); if(!box)return;
    var w=weights(), total=pct(w)||1;
    var rows=PILLARS.map(function(p){
      var k=p[0], v=w[k];
      return '<div class="wt-row"><label for="wt-'+k+'"><b>'+esc(p[1])+'</b><span>'+esc(p[3])+'</span></label>'+
        '<input id="wt-'+k+'" class="wt-s" type="range" min="0" max="60" step="1" value="'+v+'" data-k="'+k+'" '+
          'aria-label="'+esc(p[1])+' weight">'+
        '<output class="wt-o" for="wt-'+k+'">'+(v/total*100).toFixed(0)+'%</output></div>';
    }).join('');
    box.innerHTML=
      // the sliders on the left, what they did on the right: the page uses its width, and the
      // answer to "and so?" sits beside the control that asked it
      '<div class="wt-body"><div class="wt-grid">'+rows+'</div><aside class="wt-side">'+weightEffect()+
        '<div class="wt-actions"><button class="filter" id="wt-reset"'+(w.__custom?'':' disabled')+'>Back to the starting point</button></div>'+
      '<p class="wt-note small muted"><b>Not a credit rating</b> under the UK or EU Credit Rating Agency Regulations: arithmetic on '+
        'published figures and ratings, combined your way. <b>Not advice:</b> your policy, limits and tenors remain yours.</p></aside></div>';
  }

  // Moving a slider is abstract until you see what it did. This is the answer to "and so?": how far
  // the reader's own weights carry the names on their own list away from the starting point.
  function weightEffect(){
    var pool=((data&&data.rows)||[]).filter(function(e){return e.pw0!=null&&e.score!=null});
    if(!pool.length)return '';
    var mine={}; load().forEach(function(it){mine[it.id]=1});
    var yours=pool.filter(function(e){return mine[e.id]});
    var use=yours.length?yours:pool,
        what=yours.length?'your '+yours.length+' counterparties':pool.length+' covered names';
    var moved=use.filter(function(e){return e.band!==e.band0});
    var deltas=use.map(function(e){return {e:e,d:e.score-e.pw0}}).sort(function(a,b){return b.d-a.d});
    var big=deltas[0], small=deltas[deltas.length-1];
    var spread=Math.max(Math.abs(big?big.d:0),Math.abs(small?small.d:0));
    if(spread<0.05)
      return '<div class="wt-effect wt-flat">These are the starting weights, so every score is the published one. '+
             'Move a slider and this line says what changed.</div>';
    function mover(x,cls){
      if(!x||Math.abs(x.d)<0.05)return '';
      return '<span class="wt-mv '+cls+'"><b>'+esc(x.e.short)+'</b>'+
             '<i>'+x.e.pw0.toFixed(1)+' \u2192 '+x.e.score.toFixed(1)+'</i>'+
             '<em>'+(x.d>0?'+':'')+x.d.toFixed(1)+'</em></span>';
    }
    return '<div class="wt-effect"><div class="wt-eh">Against the starting point, across '+what+
      ': <b>'+(moved.length||'no')+'</b> change band, and the largest move is <b>'+spread.toFixed(1)+'</b> points.</div>'+
      '<div class="wt-movers">'+deltas.slice(0,3).map(function(x){return mover(x,'up')}).join('')+
        deltas.slice(-3).reverse().map(function(x){return mover(x,'down')}).join('')+'</div></div>';
  }
  function weightLine(){
    var out=document.getElementById('wt-vals'); if(!out)return;
    var w=weights(), total=pct(w)||1;
    out.innerHTML=PILLARS.map(function(p){return '<span class="wt-v"><b>'+(w[p[0]]/total*100).toFixed(0)+'%</b>'+esc(p[1].toLowerCase())+'</span>'}).join('')+
      '<span class="wt-who small muted">'+(w.__custom?'set by you':'the starting point')+'</span>';
  }
  function openWeights(){weightPanel(); openPage('weights')}
  function bindWeights(){
    var box=document.getElementById('pol-weights'); if(!box)return;
    var chg=document.getElementById('wt-change'); if(chg)chg.addEventListener('click',openWeights);
    weightPanel();          // the page is in the document from the start, so it is drawn from the start
    box.addEventListener('input',function(ev){
      var s=ev.target.closest('.wt-s'); if(!s)return;
      var w=weights(); delete w.__custom; w[s.dataset.k]=+s.value; saveWeights(w);
      // the panel reports what the weights did, so the scores are recomputed before it is drawn
      applyWeights(); weightPanel(); render();
    });
    box.addEventListener('click',function(ev){
      if(!ev.target.closest('#wt-reset'))return;
      saveWeights({}); applyWeights(); weightPanel(); render();
    });
  }

  function init(){
    data.rows.forEach(function(e){byId[e.id]=e});
    document.addEventListener('click',function(ev){var b=ev.target.closest('.pol-rm');if(b){var p=load().filter(function(x){return x.id!==b.dataset.id});save(p);render();return}
      var st=ev.target.closest('.uni-star');if(st){toggleWatch(st.dataset.id);render();return}
      if(ev.target.closest('#uni-open,.uni-open')){openUni();return}
      var a=ev.target.closest('.pol-add-ll');if(a){add(a.dataset.id,+a.dataset.tenor);var d=document.getElementById('pol-modal');if(d&&d.open)d.close();return}
      // one tenor at a time: the chips swap the pane rather than scroll four lists past you
      var tc=ev.target.closest('.ll-t')||ev.target.closest('.ll-jump');
      if(tc){var box=document.getElementById('pol-ll')||document;
        if(tc.classList.contains('ll-jump'))tc=box.querySelector('.ll-t[data-t="'+tc.dataset.t+'"]')||tc;
        [].forEach.call(box.querySelectorAll('.ll-t'),function(b){b.classList.toggle('active',b===tc)});
        [].forEach.call(box.querySelectorAll('.ll-pane'),function(q){q.hidden=q.dataset.t!==tc.dataset.t});
        return}
      if(ev.target.id==='md-close'){document.getElementById('pol-modal').close();return}
      // a card opens its detail; a link inside it still navigates
      if(ev.target.id==='pol-view-cards'||ev.target.id==='pol-view-table'){setPolView(ev.target.id==='pol-view-table'?'table':'cards');render();return}
      var pth=ev.target.closest('#pol-table th[data-k]');
      if(pth){var k=pth.dataset.k; polSort.dir=polSort.key===k?-polSort.dir:(k==='short'?1:-1); polSort.key=k; render();return}
      var card=ev.target.closest('.pol-card,.pol-tr,.ll-r,.uni-row');
      if(card&&!ev.target.closest('a,button,select,label')){
        var tn=card.dataset.tenor?+card.dataset.tenor:(card.classList.contains('uni-row')?curTenor():0);
        openModal(card.dataset.id,tn);return}
      if(ev.target.id==='pol-demo-x'){save([]);render();return}
      if(ev.target.id==='pol-demo'){save(demoPolicy());render();return}
      if(ev.target.id==='pol-clear'){if(confirm('Remove every counterparty from this policy?')){save([]);render()}return}
      if(ev.target.id==='pol-use-shared'){save(window.__shared);window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);render();return}
      if(ev.target.id==='pol-keep-mine'){window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);return}
    });
    // choosing a tenor is a policy change, so it is written the moment it is made
    document.addEventListener('change',function(ev){
      var sel=ev.target.closest('.cp-ten select'); if(!sel)return;
      add(sel.dataset.id,+sel.value);
    });
    // the addresses the old tabs answered to still open the right thing
    function byHash(){
      var h=location.hash.replace('#','').split('&')[0];
      if(h==='weights')weightPanel();      // the tab itself is opened by the address, like any other
    }
    byHash(); addEventListener('hashchange',byHash);
    // a reader with a list opens on the list; a reader without one opens on how to build it
    if(!location.hash&&load().length){var pt=document.querySelector('.tab[data-tab="policy"]'); if(pt&&!pt.classList.contains('active'))pt.click()}
    document.addEventListener('keydown',function(ev){
      if(ev.key!=='Enter'&&ev.key!==' ')return;
      var card=ev.target.closest&&ev.target.closest('.ll-r,.pol-card,.pol-tr');
      if(card&&!ev.target.closest('a,button')){ev.preventDefault();openModal(card.dataset.id,card.dataset.tenor?+card.dataset.tenor:0)}
    });
    var m=location.hash.match(/#p=([A-Za-z0-9_\-]+)/);if(m){var sh=decode(m[1]);if(sh&&sh.length){if(!load().length){save(sh);history.replaceState(null,'',location.pathname)}else{window.__shared=sh;var box=document.getElementById('pol-shared');box.hidden=false;box.querySelector('span').textContent='This link carries a policy of '+sh.length+' counterparties.'}}}
    render();
    initUni();
    weightPanel(); bindWeights();
  }
  var box=document.getElementById('policy-body');if(!box)return;
  fetch(ROOT+'data/peers.json').then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(j){PEERS=j}).catch(function(){});
  function failed(){
    dispatchEvent(new Event('cp:ready'));
    box.innerHTML='<div class="empty">Could not load the counterparty data. Reload the page.</div>';
    var u=document.getElementById('uni-body');
    if(u)u.innerHTML='<tr><td colspan="9" class="empty">Could not load the counterparty data. Reload the page.</td></tr>';
  }
  fetch(ROOT+'data/policy.json').then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(j){data=j;applyWeights();init()}).catch(failed);
})();
