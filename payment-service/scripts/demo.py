"""Проверка HTTP API и остатков в PostgreSQL. Запуск из папки проекта."""
from datetime import datetime
import json
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

base = "http://127.0.0.1:18080/payments"
report = []

def log(line):
    print(line)
    report.append(line)

def sql(statement):
    return subprocess.check_output(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "payments", "-d",
         "payments", "-v", "ON_ERROR_STOP=1", "-qAt", "-c", statement], text=True
    ).strip()

def http(url, body=None, key=None):
    headers = {"Content-Type": "application/json", "Idempotency-Key": key} if key else {}
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers)
    log(f"{req.get_method()} {url} {headers} {body or ''}")
    with urlopen(req, timeout=10) as response:
        result = json.load(response)
        log(f"HTTP {response.status} {json.dumps(result, ensure_ascii=False)}")
        return result

# Новая пара счетов позволяет повторить опыт, сохранив предыдущие платежи.
sender, recipient = map(int, sql("""
    INSERT INTO accounts(user_id, balance) VALUES (1, 100000), (2, 20000) RETURNING id
""").splitlines())

def balances():
    return list(map(int, sql(f"SELECT balance FROM accounts WHERE id IN ({sender},{recipient}) ORDER BY id").splitlines()))

def scenario(title, amount, key, expected, status):
    log(f"\n{title}")
    log(f"Остатки до, коп.: {balances()}")
    result = http(base, dict(sender=sender, recipient=recipient, amount=amount), key)
    after = balances()
    log(f"Остатки после, коп.: {after}")
    assert after == expected and result["status"] == status
    return result

first = scenario("1. Перевод 150 рублей", 15000, "transfer-1", [85000, 35000], "SUCCEEDED")
repeat = scenario("2. Повтор с тем же ключом", 15000, "transfer-1", [85000, 35000], "SUCCEEDED")
assert first == repeat
declined = scenario("3. Недостаток средств", 100000, "transfer-2", [85000, 35000], "DECLINED")
assert http(base + "/" + first["id"]) == first
count = sql(f"SELECT count(*) FROM payments WHERE sender = {sender}")
assert count == "2"
log(f"Число записей о платежах: {count}. Все проверки пройдены.")
path = Path("results") / datetime.now().strftime("demo-%Y%m%d-%H%M%S-%f.txt")
path.parent.mkdir(exist_ok=True)
path.write_text("\n".join(report) + "\n", encoding="utf-8")
print(path)
