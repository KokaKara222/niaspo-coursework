"""Проверка нового платежа при отключении рабочего узла Swarm."""
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

here = Path(__file__).resolve().parent
lines = []
url = 'http://127.0.0.1:28082/payments'

def log(value):
    line = f'{datetime.now().astimezone().isoformat(timespec="seconds")} {value}'
    print(line, flush=True)
    lines.append(line)

def nodes(*args):
    return subprocess.check_output(['docker','compose','-f',str(here/'nodes.yaml'),*args],text=True).strip()

def manager(*args):
    return nodes('exec','-T','manager','docker',*args)

def sql(query):
    container = manager('ps','-q','-f','label=com.docker.swarm.service.name=payments_db')
    return manager('exec',container,'psql','-U','payments','-d','payments','-Atqc',query)

def wait_for_both_workers():
    for _ in range(100):
        current = manager('service','ps','payments_app','--filter','desired-state=running',
                          '--format','{{.Node}} {{.CurrentState}}')
        running = {line.split()[0] for line in current.splitlines() if ' Running ' in line}
        if running == {'worker1','worker2'}:
            return
        time.sleep(2)
    raise RuntimeError(current)

def post(amount,key):
    body = json.dumps(dict(sender=sender,recipient=recipient,amount=amount)).encode()
    req = Request(url,data=body,headers={'Content-Type':'application/json','Idempotency-Key':key})
    with urlopen(req,timeout=10) as res:
        payment=json.load(res)
        log(f'POST {url} {key} {body.decode()} HTTP {res.status} {payment}')
        assert payment['status']=='SUCCEEDED'
        return payment

wait_for_both_workers()
log(manager('service','ps','payments_app','--filter','desired-state=running','--format','{{.Name}} {{.Node}} {{.CurrentState}}'))
sender,recipient = map(int,sql('INSERT INTO accounts(user_id,balance) VALUES (1,100000),(2,20000) RETURNING id').splitlines())
first=post(15000,'first')
try:
    nodes('stop','worker1')
    for _ in range(60):
        if manager('node','inspect','worker1','-f','{{.Status.State}}') == 'down':
            break
        time.sleep(1)
    else:
        raise RuntimeError('Swarm не зарегистрировал остановку worker1')
    log(manager('node','ls','--format','{{.Hostname}} {{.Status}}'))
    assert post(15000,'first') == first
    assert post(5000,'second')['id'] != first['id']
    rows=sql(f'SELECT balance FROM accounts WHERE id IN ({sender},{recipient}) ORDER BY id').splitlines()
    count=sql(f'SELECT count(*) FROM payments WHERE sender={sender}')
    log(f'Остатки (коп.) {rows}, платежей {count}')
    assert rows==['80000','40000'] and count=='2'
finally:
    nodes('up','-d','--force-recreate','worker1')
wait_for_both_workers()
log(manager('service','ps','payments_app','--filter','desired-state=running','--format','{{.Name}} {{.Node}} {{.CurrentState}}'))
path=here.parent/'results'/datetime.now().strftime('swarm-%Y%m%d-%H%M%S.txt')
path.write_text('\n'.join(lines)+'\n')
print(path)
