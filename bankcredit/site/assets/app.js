(function(){
  var KEY='counterparty.watch';
  function watch(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return[]}}
  function setWatch(w){try{localStorage.setItem(KEY,JSON.stringify(w))}catch(e){}}
  function paintWatch(){var w=watch();document.querySelectorAll('.watch,.watch-btn').forEach(function(b){var on=w.indexOf(b.dataset.id)>=0;b.classList.toggle('on',on);var s=b.querySelector('span');if(s)s.textContent=on?'Watching':'Watch'})}
  document.addEventListener('click',function(e){
    var b=e.target.closest('.watch,.watch-btn');if(b){e.preventDefault();var w=watch(),i=w.indexOf(b.dataset.id);if(i>=0)w.splice(i,1);else w.push(b.dataset.id);setWatch(w);paintWatch();applyFilter();return}
    var f=e.target.closest('.filter');if(f){document.querySelectorAll('.filter').forEach(function(x){x.classList.remove('active')});f.classList.add('active');applyFilter();return}
    var t=e.target.closest('.tab');var card=t&&t.closest('.tabs-card');if(t&&card){card.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active')});card.querySelectorAll('.panel').forEach(function(p){p.classList.toggle('active',p.dataset.panel===t.dataset.tab)});t.classList.add('active');history.replaceState(null,'','#'+t.dataset.tab);return}
    var th=e.target.closest('th[data-sort]');if(th){sortBy(th.dataset.sort,th.cellIndex);return}
    if(e.target.closest('#menuBtn')){document.body.classList.toggle('nav-open')}
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
  var h=location.hash.replace('#','');if(h){var t=document.querySelector('.tab[data-tab="'+h+'"]');if(t)t.click()}
  paintWatch();
})();

// Events page: type filter
(function(){var f=document.getElementById('event-filters');if(!f)return;var q=document.getElementById('evq');
  function apply(){var a=(f.querySelector('.filter.active')||{}).dataset||{},t=(q&&q.value||'').trim().toLowerCase();
    document.querySelectorAll('#events .event').forEach(function(e){e.hidden=!((!a.type||a.type==='all'||e.dataset.type===a.type)&&(!t||e.textContent.toLowerCase().indexOf(t)>=0))});
    document.querySelectorAll('#events .ev-day').forEach(function(h){var n=h.nextElementSibling,any=false;while(n&&!n.classList.contains('ev-day')){if(!n.hidden)any=true;n=n.nextElementSibling}h.hidden=!any})}
  f.addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;f.querySelectorAll('button').forEach(function(x){x.classList.toggle('active',x===b)});apply()});
  if(q)q.addEventListener('input',apply);})();

// Profile trends: a small multiple opens its full-size chart in a dialog
(function(){var d=document.createElement('dialog');d.className='chart-dialog';d.innerHTML='<div class="cd-head"><div><h3></h3><div class="small muted"></div></div><button class="cd-close" aria-label="Close">×</button></div><div class="cd-body"></div>';
  document.addEventListener('click',function(e){var b=e.target.closest('.sm');if(b){if(!d.isConnected)document.body.appendChild(d);var t=b.querySelector('template');d.querySelector('h3').textContent=b.dataset.title||'';d.querySelector('.cd-head .small').textContent=b.dataset.sub||'';d.querySelector('.cd-body').innerHTML=t?t.innerHTML:'';d.showModal();return}
    if(e.target.closest('.cd-close')||(e.target===d))d.close()});
})();

// Ratings grid: band tiles, grade bars and the "moved" chip filter the rows alongside region and search
(function(){var tb=document.querySelector('table.rgrid tbody');if(!tb)return;var grade=null,band=null,cnt=document.getElementById('rg-count'),clear=document.querySelector('.gclear');
  function apply(){var region=(document.querySelector('.filter.active[data-region]')||{}).dataset||{},term=((document.getElementById('q')||{}).value||'').toLowerCase(),w=[];try{w=JSON.parse(localStorage.getItem('counterparty.watch')||'[]')}catch(e){}
    var n=0;tb.querySelectorAll('tr').forEach(function(tr){var d=tr.dataset,ok=true;
      if(region.region&&region.region!=='all'){ok=region.region==='watch'?w.indexOf(d.id)>=0:region.region==='moved'?d.moved==='1':d.region===region.region}
      if(ok&&grade)ok=d.grade===grade;if(ok&&band)ok=d.band===band;if(ok&&term)ok=tr.textContent.toLowerCase().indexOf(term)>=0;tr.style.display=ok?'':'none';if(ok)n++});
    if(cnt)cnt.textContent=n+' shown';document.querySelectorAll('.gfilter').forEach(function(b){b.classList.toggle('active',b.dataset.grade===grade)});document.querySelectorAll('.bfilter').forEach(function(b){b.classList.toggle('active',b.dataset.band===band)});if(clear)clear.hidden=!grade&&!band}
  document.addEventListener('click',function(e){var g=e.target.closest('.gfilter');if(g){grade=grade===g.dataset.grade?null:g.dataset.grade;band=null;apply();return}var b=e.target.closest('.bfilter');if(b){band=band===b.dataset.band?null:b.dataset.band;grade=null;apply();return}if(e.target.closest('.gclear')){grade=null;band=null;apply();return}if(e.target.closest('.filter[data-region]'))setTimeout(apply,0)});
  var q=document.getElementById('q');if(q)q.addEventListener('input',apply);apply()})();
