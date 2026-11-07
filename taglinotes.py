"""Taglinotes: gestão local. Python 3.12, apenas biblioteca padrão."""
import calendar
import datetime as dt
import json
import os
import sqlite3
import unicodedata
import uuid
from decimal import InvalidOperation
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'dados'
DATA.mkdir(exist_ok=True)

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c) and c.isalnum())

def due_date(day, cycle, anchor):
    if cycle == 'Semanal':
        return day + dt.timedelta(days=(anchor-day.weekday()) % 7)
    if cycle == 'Mensal':
        candidate = day.replace(day=min(anchor, calendar.monthrange(day.year, day.month)[1]))
        if candidate < day:
            year, month = (day.year+1, 1) if day.month == 12 else (day.year, day.month+1)
            candidate = dt.date(year, month, min(anchor, calendar.monthrange(year, month)[1]))
        return candidate
    return day

class Store:
    def __init__(self, path=DATA/'taglinotes.sqlite'):
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY,name TEXT NOT NULL,cycle TEXT NOT NULL DEFAULT 'Mensal',anchor INTEGER NOT NULL DEFAULT 10);
        CREATE TABLE IF NOT EXISTS aliases(alias TEXT PRIMARY KEY,client INTEGER NOT NULL REFERENCES clients(id));
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,original TEXT NOT NULL,sent_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,client INTEGER NOT NULL REFERENCES clients(id),due TEXT NOT NULL,paid TEXT,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS services(id TEXT PRIMARY KEY,client INTEGER NOT NULL REFERENCES clients(id),date TEXT NOT NULL,description TEXT NOT NULL,cents INTEGER CHECK(cents>=0),due TEXT NOT NULL,message TEXT REFERENCES messages(id),batch TEXT REFERENCES batches(id));
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,at TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL);
        ''')

    def audit(self, action, details):
        self.db.execute('INSERT INTO history(at,action,details) VALUES(?,?,?)',(dt.datetime.now().isoformat(),action,json.dumps(details,ensure_ascii=False)))

    def client(self, name, aliases, cycle, anchor, ident=None):
        if not name.strip(): raise ValueError('Informe o nome do cliente.')
        if cycle not in ('Semanal','Mensal','A definir'): raise ValueError('Periodicidade inválida.')
        if (cycle == 'Semanal' and not 0 <= anchor <= 6) or (cycle == 'Mensal' and not 1 <= anchor <= 31):
            raise ValueError('Semanal: 0=segunda até 6=domingo. Mensal: dia 1 a 31.')
        keys={norm(x) for x in [name]+aliases.split(',') if norm(x)}
        with self.db:
            for key in keys:
                row=self.db.execute('SELECT client FROM aliases WHERE alias=?',(key,)).fetchone()
                if row and row[0]!=ident: raise ValueError('Nome ou alias já pertence a outro cliente: '+key)
            if ident:
                self.db.execute('UPDATE clients SET name=?,cycle=?,anchor=? WHERE id=?',(name.strip(),cycle,anchor,ident))
            else:
                ident=self.db.execute('INSERT INTO clients(name,cycle,anchor) VALUES(?,?,?)',(name.strip(),cycle,anchor)).lastrowid
            for key in keys: self.db.execute('INSERT OR IGNORE INTO aliases VALUES(?,?)',(key,ident))
            self.audit('cliente',{'id':ident,'name':name,'cycle':cycle,'anchor':anchor})
        return ident

    def add(self, client, date, description, cents, original='', source=None, due=None):
        day=dt.date.fromisoformat(date)
        if not description.strip(): raise ValueError('Informe o serviço.')
        if cents is not None and cents < 0: raise ValueError('Valor negativo.')
        c=self.db.execute('SELECT * FROM clients WHERE id=?',(client,)).fetchone()
        if not c: raise ValueError('Cliente inexistente.')
        source=source or 'manual:'+str(uuid.uuid4())
        with self.db:
            existing=self.db.execute('SELECT id FROM services WHERE id=?',(source,)).fetchone()
            if existing: return existing[0]
            self.db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?)',(source,original,date))
            due=due or ('' if c['cycle']=='A definir' else due_date(day,c['cycle'],c['anchor']).isoformat())
            if due:dt.date.fromisoformat(due)
            self.db.execute('INSERT INTO services VALUES(?,?,?,?,?,?,?,NULL)',(source,client,date,description.strip(),cents,due,source))
            self.audit('novo serviço',{'id':source})
        return source

    def group(self, ids, due):
        dt.date.fromisoformat(due)
        if not ids: raise ValueError('Selecione serviços.')
        with self.db:
            rows=[self.db.execute('SELECT * FROM services WHERE id=?',(i,)).fetchone() for i in ids]
            if any(r is None for r in rows): raise ValueError('Serviço inexistente.')
            if len({r['client'] for r in rows})!=1: raise ValueError('Selecione serviços do mesmo cliente.')
            if any(r['batch'] or r['cents'] is None for r in rows): raise ValueError('Confira os valores e selecione serviços ainda não agrupados.')
            ident='ACE-'+uuid.uuid4().hex[:10].upper()
            self.db.execute('INSERT INTO batches VALUES(?,?,?,NULL,?)',(ident,rows[0]['client'],due,dt.date.today().isoformat()))
            self.db.executemany('UPDATE services SET batch=? WHERE id=?',[(ident,i) for i in ids])
            self.audit('fechamento',{'id':ident,'services':ids,'due':due})
        return ident

    def backup(self, path):
        dest=sqlite3.connect(path)
        try:self.db.backup(dest)
        finally:dest.close()

def money(cents):
    return 'Sem valor' if cents is None else ('R$ {:,.2f}'.format(cents/100).replace(',','X').replace('.',',').replace('X','.'))

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.store=Store()
        self.title('Taglinotes • Serviços e cobranças')
        self.geometry('1200x760'); self.minsize(950,600); self.configure(bg='#f4f6f8')
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('Treeview',rowheight=38,font=('Segoe UI',10),background='white',fieldbackground='white',borderwidth=0)
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background='#e8edf2',padding=10)
        style.configure('TButton',font=('Segoe UI',10),padding=(12,8))
        style.configure('TLabel',font=('Segoe UI',10),background='#f4f6f8')
        side=tk.Frame(self,bg='#142a38',width=210);side.pack(side='left',fill='y');side.pack_propagate(False)
        tk.Label(side,text='taglinotes',font=('Segoe UI',24,'bold'),fg='#6ce1bb',bg='#142a38').pack(pady=(35,5))
        tk.Label(side,text='Sua rotina em ordem',fg='#b7c8d2',bg='#142a38').pack(pady=(0,35))
        for title,fn in [('Serviços',self.services),('Clientes e aliases',self.clients),('Acertos e cobranças',self.batches),('Mensagens pendentes',self.pending),('Histórico',self.history),('Salvar backup',self.backup)]:
            tk.Button(side,text=title,command=fn,anchor='w',bg='#142a38',fg='white',activebackground='#284858',activeforeground='white',relief='flat',font=('Segoe UI',11),padx=22,pady=14).pack(fill='x')
        tk.Label(side,text='Local • dados no seu notebook',fg='#b7c8d2',bg='#142a38',wraplength=170).pack(side='bottom',pady=25)
        self.body=tk.Frame(self,bg='#f4f6f8');self.body.pack(fill='both',expand=True,padx=28,pady=24)
        self.services()
        self.store.backup(DATA/'backup-inicializacao.sqlite')

    def base(self,title,subtitle):
        for w in self.body.winfo_children():w.destroy()
        tk.Label(self.body,text=title,font=('Segoe UI',24,'bold'),fg='#142a38',bg='#f4f6f8').pack(anchor='w')
        ttk.Label(self.body,text=subtitle).pack(anchor='w',pady=(5,20))
        self.bar=ttk.Frame(self.body);self.bar.pack(fill='x',pady=(0,16))

    def table(self,columns):
        frame=ttk.Frame(self.body);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='extended')
        for c in columns:tree.heading(c,text=c);tree.column(c,width=130,minwidth=70)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        for tag,color in [('late','#ffe4e6'),('soon','#fff0cc'),('ok','#e0f4ed'),('missing','#e8e5ff')]:tree.tag_configure(tag,background=color)
        return tree

    def safe(self,fn):
        try:fn()
        except (ValueError,sqlite3.Error,InvalidOperation) as e:messagebox.showerror('Confira os dados',str(e),parent=self)

    def services(self):
        self.base('Serviços','Confira os relatos, complete valores e selecione serviços para uma nota.')
        for text,fn in [('Novo serviço',self.new_service),('Ver original / editar',self.edit_service),('Agrupar para nota',self.group),('Atualizar',self.services)]:ttk.Button(self.bar,text=text,command=lambda f=fn:self.safe(f)).pack(side='left',padx=(0,8))
        self.tree=self.table(('Cliente','Data','Serviço','Valor','Prazo','Situação'))
        self.tree.column('Serviço',width=290)
        rows=self.store.db.execute('SELECT s.*,c.name,b.paid,b.due AS batch_due FROM services s JOIN clients c ON c.id=s.client LEFT JOIN batches b ON b.id=s.batch ORDER BY COALESCE(b.due,s.due),s.date').fetchall()
        for r in rows:
            due=r['batch_due'] or r['due'];days=(dt.date.fromisoformat(due)-dt.date.today()).days if due else 99999
            status,tag=('Pago','ok') if r['paid'] else ('Sem valor','missing') if r['cents'] is None else ('Vencido','late') if days<0 else ('Vence hoje' if days==0 else f'Vence em {days} dias','soon') if days<=3 else ('Em acerto' if r['batch'] else 'Em aberto','ok')
            if not due and not r['paid']:status,tag='Definir prazo','missing'
            self.tree.insert('', 'end',iid=r['id'],values=(r['name'],r['date'],r['description'],money(r['cents']),due or 'A definir',status),tags=(tag,))
        self.tree.bind('<Double-1>',lambda e:self.safe(self.edit_service))

    def form(self,title,fields,submit):
        win=tk.Toplevel(self);win.title(title);win.geometry('560x620');win.configure(bg='#f4f6f8');win.transient(self);win.grab_set()
        entries={}
        for label,value in fields:
            ttk.Label(win,text=label).pack(anchor='w',padx=24,pady=(12,3))
            entry=ttk.Entry(win);entry.insert(0,str(value));entry.pack(fill='x',padx=24);entries[label]=entry
        def save():
            try:submit({k:v.get() for k,v in entries.items()});win.destroy()
            except (ValueError,sqlite3.Error,InvalidOperation) as e:messagebox.showerror('Confira os dados',str(e),parent=win)
        ttk.Button(win,text='Salvar',command=save).pack(pady=22)
        return win

    def clients(self):
        self.base('Clientes e aliases','Aliases ignoram acentos, espaços e maiúsculas. Novas regras valem para novos serviços.')
        ttk.Button(self.bar,text='Novo cliente',command=lambda:self.client_form()).pack(side='left')
        ttk.Button(self.bar,text='Editar selecionado',command=lambda:self.safe(lambda:self.client_form(int(self.tree.selection()[0])) if self.tree.selection() else None)).pack(side='left',padx=10)
        self.tree=self.table(('Cliente','Periodicidade','Dia','Aliases'))
        for r in self.store.db.execute('SELECT * FROM clients ORDER BY name'):
            aliases=', '.join(x[0] for x in self.store.db.execute('SELECT alias FROM aliases WHERE client=?',(r['id'],)))
            self.tree.insert('','end',iid=str(r['id']),values=(r['name'],r['cycle'],r['anchor'],aliases))

    def client_form(self,ident=None):
        r=self.store.db.execute('SELECT * FROM clients WHERE id=?',(ident,)).fetchone() if ident else None
        def save(v):self.store.client(v['Nome'],v['Aliases separados por vírgula'],v['Periodicidade: Semanal ou Mensal'],int(v['Dia: semanal 0=seg … 6=dom; mensal 1–31']),ident);self.clients()
        self.form('Cliente',[('Nome',r['name'] if r else ''),('Aliases separados por vírgula',''),('Periodicidade: Semanal ou Mensal',r['cycle'] if r else 'A definir'),('Dia: semanal 0=seg … 6=dom; mensal 1–31',r['anchor'] if r else 1)],save)

    def new_service(self):
        def save(v):
            row=self.store.db.execute('SELECT client FROM aliases WHERE alias=?',(norm(v['Cliente ou alias']),)).fetchone()
            if not row:raise ValueError('Cadastre primeiro o cliente ou alias.')
            from decimal import Decimal
            cents=None if not v['Valor total (R$)'].strip() else int((Decimal(v['Valor total (R$)'].replace(',','.'))*100).quantize(Decimal('1')))
            self.store.add(row[0],v['Data AAAA-MM-DD'],v['Descrição'],cents,v['Mensagem original']);self.services()
        self.form('Novo serviço',[('Cliente ou alias',''),('Data AAAA-MM-DD',dt.date.today()),('Descrição',''),('Valor total (R$)',''),('Mensagem original','')],save)

    def edit_service(self):
        if not self.tree.selection():return
        ident=self.tree.selection()[0]
        r=self.store.db.execute('SELECT s.*,m.original FROM services s LEFT JOIN messages m ON m.id=s.message WHERE s.id=?',(ident,)).fetchone()
        if r['batch']:
            messagebox.showinfo('Serviço agrupado',r['description']+'\n\nMensagem original:\n'+(r['original'] or '(registro manual)')+'\n\nValores bloqueados após fechamento.');return
        def save(v):
            from decimal import Decimal
            cents=None if not v['Valor total (R$)'].strip() else int((Decimal(v['Valor total (R$)'].replace(',','.'))*100).quantize(Decimal('1')))
            if v['Vencimento AAAA-MM-DD']:dt.date.fromisoformat(v['Vencimento AAAA-MM-DD'])
            if not v['Descrição'].strip() or (cents is not None and cents<0):raise ValueError('Descrição ou valor inválido.')
            with self.store.db:
                self.store.audit('edição de serviço',{'antes':dict(r),'depois':v})
                self.store.db.execute('UPDATE services SET description=?,cents=?,due=? WHERE id=?',(v['Descrição'],cents,v['Vencimento AAAA-MM-DD'],ident))
            self.services()
        win=self.form('Conferir atendimento',[('Descrição',r['description']),('Valor total (R$)','' if r['cents'] is None else r['cents']/100),('Vencimento AAAA-MM-DD',r['due'])],save)
        ttk.Label(win,text='Mensagem original • preservada').pack(anchor='w',padx=24)
        text=tk.Text(win,height=10,wrap='word',font=('Segoe UI',10));text.insert('1.0',r['original'] or '(registro manual)');text.configure(state='disabled');text.pack(fill='both',expand=True,padx=24,pady=12)

    def group(self):
        ids=self.tree.selection()
        if not ids:return
        due=simpledialog.askstring('Fechamento','Data de vencimento (AAAA-MM-DD):',initialvalue=dt.date.today().isoformat(),parent=self)
        if due:self.store.group(ids,due);self.batches()

    def batches(self):
        self.base('Acertos e cobranças','Agrupamentos prontos para conferência. O aplicativo prepara o texto; não emite nota fiscal.')
        ttk.Button(self.bar,text='Ver texto para nota',command=lambda:self.safe(self.batch_text)).pack(side='left')
        ttk.Button(self.bar,text='Registrar pagamento',command=lambda:self.safe(self.pay)).pack(side='left',padx=10)
        self.tree=self.table(('Acerto','Cliente','Serviços','Total','Vencimento','Situação'))
        for r in self.store.db.execute('SELECT b.*,c.name,COUNT(s.id) qty,SUM(s.cents) total FROM batches b JOIN clients c ON c.id=b.client JOIN services s ON s.batch=b.id GROUP BY b.id ORDER BY b.due'):
            days=(dt.date.fromisoformat(r['due'])-dt.date.today()).days
            status,tag=('Pago','ok') if r['paid'] else ('Vencido','late') if days<0 else ('Prazo próximo','soon') if days<=3 else ('A cobrar','ok')
            self.tree.insert('','end',iid=r['id'],values=(r['id'],r['name'],r['qty'],money(r['total']),r['due'],status),tags=(tag,))

    def batch_text(self):
        if not self.tree.selection():return
        ident=self.tree.selection()[0]
        rows=self.store.db.execute('SELECT s.*,c.name FROM services s JOIN clients c ON c.id=s.client WHERE s.batch=? ORDER BY s.date',(ident,)).fetchall()
        text=rows[0]['name']+'\n'+ '\n'.join(f"{r['date']} — {r['description']} — {money(r['cents'])}" for r in rows)+'\nTotal: '+money(sum(r['cents'] for r in rows))
        win=tk.Toplevel(self);win.title('Rascunho para nota • '+ident);area=tk.Text(win,wrap='word',font=('Segoe UI',12));area.pack(fill='both',expand=True);area.insert('1.0',text)

    def pay(self):
        if not self.tree.selection():return
        ident=self.tree.selection()[0]
        if messagebox.askyesno('Pagamento','Confirmar recebimento integral deste acerto?'):
            with self.store.db:self.store.db.execute('UPDATE batches SET paid=? WHERE id=?',(dt.date.today().isoformat(),ident));self.store.audit('pagamento',{'id':ident})
            self.batches()

    def pending(self):
        self.base('Mensagens pendentes','Relatos preservados que ainda não geraram serviço. Consulte a execução com erro no n8n para retentar.')
        ttk.Button(self.bar,text='Atualizar',command=self.pending).pack(side='left')
        tree=self.table(('Origem','Recebida em','Mensagem original'))
        tree.column('Mensagem original',width=550)
        for r in self.store.db.execute('SELECT m.* FROM messages m LEFT JOIN services s ON s.message=m.id WHERE s.id IS NULL ORDER BY m.sent_at DESC'):
            tree.insert('','end',values=(r['id'],r['sent_at'],r['original']))
        def show(event):
            if tree.selection():messagebox.showinfo('Mensagem original',tree.item(tree.selection()[0])['values'][2],parent=self)
        tree.bind('<Double-1>',show)

    def history(self):
        self.base('Histórico','Registro das operações realizadas no Taglinotes.')
        tree=self.table(('Quando','Ação','Detalhes'))
        for r in self.store.db.execute('SELECT * FROM history ORDER BY id DESC LIMIT 500'):tree.insert('','end',values=(r['at'],r['action'],r['details']))

    def backup(self):
        target=filedialog.asksaveasfilename(title='Salvar backup',defaultextension='.sqlite',initialfile='Taglinotes-'+dt.date.today().isoformat()+'.sqlite')
        if target:self.store.backup(target);messagebox.showinfo('Backup','Backup salvo com sucesso.')

if __name__=='__main__':App().mainloop()
