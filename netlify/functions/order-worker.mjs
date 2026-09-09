import {getDatabase} from '@netlify/database';
import nodemailer from 'nodemailer';
import {settings,now,one,transaction} from '../../server/netlify/core.mjs';
import {reconcile} from '../../server/netlify/paypal.mjs';
export default async function(){
 const pool=getDatabase().pool,s=settings(),env=process.env;
 const pending=(await pool.query("SELECT id FROM orders WHERE paypal_id IS NOT NULL AND payment_status IN ('pending','unpaid','failed','cancelled') AND created>$1 ORDER BY created DESC LIMIT 1",[now()-259200])).rows;
 for(const r of pending)try{await reconcile(pool,r.id,s)}catch{/* Next schedule retries uncertain provider responses. */}
 if(env.SMTP_HOST){const transport=nodemailer.createTransport({host:env.SMTP_HOST,port:Number(env.SMTP_PORT||587),secure:env.SMTP_PORT==='465',requireTLS:env.SMTP_PORT!=='465',auth:env.SMTP_USER?{user:env.SMTP_USER,pass:env.SMTP_PASSWORD}:undefined,connectionTimeout:10000,socketTimeout:15000});
 for(let i=0;i<1;i++){const r=await transaction(pool,async c=>{const row=await one(c,'SELECT * FROM outbox WHERE sent IS NULL AND next_try<$1 ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1',[now()]);if(row)await c.query('UPDATE outbox SET next_try=$1 WHERE id=$2',[now()+300,row.id]);return row;});if(!r)break;try{await transport.sendMail({from:env.SMTP_FROM||s.seller.email,to:r.recipient,subject:r.subject,text:r.body,messageId:`<drivebox-${r.id}@${new URL(s.origin).hostname}>`});await pool.query('UPDATE outbox SET sent=$1 WHERE id=$2',[now(),r.id]);}catch{await pool.query('UPDATE outbox SET attempts=attempts+1,next_try=$1 WHERE id=$2',[now()+Math.min(3600,60*2**Math.min(r.attempts,6)),r.id]);}}
 transport.close();}
 await pool.query('DELETE FROM request_limits WHERE expires<$1',[now()-3600]);await pool.query('DELETE FROM sessions WHERE expires<$1',[now()]);return new Response(null,{status:204});
}
export const config={schedule:'*/5 * * * *'};
