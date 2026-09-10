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

  // The weighting model lives in app.js, because a profile page carries no policy.js and must
  // still show the reader's own weights rather than ours.
  var CPW=window.CPW, PILLARS=CPW.PILLARS;
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
  function save(p){try{localStorage.setItem(KEY,JSON.stringify(p))}catch(e){}}
  // the definition marker, drawn from the glossary every page carries
  function mk(k){return window.tipMark?window.tipMark(k):''}
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function fmt(v,dp,suf){return v==null?'<span class="na">—</span>':'<span class="mono">'+Number(v).toFixed(dp==null?1:dp)+(suf||'')+'</span>'}
  function tenorLabel(d){for(var i=0;i<TENORS.length;i++)if(TENORS[i][0]===d)return TENORS[i][1];return d+' days'}
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
  // one number, one colour, one letter - used wherever a score is shown in a row or a card
  function scoreNum(v,band,cls){
    if(v==null)return '<span class="na">\u2014</span>';
    return '<span class="sc-n'+(cls?' '+cls:'')+'" style="color:'+scoreColour(v)+'">'+v.toFixed(cls==='sc-1'?1:0)+'</span>'+
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
  var AGN_FULL={fitch:'Fitch',sp:'S&P',moodys:"Moody's",dbrs:'DBRS',kbra:'KBRA',scope:'Scope',jcr:'JCR',
                capital:'Capital Intelligence',creditreform:'Creditreform'};
  function sovPill(e){
    var sv=e&&e.sovereign;
    if(!sv||!sv.composite)return esc((e&&e.country)||'');
    var ags=sv.agencies.map(function(a){return (AGN_FULL[a.agency]||a.agency)+' '+a.value+(a.outlook?' ('+a.outlook+')':'')}).join(' \u00b7 ');
    return '<span class="sov" title="'+esc(sv.name+' sovereign rating, '+sv.n+(sv.n===1?' agency: ':' agencies: ')+ags+
           '. Context, not part of the score.')+'">'+esc(e.country||'')+'<b>'+esc(sv.composite)+'</b></span>';
  }
  function mkt(m,terse){if(!m||m.direction==='none')return terse?'<span class="na">\u2014</span>'  :'<span class="muted">no market data</span>';var k=m.direction==='down'?'bad':(m.direction==='up'?'good':'muted');return chip(m.label,k,m.label)}
  function ratings(r){return (r||[]).map(function(x){return '<span class="mono" title="'+esc(x.agency+' '+x.type+(x.outlook?' · '+x.outlook:''))+'">'+esc(x.letter)+' '+esc(x.value)+'</span>'}).join(' <span class="muted">·</span> ')||'<span class="muted">unrated</span>'}
  function shortR(r){return (r||[]).map(function(x){return '<span class="mono">'+esc(x.letter)+' '+esc(x.value)+'</span>'}).join(' <span class="muted">·</span> ')||'<span class="muted">—</span>'}
  function snapshot(e){return {score:e.score,band:e.band,grade:e.rating_grade,market:e.market&&e.market.direction,asof:e.asof}}
  // nothing makes a share link any more; a link already sent still opens one
  function decode(s){try{s=s.replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';return JSON.parse(decodeURIComponent(escape(atob(s))))}catch(e){return null}}

  // A headline is clipped to a line on a card and to two in the dialog, so the row carries the
  // whole of it in a tooltip, with the date, what kind of event it is and where it came from.
  var EV_WORD={bad:'adverse',warn:'one to watch',good:'positive'};
  function evRow(x){
    var k=x.severity==='bad'?'bad':(x.severity==='warn'?'warn':'good'), w=EV_WORD[k];
    var tip=tipd(tipHead(esc(x.date||''),w)+'<i>'+esc(x.title||'')+'</i>'+
      // a headline usually ends in its own publication, so the source is only worth a line of its own
      // when it is not already there
      ((x.source&&String(x.title||'').toLowerCase().indexOf(String(x.source).toLowerCase())<0)?'<i>'+esc(x.source)+'</i>':'')+
      (x.type?'<i>'+esc(x.type==='news'?'headline':x.type+' action')+'</i>':''));
    var t=esc(x.title||'');
    return '<div'+tip+'><span class="dot dot-'+k+'" title="'+w+'"></span>'+
      '<span class="mono muted">'+esc(x.date||'')+'</span><span class="hd">'+
      (x.url?'<a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+t+'</a>':t)+'</span></div>';
  }

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

  function bandMix(es){
    var n={},who={},tot=0;BANDS.forEach(function(b){n[b]=0;who[b]=[]});
    es.forEach(function(e){if(e.band&&n[e.band]!=null){n[e.band]++;who[e.band].push(e);tot++}});
    if(!tot)return '<div class="muted small">no scored names</div>';
    var w=260,h=16,x=0,parts='',key='';
    BANDS.forEach(function(b){
      if(!n[b])return;
      var seg=n[b]/tot*w;
      var sc=who[b].map(function(e){return e.score}).sort(function(a,c){return a-c});
      var tip=tipd(tipHead('Band '+b,n[b]+' of '+tot)+
        '<i>'+Math.round(n[b]/tot*100)+'% of your scored names \u00b7 score '+BAND_RANGE[b]+'</i>'+
        '<i>lowest here <em>'+sc[0].toFixed(1)+'</em>, highest '+sc[sc.length-1].toFixed(1)+'</i>'+
        '<i>'+names(who[b])+'</i>');
      parts+='<rect x="'+x.toFixed(1)+'" y="0" width="'+Math.max(0,seg-2).toFixed(1)+'" height="'+h+'" rx="3" fill="'+BANDC[b]+'"'+tip+'/>';
      x+=seg;
      key+='<span class="pv-key"'+tip+'><i style="background:'+BANDC[b]+'"></i>'+b+' <b>'+n[b]+'</b></span>';
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
    var amax=Math.max.apply(null,ax)||1, bw=w/bins, inner='', hits='';
    var scored=all.filter(function(e){return e.score!=null});
    for(var j=0;j<bins;j++){
      var ah=ax[j]/amax*(base-4);
      if(ah>0)inner+='<rect x="'+(j*bw+.6).toFixed(1)+'" y="'+(base-ah).toFixed(1)+'" width="'+(bw-1.2).toFixed(1)+'" height="'+ah.toFixed(1)+'" rx="1.5" fill="'+(solo?'#c3ced9':'#e9ecef')+'"/>';
      // the bar is a few pixels wide, so the thing you can point at is the whole column
      var lo=j*100/bins, hi=(j+1)*100/bins;
      var inBin=scored.filter(function(e){return e.score>=lo&&(e.score<hi||(j===bins-1&&e.score<=100))});
      var yours=(mine||[]).filter(function(e){return e.score!=null&&e.score>=lo&&e.score<hi});
      if(inBin.length)hits+='<rect x="'+(j*bw).toFixed(1)+'" y="0" width="'+bw.toFixed(1)+'" height="'+base+'" fill="transparent"'+
        tipd(tipHead('Scores '+lo+' to '+hi,inBin.length+(inBin.length===1?' name':' names'))+
          '<i>'+Math.round(inBin.length/scored.length*100)+'% of the '+scored.length+' scored names sit in this range</i>'+
          '<i>'+names(inBin.sort(function(a,b){return b.score-a.score}),5)+'</i>'+
          (yours.length?'<i>yours here: <em>'+names(yours,4)+'</em></i>':''))+'/>';
    }
    inner+='<line x1="0" x2="'+w+'" y1="'+base+'" y2="'+base+'" stroke="#dee2e6" stroke-width="1"/>'+hits;
    mine.forEach(function(e){
      if(e.score==null)return;
      var x=e.score/100*w;
      var below=scored.filter(function(o){return o.score<e.score}).length;
      var tip=tipd(tipHead(esc(e.short),e.score.toFixed(1)+' \u00b7 band '+esc(e.band||'?'))+
        '<i>stronger than <em>'+Math.round(below/Math.max(1,scored.length)*100)+'%</em> of the '+scored.length+' scored names</i>'+
        '<i>'+(e.rating_composite?'rated '+esc(e.rating_composite)+' \u00b7 ':'')+
        (e.cet1!=null?'CET1 '+e.cet1.toFixed(1)+'% \u00b7 ':'')+(e.lcr!=null?'LCR '+Math.round(e.lcr)+'%':'')+'</i>'+
        (e.asof?'<i>figures as at '+esc(e.asof)+'</i>':''));
      inner+='<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+(base-13)+'" y2="'+(base+4)+'" stroke="#fff" stroke-width="3.4"/>'+
             '<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+(base-13)+'" y2="'+(base+4)+'" stroke="#fd7e14" stroke-width="2"/>'+
             '<rect x="'+(x-5).toFixed(1)+'" y="'+(base-15)+'" width="10" height="21" fill="transparent"'+tip+'/>';
    });
    inner+='<text x="1" y="'+h+'" class="pv-ax">0</text><text x="'+(w/2)+'" y="'+h+'" text-anchor="middle" class="pv-ax">50</text><text x="'+w+'" y="'+h+'" text-anchor="end" class="pv-ax">100</text>';
    return svg(w,h,inner);
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
    var w=260,h=52,bw=w/present.length,bar=Math.min(bw-3,26),mx=Math.max.apply(null,present.map(function(g){return n[g]})),inner='';
    present.forEach(function(g,i){
      var bh=Math.max(4,n[g]/mx*(h-16));
      var ig=GRADES.indexOf(g);
      var tip=tipd(tipHead(esc(g),n[g]+' of '+tot)+
        '<i>'+(ig<=3?'the top of investment grade':ig<=6?'the strong end of investment grade':ig<=9?'the middle of investment grade':'below investment grade')+
        ' \u00b7 '+Math.round(n[g]/tot*100)+'% of your rated names</i>'+
        (uni[g]?'<i><em>'+uni[g]+'</em> of the '+urated+' rated names covered carry '+esc(g)+'</i>':'')+
        '<i>'+names(who[g])+'</i>');
      inner+='<rect x="'+(i*bw+(bw-bar)/2).toFixed(1)+'" y="'+(h-16-bh).toFixed(1)+'" width="'+bar.toFixed(1)+'" height="'+bh.toFixed(1)+'" rx="2" fill="#143659"/>'+
             '<rect x="'+(i*bw).toFixed(1)+'" y="0" width="'+bw.toFixed(1)+'" height="'+(h-16)+'" fill="transparent"'+tip+'/>'+
             '<text x="'+(i*bw+bw/2).toFixed(1)+'" y="'+h+'" text-anchor="middle" class="pv-ax">'+g+'</text>';
    });
    return svg(w,h,inner);
  }

  function tenorScore(items){
    // the question this answers: are the longest tenors on the weakest names?
    var pts=items.map(function(it){var e=byId[it.id];return e&&e.score!=null?{t:it.tenor,s:e.score,e:e}:null}).filter(Boolean);
    if(!pts.length)return '<div class="muted small">no scored names</div>';
    var w=260,h=52,pad=14;
    var maxT=Math.max.apply(null,pts.map(function(p){return p.t}));
    var X=function(t){return maxT<=0?w/2:8+(t/maxT)*(w-20)};
    var Y=function(s){return (h-pad)-(s/100)*(h-pad-6)};
    var inner='<line x1="0" x2="'+w+'" y1="'+Y(50).toFixed(1)+'" y2="'+Y(50).toFixed(1)+'" stroke="#e9ecef" stroke-width="1"/>';
    var weakest=Math.min.apply(null,pts.map(function(p){return p.s}));
    var longest=Math.max.apply(null,pts.map(function(p){return p.t}));
    pts.forEach(function(p){
      var e=p.e, atOrAbove=pts.filter(function(o){return o.t>=p.t});
      var minAt=Math.min.apply(null,atOrAbove.map(function(o){return o.s}));
      var tip=tipd(tipHead(esc(e.short),e.score.toFixed(1)+' \u00b7 band '+esc(e.band||'?'))+
        '<i>accepted to <em>'+esc(tenorLabel(p.t))+'</em>'+(p.t===longest?' \u2014 your longest':'')+
        (p.s===weakest?' \u00b7 your weakest score':'')+'</i>'+
        '<i>'+(e.rating_composite?'rated '+esc(e.rating_composite)+' \u00b7 ':'')+
        (e.cet1!=null?'CET1 '+e.cet1.toFixed(1)+'% \u00b7 ':'')+(e.lcr!=null?'LCR '+Math.round(e.lcr)+'%':'')+'</i>'+
        '<i>weakest you accept at '+esc(tenorLabel(p.t))+' or longer: '+minAt.toFixed(1)+'</i>');
      inner+='<circle cx="'+X(p.t).toFixed(1)+'" cy="'+Y(p.s).toFixed(1)+'" r="4.5" fill="'+(BANDC[e.band]||'#7d93ad')+'" stroke="#fff" stroke-width="1.5"/>'+
             '<circle cx="'+X(p.t).toFixed(1)+'" cy="'+Y(p.s).toFixed(1)+'" r="10" fill="transparent"'+tip+'/>';
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
    var extra=(b.ratings_all||[]).length-(((e&&e.ratings)||[]).length);
    // pillars come through as [score, weight]
    var sd=(b.score_detail&&b.score_detail.pillars)||null;
    var pill=sd?Object.keys(sd).map(function(k){var v=sd[k]||[];var pc=v[0],wt=v[1];
      var col=pillarColour(pc);
      var tip=tipd(tipHead(esc(k.replace(/_/g,' ')),(pc==null?'not held':pc.toFixed(0)+' of 100'))+
        '<i>worth <em>'+(wt==null?'0':wt)+'%</em> of the score'+(pc==null?' \u2014 re-scaled away, since this bank does not publish it':'')+'</i>'+
        (pc!=null?'<i>'+(pc>=80?'strong':pc>=60?'middling':pc>=40?'weak':'very weak')+' against the method\u2019s thresholds</i>':''));
      return '<div class="md-pill"'+tip+'><span>'+esc(k.replace(/_/g,' '))+'</span>'+
             '<div class="meter meter-sm"><i style="width:'+(pc==null?0:Math.max(0,Math.min(100,pc)))+'%;background:'+col+'"></i></div>'+
             '<b style="color:'+col+'">'+(pc==null?'\u2014':pc.toFixed(0))+'</b><i>w'+(wt==null?'':wt)+'</i></div>'}).join(''):'';
    var ev=(b.events||(e&&e.recent)||[]).slice(0,7).map(evRow).join('')
           ||'<div class="muted small">Nothing recorded in the window.</div>';
    // The same panels the open card uses: a ruled heading on a white box, four of them on a
    // tinted ground. A dialog that looks like the row it came from is one thing to learn, not two.
    return '<div class="md-grid">'+
      sect('Trends',(n?n+' series held':''),
        '<div class="md-trends" id="md-trends">'+charts+'</div>'+
        (n&&Object.keys(pg).length?'<p class="mt-legend"><span class="mt-key"></span>The band is where this bank\u2019s peer group stands today, quartile to quartile, median dashed.</p>':''),
        'md-trend-panel')+
      '<div class="md-col">'+
        sect('Ratings'+mk('rating'),'',ratingCell(e)+ratingPath(b)+
          (extra>0?'<p class="md-foot">'+extra+' further rating'+(extra>1?'s':'')+' by type on the full profile.</p>':''))+
        sect('Score make-up'+mk('pillar'),(e.score==null?'':'score '+e.score.toFixed(0)),
          (pill?'<div class="md-pills">'+pill+'</div>':'<div class="muted small">No public score for this entity.</div>')+
          (b.percentile!=null?'<p class="md-foot">Stronger than <b>'+Math.round(b.percentile)+'%</b> of its peer group'+
            mk('percentile')+' ('+esc(String(b.peer_group||'').replace(/_/g,' '))+').</p>':''))+
      '</div>'+
      sect('Events',(e.news30&&(e.news30.bad+e.news30.warn+e.news30.good)?newsMix(e):''),
        '<div class="cp-news md-news">'+ev+'</div>')+
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
      ((e.market&&e.market.direction!=='none')?'<div class="md-mkt">'+mkt(e.market)+'</div>':'')+
      '<div class="md-act">'+act+'<a class="filter" href="'+ROOT+'banks/'+esc(id)+'.html">Full profile</a>'+
      '<button class="filter" id="md-close" aria-label="Close">Close</button></div></div>'+
      '<div id="md-body"><div class="md-grid">'+
        sect('Trends','','<div class="md-wait">'+[0,1,2,3,4,5].map(function(){return '<div class="md-sk"></div>'}).join('')+'</div>','md-trend-panel')+
        '<div class="md-col">'+sect('Ratings','',sk(4))+sect('Score make-up','',sk(5))+'</div>'+
        sect('Events','',sk(6))+'</div></div>';
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
        '<td class="mono small">'+sovPill(e)+'</td>'+
        '<td class="num">'+(e.score==null?'<span class="na">—</span>':
            // the number and its band already say where the name stands, and the table sorts on it;
            // a bar in every one of 152 rows only adds weight
            scoreNum(e.score,e.band,'sc-1'))+
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


  // ---- an open card ----------------------------------------------------------------------
  // Four panels, one question each, on a tinted ground so the sections are told apart at a
  // glance. No figure is left bare: 14.3% CET1 is strong or thin depending on the company it
  // keeps, so every measure is drawn against the spread of the same measure across the covered
  // universe - middle half shaded, median marked, this bank in orange. That is the idiom the
  // profile trends already use for a peer group, at the size of a card.
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
  // the 30-day mix, on the headline panel's own heading: how much has been said about this bank
  // lately, and in what temper, without making the reader count the lines below
  function newsMix(e){
    var n=e.news30||{}, out=['bad','warn','good'].filter(function(k){return n[k]}).map(function(k){
      return '<span class="dot dot-'+k+'"></span>'+n[k];
    }).join('');
    return (out?out+' in 30 days':'nothing in 30 days')+' \u00b7 90-day window';
  }
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
        '<i>the composite rating on every day it changed, from the register’s own action log</i>'+
        (last?'<i>last move: '+esc(AGN_FULL[last.agency]||last.agency)+' '+
          esc(last.action)+(last.value?' to '+esc(last.value):'')+' on '+esc(last.date)+'</i>':'')+
        '<i>green marks a step up, red a step down; nothing before July 2015 is on the platform</i>')+'>'+
      '<span class="rp-e" style="color:'+gradeColour(a)+'">'+esc(a)+'</span>'+
      '<svg viewBox="0 0 '+w+' '+ht+'" preserveAspectRatio="none" class="rp-svg" aria-hidden="true">'+
        '<path d="'+d+'" fill="none" stroke="#0a2540" stroke-width="2" stroke-opacity=".85" '+
        'vector-effect="non-scaling-stroke" stroke-linejoin="round"/>'+dots+'</svg>'+
      '<span class="rp-e" style="color:'+gradeColour(b)+'">'+esc(b)+'</span>'+
      '<span class="rp-t">'+(bits.join(' · ')||'no change')+'<span class="muted"> since '+
        esc(String(h.start||'').slice(0,4))+'</span></span></div>';
  }
  // ---- the shortlist ----
  // Twenty-four cards carrying the same eight figures in the same eight places is a table that has
  // been taken apart: nothing lines up, so nothing can be compared down a column, and the eye has
  // to find each number again in every card. One row a name, and the columns do the comparing.
  function llTable(cands,w,t){
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
      var mp=(e.market&&e.market.direction!=='none')?mkt(e.market):'';
      var bar=(vs!=null&&vs>0)?'<span class="ll-bar2" style="width:'+Math.max(3,vs/span*100).toFixed(0)+
        '%;background:'+(BANDC[e.band]||'#c9d3de')+'" title="'+vs.toFixed(1)+' points above the weakest name you accept at this tenor"></span>':'';
      return '<tr class="ll-r" data-id="'+esc(e.id)+'" data-tenor="'+t+'" tabindex="0" role="button" aria-label="'+
          esc(e.short)+', open detail" style="--band:'+(BANDC[e.band]||'#c9d3de')+'">'+
        '<td class="ll-rank mono">'+(i+1)+'</td>'+
        '<td class="ll-name"><span class="ll-nm">'+esc(e.short)+typeTag(e)+'</span>'+
          '<span class="ll-co">'+esc(e.name)+' · '+sovPill(e)+'</span></td>'+
        '<td class="ll-sc">'+scoreNum(e.score,e.band,'sc-2')+
          '<span class="ll-track">'+bar+'</span></td>'+
        '<td class="ll-cpc"><b style="color:'+gradeColour(e.rating_composite)+'">'+esc(e.rating_composite||'—')+'</b>'+
          '<span class="ll-ags">'+(e.ratings||[]).map(function(x){return esc(x.letter)}).join('')+'</span></td>'+
        kpi('cet1',e.cet1,1)+kpi('leverage',e.leverage,1)+kpi('lcr',e.lcr,0,'%')+kpi('nsfr',e.nsfr,0,'%')+
        '<td class="ll-mkt">'+mp+'</td>'+
        '<td class="ll-addc"><button class="filter ll-add pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="'+t+'">Add</button></td></tr>';
    }).join('');
    return '<div class="table-wrap"><table class="plain ll-t2"><thead><tr>'+
      '<th></th><th>Name</th><th>Score'+mk('score')+'</th><th>Rating</th>'+
      '<th>CET1</th><th>LEV</th><th>LCR</th><th>NSFR</th><th>Market</th><th></th>'+
      '</tr></thead><tbody>'+rows+'</tbody></table></div>';
  }
  function ratingCell(e){
    var r=(e.ratings||[]);
    if(!r.length)return '<div class="cp-rt-none">No agency rates this entity.</div>';
    var sh={};(e.short_ratings||[]).forEach(function(x){sh[x.letter]=x.value});
    var ix=r.map(function(x){return gradeIndex(x.value)}).filter(function(i){return i>=0}), strip='';
    if(ix.length){
      // the axis is the range the covered universe occupies, not AAA to default, so the notches
      // that separate one bank from another are the ones that get the width
      var st=uni('rating_grade');
      var lo=Math.min(st?Math.floor(st.lo)-1:2,Math.min.apply(null,ix)),
          hi=Math.max(st?Math.ceil(st.hi)-1:12,Math.max.apply(null,ix));
      if(hi-lo<3)hi=lo+3;
      var X=function(i){return Math.max(2,Math.min(98,(i-lo)/(hi-lo)*100))};
      // two agencies at the same grade would be one dot, and the reader would count three where
      // there are four: they stack upwards from the axis instead, so agreement is visible as height
      var n={}, stack=1;
      ix.forEach(function(i){n[i]=(n[i]||0)+1; if(n[i]>stack)stack=n[i]});
      var base=8*Math.min(stack-1,2), axT=5+base, seen={};
      var dots=r.map(function(x){
        var i=gradeIndex(x.value); if(i<0)return '';
        var k=Math.min((seen[i]=(seen[i]||0)+1)-1,2);
        return '<span class="cr-dot" style="left:'+X(i).toFixed(1)+'%;top:'+(2+base-8*k)+'px;background:'+gradeColour(x.value)+'"></span>';
      }).join('');
      var spread=Math.max.apply(null,ix)-Math.min.apply(null,ix);
      var tip=tipd(tipHead('On the scale',e.rating_composite?'composite '+esc(e.rating_composite):'')+
        '<i>'+r.map(function(x){return esc((AGN_FULL[x.agency]||x.agency)+' '+x.value)}).join(' \u00b7 ')+'</i>'+
        '<i>'+(spread?'the agencies differ by <em>'+spread+' notch'+(spread>1?'es':'')+'</em>':'<em>every agency agrees</em>')+
        ', and the orange mark is the median they make</i>'+
        '<i>the axis spans the covered names, '+esc(GRADES[Math.max(0,lo)])+' to '+esc(GRADES[Math.min(16,hi)])+'</i>');
      strip='<div class="cr-scale" style="height:'+(25+base)+'px"'+tip+'>'+
        '<span class="cr-ax" style="top:'+axT+'px"></span>'+
        ((lo<=9&&hi>=10)?'<span class="cr-ig" style="left:'+X(9.5).toFixed(1)+'%;top:'+(axT-4)+'px"></span>':'')+dots+
        (e.rating_grade!=null?'<span class="cr-c" style="left:'+X(e.rating_grade-1).toFixed(1)+
          '%;height:'+(axT+9)+'px"></span>':'')+
        '<span class="cr-e cr-e1">'+esc(GRADES[Math.max(0,lo)])+'</span>'+
        '<span class="cr-e cr-e2">'+esc(GRADES[Math.min(16,hi)])+'</span></div>';
    }
    var rows=r.map(function(x){
      var o=OUTLOOK[String(x.outlook||'').toLowerCase()]||['','lv','no outlook published'];
      return '<div class="cr" title="'+esc((AGN_FULL[x.agency]||x.agency)+' '+x.type+' rating'+
             (x.date?', '+x.date:'')+(x.outlook?' \u00b7 '+x.outlook+' outlook':''))+'">'+
        '<span class="cr-a">'+esc(AGN_FULL[x.agency]||x.agency)+'</span>'+
        '<b class="cr-g" style="color:'+gradeColour(x.value)+'">'+esc(x.value)+'</b>'+
        '<span class="cr-o '+o[1]+'">'+o[0]+'</span>'+
        '<span class="cr-s mono">'+esc(sh[x.letter]||'')+'</span></div>';
    }).join('');
    return '<div class="cr-top"><span class="cr-comp" style="color:'+gradeColour(e.rating_composite)+'">'+
      esc(e.rating_composite||'\u2014')+'</span><span class="small muted">composite of '+r.length+
      ' agenc'+(r.length>1?'ies':'y')+'</span></div>'+strip+'<div class="cr-rows">'+rows+'</div>';
  }


  // a tab says how much is behind it, so a reader knows whether it is worth the click
  function tabCount(id,n){var el=document.getElementById(id); if(el)el.textContent=n?String(n):''}
  function render(){
    var p=load(); var out=document.getElementById('policy-body'); if(!out||!data)return;
    var llBox=document.getElementById('pol-ll'), llHtml='', llN=0;
    TIPS={}; hideTip();                       // the marks are about to be rebuilt
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
                 '<span class="pe-sc">'+scoreNum(e.score,e.band,'sc-1')+'</span>'+
                 '<button class="filter pol-add-ll" data-id="'+esc(e.id)+'" data-tenor="365">Add</button></div>';
        }).join('')+'</div></div>'}
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
        return '<div class="pol-card'+(moved?' pol-card-flag':'')+'" data-id="'+esc(e.id)+'">'+
          '<div class="cp-top">'+
            // The country and its rating are drawn twice and shown once: on the second line with the
            // legal name where there is room for a second line, and up beside the name where there
            // is not, which is a card in a two-column list. A pill is a dozen bytes; a layout that
            // has to choose between the country and a third line of wrapping is not.
            '<div class="cp-id"><a class="cp-nm" href="'+ROOT+'banks/'+esc(e.id)+'.html">'+esc(e.short)+'</a>'+typeTag(e)+
              '<span class="cp-sov">'+sovPill(e)+'</span>'+
              '<div class="cp-sub">'+esc(e.name)+' · '+sovPill(e)+'</div></div>'+
            '<div class="cp-stats">'+
              kv(scoreNum(e.score,e.band),'score','ck-score ck-sep')+
              kv('<span style="color:'+gradeColour(e.rating_composite)+'">'+esc(e.rating_composite||'—')+'</span>','rating')+
            '</div>'+
            tenorPick(it)+
            '<div class="cp-tags">'+(worst_fl?chip(worst_fl[2]||worst_fl[1],worst_fl[0])
              :((e.market&&e.market.direction!=='none')?mkt(e.market):''))+'</div>'+
            '<button class="pol-rm" data-id="'+esc(e.id)+'" title="Remove from policy" aria-label="Remove '+esc(e.short)+'">×</button>'+
          '</div></div>';
      }).join('');
      html+='<div class="pol-summary">'+(n_flag?chip(n_flag+' of '+p.length+' need a look','warn'):chip('All '+p.length+' names unchanged since approval','good'))+' <span class="small muted">Flags compare today with the day you approved each name.</span></div>';
      html+=overview(p.filter(function(it){return byId[it.id]}));
      html+='<div class="pol-list">'+rows+'</div>';
      // like-for-like: names at least as strong as the weakest you already accept at each tenor
      // One tenor at a time, chosen from a row of chips rather than four lists down a page. Each
      // one now stands alone: it shows every covered name that clears the bar at that tenor, not
      // the ones a longer tenor did not already list. A name that qualifies at 24 months qualifies
      // at 12, and reading the 12-month list should not depend on having read the other.
      var tenors=[];p.forEach(function(it){if(tenors.indexOf(it.tenor)<0)tenors.push(it.tenor)});tenors.sort(function(a,b){return b-a});
      var chips='', panes='', union={}, first=null;
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
        // the chip counts every match; the grid draws the 24 strongest of them
        var total=cands.length;
        // the tab badge counts every distinct name any tenor turns up, not just the ones drawn
        cands.forEach(function(e){union[e.id]=1}); cands=cands.slice(0,24);
        if(first==null)first=t;
        var wg=GRADES[Math.floor((w.grade||1)+0.5)-1]||'?';
        chips+='<button class="filter ll-t'+(t===first?' active':'')+'" data-t="'+t+'">'+esc(tenorLabel(t))+
               '<span class="cnt">'+total+'</span></button>';
        panes+='<div class="ll-pane" data-t="'+t+'"'+(t===first?'':' hidden')+'>'+
          '<div class="ll-head">'+(total>cands.length?'<span class="ll-n">the '+cands.length+' strongest of '+total+'</span>':'')+
          '<span class="ll-bar">the weakest you accept at '+esc(tenorLabel(t))+
            '<b class="band mono band-'+esc(w.band||'')+'">'+esc(w.band||'?')+'</b>'+
            '<b style="color:'+gradeColour(wg)+'">'+esc(wg)+'</b>'+
            '<b style="color:'+scoreColour(w.score)+'">'+(w.score!=null?w.score.toFixed(1):'?')+'</b></span></div>'+
          (cands.length?llTable(cands,w,t)
           :'<p class="small muted">No covered name outside your policy matches the standing you accept at this tenor.</p>')+
        '</div>';
      });
      ll=(tenors.length>1?'<div class="ll-tenors filters">'+chips+'</div>':'')+panes;
      llN=Object.keys(union).length;
      llHtml='<p class="panel-lede small muted">Covered names at least as strong as the weakest you already accept at each tenor \u2014 same or better band, ratings and score, and no widening market signal.</p>'+ll;
    }
    out.innerHTML=html;
    if(llBox)llBox.innerHTML=llHtml||'<div class="empty">Approve a name and this fills with the covered names that match the standing you accept.</div>';
    tabCount('tn-policy',p.length); tabCount('tn-ll',llN);
    renderUni();
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
  function add(id,tenor){var p=load();var e=byId[id];if(!e)return;var ex=p.filter(function(x){return x.id===id})[0];
    if(ex){ex.tenor=tenor}else{p.push({id:id,tenor:tenor,added:new Date().toISOString().slice(0,10),base:snapshot(e)})}save(p);render()}
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
      '<div class="wt-head"><div><h3>Your weightings</h3>'+
        '<p class="small muted">These are yours, not ours. Move a slider and every score on this site is '+
        'recomputed from the figures using your weights, on this device, at once. Nothing is sent anywhere.</p></div>'+
        '<button class="filter" id="wt-reset"'+(w.__custom?'':' disabled')+'>Back to the starting point</button></div>'+
      '<div class="wt-grid">'+rows+'</div>'+
      '<div class="wt-foot">'+
        '<p><b>This is not a credit rating.</b> It is arithmetic on figures the banks publish themselves and on '+
        'the ratings their agencies publish, combined the way you have chosen to combine them. It is not issued '+
        'by a registered credit rating agency and it is not a credit rating within the meaning of the UK or EU '+
        'Credit Rating Agency Regulations.</p>'+
        '<p><b>This is not advice.</b> Nothing here is investment advice, a recommendation, or a suggestion that '+
        'you should or should not deal with any counterparty, at any tenor, for any amount. Your counterparty '+
        'policy, your limits and your tenors remain yours, and your adviser’s.</p>'+
        '<p><b>The judgement is yours.</b> How much capital counts for against liquidity, or ratios against the '+
        'agencies, is a policy question with no correct answer. The starting point is one reasonable set of '+
        'weights and is deliberately not called a house view, a model or a recommendation. It carries no more '+
        'authority than any other set, including yours.</p>'+
        '<p class="muted">Figures come from each bank’s own regulatory disclosures and from the ESMA European '+
        'Rating Platform, with their dates shown. They can be wrong, late or missing, and a score computed from '+
        'them can be too. Check anything you rely on against the source, which every figure on this site names.</p>'+
      '</div>';
  }
  function bindWeights(){
    var box=document.getElementById('pol-weights'); if(!box)return;
    box.addEventListener('input',function(ev){
      var s=ev.target.closest('.wt-s'); if(!s)return;
      var w=weights(); delete w.__custom; w[s.dataset.k]=+s.value; saveWeights(w);
      weightPanel(); applyWeights(); render();
    });
    box.addEventListener('click',function(ev){
      if(!ev.target.closest('#wt-reset'))return;
      saveWeights({}); weightPanel(); applyWeights(); render();
    });
  }

  function init(){
    var sel=document.getElementById('pol-name');var dl=document.getElementById('pol-names');
    data.rows.forEach(function(e){byId[e.id]=e;var o=document.createElement('option');o.value=e.short+' — '+e.name;o.dataset.id=e.id;dl.appendChild(o)});
    var ten=document.getElementById('pol-tenor');TENORS.forEach(function(t){var o=document.createElement('option');o.value=t[0];o.textContent=t[1];if(t[0]===365)o.selected=true;ten.appendChild(o)});
    document.getElementById('pol-add').addEventListener('click',function(){var v=sel.value;var id=null;for(var i=0;i<dl.options.length;i++)if(dl.options[i].value===v){id=dl.options[i].dataset.id;break}
      if(!id){var q=v.toLowerCase();data.rows.some(function(e){if(e.short.toLowerCase()===q||e.name.toLowerCase()===q){id=e.id;return true}})}
      if(!id){sel.classList.add('err');return}sel.classList.remove('err');add(id,+ten.value);sel.value=''});
    document.addEventListener('click',function(ev){var b=ev.target.closest('.pol-rm');if(b){var p=load().filter(function(x){return x.id!==b.dataset.id});save(p);render();return}
      var a=ev.target.closest('.pol-add-ll');if(a){add(a.dataset.id,+a.dataset.tenor);var d=document.getElementById('pol-modal');if(d&&d.open)d.close();return}
      // one tenor at a time: the chips swap the pane rather than scroll four lists past you
      var tc=ev.target.closest('.ll-t');
      if(tc){var box=document.getElementById('pol-ll')||document;
        [].forEach.call(box.querySelectorAll('.ll-t'),function(b){b.classList.toggle('active',b===tc)});
        [].forEach.call(box.querySelectorAll('.ll-pane'),function(q){q.hidden=q.dataset.t!==tc.dataset.t});
        return}
      if(ev.target.id==='md-close'){document.getElementById('pol-modal').close();return}
      // a card opens its detail; a link inside it still navigates
      var card=ev.target.closest('.pol-card,.ll-r,.uni-row');
      if(card&&!ev.target.closest('a,button,select,label')){
        var tn=card.dataset.tenor?+card.dataset.tenor:(card.classList.contains('uni-row')?+document.getElementById('uni-tenor').value:0);
        openModal(card.dataset.id,tn);return}
      if(ev.target.id==='pol-clear'){if(confirm('Remove every counterparty from this policy?')){save([]);render()}return}
      if(ev.target.id==='pol-use-shared'){save(window.__shared);window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);render();return}
      if(ev.target.id==='pol-keep-mine'){window.__shared=null;document.getElementById('pol-shared').hidden=true;history.replaceState(null,'',location.pathname);return}
    });
    // choosing a tenor is a policy change, so it is written the moment it is made
    document.addEventListener('change',function(ev){
      var sel=ev.target.closest('.cp-ten select'); if(!sel)return;
      add(sel.dataset.id,+sel.value);
    });
    document.addEventListener('click',function(ev){
      if(!ev.target.closest('#pol-browse'))return;
      var t=document.querySelector('.tab[data-tab="universe"]'); if(t&&!t.classList.contains('active'))t.click();
      var q=document.getElementById('uni-q'); if(q)q.focus({preventScroll:true});
      var box=document.getElementById('browse'); if(box)box.scrollIntoView({behavior:'smooth',block:'start'});
    });
    document.addEventListener('keydown',function(ev){
      if(ev.key!=='Enter'&&ev.key!==' ')return;
      var card=ev.target.closest&&ev.target.closest('.ll-r,.pol-card');
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
