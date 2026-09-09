import {randomBytes} from 'node:crypto';
import {Problem,settings,issues,hash,now,safeEqual,clean,view,one,order,transaction,quote,createOrder,limited,catalog,enqueue} from './core.mjs';
import {payCreate,reconcile,cancel,changeMethod,webhook} from './paypal.mjs';
export function handler(getPool,env=process.env){return async function(request,context={}){
 const headers={'Cache-Control':'no-store','Content-Type':'application/json; charset=utf-8','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'};let status=200;
 try{
 const s=settings(env),method=request.method;let path=new URL(request.url).pathname;path=path.replace(/^\/\.netlify\/functions\/store/,'/api');if(!['GET','HEAD','POST'].includes(method))throw new Problem('method_not_allowed',405);
 let p={};if(method==='POST'){if(path!=='/api/paypal/webhook'&&request.headers.get('origin')!==s.origin)throw new Problem('invalid_origin',403);if(!request.headers.get('content-type')?.startsWith('application/json'))throw new Problem('json_required',415);if(Number(request.headers.get('content-length'))>32768)throw new Problem('too_large',413);const text=await request.text();if(Buffer.byteLength(text)>32768)throw new Problem('too_large',413);try{p=JSON.parse(text)}catch{throw new Problem('invalid_fields')}if(!p||Array.isArray(p)||typeof p!=='object')throw new Problem('invalid_fields');}
 let result;const pool=await getPool(),ip=context.ip||'unknown';
 if(path==='/api/config'){result={testMode:!s.production,acceptingOrders:!s.production||!issues(s).length,paymentMethods:['card','paypal',...(s.cod?['cash_on_delivery']:[])],paypal:{configured:s.paypalEnabled,clientId:s.paypalEnabled?s.clientId:null,environment:s.paypalEnv},seller:s.seller,discountPercent:s.discount,freeShipping:s.free,gelPerUsd:String(s.rate)};}
 else if(path==='/api/catalog'){const rows=(await pool.query('SELECT * FROM inventory')).rows;result=catalog.map(p=>({...p,stock:rows.find(r=>r.id===p.id)?.stock??p.stock}));}
 else if(path==='/api/quote'&&method==='POST')result=await quote(p,pool,s);
 else if(path==='/api/orders'&&method==='POST'){await limited(pool,ip,'orders',10,600);result=await createOrder(pool,p,request.headers.get('idempotency-key')||'',s);status=201;}
 else if(path==='/api/order'&&method==='POST'){await limited(pool,ip,'lookup',60);result=view(await order(pool,clean(p.id,5,40),clean(p.token,32,128)));}
 else if(['/api/paypal/create-order','/api/paypal/capture-order','/api/payment/capture','/api/paypal/cancel-order','/api/payment/method'].includes(path)&&method==='POST'){
 await limited(pool,ip,'payment',30);const id=clean(p.id,5,40),token=clean(p.token,32,128);const r=await order(pool,id,token);
 if(path.endsWith('create-order'))result=await payCreate(pool,id,token,s);
 else if(path.endsWith('cancel-order'))result=await cancel(pool,id,token,s);
 else if(path.endsWith('/method'))result=await changeMethod(pool,id,token,p.paymentMethod,s);
 else result=await reconcile(pool,id,s,path==='/api/payment/capture'?r.paypal_id:clean(p.orderId,1,100));
 }
 else if(path==='/api/paypal/webhook'&&method==='POST')result=await webhook(pool,p,request.headers,s);
 else if(path==='/api/admin/login'&&method==='POST'){await limited(pool,ip,'login',5,900);if(s.admin.length<16||!safeEqual(String(p.password||''),s.admin))throw new Problem('unauthorized',401);const token=randomBytes(32).toString('hex');await pool.query('INSERT INTO sessions(token,expires) VALUES($1,$2)',[hash(token),now()+28800]);headers['Set-Cookie']=`db_admin=${token}; HttpOnly; SameSite=Strict; Path=/api/admin; Max-Age=28800${s.origin.startsWith('https://')?'; Secure':''}`;result={ok:true};}
 else if(path.startsWith('/api/admin/')){
 const token=/(?:^|;\s*)db_admin=([a-f0-9]+)/.exec(request.headers.get('cookie')||'')?.[1];if(!token||!await one(pool,'SELECT token FROM sessions WHERE token=$1 AND expires>$2',[hash(token),now()]))throw new Problem('unauthorized',401);
 if(path==='/api/admin/orders'&&method==='GET')result=(await pool.query('SELECT * FROM orders ORDER BY created DESC LIMIT 500')).rows.map(view);
 else if(path==='/api/admin/readiness'&&method==='GET')result={issues:issues(s),unsentEmails:Number((await one(pool,'SELECT count(*) AS total FROM outbox WHERE sent IS NULL')).total),testMode:!s.production};
 else if(path==='/api/admin/inventory'&&method==='GET')result=(await pool.query('SELECT * FROM inventory')).rows;
 else if(path==='/api/admin/inventory'&&method==='POST'){if(!catalog.some(x=>x.id===p.id)||!Number.isInteger(p.stock)||p.stock<0||p.stock>100000)throw new Problem('invalid_fields');await transaction(pool,async c=>{await c.query('SELECT pg_advisory_xact_lock(71843001)');await c.query('INSERT INTO inventory(id,stock) VALUES($1,$2) ON CONFLICT(id) DO UPDATE SET stock=excluded.stock',[p.id,p.stock]);});result={ok:true};}
 else if(path==='/api/admin/logout'&&method==='POST'){await pool.query('DELETE FROM sessions WHERE token=$1',[hash(token)]);headers['Set-Cookie']='db_admin=; HttpOnly; SameSite=Strict; Path=/api/admin; Max-Age=0';result={ok:true};}
 else if(path==='/api/admin/collect'&&method==='POST')result=await transaction(pool,async c=>{const r=await order(c,p.id,undefined,true);if(r.payment!=='cash_on_delivery'||r.status!=='delivered')throw new Problem('invalid_payment_state',409);return view(await one(c,"UPDATE orders SET payment_status='paid' WHERE id=$1 RETURNING *",[p.id]));});
 else if(path==='/api/admin/status'&&method==='POST')result=await transaction(pool,async c=>{
 await c.query('SELECT pg_advisory_xact_lock(71843001)');const r=await order(c,p.id,undefined,true),allowed={new:['confirmed','cancelled'],confirmed:['shipped','cancelled'],shipped:['delivered'],delivered:[],cancelled:[]};if(!allowed[r.status]?.includes(p.status))throw new Problem('invalid_status',409);if(p.status==='shipped'&&['card','paypal'].includes(r.payment)&&r.payment_status!=='paid')throw new Problem('payment_required',409);if(p.status==='cancelled'&&['card','paypal'].includes(r.payment))throw new Problem('paypal_review_required',409);if(p.status==='cancelled')for(const x of r.body.items)await c.query('UPDATE inventory SET stock=stock+$1 WHERE id=$2',[x.qty,x.id]);const updated=await one(c,'UPDATE orders SET status=$1 WHERE id=$2 RETURNING *',[p.status,p.id]);await c.query('INSERT INTO audit(order_id,created,action) VALUES($1,$2,$3)',[p.id,now(),p.status]);await enqueue(c,updated,s,'DRIVEBOX '+p.status+' — '+p.id);return view(updated);});
 else throw new Problem('not_found',404);
 }else throw new Problem('not_found',404);
 return new Response(method==='HEAD'?null:JSON.stringify(result),{status,headers});
 }catch(e){const known=e instanceof Problem;return new Response(JSON.stringify({error:known?e.code:'server_error'}),{status:known?e.status:500,headers});}
};}
