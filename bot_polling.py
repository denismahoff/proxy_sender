import json as json_lib
import os
import random
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3

urllib3.disable_warnings()

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip() or "8943253858:AAFAHf0yh5p2SvhaiZFb0q8jCRi8LIOxRXY"
OFFSET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_offset.txt")

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/kort0881/telegram-proxy-collector/main/proxy_all.txt",
    "https://raw.githubusercontent.com/SoliSpirit/mtproto/master/all_proxies.txt",
]

PING_TIMEOUT = 3


def load_offset():
    try:
        with open(OFFSET_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


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
                    return lines
        except Exception:
            pass
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
        resp = requests.get(f"http://ip-api.com/json/{server}?fields=countryCode", timeout=5)
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
    russian_proxies = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(verify_proxy, link): link for link in proxy_links}
        for future in as_completed(futures):
            result = future.result()
            if result:
                russian_proxies.append(result)
    return russian_proxies


def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data=json_lib.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }), headers={"Content-Type": "application/json"}, timeout=10)


def handle_proxy_command(chat_id):
    send_message(chat_id, "Ищу свежие прокси, это займёт до 5 минут...")

    all_proxies = fetch_proxies()
    if not all_proxies:
        send_message(chat_id, "Не удалось загрузить прокси")
        return

    russian_proxies = filter_russian_proxies(all_proxies)
    if not russian_proxies:
        send_message(chat_id, "Российские прокси не найдены")
        return

    selected = random.sample(russian_proxies, min(5, len(russian_proxies)))
    message = "Свежие MTProto прокси (РФ):\n\n"
    for i, proxy in enumerate(selected, 1):
        message += f"{i}. {proxy}\n"
    message += "\nНажмите для подключения в Telegram."
    send_message(chat_id, message)


def poll_once():
    offset = load_offset()

    resp = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
        params={"offset": offset, "timeout": 2},
        timeout=10,
    )
    data = resp.json()

    new_offset = offset
    for update in data.get("result", []):
        new_offset = update["update_id"] + 1
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")

        if not chat_id:
            continue

        if text == "/start":
            send_message(chat_id, "Доступные команды:\n\n/proxy — получить список из 5 свежих MTProto прокси (РФ)\n\nОтвет приходит в течение 5 минут.")
        elif text == "/proxy":
            handle_proxy_command(chat_id)

    save_offset(new_offset)
    print(f"Обработано. Offset: {offset} -> {new_offset}")


if __name__ == "__main__":
    poll_once()
