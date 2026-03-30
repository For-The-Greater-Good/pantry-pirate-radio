/* ppr-beacon analytics — ~1KB client-side tracker */
(function(){
  var e=document.querySelector('meta[name="beacon-analytics"]');
  var endpoint=e?e.content:'';
  if(!endpoint)return;
  function send(ev,data){
    var p=JSON.stringify({e:ev,p:location.pathname,t:Date.now(),r:document.referrer,d:data||{}});
    if(navigator.sendBeacon){navigator.sendBeacon(endpoint,p)}
  }
  if(!/bot|crawl|spider/i.test(navigator.userAgent)){send('pv')}
  document.addEventListener('click',function(ev){
    var a=ev.target.closest('a[data-track]');
    if(a)send('click',{action:a.dataset.track,href:a.href});
  });
})();
