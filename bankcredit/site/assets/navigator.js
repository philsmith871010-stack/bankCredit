// Bank navigator: search, combinable facets, sort, families kept together. State lives in the URL hash.
(function(){
  var list=document.getElementById('nvlist');if(!list)return;
  var rows=[].slice.call(list.querySelectorAll('.nv-row')),q=document.getElementById('nvq'),sort=document.getElementById('nvsort'),count=document.getElementById('nvcount'),empty=document.getElementById('nvempty');
  var KEY='counterparty.watch';function watch(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
  var state={region:'all',type:'all',band:'all',grade:'all',watch:'all',q:'',sort:'family'};
  function readHash(){var h=location.hash.replace('#','');if(!h)return;h.split('&').forEach(function(kv){var p=kv.split('=');if(p[0] in state)state[p[0]]=decodeURIComponent(p[1]||'')})}
  function writeHash(){var parts=[];Object.keys(state).forEach(function(k){var d=(k==='q')?'':(k==='sort'?'family':'all');if(state[k]!==d)parts.push(k+'='+encodeURIComponent(state[k]))});history.replaceState(null,'',parts.length?'#'+parts.join('&'):location.pathname)}
  function matches(r,skip){var d=r.dataset,w=null;
    if(skip!=='region'&&state.region!=='all'&&d.region!==state.region)return false;
    if(skip!=='type'&&state.type!=='all'&&d.type!==state.type)return false;
    if(skip!=='band'&&state.band!=='all'&&d.band!==state.band)return false;
    if(skip!=='grade'&&state.grade!=='all'&&d.grade!==state.grade)return false;
    if(skip!=='watch'&&state.watch==='watch'){w=w||watch();if(w.indexOf(d.id)<0)return false}
    if(state.q){var t=state.q.toLowerCase();if(d.name.indexOf(t)<0&&(r.querySelector('.sub')||{}).textContent.toLowerCase().indexOf(t)<0)return false}
    return true}
  function apply(){var shown=0,vis={};rows.forEach(function(r){var ok=matches(r);r.hidden=!ok;if(ok){shown++;vis[r.dataset.id]=1}});
    // a subsidiary whose parent is filtered out stands on its own
    rows.forEach(function(r){r.classList.toggle('nv-orphan',!!r.dataset.group&&!vis[r.dataset.group])});
    var s=state.sort,sorted=rows.slice();
    if(s==='family')sorted.sort(function(a,b){return +a.dataset.i-+b.dataset.i});
    else if(s==='name')sorted.sort(function(a,b){return a.dataset.name.localeCompare(b.dataset.name)});
    else if(s==='score')sorted.sort(function(a,b){return +b.dataset.score-+a.dataset.score||a.dataset.name.localeCompare(b.dataset.name)});
    else if(s==='rating')sorted.sort(function(a,b){return +a.dataset.g-+b.dataset.g||+b.dataset.score-+a.dataset.score});
    else if(s==='asof')sorted.sort(function(a,b){return (b.dataset.asof||'').localeCompare(a.dataset.asof||'')||a.dataset.name.localeCompare(b.dataset.name)});
    sorted.forEach(function(r){list.appendChild(r)});
    list.classList.toggle('nv-flat',s!=='family');
    count.textContent=shown+' of '+rows.length;empty.hidden=shown>0;
    // facet counts: what each chip would leave, given the other filters
    document.querySelectorAll('.nv-f').forEach(function(b){var k=b.dataset.key,v=b.dataset.val,n=0;
      rows.forEach(function(r){if(!matches(r,k))return;if(v==='all'||(k==='watch'?watch().indexOf(r.dataset.id)>=0:r.dataset[k]===v))n++});
      b.querySelector('.cnt').textContent=n;b.classList.toggle('active',state[k]===v);b.disabled=(n===0&&v!=='all')});
    writeHash()}
  document.addEventListener('click',function(e){var b=e.target.closest('.nv-f');if(b){state[b.dataset.key]=b.dataset.val;apply()}
    var w=e.target.closest('.watch');if(w&&state.watch==='watch')setTimeout(apply,0)});
  q.addEventListener('input',function(){state.q=q.value.trim();apply()});
  sort.addEventListener('change',function(){state.sort=sort.value;apply()});
  readHash();q.value=state.q;sort.value=state.sort;apply();
})();
