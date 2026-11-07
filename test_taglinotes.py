import datetime as dt
import tempfile
import unittest
from pathlib import Path
from taglinotes import Store, norm, due_date

class Tests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(norm(' Café '),norm('CAFE'))
        self.assertEqual(due_date(dt.date(2027,2,10),'Mensal',31),dt.date(2027,2,28))
        self.assertEqual(due_date(dt.date(2026,12,20),'Mensal',10),dt.date(2027,1,10))
        self.assertEqual(due_date(dt.date(2026,11,7),'Semanal',0),dt.date(2026,11,9))

    def test_transactions(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            s=Store(Path(folder)/'test.sqlite')
            c=s.client('Cliente A','Café,Cafe','Mensal',10)
            other=s.client('Cliente B','','Semanal',4)
            with self.assertRaises(ValueError):s.client('Outro','Cafe','Mensal',10)
            a=s.add(c,'2026-11-07','Teste',1200,'original','test:1')
            self.assertEqual(a,s.add(c,'2026-11-07','não substituir',9999,'novo','test:1'))
            self.assertEqual(s.db.execute('SELECT original FROM messages').fetchone()[0],'original')
            b=s.add(other,'2026-11-07','Outro',1000)
            with self.assertRaises(ValueError):s.group([a,b],'2026-11-10')
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)
            s.group([a],'2026-11-10')
            with self.assertRaises(ValueError):s.group([a],'2026-11-10')
            s.backup(Path(folder)/'backup.sqlite')
            s.db.close()

if __name__=='__main__':unittest.main()
