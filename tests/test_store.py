import os,tempfile,unittest,json,io,concurrent.futures
os.environ['DATA_DIR']=tempfile.mkdtemp();os.environ['ADMIN_PASSWORD']='test-password-long-enough'
# Tests must never use developer PayPal credentials from .env.
os.environ['PAYPAL_CLIENT_ID']='';os.environ['PAYPAL_CLIENT_SECRET']='';os.environ['PAYPAL_WEBHOOK_ID']='';os.environ['PAYPAL_ENV']='sandbox'
from server import store as s
class Orders(unittest.TestCase):
 def payload(self): return dict(cart=[{'id':'charger-holder','qty':2}],city='Tbilisi',deliveryMethod='next',name='Test Buyer',phone='+995555123456',address='Test street 12',notes='',email='',paymentMethod='test',consent=True)
 def test_server_price(self):
  p=self.payload();p['total']=.01;r=s.create_order(p,'price-test-123456789');self.assertEqual(r['totalCents'],11730)
 def test_repeat(self):
  p=self.payload();a=s.create_order(p,'repeat-test-12345678');b=s.create_order(p,'repeat-test-12345678');self.assertEqual(a['id'],b['id']);self.assertEqual(a['token'],b['token'])
 def test_changed_retry(self):
  p=self.payload();s.create_order(p,'change-test-12345678');p['cart'][0]['qty']=3
  with self.assertRaises(s.Problem):s.create_order(p,'change-test-12345678')
 def test_bad_quantities(self):
  for qty in [0,-1,21,1.5,True]:
   p=self.payload();p['cart'][0]['qty']=qty
   with self.assertRaises(s.Problem):s.create_order(p,'quantity-test-'+str(qty)+'000000')
 def test_forged_product(self):
  p=self.payload();p['cart'][0]['id']='fake'
  with self.assertRaises(s.Problem):s.create_order(p,'fake-test-1234567890')
 def test_consent(self):
  p=self.payload();p['consent']=False
  with self.assertRaises(s.Problem):s.create_order(p,'consent-test-12345678')
 def test_token_required(self):
  r=s.create_order(self.payload(),'token-test-123456789')
  with s.connect() as c:
   with self.assertRaises(s.Problem):s.get_order(c,r['id'],'wrong')
   self.assertEqual(s.get_order(c,r['id'],r['token'])['id'],r['id'])
 def test_region_same_day(self):
  p=self.payload();p.update(city='Batumi',deliveryMethod='same')
  with s.connect() as c:
   with self.assertRaises(s.Problem):s.quote(p,c)
 def test_concurrent_idempotency(self):
  with concurrent.futures.ThreadPoolExecutor(4) as pool: rows=list(pool.map(lambda _:s.create_order(self.payload(),'concurrent-123456789'),range(4)))
  self.assertEqual(len({r['id'] for r in rows}),1)
 def req(self,path,method='GET',body=None,**extra):
  b=json.dumps(body or {}).encode();env={'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(b)),'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(b),'REMOTE_ADDR':'test',**extra};out=[];raw=b''.join(s.application(env,lambda status,headers:out.append(status)));return out[0],raw
 def test_private_files(self):
  for path in ['/server/catalog.json','/data/orders.sqlite3','/.env','/../config.js','/.git/config']:
   self.assertTrue(self.req(path)[0].startswith('404'),path)
 def test_admin_private(self):self.assertTrue(self.req('/api/admin/orders')[0].startswith('401'))
 def test_csrf(self):self.assertTrue(self.req('/api/orders','POST',self.payload())[0].startswith('403'))
 def test_unconfigured_payment(self):
  p=self.payload();p['paymentMethod']='paypal'
  with self.assertRaises(s.Problem):s.create_order(p,'payment-test-12345678')

