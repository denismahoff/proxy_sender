import os
import random
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3

LAST_MSG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_msg_id.txt")

urllib3.disable_warnings()

TELEGRAM_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "8943253858:AAFAHf0yh5p2SvhaiZFb0q8jCRi8LIOxRXY")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID", "1017061793")

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/kort0881/telegram-proxy-collector/main/proxy_all.txt",
    "https://raw.githubusercontent.com/SoliSpirit/mtproto/master/all_proxies.txt",
]

PING_TIMEOUT = 3


def fetch_proxies():
    for url in PROXY_SOURCES:
        try:
            response = requests.get(url, timeout=10, verify=False)
            if response.status_code == 200:
                lines = [
                    line.strip()
                    for line in response.text.split("\n")
                    if line.strip().startswith("tg://proxy") or line.strip().startswith("https://t.me/proxy")
                ]
                if lines:
                    print(f"Получено {len(lines)} прокси из {url}")
                    return lines
        except Exception as e:
            print(f"Ошибка при загрузке {url}: {e}")
    return []


def extract_server_info(proxy_link):
    parsed = urllib.parse.urlparse(proxy_link)
    params = urllib.parse.parse_qs(parsed.query)
    server = params.get("server", [None])[0]
    port = int(params.get("port", [443])[0])
    return server, port


def is_russian_ip(server):
    try:
        socket.inet_aton(server)
    except OSError:
        return False

    try:
        resp = requests.get(
            f"http://ip-api.com/json/{server}?fields=countryCode",
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("countryCode") == "RU"
    except Exception:
        pass
    return False


def check_ping(server, port):
    try:
        sock = socket.create_connection((server, port), timeout=PING_TIMEOUT)
        sock.close()
        return True
    except (socket.timeout, OSError):
        return False


def verify_proxy(proxy_link):
    server, port = extract_server_info(proxy_link)
    if not server:
        return None

    if not is_russian_ip(server):
        return None

    if not check_ping(server, port):
        return None

    return proxy_link


def filter_russian_proxies(proxy_links, max_workers=20):
    print(f"Проверяю {len(proxy_links)} прокси на принадлежность к РФ...")
    russian_proxies = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(verify_proxy, link): link for link in proxy_links}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                russian_proxies.append(result)
                print(f"  [{i}/{len(proxy_links)}] OK: {extract_server_info(result)[0]}")
            if i % 50 == 0:
                print(f"  Проверено {i}/{len(proxy_links)}...")

    print(f"Найдено российских прокси: {len(russian_proxies)}")
    return russian_proxies


def load_last_msg_id():
    try:
        with open(LAST_MSG_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def save_last_msg_id(msg_id):
    with open(LAST_MSG_FILE, "w") as f:
        f.write(str(msg_id))


def delete_old_message():
    msg_id = load_last_msg_id()
    if not msg_id:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": msg_id,
    }, timeout=10)

    if resp.status_code == 200 and resp.json().get("ok"):
        print(f"Удалено старое сообщение {msg_id}")
    else:
        print(f"Не удалось удалить {msg_id}: {resp.text}")


def send_to_telegram(proxies):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TG_BOT_TOKEN или TG_CHAT_ID не заданы")
        return

    delete_old_message()

    selected = random.sample(proxies, min(3, len(proxies)))

    message = "Свежие MTProto прокси (РФ):\n\n"
    for i, proxy in enumerate(selected, 1):
        message += f"{i}. {proxy}\n"
    message += "\nНажмите для подключения в Telegram."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }, timeout=10)

    if resp.status_code == 200:
        msg_id = resp.json()["result"]["message_id"]
        save_last_msg_id(msg_id)
        print(f"Отправлено! message_id={msg_id}")
    else:
        print(f"Ошибка отправки: {resp.text}")


def main():
    all_proxies = fetch_proxies()

    if not all_proxies:
        print("Прокси не получены")
        return

    russian_proxies = filter_russian_proxies(all_proxies)

    if not russian_proxies:
        print("Российские прокси не найдены")
        return

    send_to_telegram(russian_proxies)


if __name__ == "__main__":
    main()
