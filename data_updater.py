import schedule
import time
import subprocess
from datetime import datetime

def run_scripts():
    print(f"[{datetime.now()}] Запуск скриптов...")
    try:
        subprocess.run(["python", "parsers/parser_kancleroptshilovo.py"], check=True)
        subprocess.run(["python", "parsers/parser_officemag.p"], check=True)
        print("Скрипты выполнены.")
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении скрипта: {e}")

schedule.every().day.at("00:00").do(run_scripts)

print("Планировщик запущен. Ожидаем запуск в 00:00...")
while True:
    schedule.run_pending()
    time.sleep(1)