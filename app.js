const CFG=window.DRIVEBOX_CONFIG, P=window.DRIVEBOX_PRODUCTS, I=window.DRIVEBOX_I18N;
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
function getLang(){const l=localStorage.getItem('drivebox_lang')||CFG.defaultLanguage;return ['ka','ru','en'].includes(l)?l:'ka'}
function syncDocumentLang(){document.documentElement.lang=getLang()}
function setLang(l){if(!I[l])return;localStorage.setItem('drivebox_lang',l);renderLanguage()}
function renderLanguage(){syncDocumentLang();renderHeader();renderFooter();renderHome();renderProduct();renderCheckout();initLegal();$$('[data-t]').forEach(el=>el.textContent=t(el.dataset.t).replace('{hour}',CFG.shipping.sameDayCutoffHour));const title=document.body.dataset.pageTitle;if(title)document.title=t(title)+' — '+CFG.brand;const offer=$('#store-offer');if(offer)offer.innerHTML=promotionBlock();const note=$('#payment-note');if(note)note.textContent=t(CFG.testMode?'paymentNote':'payNote');const message=$('#checkout-message');if(message?.dataset.t)message.textContent=t(message.dataset.t);document.dispatchEvent(new Event('drivebox:language'));}
window.addEventListener('storage',e=>{if(e.key==='drivebox_lang')renderLanguage();if(e.key==='drivebox_cart'){updateCartBadge();syncHomeCart();renderCheckout();}});
function t(k){return I[getLang()]?.[k]||I.ka[k]||k}
function formatGEL(v){return `${Number(v).toFixed(v%1?2:0)} ₾`}
function getCart(){try{const c=JSON.parse(localStorage.getItem('drivebox_cart')||'[]');return Array.isArray(c)?c.filter(row=>P.some(p=>p.id===row.id)&&Number.isInteger(row.qty)&&row.qty>0):[]}catch{return[]}}
function saveCart(c){localStorage.setItem('drivebox_cart',JSON.stringify(c));updateCartBadge();syncHomeCart()}
function addToCart(id,qty=1){let c=getCart();const row=c.find(x=>x.id===id);if(row)row.qty=Math.min(20,row.qty+qty);else c.push({id,qty:Math.min(20,qty)});saveCart(c);showToast(t('added'))}
function removeFromCart(id){saveCart(getCart().filter(x=>x.id!==id));renderCheckout()}
function cartCount(){return getCart().reduce((a,b)=>a+b.qty,0)}
function updateCartBadge(){$$('.cart-count').forEach(el=>el.textContent=cartCount())}
function showToast(msg){let n=document.createElement('div');n.textContent=msg;n.style.cssText='position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#fff;color:#111;padding:11px 16px;border-radius:999px;font-weight:800;z-index:100;box-shadow:0 12px 40px #0008';document.body.appendChild(n);setTimeout(()=>n.remove(),1400)}
function productUrl(p){return `products/${p.slug}.html`}
function renderHeader(){const root=$('#site-header');if(!root)return;root.innerHTML=`${CFG.testMode?`<div class="topbar">${t('test')}</div>`:''}<header class="header"><div class="container nav"><a class="brand" href="${root.dataset.depth||''}index.html">DRIVE<span>BOX</span></a><nav class="navlinks"><a href="${root.dataset.depth||''}index.html#products">${t('shop')}</a><a href="${root.dataset.depth||''}legal/delivery.html">${t('delivery')}</a><a href="${root.dataset.depth||''}legal/returns.html">${t('returns')}</a><a href="${root.dataset.depth||''}legal/contact.html">${t('contact')}</a></nav><div class="nav-actions"><select class="lang" aria-label="${t('language')}"><option value="ka">KA</option><option value="ru">RU</option><option value="en">EN</option></select><a class="cart-btn" href="${root.dataset.depth||''}checkout.html">${t('cart')} <span class="cart-count">0</span></a></div></div></header>`;const sel=$('.lang',root);sel.value=getLang();sel.onchange=e=>setLang(e.target.value);updateCartBadge()}
function renderFooter(){const root=$('#site-footer');if(!root)return;const d=root.dataset.depth||'';root.innerHTML=`<footer class="footer"><div class="container footer-grid"><div><div class="brand">DRIVE<span>BOX</span></div><p>${t('footer')}</p></div><div><b>${t('shop')}</b><a href="${d}index.html#products">${t('shop')}</a><a href="${d}legal/delivery.html">${t('delivery')}</a><a href="${d}legal/returns.html">${t('returns')}</a></div><div><b>${t('legalSeller')}</b><a href="${d}legal/terms.html">${t('terms')}</a><a href="${d}legal/privacy.html">${t('privacy')}</a><a href="${d}legal/contact.html">${t('contact')}</a></div></div></footer>`}
function detail(p){return window.DRIVEBOX_PRODUCT_DETAILS?.[p.id]||{}}
function localized(value){return typeof value==='string'?value:value?.[getLang()]||''}
function unitCents(p){return Math.round(Math.round(p.price*100)*(100-(CFG.promotion?.enabled?CFG.promotion.discountPercent:0))/100)}
function priceBlock(p){const current=unitCents(p)/100;return `<span class="price">${formatGEL(current)}</span>${current<p.price?`<span class="compare">${formatGEL(p.price)}</span><span class="saving">${t('save')} ${formatGEL(p.price-current)}</span>`:''}`}
function promotionBlock(){return CFG.promotion?.enabled?`<div class="promotion"><b>${t('offer')}</b><span>${t('offerDetail')}</span></div>`:''}
function galleryImages(p){return p.gallery?.length?p.gallery:[p.image]}
function assetUrl(src){return /^(https?:|data:|\/)/.test(src)?src:($('#site-header')?.dataset.depth||'')+src}
function renderHome(){
  const root=$('#products-grid');if(!root)return;const l=getLang();
  // Provisional merchandising order, not a measured search-volume ranking.
  const priority=['dashcam','carplay','charger-holder','compressor','vacuum','jumpstarter','headlight-kit'];
  const ranked=[...P].sort((a,b)=>(priority.includes(a.id)?priority.indexOf(a.id):priority.length)-(priority.includes(b.id)?priority.indexOf(b.id):priority.length));
  root.innerHTML=ranked.map(p=>`<article class="product-card"><a class="product-card-link" href="${productUrl(p)}"><div class="product-image"><img src="${assetUrl(galleryImages(p)[0])}" alt="${p.name[l]}" loading="lazy" referrerpolicy="no-referrer">${CFG.promotion?.enabled?'<span class="sale-tag">−15%</span>':''}</div><div class="product-body"><span class="pill">${localized(detail(p).brand)||p.supplier}</span><h3>${p.name[l]}</h3><p>${p.tagline[l]}</p>${priceBlock(p)}</div></a><div class="product-card-actions" data-cart-product="${p.id}"></div></article>`).join('');
  syncHomeCart();
}
function syncHomeCart(){
  const cart=getCart();
  const labels={ru:['В корзине','Уменьшить количество','Увеличить количество'],en:['In cart','Decrease quantity','Increase quantity'],ka:['კალათაში','რაოდენობის შემცირება','რაოდენობის გაზრდა']}[getLang()];
  $$('[data-cart-product]').forEach(host=>{
    const id=host.dataset.cartProduct,qty=cart.find(row=>row.id===id)?.qty||0;
    const active=qty>0;
    if(host.dataset.active!==String(active)){
      const hadFocus=host.contains(document.activeElement);
      host.dataset.active=String(active);
      host.innerHTML=active?`<div class="home-cart-stepper"><button type="button" data-delta="-1" aria-label="${labels[1]}">−</button><span class="home-cart-count" role="status" aria-live="polite"><small>${labels[0]}</small><strong></strong></span><button type="button" data-delta="1" aria-label="${labels[2]}">+</button></div>`:`<button type="button" class="btn primary" data-add-product="${id}">${t('add')}</button>`;
      host.querySelector('[data-add-product]')?.addEventListener('click',()=>addToCart(id));
      host.querySelectorAll('[data-delta]').forEach(button=>button.onclick=()=>{
        const next=getCart(),row=next.find(item=>item.id===id);
        if(!row)return;
        row.qty=Math.max(0,Math.min(20,row.qty+Number(button.dataset.delta)));
        saveCart(next.filter(item=>item.qty>0));
      });
      if(hadFocus)host.querySelector('button').focus({preventScroll:true});
    }
    if(active){host.querySelector('strong').textContent=qty;host.querySelector('[data-delta="1"]').disabled=qty>=20;}
  });
}
function renderProduct(){
  const root=$('#product-root');if(!root)return;
  const p=P.find(x=>x.id===document.body.dataset.product);if(!p)return;
  const l=getLang(),d=detail(p),photos=galleryImages(p);document.title=`${p.name[l]} — ${CFG.brand}`;
  root.innerHTML=`<section class="product-hero"><div class="container product-layout"><div class="product-gallery" aria-label="${t('gallery')}"><button class="product-main-image" id="gallery-open" aria-label="${t('zoom')}"><img id="gallery-main" src="${assetUrl(photos[0])}" alt="${p.name[l]}" referrerpolicy="no-referrer"><span class="zoom-hint">＋ ${t('zoom')}</span></button><div class="gallery-thumbs">${photos.map((src,i)=>`<button type="button" data-photo="${i}" aria-label="${t('photo')} ${i+1}" aria-pressed="${i===0}"><img src="${assetUrl(src)}" alt="${p.name[l]} — ${t('photo')} ${i+1}" loading="lazy" referrerpolicy="no-referrer"></button>`).join('')}</div>${d.galleryNote?`<p class="gallery-note">${localized(d.galleryNote)}</p>`:''}</div><div class="product-info"><div class="kicker">${localized(d.brand)}</div><h1>${p.name[l]}</h1><p class="lead">${p.tagline[l]}</p><div class="buybox"><div>${priceBlock(p)}</div>${promotionBlock()}<div class="cta-row"><button class="btn primary" id="add-product">${t('add')}</button><button class="btn secondary" id="buy-product" type="button">${t('buy')}</button></div><div class="micro"><div><span class="check">✓</span>${t('productSupport')}</div><div><span class="check">✓</span>${t('productWarranty')}</div></div></div></div></div></section><section class="section product-story"><div class="container"><h2>${t('aboutProduct')}</h2><p class="product-description">${localized(d.description)}</p><div class="bullet-list">${p.bullets[l].map(x=>`<div class="bullet">✓ ${x}</div>`).join('')}</div><div class="product-detail-grid"><div><h2>${t('specifications')}</h2><dl class="spec-list"><div><dt>${t('brandLabel')}</dt><dd>${localized(d.brand)}</dd></div><div><dt>${t('modelLabel')}</dt><dd>${localized(d.model)}</dd></div>${(d.specs||[]).map(([key,val])=>`<div><dt>${t(key)}</dt><dd>${localized(val)}</dd></div>`).join('')}</dl>${d.source?`<a class="source-link" href="${d.source}" target="_blank" rel="noopener noreferrer">${t('source')} ↗</a>`:''}</div><aside class="compatibility-card"><h3>${t('compatibility')}</h3><p>${localized(d.compatibility)}</p></aside></div></div></section><section class="section"><div class="container faq"><h2>${t('faq')}</h2>${[1,2,3].map(n=>`<details><summary>${t('faq'+n+'q')}</summary><p>${t('faq'+n+'a')}</p></details>`).join('')}</div></section><dialog id="photo-dialog" aria-label="${t('gallery')}"><div class="viewer-toolbar"><span id="viewer-count" aria-live="polite"></span><button class="btn secondary" id="viewer-close">${t('close')} ×</button></div><div class="viewer-stage"><button class="viewer-arrow" id="viewer-prev" aria-label="${t('previous')}">‹</button><img id="viewer-image" alt="${p.name[l]}"><button class="viewer-arrow" id="viewer-next" aria-label="${t('next')}">›</button></div></dialog>`;
  $('#add-product').onclick=()=>addToCart(p.id);
  $('#buy-product').onclick=()=>{addToCart(p.id);location.href='../checkout.html'};
  let selected=0;const dialog=$('#photo-dialog');
  function selectPhoto(i){selected=(i+photos.length)%photos.length;$('#gallery-main').src=assetUrl(photos[selected]);$('#viewer-image').src=assetUrl(photos[selected]);$('#viewer-count').textContent=`${selected+1} / ${photos.length}`;$$('[data-photo]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.photo)===selected)))}
  $$('[data-photo]').forEach(b=>b.onclick=()=>selectPhoto(Number(b.dataset.photo)));
  $('#gallery-open').onclick=()=>{selectPhoto(selected);dialog.showModal()};$('#viewer-close').onclick=()=>dialog.close();
  $('#viewer-prev').onclick=()=>selectPhoto(selected-1);$('#viewer-next').onclick=()=>selectPhoto(selected+1);
  $('#viewer-prev').hidden=$('#viewer-next').hidden=photos.length<2;
  dialog.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'){e.preventDefault();selectPhoto(selected-1)}if(e.key==='ArrowRight'){e.preventDefault();selectPhoto(selected+1)}});
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
}
function shippingCost(subtotal,city,method){if(CFG.promotion?.enabled&&CFG.promotion.freeShipping)return 0;if(subtotal>=CFG.shipping.freeFrom)return 0;if((city||'').toLowerCase().includes('tbil')||(city||'').includes('თბილის')||(city||'').toLowerCase().includes('тбил'))return method==='same'?CFG.shipping.tbilisiSameDay:CFG.shipping.tbilisiNextDay;return CFG.shipping.regions}
function renderCheckout(){const itemsRoot=$('#cart-items');if(!itemsRoot)return;const c=getCart(),l=getLang();$('#checkout-submit').disabled=!c.length;if(!c.length){itemsRoot.innerHTML=`<p>${t('empty')}</p>`;$('#checkout-submit').disabled=true;updateTotals();return}itemsRoot.innerHTML=c.map(row=>{const p=P.find(x=>x.id===row.id);return `<div class="cart-line"><img src="${assetUrl(galleryImages(p)[0])}" alt="${p.name[l]}" referrerpolicy="no-referrer"><div><b>${p.name[l]}</b><div class="muted">${row.qty} × ${formatGEL(unitCents(p)/100)}</div></div><div><b>${formatGEL(unitCents(p)*row.qty/100)}</b><br><button class="btn secondary" style="padding:5px 9px;margin-top:6px" aria-label="${t('remove')}" onclick="removeFromCart('${p.id}')">×</button></div></div>`}).join('');updateTotals()}
function updateTotals(){
  const c=getCart();let baseCents=0,totalCents=0;
  c.forEach(row=>{const p=P.find(x=>x.id===row.id);baseCents+=Math.round(p.price*100)*row.qty;totalCents+=unitCents(p)*row.qty});
  const subtotal=baseCents/100,discount=(baseCents-totalCents)/100;
  const city=$('#city')?.value||'Tbilisi',method=$('#delivery-method')?.value||'same';
  const ship=c.length?shippingCost(totalCents/100,city,method):0,total=(totalCents+Math.round(ship*100))/100;
  if($('#subtotal-val'))$('#subtotal-val').textContent=formatGEL(subtotal);
  if($('#discount-val'))$('#discount-val').textContent='−'+formatGEL(discount);
  if($('#shipping-val'))$('#shipping-val').textContent=ship?formatGEL(ship):t('free');
  if($('#total-val'))$('#total-val').textContent=formatGEL(total);
  return {subtotal,discount,ship,total};
}
function initCheckout(){ /* Initialized by commerce.js after server settings load. */ }
function initLegal(){const root=$('#legal-seller');if(root){root.replaceChildren();Object.values({name:CFG.seller.legalName,id:CFG.seller.idNumber,phone:CFG.seller.phone,email:CFG.seller.email}).filter(v=>v&&!/REPLACE|XXX/.test(v)).forEach(v=>{const line=document.createElement('div');line.textContent=v;root.appendChild(line)});}}
document.addEventListener('DOMContentLoaded',()=>{renderLanguage();initCheckout();});
