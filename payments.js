/* PayPal v6: the provider owns all card fields; this application never reads card data. */
for(const [lang,copy] of Object.entries({
 ru:{card:'Банковская карта',paypal:'PayPal',cash_on_delivery:'Оплата при получении',pending:'Ожидает оплаты',failed:'Не удалось провести оплату',refunded:'Средства возвращены',partially_refunded:'Частичный возврат',sandboxNotice:'Тестовый режим: реальные деньги не списываются, заказ не доставляется.',thankYou:'Спасибо за заказ!',paymentSuccess:'Оплата успешно получена. Заказ передан в обработку.',paymentProcessing:'Оплата проходит…',paymentPending:'Подтверждение оплаты ещё не получено. Обновите статус через несколько секунд.',paymentCancelled:'Вы отменили оплату. Корзина сохранена — можно попробовать снова.',paymentFailed:'Не удалось провести оплату. Корзина сохранена. Попробуйте ещё раз.',cardUnavailable:'Оплата картой сейчас недоступна. Выберите PayPal или оплату при получении.',sdkUnavailable:'Онлайн-оплата временно недоступна. Попробуйте ещё раз.',tryAgain:'Попробовать ещё раз',cardNumber:'Номер карты',cardExpiry:'ММ/ГГ',cardCvv:'CVV',cardName:'Имя владельца',payCard:'Оплатить картой',switchPayPal:'Оплатить через PayPal',payment_environment_changed:'Этот заказ создан в другом режиме оплаты. Обратитесь в магазин.',payment_review_required:'Статус платежа требует проверки. Свяжитесь с магазином.',payment_order_mismatch:'Не удалось подтвердить платёж. Обновите статус заказа.',already_processed:'Этот платёж уже обработан. Обновите статус заказа.'},
 en:{card:'Bank card',paypal:'PayPal',cash_on_delivery:'Pay on delivery',pending:'Awaiting payment',failed:'Payment failed',refunded:'Refunded',partially_refunded:'Partially refunded',sandboxNotice:'Test mode: no real charge or delivery.',thankYou:'Thank you for your order!',paymentSuccess:'Payment received. Your order is being processed.',paymentProcessing:'Processing payment…',paymentPending:'Payment confirmation is pending. Refresh the status shortly.',paymentCancelled:'Payment cancelled. Your cart is saved; you can retry.',paymentFailed:'Payment failed. Your cart is saved. Please retry.',cardUnavailable:'Card payment is unavailable. Choose PayPal or pay on delivery.',sdkUnavailable:'Online payment is temporarily unavailable. Please retry.',tryAgain:'Try again',cardNumber:'Card number',cardExpiry:'MM/YY',cardCvv:'CVV',cardName:'Cardholder name',payCard:'Pay by card',switchPayPal:'Pay with PayPal',payment_environment_changed:'This order belongs to a different payment environment. Contact the store.',payment_review_required:'Payment needs review. Contact the store.',payment_order_mismatch:'Payment could not be verified. Refresh the order status.',already_processed:'Payment already processed. Refresh the order status.'},
 ka:{card:'საბანკო ბარათი',paypal:'PayPal',cash_on_delivery:'გადახდა მიღებისას',pending:'გადახდის მოლოდინში',failed:'გადახდა ვერ შესრულდა',refunded:'თანხა დაბრუნებულია',partially_refunded:'თანხა ნაწილობრივ დაბრუნებულია',sandboxNotice:'სატესტო რეჟიმი: რეალური თანხა არ ჩამოიჭრება და მიწოდება არ შესრულდება.',thankYou:'გმადლობთ შეკვეთისთვის!',paymentSuccess:'გადახდა მიღებულია. შეკვეთა დამუშავების პროცესშია.',paymentProcessing:'გადახდა მიმდინარეობს…',paymentPending:'გადახდის დადასტურება ჯერ არ მიღებულა. განაახლეთ სტატუსი რამდენიმე წამში.',paymentCancelled:'გადახდა გაუქმებულია. კალათა შენახულია; სცადეთ ხელახლა.',paymentFailed:'გადახდა ვერ შესრულდა. კალათა შენახულია. სცადეთ ხელახლა.',cardUnavailable:'ბარათით გადახდა მიუწვდომელია. აირჩიეთ PayPal ან გადახდა მიღებისას.',sdkUnavailable:'ონლაინ გადახდა დროებით მიუწვდომელია. სცადეთ ხელახლა.',tryAgain:'ხელახლა ცდა',cardNumber:'ბარათის ნომერი',cardExpiry:'თთ/წწ',cardCvv:'CVV',cardName:'ბარათის მფლობელი',payCard:'ბარათით გადახდა',switchPayPal:'PayPal-ით გადახდა',payment_environment_changed:'შეკვეთა გადახდის სხვა რეჟიმშია შექმნილი. დაუკავშირდით მაღაზიას.',payment_review_required:'გადახდა შემოწმებას საჭიროებს. დაუკავშირდით მაღაზიას.',payment_order_mismatch:'გადახდა ვერ დადასტურდა. განაახლეთ სტატუსი.',already_processed:'გადახდა უკვე დამუშავებულია. განაახლეთ სტატუსი.'}
}))Object.assign(commerceText[lang],copy);
let paymentSdkPromise;
async function paymentSdk(){
 if(!storeSettings?.paypal?.configured)throw Error('sdkUnavailable');
 if(!paymentSdkPromise)paymentSdkPromise=(async()=>{
  await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=storeSettings.paypal.environment==='live'?'https://www.paypal.com/web-sdk/v6/core':'https://www.sandbox.paypal.com/web-sdk/v6/core';script.onload=resolve;script.onerror=()=>{script.remove();reject(Error('sdkUnavailable'))};document.head.append(script)});
  return window.paypal.createInstance({clientId:storeSettings.paypal.clientId,components:['paypal-payments','paypal-guest-payments','card-fields'],pageType:'checkout'});
 })().catch(e=>{paymentSdkPromise=null;throw e});
 return paymentSdkPromise;
}
async function mountPayment(root,order,credentials,onPaid){
 root.replaceChildren();const status=document.createElement('p');status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
 let busy=false,paid=false,completedOrder=null,deferCompletion=false;const setMessage=key=>status.textContent=ct(key);
 const controls=document.createElement('div');root.append(controls);
 const setBusy=value=>{busy=value;root.setAttribute('aria-busy',String(value));for(const button of controls.querySelectorAll('button,paypal-button,paypal-basic-card-button'))button.disabled=value};
 const approve=async data=>{
  setBusy(true);setMessage('paymentProcessing');
  try{const confirmed=await api('/api/paypal/capture-order',{...credentials,orderId:data.orderId});paid=confirmed.paymentStatus==='paid';if(paid){completedOrder=confirmed;if(!deferCompletion)await onPaid(confirmed);}else setMessage(confirmed.paymentStatus==='failed'?'paymentFailed':'paymentPending');}
  catch(e){setMessage(e.message in commerceText[getLang()]?e.message:'paymentFailed');throw e;}
  finally{setBusy(false)}
 };
 const cancel=async()=>{setMessage('paymentCancelled');setBusy(false);try{await api('/api/paypal/cancel-order',credentials)}catch{/* Cancellation never marks an order as paid. */}};
 const fail=()=>{setMessage('paymentFailed');setBusy(false)};
 const create=()=>api('/api/paypal/create-order',credentials);
 try{
  setMessage('loading');const sdk=await paymentSdk();const eligible=await sdk.findEligibleMethods({currencyCode:'USD',amount:order.usd});status.textContent='';
  if(order.paymentMethod==='card'&&eligible.isEligible('advanced_cards')){
   const session=sdk.createCardFieldsOneTimePaymentSession();
   for(const [type,key] of [['name','cardName'],['number','cardNumber'],['expiry','cardExpiry'],['cvv','cardCvv']]){const label=document.createElement('div');label.className='hosted-card-field';const title=document.createElement('div');title.textContent=ct(key);label.append(title);label.append(session.createCardFieldsComponent({type,placeholder:ct(key),style:{input:{fontSize:'16px',color:'#172638'}}}));controls.append(label)}
   const pay=document.createElement('button');pay.type='button';pay.className='btn primary';pay.textContent=ct('payCard');controls.append(pay);pay.onclick=async()=>{if(busy)return;setBusy(true);setMessage('paymentProcessing');try{const {orderId}=await create();const outcome=await session.submit(orderId);if(outcome.state==='succeeded')await approve({orderId:outcome.data?.orderId||orderId});else if(outcome.state==='canceled')await cancel();else fail();}catch{fail()}finally{setBusy(false)}};
  }else if(order.paymentMethod==='card'&&eligible.isEligible('card')){
   const container=document.createElement('paypal-basic-card-container');const button=document.createElement('paypal-basic-card-button');container.append(button);controls.append(container);
   deferCompletion=true;const session=sdk.createPayPalGuestOneTimePaymentSession({onApprove:approve,onComplete:async()=>{if(paid)await onPaid(completedOrder);else setMessage('paymentPending')},onCancel:cancel,onError:fail,onWarn:()=>setMessage('paymentFailed')});
   button.addEventListener('click',()=>{if(busy)return;setBusy(true);session.start({presentationMode:'auto',targetElement:button},create()).catch(fail)});
  }else if(order.paymentMethod==='paypal'&&eligible.isEligible('paypal')){
   const button=document.createElement('paypal-button');button.setAttribute('type','pay');controls.append(button);
   const session=sdk.createPayPalOneTimePaymentSession({onApprove:approve,onCancel:cancel,onError:fail});
   button.addEventListener('click',()=>{if(busy)return;setBusy(true);session.start({presentationMode:'auto'},create()).catch(fail)});
   if(session.hasReturned())await session.resume();
  }else{
   setMessage(order.paymentMethod==='card'?'cardUnavailable':'sdkUnavailable');
   if(!order.paypalOrderId){
    for(const method of ['paypal','cash_on_delivery']){
     if(method===order.paymentMethod||!storeSettings.paymentMethods.includes(method)||method==='paypal'&&!eligible.isEligible('paypal'))continue;
     const button=document.createElement('button');button.type='button';button.className='btn secondary';button.textContent=ct(method);controls.append(button);
     button.onclick=async()=>{if(busy)return;setBusy(true);try{const updated=await api('/api/payment/method',{...credentials,paymentMethod:method});if(method==='cash_on_delivery')await onPaid(updated);else await mountPayment(root,updated,credentials,onPaid)}catch(e){setMessage(e.message in commerceText[getLang()]?e.message:'paymentFailed');setBusy(false)}};
    }
   }
  }
 }catch{setMessage('sdkUnavailable');const retry=document.createElement('button');retry.className='btn secondary';retry.textContent=ct('tryAgain');retry.onclick=()=>mountPayment(root,order,credentials,onPaid);controls.append(retry)}
}
