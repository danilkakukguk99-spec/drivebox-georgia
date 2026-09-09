import {readdir, mkdir, rm, cp} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=new URL('../',import.meta.url),dest=new URL('dist/',root);
await rm(dest,{recursive:true,force:true});await mkdir(dest);
const publicFiles=new Set(['index.html','checkout.html','order.html','admin.html','paypal.html','styles.css','app.js','commerce.js','payments.js','admin.js','config.js','products.js','i18n.js','product-media.js','product-details.js','robots.txt','sitemap.xml']);
for(const name of publicFiles)await cp(new URL(name,root),new URL(name,dest));
for(const name of ['assets','products','legal'])await cp(new URL(name,root),new URL(name,dest),{recursive:true,filter:src=>!src.split('/').at(-1).startsWith('.')});
console.log('Built public files in',fileURLToPath(dest));
