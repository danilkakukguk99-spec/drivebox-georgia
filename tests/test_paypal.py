"""Provider responses are mocks. These tests do not claim real Sandbox coverage."""
import copy,json,secrets,unittest
from unittest.mock import patch
import test_store as fixtures
from server import store as s

class PayPalCheckout(unittest.TestCase):
 def setUp(self):
  self.patcher=patch.multiple(s,PP_ID='test-client',PP_SECRET='test-secret',PP_WEBHOOK='test-webhook',PP_ENV='sandbox',COD=True)
  self.patcher.start();s.LIMITS.clear()
 def tearDown(self):self.patcher.stop()
 def new(self,method='paypal'):
  p=fixtures.Orders().payload();p['paymentMethod']=method
  return s.create_order(p,secrets.token_hex(16))
 def provider(self,order,state='COMPLETED',amount=None):
  pp='PP'+order['id'].replace('-','');
  with s.connect() as c:c.execute('UPDATE orders SET paypal_id=? WHERE id=?',(pp,order['id']))
  unit={'reference_id':order['id'],'custom_id':order['id'],'amount':{'currency_code':'USD','value':order['usd']}}
  if state=='COMPLETED':unit['payments']={'captures':[{'id':'CAP'+order['id'].replace('-',''),'status':'COMPLETED','amount':{'currency_code':'USD','value':amount or order['usd']}}]}
  return {'id':pp,'intent':'CAPTURE','status':state,'purchase_units':[unit],'payer':{'payer_id':'BUYER1','email_address':'buyer@example.test'}}
 def request(self,path,body):
  return fixtures.Orders().req(path,'POST',body,HTTP_ORIGIN=s.ORIGIN)
 def test_cod_never_calls_paypal(self):
  with patch.object(s,'paypal',side_effect=AssertionError('COD contacted PayPal')):
   o=self.new('cash_on_delivery');self.assertEqual(o['paymentStatus'],'cash_on_delivery');self.assertIsNone(o['usd'])
 def test_card_paid_and_payer_saved(self):
  o=self.new('card');response=self.provider(o)
  with patch.object(s,'paypal',return_value=response):r=s.reconcile(o['id'],response['id'])
  self.assertEqual(r['paymentStatus'],'paid')
  with s.connect() as c:
   row=s.get_order(c,o['id']);self.assertEqual(row['payer_id'],'BUYER1');self.assertEqual(row['payer_email'],'buyer@example.test');self.assertIsNotNone(row['capture_id'])
 def test_create_repeated_uses_one_provider_order(self):
  o=self.new()
  with patch.object(s,'paypal',return_value={'id':'PAYPAL123'}) as provider:
   a=s.pay_create(o['id'],o['token']);b=s.pay_create(o['id'],o['token']);self.assertEqual(a,b);self.assertEqual(provider.call_count,1)
   self.assertEqual(provider.call_args.args[2],'create-'+o['id'])
 def test_concurrent_create_one_provider_order(self):
  from concurrent.futures import ThreadPoolExecutor
  o=self.new()
  with patch.object(s,'paypal',return_value={'id':'PAYPAL'+o['id']}) as provider,ThreadPoolExecutor(4) as pool:
   results=list(pool.map(lambda _:s.pay_create(o['id'],o['token']),range(4)));self.assertEqual(provider.call_count,1);self.assertEqual(len({x['orderId'] for x in results}),1)
 def test_duplicate_capture_no_second_api_call(self):
  o=self.new();response=self.provider(o)
  with patch.object(s,'paypal',return_value=response) as provider:
   s.reconcile(o['id']);count=provider.call_count;s.reconcile(o['id']);self.assertEqual(provider.call_count,count)
 def test_capture_rejects_foreign_order_id(self):
  o=self.new();response=self.provider(o)
  with patch.object(s,'paypal') as provider:
   with self.assertRaises(s.Problem):s.reconcile(o['id'],'FOREIGN')
   provider.assert_not_called()
 def test_order_identity_currency_and_total_checks(self):
  for tamper in ['id','custom_id','reference_id','currency','amount','capture_id']:
   o=self.new();response=self.provider(o)
   if tamper=='id':response['id']='FOREIGN'
   elif tamper in ['custom_id','reference_id']:response['purchase_units'][0][tamper]='FOREIGN'
   elif tamper=='currency':response['purchase_units'][0]['payments']['captures'][0]['amount']['currency_code']='EUR'
   elif tamper=='amount':response['purchase_units'][0]['payments']['captures'][0]['amount']['value']='0.01'
   else:del response['purchase_units'][0]['payments']['captures'][0]['id']
   with patch.object(s,'paypal',return_value=response):
    with self.assertRaises(s.Problem):s.reconcile(o['id'])
   with s.connect() as c:self.assertEqual(s.get_order(c,o['id'])['payment_status'],'pending')
 def test_approve_not_paid_without_completed_capture(self):
  o=self.new();response=self.provider(o,'APPROVED')
  with patch.object(s,'paypal',return_value=response):self.assertEqual(s.reconcile(o['id'])['paymentStatus'],'pending')
 def test_capture_timeout_reconciles_success(self):
  o=self.new();approved=self.provider(o,'APPROVED');completed=self.provider(o)
  with patch.object(s,'paypal',side_effect=[approved,s.Problem('payment_service_error',502),completed]):self.assertEqual(s.reconcile(o['id'])['paymentStatus'],'paid')
 def test_cancel_then_verified_capture(self):
  o=self.new();response=self.provider(o);self.assertEqual(s.payment_cancel(o['id'],o['token'])['paymentStatus'],'cancelled')
  with patch.object(s,'paypal',return_value=response):self.assertEqual(s.reconcile(o['id'])['paymentStatus'],'paid')
  self.assertEqual(s.payment_cancel(o['id'],o['token'])['paymentStatus'],'paid')
 def test_cross_environment_blocked(self):
  o=self.new()
  with patch.multiple(s,PP_ENV='live',PROD=True):
   with self.assertRaises(s.Problem):s.pay_create(o['id'],o['token'])
 def test_frontend_price_not_trusted(self):
  p=fixtures.Orders().payload();p.update(paymentMethod='card',total=.01);p['cart'][0]['price']=.01
  self.assertEqual(s.create_order(p,secrets.token_hex(16))['totalCents'],11730)
 def test_capture_requires_receipt_token(self):
  o=self.new();response=self.provider(o)
  code,_=self.request('/api/paypal/capture-order',{'id':o['id'],'token':'x'*64,'orderId':response['id']});self.assertTrue(code.startswith('404'))
 def test_denied_webhook_and_late_denial(self):
  o=self.new();response=self.provider(o)
  event={'id':secrets.token_hex(16),'event_type':'PAYMENT.CAPTURE.DENIED','resource':{'id':'CAP1','amount':{'currency_code':'USD','value':o['usd']},'supplementary_data':{'related_ids':{'order_id':response['id']}}}}
  with patch.object(s,'paypal',return_value={'verification_status':'SUCCESS'}):s.webhook(event,{})
  with s.connect() as c:self.assertEqual(s.get_order(c,o['id'])['payment_status'],'failed')
  with patch.object(s,'paypal',return_value=response):s.reconcile(o['id'])
  event['id']=secrets.token_hex(16)
  with patch.object(s,'paypal',return_value={'verification_status':'SUCCESS'}):s.webhook(event,{})
  with s.connect() as c:self.assertEqual(s.get_order(c,o['id'])['payment_status'],'paid')
 def test_refund_duplicate_and_paid_downgrade(self):
  o=self.new();response=self.provider(o)
  with patch.object(s,'paypal',return_value=response):s.reconcile(o['id'])
  capture=response['purchase_units'][0]['payments']['captures'][0]['id']
  event={'id':secrets.token_hex(16),'event_type':'PAYMENT.CAPTURE.REFUNDED','resource':{'id':'REF'+o['id'],'amount':{'currency_code':'USD','value':o['usd']},'supplementary_data':{'related_ids':{'capture_id':capture}}}}
  with patch.object(s,'paypal',return_value={'verification_status':'SUCCESS'}):s.webhook(event,{});s.webhook(event,{})
  with patch.object(s,'paypal') as provider:self.assertEqual(s.reconcile(o['id'])['paymentStatus'],'refunded');provider.assert_not_called()
  with s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM refunds WHERE order_id=?',(o['id'],)).fetchone()[0],1)
 def test_public_config_no_secret(self):
  _,body=fixtures.Orders().req('/api/config');data=json.loads(body);self.assertNotIn('test-secret',body.decode());self.assertEqual(data['paypal']['clientId'],'test-client')
 def test_switch_unavailable_card_to_cod_no_paypal(self):
  o=self.new('card')
  with patch.object(s,'paypal') as provider:r=s.change_payment_method(o['id'],o['token'],'cash_on_delivery');provider.assert_not_called()
  self.assertEqual(r['paymentStatus'],'cash_on_delivery');self.assertIsNone(r['usd'])
