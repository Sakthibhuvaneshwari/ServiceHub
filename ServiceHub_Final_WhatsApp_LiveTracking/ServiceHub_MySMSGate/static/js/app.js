const socket=window.io?io():null;
if(socket){
 socket.on("booking_notification",d=>{showNotificationToast("🔔 New booking", "New booking request #"+d.booking_id);});
 socket.on("status_update",d=>{showNotificationToast("📌 Booking update", d.message || ("Booking #"+d.booking_id+" is now "+d.status.replaceAll("_"," ")));});
 socket.on("review_notification",d=>{showNotificationToast("⭐ New review", "You received a "+d.rating+"/5 review.");});
 socket.on("new_notification",d=>{showNotificationToast("🔔 "+d.title,d.message);refreshNotifications();});
 socket.on("location_update",d=>{if(window.updateTrackedLocation) window.updateTrackedLocation(d.lat,d.lng);});
}

function showNotificationToast(title,message){
 const toast=document.createElement('div'); toast.className='live-toast'; toast.innerHTML='<b>'+esc(title)+'</b><span>'+esc(message)+'</span>'; document.body.appendChild(toast); setTimeout(()=>toast.classList.add('show'),20); setTimeout(()=>toast.remove(),4200);
}
async function refreshNotifications(){
 if(!window.USER_ID)return;
 try{const r=await fetch('/api/notifications');const d=await r.json();renderNotifications(d);}catch(e){}
}
function renderNotifications(d){
 const count=document.getElementById('notificationCount'),list=document.getElementById('notificationList');
 if(!count||!list)return;
 count.textContent=d.unread||0; count.classList.toggle('hidden',!(d.unread>0));
 list.innerHTML=d.items.length?d.items.map(n=>`<div class="notification-item ${n.is_read?'read':'unread'}" onclick="openNotification(${n.id})"><b>${esc(n.title)}</b><span>${esc(n.message)}</span><small>${esc(n.created_at)}</small></div>`).join(''):'<p class="empty">No notifications.</p>';
}
function toggleNotifications(){document.getElementById('notificationPanel')?.classList.toggle('hidden');refreshNotifications();}
async function openNotification(id){await fetch('/api/notifications/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});refreshNotifications();}
async function markAllNotificationsRead(){await fetch('/api/notifications/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});refreshNotifications();}
window.toggleNotifications=toggleNotifications;window.markAllNotificationsRead=markAllNotificationsRead;window.openNotification=openNotification;

document.addEventListener("DOMContentLoaded",()=>{
 const tabs=document.querySelectorAll(".service-tab");
 const list=document.getElementById("provider-list");
 if(tabs.length){
   tabs.forEach(t=>t.onclick=()=>{tabs.forEach(x=>x.classList.remove("active"));t.classList.add("active");loadProviders(t.dataset.service);});
   loadProviders("Plumber");
 }
 const pf=document.getElementById("profileForm");
 if(pf) pf.onsubmit=async e=>{e.preventDefault();const r=await fetch("/api/provider/profile",{method:"POST",body:new FormData(pf)});const d=await r.json();alert(d.ok?"Profile saved.":"Unable to save profile.");if(d.ok)location.reload();}
 const wf=document.getElementById("workForm");
 if(wf) wf.onsubmit=async e=>{e.preventDefault();const r=await fetch("/api/provider/work",{method:"POST",body:new FormData(wf)});const d=await r.json();alert(d.ok?"Work added.":d.error);if(d.ok)location.reload();}
});

refreshNotifications();
setInterval(refreshNotifications, 15000);

let customerPosition=null;
async function getCustomerLocation(){if(!navigator.geolocation)return null;return await new Promise(resolve=>navigator.geolocation.getCurrentPosition(p=>resolve({lat:p.coords.latitude,lng:p.coords.longitude}),()=>resolve(null),{enableHighAccuracy:true,timeout:7000,maximumAge:60000}));}
async function loadProviders(service){
 const list=document.getElementById("provider-list"),note=document.getElementById("location-note"); list.innerHTML='<div class="loading">Finding professionals near you...</div>';
 customerPosition=await getCustomerLocation(); note.textContent=customerPosition?'📍 Same-city professionals first, then nearby cities by distance.':'📍 Location unavailable. Same-city professionals are prioritized using your registered address.';
 let url="/providers?service="+encodeURIComponent(service); if(customerPosition)url+=`&lat=${customerPosition.lat}&lng=${customerPosition.lng}`;
 const data=await (await fetch(url)).json();
 if(!data.length){list.innerHTML=`<div class="empty full-empty"><h3>No results found</h3><p>No ${esc(service)} professional is currently available in your city or nearby area.</p></div>`;return;}
 list.innerHTML=data.map(p=>`<article class="provider-card"><div class="provider-top">${p.profile_photo?`<img class="avatar" src="${p.profile_photo}">`:'<div class="avatar placeholder">👤</div>'}<div><h3>${esc(p.name)}</h3><span class="pill">${esc(p.service_type)}</span><p class="muted">${esc(p.specific_work||"Professional service")}</p></div><div class="provider-rating">★ ${p.rating}<small>${p.reviews} reviews</small></div></div><div class="location-rank"><span>${p.same_city?'🏠 Same city':'🌐 Nearby city'}</span><b>${p.distance_km!==null?p.distance_km+' km away':'Distance unavailable'}</b></div><div class="price">₹${Math.round(p.charge)} <small>service charge</small></div>${p.work_images.length?`<div class="portfolio-preview">${p.work_images.slice(0,3).map(w=>`<button class="work-pair" onclick='showPortfolio(${JSON.stringify(p.work_images)})'><div><img src="${w.before}"><span>BEFORE</span></div><div><img src="${w.after}"><span>AFTER</span></div></button>`).join('')}</div><button class="portfolio-link" onclick='showPortfolio(${JSON.stringify(p.work_images)})'>View all before & after work →</button>`:`<div class="no-work">Portfolio not uploaded yet</div>`}<div class="provider-reviews"><div class="reviews-head"><b>⭐ Customer feedback (${p.reviews})</b><button class="portfolio-link" onclick='showProviderReviews(${JSON.stringify(p.review_items)})'>View all</button></div>${p.review_items.length?p.review_items.slice(0,2).map(r=>`<div class="review-mini"><b>${esc(r.customer_name)}</b> <span class="stars">${"★".repeat(r.rating)}${"☆".repeat(5-r.rating)}</span><small>Work: ${esc(r.work_description)} · ${esc(r.created_at)}</small><p>${esc(r.feedback)}</p></div>`).join(""):`<p class="empty">No customer feedback yet.</p>`}</div><div class="provider-foot"><span>📍 ${esc(p.address)}<br>📞 ${esc(p.phone)}</span><div class="card-buttons"><a class="btn small outline" href="tel:${esc(p.phone)}">Call</a><button class="btn accent small" onclick="bookProvider(${p.id})">Book now</button></div></div></article>`).join('');
}
function esc(s){return String(s).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));}
async function bookProvider(id){let lat=customerPosition?.lat||null,lng=customerPosition?.lng||null;const r=await fetch("/api/booking",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({provider_id:id,lat,lng})});const d=await r.json();if(d.ok){alert("Booking successful! Professional has been notified.");location.reload();}else alert(d.error||"Booking failed");}
async function setBookingStatus(id,status){
 const r=await fetch("/api/booking/"+id+"/status",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});
 const d=await r.json();
 if(!d.ok){alert(d.error||"Unable to update booking");return;}
 if(d.whatsapp_url){
   const openWhatsApp = confirm("Booking status updated. Open WhatsApp to send this message to the customer?\n\n" + d.message);
   if(openWhatsApp) window.open(d.whatsapp_url,"_blank");
 }
 location.reload();
}
function shareProviderLocation(){
 navigator.geolocation.getCurrentPosition(async p=>{
 document.getElementById("plat").value=p.coords.latitude;document.getElementById("plng").value=p.coords.longitude;
 document.getElementById("locMsg").textContent="Location captured ✓";
 },()=>alert("Please allow location access."));
}
function reviewBooking(id){
 const modal=document.getElementById("reviewModal");
 if(!modal)return;
 document.getElementById("reviewBookingId").value=id;
 document.getElementById("reviewWork").value="";
 document.getElementById("reviewFeedback").value="";
 document.getElementById("reviewError").textContent="";
 setReviewStars(5);
 modal.classList.remove("hidden");
}
function closeReview(){document.getElementById("reviewModal")?.classList.add("hidden");}
function setReviewStars(n){
 document.getElementById("reviewRating").value=n;
 document.querySelectorAll("#starRating button").forEach((b,i)=>b.classList.toggle("selected",i<n));
}
async function submitReview(event){
 event.preventDefault();
 const id=document.getElementById("reviewBookingId").value;
 const rating=Number(document.getElementById("reviewRating").value);
 const work=document.getElementById("reviewWork").value.trim();
 const feedback=document.getElementById("reviewFeedback").value.trim();
 const error=document.getElementById("reviewError");
 if(!work||!feedback){error.textContent="Please enter the completed work and your feedback.";return;}
 const r=await fetch("/api/review",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({booking_id:id,rating,work_description:work,feedback})});
 const d=await r.json();
 if(!d.ok){error.textContent=d.error||"Unable to submit feedback.";return;}
 alert("Thank you! Your rating and feedback have been saved.");
 closeReview();
 location.reload();
}
function showProviderReviews(items){const m=document.getElementById("providerReviewsModal"),b=document.getElementById("providerReviewsBody");if(!m||!b)return;b.innerHTML=items.length?items.map(r=>`<div class="review"><b>${esc(r.customer_name)}</b><div class="stars">${"★".repeat(r.rating)}${"☆".repeat(5-r.rating)}</div><small>Work: ${esc(r.work_description)} · ${esc(r.created_at)}</small><p>${esc(r.feedback)}</p></div>`).join(""):"<p class=\"empty\">No feedback yet.</p>";m.classList.remove("hidden");}
function closeProviderReviews(){document.getElementById("providerReviewsModal")?.classList.add("hidden");}

