"""Pruebas locales de reserva, cupos y confirmación SMTP. No envían correos reales."""
import os, tempfile, unittest, threading, json, urllib.request, urllib.error, importlib
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from pathlib import Path

class Reservas(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();os.environ.update(BLOOM_DB=str(Path(cls.tmp.name)/'test.sqlite3'), BLOOM_ADMIN_PASSWORD='test-only-credential-123', BLOOM_CAPACITY='{"0":2,"1":1,"2":1,"3":2,"4":2,"5":1}')
  cls.s=importlib.import_module('server');cls.http=ThreadingHTTPServer(('127.0.0.1',0),cls.s.Handler);threading.Thread(target=cls.http.serve_forever,daemon=True).start();cls.url='http://127.0.0.1:'+str(cls.http.server_port)
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
 def post(self,payload):
  r=urllib.request.Request(self.url+'/api/order',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  try:res=urllib.request.urlopen(r,timeout=5)
  except urllib.error.HTTPError as e:res=e
  with res:return res.status,json.loads(res.read())
 def test_01_reservation_and_duplicate(self):
  d={'request_id':'test-request-001','kind':'catalog','name':'Cliente de prueba','phone':'0990000000','notes':'Prueba local','consent':True,'items':[{'id':0,'qty':2}]}; status,a=self.post(d);self.assertEqual(status,201);self.assertTrue(a['code'].startswith('BB-'));status,b=self.post(d);self.assertEqual(status,200);self.assertEqual(a['code'],b['code']);
  with self.s.db() as c:
   row=c.execute('SELECT status,total FROM orders WHERE code=?',(a['code'],)).fetchone();self.assertEqual(tuple(row),('confirmado',500));self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox WHERE code=?',(a['code'],)).fetchone()[0],1)
  d['request_id']='test-request-002';self.assertEqual(self.post(d)[0],400)
 def test_02_custom(self):
  status,r=self.post({'request_id':'test-custom-001','kind':'custom','name':'Cliente de prueba','phone':'0990000000','notes':'Ramo rojo con tarjeta','budget':10,'consent':True});self.assertEqual(status,201);self.assertEqual(r['status'],'cotizacion')
 def test_03_smtp_465_and_587(self):
  for port,attr in [('465','SMTP_SSL'),('587','SMTP')]:
   with patch.dict(os.environ,{'BLOOM_NOTIFY_EMAIL':'test@example.invalid','SMTP_HOST':'localhost','SMTP_USER':'test@example.invalid','SMTP_PASSWORD':'test-only','SMTP_PORT':port}),patch.object(self.s.smtplib,attr) as smtp:
    self.assertTrue(self.s.mail('PRUEBA','Sin correo real'));smtp.return_value.__enter__.return_value.send_message.assert_called_once()
 def test_04_smtp_failure(self):
  with patch.dict(os.environ,{'BLOOM_NOTIFY_EMAIL':'test@example.invalid','SMTP_HOST':'localhost','SMTP_USER':'test@example.invalid','SMTP_PASSWORD':'test-only','SMTP_PORT':'465'}),patch.object(self.s.smtplib,'SMTP_SSL',side_effect=OSError): self.assertFalse(self.s.mail('PRUEBA','Sin correo real'))
if __name__=='__main__':unittest.main(verbosity=2)
