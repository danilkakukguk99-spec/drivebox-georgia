import {createHash, randomBytes, timingSafeEqual} from 'node:crypto';
import catalog from '../catalog.json' with {type:'json'};
export class Problem extends Error {constructor(code,status=400){super(code);this.code=code;this.status=status;}}
export const hash=v=>createHash('sha256').update(String(v)).digest('hex');
export const now=()=>Date.now()/1000;
export const safeEqual=(a,b)=>{const x=Buffer.from(String(a)),y=Buffer.from(String(b));return x.length===y.length&&timingSafeEqual(x,y)};
export const clean=(v,min,max,code='invalid_fields')=>{if(typeof v!=='string'||v.trim().length<min||v.trim().length>max)throw new Problem(code);return v.trim()};
export const cents=v=>{if(typeof v!=='string'||!/^\d+(\.\d{1,2})?$/.test(v))throw new Problem('payment_amount_mismatch',409);const [a,b='']=v.split('.');const n=Number(a)*100+Number(b.padEnd(2,'0'));if(!Number.isSafeInteger(n))throw new Problem('payment_amount_mismatch',409);return n;};
export function settings(env=process.env){
 const production=env.APP_ENV==='production',paypalEnv=env.PAYPAL_ENV||'sandbox';
 if(!['sandbox','live'].includes(paypalEnv))throw new Problem('store_not_ready',503);
 const origin=(env.PUBLIC_URL||env.URL||'http://localhost:8000').replace(/\/$/,'');
 const rate=Number(env.GEL_PER_USD||'2.70'),discount=Number(env.DISCOUNT_PERCENT||15);
 if(!(rate>0)||!Number.isInteger(discount)||discount<0||discount>100)throw new Problem('store_not_ready',503);
 const s={production,origin,paypalEnv,rate,discount,free:env.FREE_SHIPPING!=='false',cod:env.ALLOW_COD==='true',clientId:env.PAYPAL_CLIENT_ID||'',secret:env.PAYPAL_CLIENT_SECRET||'',webhook:env.PAYPAL_WEBHOOK_ID||'',admin:env.ADMIN_PASSWORD||'',seller:Object.fromEntries(['name','id','address','phone','email','whatsapp'].map(k=>[k,env['SELLER_'+k.toUpperCase()]||''])),env};
 s.paypalEnabled=!!(s.clientId&&s.secret&&(paypalEnv==='sandbox'||production&&s.webhook));return s;
}
export function issues(s){const a=[];if(s.admin.length<16)a.push('ADMIN_PASSWORD');for(const k of ['name','id','address','phone','email'])if(!s.seller[k])a.push('SELLER_'+k.toUpperCase());if(!s.cod&&!s.paypalEnabled)a.push('Payment method');if(s.production){if(!s.origin.startsWith('https://'))a.push('PUBLIC_URL');if(s.paypalEnabled&&s.paypalEnv!=='live')a.push('PAYPAL_ENV');for(const k of ['SMTP_HOST','SMTP_FROM'])if(!s.env[k])a.push(k);for(const k of ['LEGAL_CONFIRMED','FULFILLMENT_CONFIRMED'])if(s.env[k]!=='true')a.push(k);}return a;}
export const view=r=>({...r.body,id:r.id,createdAt:Number(r.created),status:r.status,paymentStatus:r.payment_status,paymentMethod:r.payment,usd:r.usd,paypalOrderId:r.paypal_id,paymentPhase:r.payment_phase,testMode:r.body.testMode});
export async function one(c,sql,args=[]){return (await c.query(sql,args)).rows[0]}
export async function transaction(pool,fn){const c=await pool.connect();try{await c.query('BEGIN');const result=await fn(c);await c.query('COMMIT');return result}catch(e){await c.query('ROLLBACK');throw e}finally{c.release()}}
export async function order(c,id,token,lock=false){const r=await one(c,'SELECT * FROM orders WHERE id=$1'+(lock?' FOR UPDATE':''),[id]);if(!r||(token!==undefined&&!safeEqual(r.token,hash(token))))throw new Problem('not_found',404);return r;}
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
export async function quote(p,c,s){
 const city=clean(p.city,2,100,'invalid_city');if(!Array.isArray(p.cart)||!p.cart.length||p.cart.length>30)throw new Problem('invalid_cart');
 const seen=new Set(),items=[];let base=0,total=0;
 for(const row of p.cart){const item=catalog.find(x=>x.id===row?.id);if(!item?.active||!Number.isInteger(row.qty)||row.qty<1||row.qty>20||seen.has(row.id))throw new Problem('invalid_cart');seen.add(row.id);const stock=await one(c,'SELECT stock FROM inventory WHERE id=$1',[row.id]);if(stock&&stock.stock<row.qty)throw new Problem('out_of_stock',409);const unit=Math.round(item.priceCents*(100-s.discount)/100);items.push({id:item.id,name:item.name,qty:row.qty,unitCents:unit});base+=item.priceCents*row.qty;total+=unit*row.qty;}
 const tbilisi=['tbilisi','тбилиси','თბილისი'].includes(city.toLowerCase()),method=p.deliveryMethod||'next';if(!['same','next'].includes(method))throw new Problem('invalid_delivery');const hour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Tbilisi',hour:'2-digit',hourCycle:'h23'}).format(new Date()));if(method==='same'&&(!tbilisi||hour>=15))throw new Problem('same_day_unavailable',409);
 const shipping=s.free||total>=25000?0:tbilisi?(method==='same'?900:700):1200;return {items,subtotalCents:base,discountCents:base-total,shippingCents:shipping,totalCents:total+shipping,currency:'GEL',city,deliveryMethod:method};
}
export async function enqueue(c,r,s,subject){const o=view(r),url=s.origin+'/order.html#'+r.id+'/'+hash('receipt:'+r.idem);const body=[subject,...o.items.map(x=>x.name[o.language]+' × '+x.qty),(o.totalCents/100).toFixed(2)+' GEL',o.city+', '+o.address,url].join('\n');for(const email of new Set([s.seller.email,o.email].filter(Boolean)))await c.query('INSERT INTO outbox(order_id,subject,recipient,body) VALUES($1,$2,$3,$4)',[r.id,subject,email,body]);}
export async function createOrder(pool,p,idem,s){
 if(s.production&&issues(s).length)throw new Problem('store_not_ready',503);if(!/^[a-zA-Z0-9-]{16,80}$/.test(idem))throw new Problem('invalid_request_id');if(p.consent!==true)throw new Problem('consent_required');const fingerprint=hash(JSON.stringify(canonical(p))),token=hash('receipt:'+idem);
 return transaction(pool,async c=>{
 await c.query('SELECT pg_advisory_xact_lock(hashtext($1))',['create:'+idem]);const old=await one(c,'SELECT * FROM orders WHERE idem=$1',[idem]);if(old){if(old.fingerprint!==fingerprint)throw new Problem('request_conflict',409);return {...view(old),token};}
 // Serialize inventory edits with checkout; stock and the order commit together.
 await c.query('SELECT pg_advisory_xact_lock(71843001)');const q=await quote(p,c,s);if(p.expectedTotalCents!==undefined&&p.expectedTotalCents!==q.totalCents)throw new Problem('price_changed',409);
 const name=clean(p.name,2,120,'invalid_name'),phone=clean(p.phone,7,30,'invalid_phone'),address=clean(p.address,5,300,'invalid_address'),email=clean(p.email||'',0,200,'invalid_email'),notes=clean(p.notes||'',0,1000,'invalid_notes');if(!/^\+?[\d ()-]{7,30}$/.test(phone)||phone.replace(/\D/g,'').length<7||phone.replace(/\D/g,'').length>15)throw new Problem('invalid_phone');if(email&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))throw new Problem('invalid_email');
 const payment=p.paymentMethod,online=['card','paypal'].includes(payment);if(!online&&payment!=='cash_on_delivery'||online&&!s.paypalEnabled||payment==='cash_on_delivery'&&!s.cod)throw new Problem('payment_unavailable',503);
 const body={...q,name,phone,address,email,notes,language:['ka','ru','en'].includes(p.language)?p.language:'ka',consentVersion:'2026-09-08',testMode:!s.production},id='DB-'+randomBytes(6).toString('hex').toUpperCase(),usd=online?(Math.round(q.totalCents/s.rate)/100).toFixed(2):null;
 const r=await one(c,'INSERT INTO orders(id,token,idem,fingerprint,created,status,payment,payment_status,usd,body,paypal_env,paypal_account) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *',[id,hash(token),idem,fingerprint,now(),'new',payment,online?'pending':'cash_on_delivery',usd,body,online?s.paypalEnv:null,online?hash(s.clientId):null]);for(const item of q.items)await c.query('UPDATE inventory SET stock=stock-$1 WHERE id=$2',[item.qty,item.id]);await enqueue(c,r,s,'DRIVEBOX — '+id);return {...view(r),token};});
}
export async function limited(pool,ip,action,max,seconds=60){const stamp=now(),bucket=Math.floor(stamp/seconds),id=hash(ip)+':'+action+':'+bucket;const r=await one(pool,'INSERT INTO request_limits(id,hits,expires) VALUES($1,1,$2) ON CONFLICT(id) DO UPDATE SET hits=request_limits.hits+1 RETURNING hits',[id,stamp+seconds]);if(r.hits>max)throw new Problem('rate_limit',429);}
export {catalog};
