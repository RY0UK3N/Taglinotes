"""API local: token exclusivo, fila persistente e gravação idempotente."""
import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from taglinotes import DATA, Store, norm

TOKEN_PATH=DATA/'integration-token.txt'
if not TOKEN_PATH.exists():TOKEN_PATH.write_text(secrets.token_urlsafe(32),encoding='utf-8')
TOKEN=TOKEN_PATH.read_text(encoding='utf-8').strip()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=="/health":return self.reply(200,{"app":"Taglinotes","status":"ok"})
        self.reply(404,{"error":"Rota inexistente"})
    def reply(self,status,data):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def do_POST(self):
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):return self.reply(401,{'error':'Não autorizado'})
        store=None
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=100000:raise ValueError('Tamanho inválido')
            data=json.loads(self.rfile.read(size))
            source=str(data['chat_id'])+':'+str(data['message_id'])
            store=Store()
            if self.path=='/v1/messages':
                original=data['text'];sent=data['sent_at']
                if not isinstance(original,str) or not isinstance(sent,str):raise ValueError('Mensagem inválida')
                with store.db:store.db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?)',(source,original,sent))
                return self.reply(200,{'id':source,'stored':True})
            if self.path=='/v1/services':
                msg=store.db.execute('SELECT * FROM messages WHERE id=?',(source,)).fetchone()
                if not msg:raise ValueError('Salve a mensagem original primeiro')
                client=store.db.execute('SELECT client FROM aliases WHERE alias=?',(norm(data['client']),)).fetchone()
                if not client:
                    name=data['client'].strip()
                    if len(norm(name))<2:raise ValueError('Informe o cliente')
                    client=(store.client(name,'','A definir',1),)
                cents=data.get('amount_cents')
                if cents is not None and (type(cents)!=int or cents<0):raise ValueError('Valor deve ser inteiro em centavos')
                ident=store.add(client[0],data['date'],data['description'],cents,msg['original'],source)
                return self.reply(200,{'id':ident,'stored':True})
            self.reply(404,{'error':'Rota inexistente'})
        except (ValueError,KeyError,TypeError) as exc:self.reply(422,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'Falha ao salvar; tente novamente'})
        finally:
            if store:store.db.close()

if __name__=='__main__':HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
