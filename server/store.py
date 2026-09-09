"""DRIVEBOX order service. Run behind HTTPS in production; SQLite requires persistent disk."""
import base64, hashlib, hmac, json, mimetypes, os, re, secrets, smtplib, sqlite3, threading, time, urllib.request, urllib.error
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
# Local .env is optional; production should inject secrets through the host.
if (ROOT / '.env').is_file():
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key,value=line.split('=',1); os.environ.setdefault(key.strip(),value.strip())
DATA = Path(os.environ.get('DATA_DIR', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
DB = DATA / 'orders.sqlite3'
PROD = os.environ.get('APP_ENV') == 'production'
ORIGIN = os.environ.get('PUBLIC_URL', 'http://localhost:8000').rstrip('/')
ADMIN = os.environ.get('ADMIN_PASSWORD', '')
COD = os.environ.get('ALLOW_COD', 'false').lower() == 'true'
PP_ENV = os.environ.get('PAYPAL_ENV', 'sandbox')
if PP_ENV not in ('sandbox','live'): raise RuntimeError('PAYPAL_ENV must be sandbox or live')
PP_BASE = 'https://api-m.paypal.com' if PP_ENV == 'live' else 'https://api-m.sandbox.paypal.com'
PP_ID, PP_SECRET = os.environ.get('PAYPAL_CLIENT_ID', ''), os.environ.get('PAYPAL_CLIENT_SECRET', '')
PP_WEBHOOK = os.environ.get('PAYPAL_WEBHOOK_ID', '')
RATE = Decimal(os.environ.get('GEL_PER_USD', '2.70'))
DISCOUNT = int(os.environ.get('DISCOUNT_PERCENT', '15'))
FREE = os.environ.get('FREE_SHIPPING', 'true').lower() == 'true'
CAT = {x['id']: x for x in json.loads((ROOT/'server/catalog.json').read_text())}
SELLER = {k: os.environ.get('SELLER_'+k.upper(), '') for k in ['name','id','address','phone','email','whatsapp']}
LIMITS = {}; LIMIT_LOCK = threading.Lock()
PAYMENT_LOCKS = [threading.RLock() for _ in range(64)]
def payment_lock(oid): return PAYMENT_LOCKS[int(hashlib.sha256(oid.encode()).hexdigest(),16)%64]
def paypal_enabled(): return bool(PP_ID and PP_SECRET and (PP_ENV=="sandbox" or (PROD and PP_WEBHOOK)))

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()

def connect():
    c=sqlite3.connect(DB, timeout=15, factory=ClosingConnection); c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); return c

def initialize():
    with connect() as c:
        c.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, token TEXT NOT NULL, idem TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL, payment TEXT NOT NULL, payment_status TEXT NOT NULL, paypal_id TEXT UNIQUE, capture_id TEXT, usd TEXT, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, order_id TEXT, created REAL, action TEXT);
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, order_id TEXT, subject TEXT, recipient TEXT, body TEXT, attempts INTEGER DEFAULT 0, next_try REAL DEFAULT 0, sent REAL);
        CREATE TABLE IF NOT EXISTS inventory(id TEXT PRIMARY KEY, stock INTEGER NOT NULL CHECK(stock>=0));''')
        columns={r['name'] for r in c.execute('PRAGMA table_info(orders)')}
        for name,kind in {'paypal_env':'TEXT','paypal_account':'TEXT','payer_id':'TEXT','payer_email':'TEXT','payment_phase':"TEXT DEFAULT 'not_started'",'paypal_started':'REAL'}.items():
            if name not in columns: c.execute('ALTER TABLE orders ADD COLUMN '+name+' '+kind)
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS capture_unique ON orders(capture_id) WHERE capture_id IS NOT NULL')
        c.execute('CREATE TABLE IF NOT EXISTS refunds(id TEXT PRIMARY KEY, order_id TEXT NOT NULL, cents INTEGER NOT NULL)')
        c.execute("UPDATE orders SET payment='cash_on_delivery',payment_status=CASE WHEN payment_status='unpaid' THEN 'cash_on_delivery' ELSE payment_status END WHERE payment='cod'")
        for p in CAT.values():
            if p['stock'] is not None: c.execute('INSERT OR IGNORE INTO inventory VALUES (?,?)',(p['id'],p['stock']))
initialize()
DB.chmod(0o600)

class Problem(Exception):
    def __init__(self, code, status=400): self.code=code; self.status=status

def ready_issues():
    issues=[]
    if len(ADMIN)<16: issues.append('ADMIN_PASSWORD must have at least 16 characters')
    for k in ['name','id','address','phone','email']:
        if not SELLER[k]: issues.append('SELLER_'+k.upper())
    if not (COD or (PP_ID and PP_SECRET and PP_WEBHOOK)): issues.append('Enable an approved payment method')
    if PROD and not ORIGIN.startswith('https://'): issues.append('PUBLIC_URL must use HTTPS')
    if PROD and PP_ID and PP_ENV != 'live': issues.append('PayPal must be live in production')
    if PROD and not os.environ.get('SMTP_HOST'): issues.append('SMTP_HOST for order notifications')
    if PROD and os.environ.get('LEGAL_CONFIRMED') != 'true': issues.append('LEGAL_CONFIRMED')
    if PROD and os.environ.get('FULFILLMENT_CONFIRMED') != 'true': issues.append('FULFILLMENT_CONFIRMED')
    return issues

def limited(ip, action, count, seconds=60):
    now=time.time(); key=(ip,action)
    with LIMIT_LOCK:
        for k in list(LIMITS):
            if not LIMITS[k] or now-LIMITS[k][-1]>3600: del LIMITS[k]
        hits=[t for t in LIMITS.get(key,[]) if now-t<seconds]
        if len(hits)>=count: raise Problem('rate_limit',429)
        LIMITS[key]=hits+[now]

def clean(value, minimum, maximum, error="invalid_fields"):
    if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum: raise Problem(error)
    return value.strip()

def quote(payload, c):
    cart=payload.get('cart'); city=clean(payload.get('city',''),2,100,'invalid_city')
    if not isinstance(cart,list) or not 1<=len(cart)<=30: raise Problem('invalid_cart')
    rows=[]; seen=set(); base=0; total=0
    for row in cart:
        if not isinstance(row,dict): raise Problem('invalid_cart')
        p=CAT.get(row.get('id')); qty=row.get('qty')
        if not p or not p['active'] or type(qty)!=int or not 1<=qty<=20 or p['id'] in seen: raise Problem('invalid_cart')
        seen.add(p['id']); stock=c.execute('SELECT stock FROM inventory WHERE id=?',(p['id'],)).fetchone()
        if stock and stock['stock']<qty: raise Problem('out_of_stock',409)
        unit=int((Decimal(p['priceCents'])*(100-DISCOUNT)/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        rows.append({'id':p['id'],'name':p['name'],'qty':qty,'unitCents':unit}); base+=p['priceCents']*qty; total+=unit*qty
    tbilisi=city.casefold() in ['tbilisi','тбилиси','თბილისი']
    method=payload.get('deliveryMethod','next')
    if method not in ['same','next']: raise Problem('invalid_delivery')
    if method=='same' and (not tbilisi or datetime.now(ZoneInfo('Asia/Tbilisi')).hour>=15): raise Problem('same_day_unavailable',409)
    ship=0 if FREE or total>=25000 else (900 if method=='same' else 700) if tbilisi else 1200
    return {'items':rows,'subtotalCents':base,'discountCents':base-total,'shippingCents':ship,'totalCents':total+ship,'currency':'GEL','city':city,'deliveryMethod':method}

def enqueue(c, order, subject):
    row=c.execute('SELECT idem FROM orders WHERE id=?',(order['id'],)).fetchone()
    receipt=ORIGIN+'/order.html#'+order['id']+'/'+hashlib.sha256(('receipt:'+row['idem']).encode()).hexdigest()
    lang=order.get('language','ka')
    words={'ru':['Заказ','Статус','Оплата','Итого','Проверить заказ'],'en':['Order','Status','Payment','Total','View order'],'ka':['შეკვეთა','სტატუსი','გადახდა','ჯამი','შეკვეთის ნახვა']}[lang]
    body='\n'.join([words[0]+' '+order['id'],words[1]+': '+order['status'],words[2]+': '+order['paymentStatus'],'',*[x['name'][lang]+' × '+str(x['qty']) for x in order['items']],words[3]+': '+format(order['totalCents']/100,'.2f')+' GEL',order['city']+', '+order['address'],'',words[4]+': '+receipt])
    if SELLER['email']: c.execute('INSERT INTO outbox(order_id,subject,recipient,body) VALUES (?,?,?,?)',(order['id'],subject,SELLER['email'],body))
    if order.get('email'): c.execute('INSERT INTO outbox(order_id,subject,recipient,body) VALUES (?,?,?,?)',(order['id'],subject,order['email'],body))

def get_order(c, oid, token=None):
    row=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if not row or (token is not None and not hmac.compare_digest(row['token'],hashlib.sha256(token.encode()).hexdigest())): raise Problem('not_found',404)
    return row

def view(row):
    return {**json.loads(row['body']),'id':row['id'],'createdAt':row['created'],'status':row['status'],'paymentStatus':row['payment_status'],'paymentMethod':row['payment'],'usd':row['usd'],'paypalOrderId':row['paypal_id'],'paymentPhase':row['payment_phase'],'testMode':json.loads(row['body']).get('testMode', True)}

def create_order(payload, idem):
    if PROD and ready_issues(): raise Problem('store_not_ready',503)
    if not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',idem): raise Problem('invalid_request_id')
    if payload.get('consent') is not True: raise Problem('consent_required')
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    # Derive an unguessable repeatable receipt token from the client's random request key.
    token=hashlib.sha256(('receipt:'+idem).encode()).hexdigest()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM orders WHERE idem=?',(idem,)).fetchone()
        if old:
            if old['fingerprint']!=fingerprint: raise Problem('request_conflict',409)
            return {**view(old),'token':token}
        q=quote(payload,c)
        if 'expectedTotalCents' in payload and payload['expectedTotalCents']!=q['totalCents']: raise Problem('price_changed',409)
        name=clean(payload.get('name'),2,120,'invalid_name'); phone=clean(payload.get('phone'),7,30,'invalid_phone')
        if not re.fullmatch(r'\+?[\d ()-]{7,30}',phone) or not 7<=len(re.sub(r'\D','',phone))<=15: raise Problem('invalid_phone')
        email=clean(payload.get('email',''),0,200,'invalid_email')
        if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise Problem('invalid_email')
        payment=payload.get('paymentMethod')
        if payment=='cod': payment='cash_on_delivery'
        if payment=='cash_on_delivery' and not COD: raise Problem('payment_unavailable',503)
        if payment in ['card','paypal'] and not paypal_enabled(): raise Problem('payment_unavailable',503)
        if payment not in ['cash_on_delivery','card','paypal','test'] or (payment=='test' and PROD): raise Problem('payment_unavailable')
        body={**q,'name':name,'phone':phone,'address':clean(payload.get('address'),5,300,'invalid_address'),'email':email,'notes':clean(payload.get('notes',''),0,1000,'invalid_notes'),'language':payload.get('language') if payload.get('language') in ['ka','ru','en'] else 'ka','consentVersion':'2026-09-08','testMode':not PROD}
        oid='DB-'+secrets.token_hex(6).upper()
        usd=str((Decimal(q['totalCents'])/100/RATE).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if payment in ['card','paypal'] else None
        c.execute('INSERT INTO orders(id,token,idem,fingerprint,created,status,payment,payment_status,usd,body,paypal_env,paypal_account) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                  (oid,hashlib.sha256(token.encode()).hexdigest(),idem,fingerprint,time.time(),'new',payment,
                   'pending' if payment in ['card','paypal'] else 'cash_on_delivery' if payment=='cash_on_delivery' else 'unpaid',
                   usd,json.dumps(body,ensure_ascii=False),PP_ENV if usd else None,hashlib.sha256(PP_ID.encode()).hexdigest() if usd else None))
        for item in q['items']: c.execute('UPDATE inventory SET stock=stock-? WHERE id=?',(item['qty'],item['id']))
        result=view(get_order(c,oid)); enqueue(c,result,'DRIVEBOX — '+oid)
        c.execute('INSERT INTO audit(order_id,created,action) VALUES (?,?,?)',(oid,time.time(),'created'))
        return {**result,'token':token}

def paypal(path, body=None, request_id=None):
    credentials=base64.b64encode((PP_ID+':'+PP_SECRET).encode()).decode()
    try:
        req=urllib.request.Request(PP_BASE+'/v1/oauth2/token',data=b'grant_type=client_credentials',headers={'Authorization':'Basic '+credentials,'Content-Type':'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(req,timeout=20) as r: token=json.load(r)['access_token']
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        if request_id: headers['PayPal-Request-Id']=request_id
        req=urllib.request.Request(PP_BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=25) as r: return json.load(r)
    except (urllib.error.URLError,KeyError,ValueError): raise Problem('payment_service_error',502)

def check_payment_order(row):
    if row['payment'] not in ['card','paypal'] or row['status']=='cancelled': raise Problem('invalid_payment_state',409)
    if not paypal_enabled(): raise Problem('payment_unavailable',503)
    if row['paypal_env']!=PP_ENV or row['paypal_account']!=hashlib.sha256(PP_ID.encode()).hexdigest():
        raise Problem('payment_environment_changed',409)

def payment_phase(c, oid, phase):
    c.execute('UPDATE orders SET payment_phase=? WHERE id=?',(phase,oid))
    c.execute('INSERT INTO audit(order_id,created,action) VALUES (?,?,?)',(oid,time.time(),'payment_'+phase))

def pay_create(oid, token):
    with payment_lock(oid):
        with connect() as c:
            row=get_order(c,oid,token); check_payment_order(row)
            if row['payment_status'] in ['paid','refunded','partially_refunded','review_required']: raise Problem('already_processed',409)
            if row['paypal_id']: return {'orderId':row['paypal_id']}
            # Never issue a fresh create request after the provider's idempotency window.
            if row['paypal_started'] and time.time()-row['paypal_started']>5*3600: raise Problem('payment_review_required',409)
            if not row['paypal_started']: c.execute('UPDATE orders SET paypal_started=? WHERE id=?',(time.time(),oid))
            payment_phase(c,oid,'started')
        body={'intent':'CAPTURE','purchase_units':[{'reference_id':oid,'custom_id':oid,'amount':{'currency_code':'USD','value':row['usd']}}]}
        # The JS SDK supplies the funding source. Never send raw card details to this server.
        result=paypal('/v2/checkout/orders',body,'create-'+oid)
        pp=clean(result.get('id'),1,100,'payment_service_error')
        if not re.fullmatch(r'[A-Za-z0-9-]+',pp): raise Problem('payment_service_error',502)
        with connect() as c: c.execute('UPDATE orders SET paypal_id=?,payment_status=? WHERE id=?',(pp,'pending',oid))
        return {'orderId':pp}

def verify_paypal_order(result, row):
    units=result.get('purchase_units',[])
    if result.get('id')!=row['paypal_id'] or result.get('intent')!='CAPTURE' or len(units)!=1: raise Problem('payment_order_mismatch',409)
    unit=units[0]
    if unit.get('custom_id')!=row['id'] or unit.get('reference_id')!=row['id']: raise Problem('payment_order_mismatch',409)
    amount=unit.get('amount',{})
    if amount.get('currency_code')!='USD' or Decimal(amount.get('value','-1'))!=Decimal(row['usd']): raise Problem('payment_amount_mismatch',409)
    return unit

def reconcile(oid, expected_pp=None):
    with payment_lock(oid):
        with connect() as c:
            row=get_order(c,oid); check_payment_order(row)
            pp=row['paypal_id']
            if not pp or (expected_pp is not None and expected_pp!=pp): raise Problem('payment_order_mismatch',409)
            if row['payment_status'] in ['paid','refunded','partially_refunded','review_required']: return view(row)
        result=paypal('/v2/checkout/orders/'+pp)
        verify_paypal_order(result,row)
        if result.get('status')=='APPROVED':
            with connect() as c: payment_phase(c,oid,'approved')
            try: paypal('/v2/checkout/orders/'+pp+'/capture',{},'capture-'+oid)
            except Problem:
                # A timeout does not prove failure. Read the authoritative provider state.
                pass
            result=paypal('/v2/checkout/orders/'+pp)
        unit=verify_paypal_order(result,row)
        captures=unit.get('payments',{}).get('captures',[])
        completed=[cap for cap in captures if cap.get('status')=='COMPLETED']
        if result.get('status')=='COMPLETED' and len(completed)==1:
            cap=completed[0]; amount=cap.get('amount',{})
            if not cap.get('id') or len(captures)!=1 or amount.get('currency_code')!='USD' or Decimal(amount.get('value','-1'))!=Decimal(row['usd']): raise Problem('payment_amount_mismatch',409)
            payer=result.get('payer') or result.get('payment_source',{}).get('paypal',{})
            with connect() as c:
                c.execute('BEGIN IMMEDIATE'); current=get_order(c,oid)
                if current['payment_status'] not in ['paid','refunded','partially_refunded','review_required']:
                    c.execute('UPDATE orders SET payment_status=?,capture_id=?,payer_id=?,payer_email=? WHERE id=?',('paid',cap['id'],payer.get('payer_id') or payer.get('account_id'),payer.get('email_address'),oid))
                    payment_phase(c,oid,'completed'); enqueue(c,view(get_order(c,oid)),'DRIVEBOX payment — '+oid)
        elif any(cap.get('status') in ['DECLINED','DENIED','FAILED'] for cap in captures):
            with connect() as c:
                c.execute("UPDATE orders SET payment_status='failed' WHERE id=? AND payment_status NOT IN ('paid','refunded','partially_refunded','review_required')",(oid,)); payment_phase(c,oid,'failed')
        with connect() as c: return view(get_order(c,oid))

def change_payment_method(oid,token,method):
    if method not in ['card','paypal','cash_on_delivery']: raise Problem('payment_unavailable',400)
    with payment_lock(oid),connect() as c:
        c.execute('BEGIN IMMEDIATE');row=get_order(c,oid,token)
        if row['paypal_id'] or row['paypal_started'] or row['status']!='new' or row['payment_status'] in ['paid','refunded','partially_refunded']: raise Problem('payment_review_required',409)
        if method=='cash_on_delivery' and not COD or method in ['card','paypal'] and not paypal_enabled(): raise Problem('payment_unavailable',503)
        total=json.loads(row['body'])['totalCents'];online=method in ['card','paypal']
        usd=str((Decimal(total)/100/RATE).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if online else None
        c.execute('UPDATE orders SET payment=?,payment_status=?,usd=?,paypal_env=?,paypal_account=? WHERE id=?',(method,'pending' if online else 'cash_on_delivery',usd,PP_ENV if online else None,hashlib.sha256(PP_ID.encode()).hexdigest() if online else None,oid))
        payment_phase(c,oid,'method_changed');return view(get_order(c,oid))

def payment_cancel(oid,token):
    with payment_lock(oid):
        with connect() as c:
            row=get_order(c,oid,token);check_payment_order(row)
            # Cancellation is a buyer UX signal, not proof that money was not captured.
            c.execute("UPDATE orders SET payment_status='cancelled' WHERE id=? AND payment_status IN ('pending','unpaid','failed')",(oid,))
            if row['payment_status'] not in ['paid','refunded','partially_refunded','review_required']: payment_phase(c,oid,'cancelled')
            return view(get_order(c,oid))

def webhook(payload,env):
    if not PP_WEBHOOK: raise Problem('payment_unavailable',503)
    verify={k:env.get('HTTP_PAYPAL_'+k.upper(),'') for k in ['auth_algo','cert_url','transmission_id','transmission_sig','transmission_time']}
    verify.update(webhook_id=PP_WEBHOOK,webhook_event=payload)
    if paypal('/v1/notifications/verify-webhook-signature',verify).get('verification_status')!='SUCCESS': raise Problem('invalid_signature',403)
    event_id=clean(payload.get('id'),1,200);kind=payload.get('event_type');resource=payload.get('resource',{})
    with connect() as c:
        if c.execute('SELECT 1 FROM events WHERE id=?',(event_id,)).fetchone(): return {'ok':True}
    pp=resource.get('supplementary_data',{}).get('related_ids',{}).get('order_id')
    if kind=='CHECKOUT.ORDER.APPROVED': pp=resource.get('id')
    with connect() as c: row=c.execute('SELECT * FROM orders WHERE paypal_id=?',(pp,)).fetchone()
    if kind in ['PAYMENT.CAPTURE.COMPLETED','CHECKOUT.ORDER.APPROVED'] and row: reconcile(row['id'],pp)
    elif kind in ['PAYMENT.CAPTURE.DENIED','PAYMENT.CAPTURE.PENDING'] and row:
        with payment_lock(row['id']),connect() as c:
            check_payment_order(row)
            if resource.get('amount',{}).get('currency_code')!='USD' or Decimal(resource.get('amount',{}).get('value','-1'))!=Decimal(row['usd']): raise Problem('payment_amount_mismatch',409)
            state='failed' if kind.endswith('DENIED') else 'pending'
            c.execute("UPDATE orders SET payment_status=? WHERE id=? AND payment_status IN ('pending','unpaid','failed','cancelled')",(state,row['id']))
            current=get_order(c,row['id'])
            if current['payment_status']==state: payment_phase(c,row['id'],state)
    elif kind in ['PAYMENT.CAPTURE.REFUNDED','PAYMENT.CAPTURE.REVERSED']:
        capture=resource.get('supplementary_data',{}).get('related_ids',{}).get('capture_id')
        for link in resource.get('links',[]):
            match=re.search(r'/v2/payments/captures/([A-Za-z0-9]+)(?:$|[?])',link.get('href',''))
            if match: capture=match[1]
        if kind.endswith('REVERSED'): capture=resource.get('id')
        with connect() as c: row=c.execute('SELECT * FROM orders WHERE capture_id=?',(capture,)).fetchone()
        if not row: raise Problem('payment_order_mismatch',409) # Retry if capture webhook has not arrived yet.
        with payment_lock(row['id']),connect() as c:
            check_payment_order(row);c.execute('BEGIN IMMEDIATE')
            if kind.endswith('REFUNDED'):
                amount=resource.get('amount',{}); cents=Decimal(amount.get('value','-1'))*100
                if amount.get('currency_code')!='USD' or cents<=0 or cents!=int(cents): raise Problem('payment_amount_mismatch',409)
                refund_id=clean(resource.get('id'),1,100)
                c.execute('INSERT OR IGNORE INTO refunds VALUES (?,?,?)',(refund_id,row['id'],int(cents)))
                refunded=c.execute('SELECT sum(cents) FROM refunds WHERE order_id=?',(row['id'],)).fetchone()[0]
                paid=int(Decimal(row['usd'])*100)
                if refunded>paid: raise Problem('payment_amount_mismatch',409)
                status='refunded' if refunded==paid else 'partially_refunded'
            else: status='review_required'
            c.execute('UPDATE orders SET payment_status=? WHERE id=?',(status,row['id']));payment_phase(c,row['id'],status)
    with connect() as c: c.execute('INSERT OR IGNORE INTO events VALUES (?,?)',(event_id,time.time()))
    return {'ok':True}

def send_outbox():
    host=os.environ.get('SMTP_HOST')
    if not host: return
    with connect() as c: rows=c.execute('SELECT * FROM outbox WHERE sent IS NULL AND next_try<? LIMIT 10',(time.time(),)).fetchall()
    for row in rows:
        try:
            msg=EmailMessage(); msg['Subject']=row['subject']; msg['From']=os.environ.get('SMTP_FROM',SELLER['email']); msg['To']=row['recipient']; msg.set_content(row['body'])
            with smtplib.SMTP(host,int(os.environ.get('SMTP_PORT','587')),timeout=15) as smtp:
                smtp.starttls()
                if os.environ.get('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
                smtp.send_message(msg)
            with connect() as c: c.execute('UPDATE outbox SET sent=? WHERE id=?',(time.time(),row['id']))
        except Exception:
            with connect() as c: c.execute('UPDATE outbox SET attempts=attempts+1,next_try=? WHERE id=?',(time.time()+min(3600,60*2**min(row['attempts'],6)),row['id']))

def worker():
    while True:
        try:
            send_outbox()
            with connect() as c: pending=c.execute("SELECT id FROM orders WHERE payment IN ('card','paypal') AND payment_status IN ('pending','unpaid','failed','cancelled') AND paypal_id IS NOT NULL AND created>? LIMIT 20",(time.time()-86400*3,)).fetchall()
            for row in pending:
                try: reconcile(row['id'])
                except Problem: pass
        except Exception:
            import traceback; traceback.print_exc()
        time.sleep(30)

def authenticated(env):
    cookie=env.get('HTTP_COOKIE',''); match=re.search(r'(?:^|;\s*)db_admin=([a-f0-9]+)',cookie)
    if not match: raise Problem('unauthorized',401)
    with connect() as c:
        if not c.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(match[1].encode()).hexdigest(),time.time())).fetchone(): raise Problem('unauthorized',401)

def application(env,start):
    headers=[('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY')]
    code=200; path=env.get('PATH_INFO','/'); method=env['REQUEST_METHOD']
    try:
        if method not in ['GET','HEAD','POST']: raise Problem('method_not_allowed',405)
        if method=='POST':
            if path!='/api/paypal/webhook' and env.get('HTTP_ORIGIN')!=ORIGIN: raise Problem('invalid_origin',403)
            length=int(env.get('CONTENT_LENGTH') or 0)
            if length>32768: raise Problem('too_large',413)
            if not env.get('CONTENT_TYPE','').startswith('application/json'): raise Problem('json_required',415)
            payload=json.loads(env['wsgi.input'].read(length))
            if not isinstance(payload,dict): raise Problem('invalid_fields')
        else: payload={}
        ip=env.get('REMOTE_ADDR','unknown')
        with connect() as c:
            if path=='/api/config':
                result={'testMode':not PROD,'acceptingOrders':not PROD or not ready_issues(),'paymentMethods':['card','paypal']+(['cash_on_delivery'] if COD else []),'paypal':{'configured':paypal_enabled(),'clientId':PP_ID if paypal_enabled() else None,'environment':PP_ENV},'seller':SELLER,'discountPercent':DISCOUNT,'freeShipping':FREE,'gelPerUsd':str(RATE)}
            elif path=='/api/catalog':
                result=[{**p,'stock':(r['stock'] if (r:=c.execute('SELECT stock FROM inventory WHERE id=?',(p['id'],)).fetchone()) else None)} for p in CAT.values()]
            elif path=='/api/quote' and method=='POST': result=quote(payload,c)
            elif path=='/api/orders' and method=='POST': limited(ip,'orders',10,600); result=create_order(payload,env.get('HTTP_IDEMPOTENCY_KEY','')); code=201
            elif path=='/api/order' and method=='POST':
                limited(ip,'lookup',60); result=view(get_order(c,clean(payload.get('id'),5,40),clean(payload.get('token'),32,128)))
            elif path=='/api/paypal/create-order' and method=='POST':
                limited(ip,'payment',30); result=pay_create(clean(payload.get('id'),5,40),clean(payload.get('token'),32,128))
            elif path in ['/api/paypal/capture-order','/api/payment/capture'] and method=='POST':
                limited(ip,'payment',30)
                row=get_order(c,clean(payload.get('id'),5,40),clean(payload.get('token'),32,128))
                pp=clean(payload.get('orderId'),1,100) if path=='/api/paypal/capture-order' else row['paypal_id']
                result=reconcile(row['id'],pp)
            elif path=='/api/payment/method' and method=='POST':
                limited(ip,'payment',30);result=change_payment_method(clean(payload.get('id'),5,40),clean(payload.get('token'),32,128),payload.get('paymentMethod'))
            elif path=='/api/paypal/cancel-order' and method=='POST':
                limited(ip,'payment',30); result=payment_cancel(clean(payload.get('id'),5,40),clean(payload.get('token'),32,128))
            elif path=='/api/paypal/webhook' and method=='POST': result=webhook(payload,env)
            elif path=='/api/admin/login' and method=='POST':
                limited(ip,'login',5,900)
                if len(ADMIN)<16 or not hmac.compare_digest(str(payload.get('password','')),ADMIN): raise Problem('unauthorized',401)
                token=secrets.token_hex(32); c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),)); c.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+28800))
                headers.append(('Set-Cookie',f'db_admin={token}; HttpOnly; SameSite=Strict; Path=/api/admin; Max-Age=28800'+('; Secure' if PROD else '')));result={'ok':True}
            elif path.startswith('/api/admin/'):
                authenticated(env)
                if path=='/api/admin/orders' and method=='GET': result=[view(r) for r in c.execute('SELECT * FROM orders ORDER BY created DESC LIMIT 500')]
                elif path=='/api/admin/collect' and method=='POST':
                    row=get_order(c,payload.get('id'))
                    if row['payment']!='cash_on_delivery' or row['status']!='delivered': raise Problem('invalid_payment_state',409)
                    c.execute("UPDATE orders SET payment_status='paid' WHERE id=?",(row['id'],))
                    c.execute('INSERT INTO audit(order_id,created,action) VALUES (?,?,?)',(row['id'],time.time(),'cod_collected'))
                    result=view(get_order(c,row['id']))
                elif path=='/api/admin/inventory' and method=='GET': result=[dict(r) for r in c.execute('SELECT * FROM inventory')]
                elif path=='/api/admin/inventory' and method=='POST':
                    ident=payload.get('id'); stock=payload.get('stock')
                    if ident not in CAT or type(stock)!=int or not 0<=stock<=100000: raise Problem('invalid_fields')
                    c.execute('INSERT INTO inventory VALUES (?,?) ON CONFLICT(id) DO UPDATE SET stock=excluded.stock',(ident,stock))
                    c.execute('INSERT INTO audit(order_id,created,action) VALUES (?,?,?)',(None,time.time(),'stock '+ident+' '+str(stock)))
                    result={'ok':True}
                elif path=='/api/admin/readiness': result={'issues':ready_issues(),'unsentEmails':c.execute('SELECT count(*) FROM outbox WHERE sent IS NULL').fetchone()[0],'testMode':not PROD}
                elif path=='/api/admin/logout' and method=='POST':
                    match=re.search(r'db_admin=([a-f0-9]+)',env.get('HTTP_COOKIE','')); c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(match[1].encode()).hexdigest(),)); headers.append(('Set-Cookie','db_admin=; HttpOnly; SameSite=Strict; Path=/api/admin; Max-Age=0'));result={'ok':True}
                elif path=='/api/admin/status' and method=='POST':
                    c.execute('BEGIN IMMEDIATE'); row=get_order(c,payload.get('id')); status=payload.get('status')
                    allowed={'new':['confirmed','cancelled'],'confirmed':['shipped','cancelled'],'shipped':['delivered'],'delivered':[],'cancelled':[]}
                    if status not in allowed[row['status']]: raise Problem('invalid_status',409)
                    if status=='shipped' and row['payment'] in ['card','paypal'] and row['payment_status']!='paid': raise Problem('payment_required',409)
                    if status=='cancelled' and row['payment'] in ['card','paypal']: raise Problem('paypal_review_required',409)
                    if status=='cancelled':
                        for item in json.loads(row['body'])['items']: c.execute('UPDATE inventory SET stock=stock+? WHERE id=?',(item['qty'],item['id']))
                    c.execute('UPDATE orders SET status=? WHERE id=?',(status,row['id'])); c.execute('INSERT INTO audit(order_id,created,action) VALUES (?,?,?)',(row['id'],time.time(),status));result=view(get_order(c,row['id']));enqueue(c,result,'DRIVEBOX '+status+' — '+row['id'])
                else: raise Problem('not_found',404)
            elif path.startswith('/api/'): raise Problem('not_found',404)
            else:
                target=ROOT/path.lstrip('/') if path!='/' else ROOT/'index.html'
                # Never serve database, backend, credentials, source control or server-side catalog.
                rel=target.relative_to(ROOT)
                if any(x.startswith('.') or x=='..' for x in rel.parts) or rel.parts[0] in ['server','data','tests','work'] or target.suffix not in ['.html','.css','.js','.png','.jpg','.jpeg','.webp','.svg','.ico','.txt','.xml'] or not target.is_file(): raise Problem('not_found',404)
                if target.name in ['readme.md']: raise Problem('not_found',404)
                raw=target.read_bytes(); headers.append(('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream'))
                if target.suffix in ['.png','.jpg','.webp']: headers[0]=('Cache-Control','public, max-age=86400')
                start('200 OK',headers); return [b'' if method=='HEAD' else raw]
        raw=json.dumps(result,ensure_ascii=False).encode()
    except Problem as e: code=e.status; raw=json.dumps({'error':e.code}).encode()
    except (ValueError,TypeError,KeyError): code=400; raw=b'{"error":"invalid_fields"}'
    except Exception:
        code=500; raw=b'{"error":"server_error"}'
        import traceback; traceback.print_exc()
    headers.extend([('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(raw)))])
    start(str(code)+' '+{200:'OK',201:'Created',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',409:'Conflict',413:'Payload Too Large',415:'Unsupported Media Type',429:'Too Many Requests',500:'Internal Server Error',502:'Bad Gateway',503:'Service Unavailable'}.get(code,'Error'),headers)
    return [b'' if method=='HEAD' else raw]

if __name__=='__main__':
    from wsgiref.simple_server import make_server
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer
    class Server(ThreadingMixIn,WSGIServer): daemon_threads=True
    threading.Thread(target=worker,daemon=True).start()
    print('DRIVEBOX local server:',ORIGIN,flush=True)
    with make_server('127.0.0.1',int(os.environ.get('PORT','8000')),application,server_class=Server) as httpd: httpd.serve_forever()