function showPortfolio(images){const m=document.getElementById("portfolioModal"),b=document.getElementById("portfolioBody");b.innerHTML=images.map(w=>`<div class="portfolio-large"><div><img src="${w.before}"><b>BEFORE</b></div><div><img src="${w.after}"><b>AFTER</b></div>${w.title?`<p>${esc(w.title)}</p>`:""}</div>`).join("");m.classList.remove("hidden");}
function closePortfolio(){document.getElementById("portfolioModal").classList.add("hidden");}
let map,marker;
function openTrack(id,lat,lng){
 document.getElementById("trackModal").classList.remove("hidden");
 setTimeout(()=>{map=L.map("map").setView([lat||11, lng||78],13);L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(map);if(lat&&lng)marker=L.marker([lat,lng]).addTo(map);},100);
}
function closeTrack(){document.getElementById("trackModal").classList.add("hidden");if(map){map.remove();map=null;}}
window.updateTrackedLocation=(lat,lng)=>{if(marker)marker.setLatLng([lat,lng]);else if(map)marker=L.marker([lat,lng]).addTo(map);if(map)map.panTo([lat,lng]);};



async function askBot(text){
 const box=document.getElementById('botMessages'); if(!box)return;
 box.insertAdjacentHTML('beforeend',`<div class="bot-msg user"><b>You</b><span>${esc(text)}</span></div>`);
 box.scrollTop=box.scrollHeight;
 try{const r=await fetch('/api/chatbot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});const d=await r.json();box.insertAdjacentHTML('beforeend',`<div class="bot-msg bot"><b>Assistant</b><span>${esc(d.reply||'Sorry, I could not answer that.')}</span></div>`);box.scrollTop=box.scrollHeight;}catch(e){box.insertAdjacentHTML('beforeend','<div class="bot-msg bot"><b>Assistant</b><span>Unable to connect. Please try again.</span></div>');}
}
function sendBot(e){e.preventDefault();const input=document.getElementById('botInput');if(!input||!input.value.trim())return;const text=input.value.trim();input.value='';askBot(text);}
window.askBot=askBot;window.sendBot=sendBot;


/* ServiceHub WhatsApp + TRUE LIVE GPS */
function serviceHubWhatsApp(phone, name) {
  let n=String(phone||"").replace(/\D/g,"");
  if(n.length===10)n="91"+n;
  if(!n){alert("WhatsApp number is not available.");return;}
  window.open("https://wa.me/"+n+"?text="+encodeURIComponent(
    "Hello "+(name||"")+", I found your profile on ServiceHub. I would like to discuss my service requirement."
  ),"_blank");
}
let serviceHubWatchId=null;
function startServiceHubLiveTracking(bookingId) {
  if(!navigator.geolocation){alert("GPS is not supported by this browser.");return;}
  stopServiceHubLiveTracking();
  const send=p=>fetch("/api/booking/"+bookingId+"/location",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({lat:p.coords.latitude,lng:p.coords.longitude,accuracy:p.coords.accuracy})
  }).catch(console.error);
  serviceHubWatchId=navigator.geolocation.watchPosition(send,
    e=>console.error("GPS error",e),
    {enableHighAccuracy:true,maximumAge:3000,timeout:15000});
  const el=document.getElementById("liveTrackingStatus"); if(el)el.textContent="🟢 Live location sharing is ON";
}
function stopServiceHubLiveTracking(){
  if(serviceHubWatchId!==null){navigator.geolocation.clearWatch(serviceHubWatchId);serviceHubWatchId=null;}
  const el=document.getElementById("liveTrackingStatus"); if(el)el.textContent="⚪ Live location sharing is OFF";
}
