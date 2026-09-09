const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.events={};this.textContent='';}
 append(...nodes){this.children.push(...nodes)} replaceChildren(...nodes){this.children=nodes}setAttribute(){}
 addEventListener(name,cb){this.events[name]=cb}querySelectorAll(){return this.children.flatMap(c=>[c,...c.querySelectorAll()])}
}
const flush=()=>new Promise(r=>setImmediate(r));
async function setup(method,eligibility,handler){
 let callbacks,calls=[],paid=0;
 const document={createElement:t=>new Element(t),head:new Element('head')};
 const sdk={findEligibleMethods:async()=>({isEligible:x=>eligibility.includes(x)}),createPayPalOneTimePaymentSession:c=>(callbacks=c,{start:async(o,p)=>{await p},hasReturned:()=>false}),createPayPalGuestOneTimePaymentSession:c=>(callbacks=c,{start:async(o,p)=>{await p}}),createCardFieldsOneTimePaymentSession:()=>({createCardFieldsComponent:()=>new Element('iframe'),submit:async id=>({state:'succeeded',data:{orderId:id}})})};
 const context=vm.createContext({document,window:{},commerceText:{ru:{},en:{},ka:{}},getLang:()=> 'ru',ct:k=>k,storeSettings:{paypal:{configured:true},paymentMethods:['card','paypal','cash_on_delivery']},api:async(path,payload)=>{calls.push({path,payload});return handler?handler(path,payload):{orderId:'PP1',paymentStatus:'paid'}},sdk});
 vm.runInContext(fs.readFileSync('payments.js','utf8')+'\npaymentSdkPromise=Promise.resolve(sdk);',context);
 const root=new Element('div');await context.mountPayment(root,{paymentMethod:method,usd:'10.00'}, {id:'DB1',token:'receipt-secret'},async()=>{paid++});
 return {root,calls,get paid(){return paid},get callbacks(){return callbacks}};
}
(async()=>{
 let t=await setup('paypal',['paypal']);await t.callbacks.onApprove({orderId:'PP1'});assert.equal(t.paid,1);assert.equal(t.calls[0].path,'/api/paypal/capture-order');assert.equal(t.calls[0].payload.orderId,'PP1');
 t=await setup('paypal',['paypal'],()=>({paymentStatus:'pending'}));await t.callbacks.onApprove({orderId:'PP1'});assert.equal(t.paid,0);
 t=await setup('paypal',['paypal'],()=>{throw Error('network')});await assert.rejects(()=>t.callbacks.onApprove({orderId:'PP1'}));assert.equal(t.paid,0);
 t=await setup('paypal',['paypal']);await t.callbacks.onCancel();assert.equal(t.paid,0);assert.equal(t.calls[0].path,'/api/paypal/cancel-order');
 t=await setup('card',['card']);await t.callbacks.onApprove({orderId:'PP1'});assert.equal(t.paid,0);await t.callbacks.onComplete();assert.equal(t.paid,1);
 t=await setup('card',['advanced_cards']);const button=t.root.querySelectorAll().find(x=>x.tagName==='button');await button.onclick();assert.equal(t.calls[0].path,'/api/paypal/create-order');assert.equal(t.calls[1].path,'/api/paypal/capture-order');assert.equal(t.paid,1);
 t=await setup('card',[]);assert.equal(t.calls.length,0);assert.equal(t.paid,0);assert.ok(t.root.querySelectorAll().some(x=>x.textContent==='cardUnavailable'));
 t=await setup('paypal',['paypal']);const ppButton=t.root.querySelectorAll().find(x=>x.tagName==='paypal-button');ppButton.events.click();ppButton.events.click();await flush();assert.equal(t.calls.filter(x=>x.path.endsWith('create-order')).length,1);
 console.log('8 SDK callback/eligibility UI tests passed (mock SDK, no external payment).');
})().catch(e=>{console.error(e);process.exitCode=1});
