import os, sqlite3, json, re, secrets, hmac, base64, time, smtplib, ssl, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.message import EmailMessage
from datetime import datetime, timezone
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv('BLOOM_DB',str(ROOT/'data'/'bloom.sqlite3')))
DB.parent.mkdir(parents=True,exist_ok=True)
PASSWORD=os.getenv('BLOOM_ADMIN_PASSWORD','')
if len(PASSWORD)<12: raise SystemExit('Configura BLOOM_ADMIN_PASSWORD (mínimo 12 caracteres).')
PRICES={0:('Rosa Signature',250),1:('Ramo Bloom',600),2:('Sweet Bloom',850),3:('Fresh Sip',150),4:('Fruit Bite',200),5:('Bloom Combo',450)}
CAPACITY={int(k):int(v) for k,v in json.loads(os.getenv('BLOOM_CAPACITY','{"0":6,"1":3,"2":2,"3":12,"4":12,"5":2}')).items()}
EVENTS={'visit','chat_open','chat_question','photo_view','add_to_cart','cart_open','custom_open'}
lock=threading.Lock(); buckets=defaultdict(list); last_interaction_mail=0

def db():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row;return c
with db() as c:
 c.executescript('''CREATE TABLE IF NOT EXISTS orders(code TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,kind TEXT,created TEXT,name TEXT,phone TEXT,items TEXT,notes TEXT,budget REAL,total INTEGER,status TEXT DEFAULT 'pendiente'); CREATE TABLE IF NOT EXISTS outbox(code TEXT PRIMARY KEY,subject TEXT NOT NULL,body TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS events(day TEXT,type TEXT,product INTEGER,count INTEGER DEFAULT 0,PRIMARY KEY(day,type,product));''')

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def mail(subject,body):
 if not all(os.getenv(x) for x in ('BLOOM_NOTIFY_EMAIL','SMTP_HOST','SMTP_USER','SMTP_PASSWORD')): return False
 try:
  msg=EmailMessage();msg['From']=os.environ['SMTP_USER'];msg['To']=os.environ['BLOOM_NOTIFY_EMAIL'];msg['Subject']=subject;msg.set_content(body)
  port=int(os.getenv('SMTP_PORT','587'));ctx=ssl.create_default_context()
  if port==465:
   with smtplib.SMTP_SSL(os.environ['SMTP_HOST'],port,context=ctx,timeout=10) as m:m.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);m.send_message(msg)
  else:
   with smtplib.SMTP(os.environ['SMTP_HOST'],port,timeout=10) as m:m.starttls(context=ctx);m.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);m.send_message(msg)
  return True
 except Exception as e: print('Aviso no enviado:',type(e).__name__,flush=True);return False
def outbox_worker():
 while True:
  try:
   with db() as c: rows=c.execute('SELECT * FROM outbox WHERE sent=0 ORDER BY rowid LIMIT 20').fetchall()
   for row in rows:
    ok=mail(row['subject'],row['body'])
    with db() as c:c.execute('UPDATE outbox SET sent=?,attempts=attempts+1 WHERE code=?',(int(ok),row['code']))
  except Exception as e:print('Cola correo:',type(e).__name__,flush=True)
  time.sleep(30)
def notify(subject,body):threading.Thread(target=mail,args=(subject,body),daemon=True).start()

def limited(ip,scope,limit):
 key=(ip,scope);t=time.monotonic()
 with lock:
  if len(buckets)>5000:
   for k in list(buckets):
    if not buckets[k] or t-buckets[k][-1]>60:del buckets[k]
  b=buckets[key];b[:]=[x for x in b if t-x<60]
  if len(b)>=limit:return True
  b.append(t);return False