class PaymentIntegrity(unittest.TestCase):
 def setUp(self):
  from unittest.mock import patch
  self.patch=patch.multiple(s,PP_ID='sandbox-id',PP_SECRET='sandbox-secret',PP_WEBHOOK='sandbox-hook',PP_ENV='sandbox');self.patch.start()
 def tearDown(self):self.patch.stop()
 def order(self,key):
  p=Orders().payload();p['paymentMethod']='paypal';r=s.create_order(p,key)
  with s.connect() as c:c.execute('UPDATE orders SET paypal_id=? WHERE id=?',('PP-'+r['id'],r['id']))
  return r
 def test_completed_capture_only_once(self):
  from unittest.mock import patch
  r=self.order('capture-good-1234567')
  response={'id':'PP-'+r['id'],'intent':'CAPTURE','status':'COMPLETED','purchase_units':[{'custom_id':r['id'],'reference_id':r['id'],'amount':{'currency_code':'USD','value':r['usd']},'payments':{'captures':[{'id':'CAP-good','status':'COMPLETED','amount':{'currency_code':'USD','value':r['usd']}}]}}]}
  with patch.object(s,'paypal',return_value=response):
   self.assertEqual(s.reconcile(r['id'])['paymentStatus'],'paid');self.assertEqual(s.reconcile(r['id'])['paymentStatus'],'paid')
 def test_wrong_capture_amount_rejected(self):
  from unittest.mock import patch
  r=self.order('capture-wrong-123456')
  response={'id':'PP-'+r['id'],'intent':'CAPTURE','status':'COMPLETED','purchase_units':[{'custom_id':r['id'],'reference_id':r['id'],'amount':{'currency_code':'USD','value':r['usd']},'payments':{'captures':[{'id':'CAP-bad','status':'COMPLETED','amount':{'currency_code':'USD','value':'0.01'}}]}}]}
  with patch.object(s,'paypal',return_value=response):
   with self.assertRaises(s.Problem):s.reconcile(r['id'])
  with s.connect() as c:self.assertEqual(s.get_order(c,r['id'])['payment_status'],'pending')
 def test_pending_not_paid(self):
  from unittest.mock import patch
  r=self.order('capture-pending-12345')
  with patch.object(s,'paypal',return_value={'id':'PP-'+r['id'],'intent':'CAPTURE','status':'PAYER_ACTION_REQUIRED','purchase_units':[{'custom_id':r['id'],'reference_id':r['id'],'amount':{'currency_code':'USD','value':r['usd']}}]}):self.assertEqual(s.reconcile(r['id'])['paymentStatus'],'pending')
 def test_forged_webhook(self):
  from unittest.mock import patch
  with patch.object(s,'paypal',return_value={'verification_status':'FAILURE'}):self.assertTrue(Orders().req('/api/paypal/webhook','POST',{'id':'forged'})[0].startswith('403'))
 def test_stock_reservation_race(self):
  with s.connect() as c:c.execute("INSERT OR REPLACE INTO inventory VALUES ('vacuum',1)")
  def buy(i):
   p=Orders().payload();p['cart']=[{'id':'vacuum','qty':1}]
   try:s.create_order(p,'stock-race-test-12345'+str(i));return True
   except s.Problem:return False
  with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(buy,range(2))),1)
 def test_changed_price(self):
  p=Orders().payload();p['expectedTotalCents']=1
  with self.assertRaises(s.Problem):s.create_order(p,'expected-price-123456')

class FieldValidation(unittest.TestCase):
 def test_short_address_specific_error(self):
  p=Orders().payload();p['address']='abc'
  with self.assertRaises(s.Problem) as ctx:s.create_order(p,'short-address-123456')
  self.assertEqual(ctx.exception.code,'invalid_address')
 def test_empty_phone_specific_error(self):
  p=Orders().payload();p['phone']=''
  with self.assertRaises(s.Problem) as ctx:s.create_order(p,'empty-phone-12345678')
  self.assertEqual(ctx.exception.code,'invalid_phone')
 def test_valid_customer_order(self):
  p=Orders().payload();p['city']='тбилиси';p['address']='Тестовая улица, 12'
  self.assertEqual(s.create_order(p,'valid-customer-123456')['city'],'тбилиси')
