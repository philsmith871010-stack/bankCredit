(function(){
  var KEY='counterparty.watch';
  function watch(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
  function setWatch(w){try{localStorage.setItem(KEY,JSON.stringify(w))}catch(e){}}
  function paintWatch(){var w=watch();document.querySelectorAll('.watch,.watch-btn').forEach(function(b){var on=w.indexOf(b.dataset.id)>=0;b.classList.toggle('on',on);var s=b.querySelector('span');if(s)s.textContent=on?'Watching':'Watch'})}
  document.addEventListener('click',function(e){
    var b=e.target.closest('.watch,.watch-btn');if(b){e.preventDefault();var w=watch(),i=w.indexOf(b.dataset.id);if(i>=0)w.splice(i,1);else w.push(b.dataset.id);setWatch(w);paintWatch();applyFilter();return}
    var f=e.target.closest('.filter');if(f){document.querySelectorAll('.filter').forEach(function(x){x.classList.remove('active')});f.classList.add('active');applyFilter();return}
    var t=e.target.closest('.tab');if(t){var card=t.closest('.tabs-card');card.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active')});card.querySelectorAll('.panel').forEach(function(p){p.classList.toggle('active',p.dataset.panel===t.dataset.tab)});t.classList.add('active');history.replaceState(null,'','#'+t.dataset.tab);return}
    var th=e.target.closest('th[data-sort]');if(th){sortBy(th.dataset.sort);return}
    if(e.target.closest('#menuBtn')){document.body.classList.toggle('nav-open')}
  });
  var q=document.getElementById('q');if(q)q.addEventListener('input',applyFilter);
  function applyFilter(){var tb=document.querySelector('#board tbody');if(!tb)return;var region=(document.querySelector('.filter.active')||{}).dataset||{};var term=(q&&q.value||'').toLowerCase();var w=watch();
    tb.querySelectorAll('tr').forEach(function(tr){var ok=true;if(region.region&&region.region!=='all'){ok=region.region==='watch'?w.indexOf(tr.dataset.id)>=0:tr.dataset.region===region.region}
      if(ok&&term)ok=tr.textContent.toLowerCase().indexOf(term)>=0;tr.style.display=ok?'':'none'})}
  var dir={};function sortBy(k){var tb=document.querySelector('#board tbody');if(!tb)return;dir[k]=dir[k]==='asc'?'desc':'asc';var rows=[].slice.call(tb.querySelectorAll('tr'));
    rows.sort(function(a,b){var av,bv;if(k==='name'){av=a.dataset.name;bv=b.dataset.name;return dir[k]==='asc'?av.localeCompare(bv):bv.localeCompare(av)}
      if(k==='score'){av=+a.dataset.score;bv=+b.dataset.score}else if(k==='asof'){av=(a.querySelector('.age')||{}).textContent||'';bv=(b.querySelector('.age')||{}).textContent||'';return dir[k]==='asc'?av.localeCompare(bv):bv.localeCompare(av)}
      else{var ci={cet1:3,leverage:4,lcr:5}[k];av=parseFloat((a.children[ci].textContent||'').replace(/[^0-9.\-]/g,''))||-1;bv=parseFloat((b.children[ci].textContent||'').replace(/[^0-9.\-]/g,''))||-1}
      return dir[k]==='asc'?av-bv:bv-av});rows.forEach(function(r){tb.appendChild(r)})}
  var h=location.hash.replace('#','');if(h){var t=document.querySelector('.tab[data-tab="'+h+'"]');if(t)t.click()}
  paintWatch();
})();

// Events page: type filter
(function(){var f=document.getElementById('event-filters');if(!f)return;f.addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;f.querySelectorAll('button').forEach(function(x){x.classList.toggle('active',x===b)});var t=b.dataset.type;document.querySelectorAll('#events .event').forEach(function(e){e.hidden=!(t==='all'||e.dataset.type===t)})})})();