def string(d,k,limit,required=False):
 v=d.get(k,'');
 if not isinstance(v,str) or len(v)>limit or (required and len(v.strip())<2):raise ValueError('Revisa '+k)
 return v.strip()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass # no IP logging by default
 def send(self,status,data,ctype='application/json; charset=utf-8',extra=None):
  if isinstance(data,dict) or isinstance(data,list):data=json.dumps(data,ensure_ascii=False).encode()
  elif isinstance(data,str):data=data.encode()
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
  for k,v in (extra or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(data)
 def admin(self):
  try: a=base64.b64decode(self.headers.get('Authorization','').removeprefix('Basic '),validate=True).decode();ok=hmac.compare_digest(a.encode(),('admin:'+PASSWORD).encode())
  except Exception:ok=False
  if not ok:self.send(401,{'error':'Acceso privado'},extra={'WWW-Authenticate':'Basic realm="Bloom propietario"'});
  return ok
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/':return self.send(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
  if path=='/api/health':return self.send(200,{'service':'bloom'})
  if path in ('/admin','/api/admin'):
   if not self.admin():return
   if path=='/admin':return self.send(200,(ROOT/'admin.html').read_bytes(),'text/html; charset=utf-8')
   with db() as c:
    orders=[dict(r) for r in c.execute('SELECT * FROM orders ORDER BY created DESC')];events=[dict(r) for r in c.execute('SELECT * FROM events ORDER BY day DESC')]
   for o in orders:o['items']=json.loads(o['items']);o.pop('request_id',None)
   return self.send(200,{'orders':orders,'events':events,'email_configured':all(os.getenv(x) for x in ('BLOOM_NOTIFY_EMAIL','SMTP_HOST','SMTP_USER','SMTP_PASSWORD'))})
  self.send(404,{'error':'No encontrado'})
 def do_POST(self):
  global last_interaction_mail
  path=self.path.split('?')[0]
  if path not in ('/api/order','/api/event','/api/admin/status','/api/admin/delete'):return self.send(404,{'error':'No encontrado'})
  if path.startswith('/api/admin') and not self.admin():return
  if limited(self.client_address[0],path,100 if path=='/api/event' else 15):return self.send(429,{'error':'Demasiadas solicitudes; espera un minuto'})
  try:
   # JSON only; reject cross-site browser requests.
   if self.headers.get('Sec-Fetch-Site')=='cross-site' or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Solicitud no válida')
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=16000:raise ValueError('Tamaño de solicitud no válido')
   d=json.loads(self.rfile.read(n));
   if not isinstance(d,dict):raise ValueError('Formato no válido')
   if path=='/api/event':
    typ=d.get('type');prod=d.get('product',-1)
    if typ not in EVENTS or type(prod) is not int or prod not in [-1,*PRICES]:raise ValueError('Evento no válido')
    with db() as c:c.execute('INSERT INTO events VALUES (?,?,?,1) ON CONFLICT(day,type,product) DO UPDATE SET count=count+1',(now()[:10],typ,prod))
    if typ in ('chat_open','cart_open','custom_open') and os.getenv('BLOOM_NOTIFY_INTERACTIONS')=='1':
     with lock:
      if time.monotonic()-last_interaction_mail>900 or last_interaction_mail==0:
       last_interaction_mail=time.monotonic();notify('Bloom & Bite: nueva interacción','Se registró una interacción anónima: '+typ+'. Consulta el panel. Avisos de interacción limitados a uno cada 15 minutos.')
    return self.send(200,{'ok':True})
   if path.startswith('/api/admin'):
    code=string(d,'code',40,True)
    with db() as c:
     if path.endswith('delete'):
      c.execute('DELETE FROM outbox WHERE code=?',(code,));c.execute('DELETE FROM orders WHERE code=?',(code,))
     else:
      status=d.get('status');
      if status not in ('pendiente','confirmado','entregado','cancelado'):raise ValueError('Estado no válido')
      c.execute('UPDATE orders SET status=? WHERE code=?',(status,code))
    return self.send(200,{'ok':True})
   if d.get('consent') is not True:raise ValueError('Se requiere autorización')
   req=string(d,'request_id',100,True);name=string(d,'name',80,True);phone=string(d,'phone',25,True);notes=string(d,'notes',600)
   if not re.fullmatch(r'[+0-9 ()-]{7,25}',phone) or len(re.sub(r'\D','',phone))<7:raise ValueError('Teléfono no válido')
   kind=d.get('kind');items=[];total=None;budget=None
   if kind=='catalog':
    raw=d.get('items');
    if not isinstance(raw,list) or not 1<=len(raw)<=6:raise ValueError('Pedido vacío o no válido')
    seen=set();total=0
    for item in raw:
     if not isinstance(item,dict):raise ValueError('Producto no válido')
     i,q=item.get('id'),item.get('qty')
     if type(i) is not int or i not in PRICES or i in seen or type(q) is not int or not 1<=q<=30:raise ValueError('Cantidad o producto no válido')
     seen.add(i);nm,p=PRICES[i];items.append({'id':i,'name':nm,'qty':q,'unit_cents':p});total+=p*q
   elif kind=='custom':
    if len(notes)<5:raise ValueError('Describe tu pedido')
    budget=d.get('budget')
    if budget is not None and (type(budget) not in (float,int) or not 1<=budget<=200):raise ValueError('Presupuesto no válido')
   else:raise ValueError('Tipo de solicitud no válido')
   with db() as c:
    c.execute('BEGIN IMMEDIATE');existing=c.execute('SELECT code FROM orders WHERE request_id=?',(req,)).fetchone()
    if existing:return self.send(200,{'code':existing['code']})
    if kind=='catalog':
     used=defaultdict(int)
     for row in c.execute("SELECT items FROM orders WHERE kind='catalog' AND status!='cancelado'"):
      for item in json.loads(row['items']):used[item['id']]+=item['qty']
     for item in items:
      if used[item['id']]+item['qty']>CAPACITY.get(item['id'],0):raise ValueError('Sin cupo suficiente para '+item['name']+'. Reduce la cantidad o consulta al equipo.')
    code='BB-'+secrets.token_hex(5).upper();c.execute('INSERT INTO orders(code,request_id,kind,created,name,phone,items,notes,budget,total) VALUES(?,?,?,?,?,?,?,?,?,?)',(code,req,kind,now(),name,phone,json.dumps(items,ensure_ascii=False),notes,budget,total))
    lines=['Nueva reserva Mateo Bloom & Bite', 'Código: '+code,'Cliente: '+name,'Teléfono: '+phone,'Tipo: '+kind]
    lines += [str(x['qty'])+' × '+x['name'] for x in items]
    lines += ['Total: '+('$'+f'{total/100:.2f}' if total is not None else 'Por cotizar'),'Presupuesto: '+(str(budget) if budget is not None else 'No indicado'),'Preferencias: '+notes,'Estado: '+('Reserva registrada; coordinar retiro' if kind=='catalog' else 'Solicitud de cotización; pendiente de precio y disponibilidad')]
    if kind=='catalog':c.execute("UPDATE orders SET status='confirmado' WHERE code=?",(code,))
    c.execute('INSERT INTO outbox(code,subject,body) VALUES(?,?,?)',(code,'Mateo Bloom & Bite | Nueva reserva '+code,'\n'.join(lines)))
   return self.send(201,{'code':code,'status':'registrado' if kind=='catalog' else 'cotizacion'})
  except (ValueError,TypeError,KeyError,OverflowError) as e:return self.send(400,{'error':str(e)[:150]})
  except Exception as e:print(type(e).__name__,flush=True);return self.send(500,{'error':'No se pudo guardar; vuelve a intentar'})
if __name__=='__main__':
 threading.Thread(target=outbox_worker,daemon=True).start()
 host=os.getenv('BLOOM_HOST','127.0.0.1');port=int(os.getenv('PORT','8080'));print(f'Bloom: http://{host}:{port} — panel /admin',flush=True);ThreadingHTTPServer((host,port),Handler).serve_forever()
