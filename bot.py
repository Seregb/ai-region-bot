import os
import re
import requests
import feedparser
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import time
import json
import urllib.parse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Константы
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# === 1. КЛЮЧЕВЫЕ СЛОВА (БЕЗ "ИИ") ===

# Основные ИИ-ключи. Их наличие сразу указывает на технологическую тематику.
AI_KEYWORDS = [
    "искусственный интеллект",
    "нейросеть",
    "машинное обучение",
    "чат-бот",
    "ИИ-ассистент",
    "LLM",
    "роботизация",
]

# Ключевые слова, которые сами по себе не гарантируют ИИ-тематику (могут встречаться
# в новостях про госуслуги, границы, инфраструктуру и т.п.), но усиливают сигнал,
# если найдены вместе с основными ИИ-ключами или словами контекста.
AI_CONTEXT_REQUIRED_KEYWORDS = [
    "распознавание лиц",
    "компьютерное зрение",
    "видеоаналитика",
    "биометрия",
    "умный город",
    "голосовой помощник",
    "голосовое управление",
    "телемедицина",
    "электронное правительство",
    "госуслуги",
    "цифровизация",
    "автоматизация процессов",
]

# Ключевые слова, которые НЕ являются самостоятельными ИИ-маркерами, а служат
# для верификации контекста. Если в тексте найдены ИИ-ключи (AI_KEYWORDS), но
# ни одно из этих слов — новость, скорее всего, не про ИИ.
AI_CONTEXT_WORDS = [
    # Явные ИИ/ML-термины
    "искусственный интеллект", "нейросет", "машинно обучен", "алгоритм",
    "deep learn", "neural network", "трансформер", "токен", "модель",
    # Технологические слова
    "технолог", "цифров", "автоматизац", "робот", "беспилотн", "дрон",
    "дата-цент", "серверн", "программ", "интернет вещей", "iot",
    # Действия с ИИ
    "внедр", "разрабат", "обуча", "анализир", "распознав", "генерир",
    "предсказ", "классифик", "обработка данных", "компьютерн зрение",
]

# Короткие ключи (<=3 символов) проверяются как целые слова (\b), чтобы не
# совпадать с другими словами: IoT ≠ Patriot, LLM ≠ SmallTalk.
AI_SHORT_KEYWORDS = {"IoT", "LLM"}

# === 2. РЕГИОНЫ РОССИИ ===
RUSSIAN_REGIONS = [
    "Московская область", "Подмосковье", "Ленинградская область",
    "Архангельская область", "Вологодская область", "Мурманская область",
    "Новгородская область", "Псковская область", "Калининградская область",
    "Тверская область", "Ярославская область", "Костромская область",
    "Ивановская область", "Владимирская область", "Рязанская область",
    "Тульская область", "Калужская область", "Смоленская область",
    "Брянская область", "Курская область", "Орловская область",
    "Липецкая область", "Тамбовская область", "Воронежская область",
    "Белгородская область", "Нижегородская область",
    "Кировская область", "Саратовская область", "Пензенская область",
    "Ульяновская область", "Самарская область",
    "Оренбургская область", "Свердловская область",
    "Челябинская область", "Курганская область", "Тюменская область",
    "Омская область", "Новосибирская область", "Томская область",
    "Кемеровская область", "Иркутская область",
    "Амурская область", "Магаданская область", "Сахалинская область",
    "Краснодарский край", "Ставропольский край", "Алтайский край",
    "Красноярский край", "Пермский край", "Приморский край",
    "Хабаровский край", "Камчатский край", "Забайкальский край",
    "Республика Татарстан", "Татарстан", "Казань",
    "Республика Башкортостан", "Башкортостан", "Уфа",
    "Москва", "Санкт-Петербург", "Петербург",
    "Новосибирск", "Екатеринбург", "Нижний Новгород",
    "Челябинск", "Самара", "Омск", "Ростов-на-Дону",
    "Красноярск", "Пермь", "Воронеж", "Волгоград", "Краснодар",
    "Саратов", "Тюмень", "Ижевск", "Барнаул",
    "Ульяновск", "Иркутск", "Хабаровск", "Ярославль", "Владивосток",
    "Томск", "Оренбург", "Кемерово", "Новокузнецк",
    "Рязань", "Астрахань", "Пенза", "Липецк",
    "Киров", "Чебоксары", "Тула", "Калининград",
    "Курск", "Ставрополь", "Сочи", "Улан-Удэ", "Тверь",
    "Магнитогорск", "Иваново", "Брянск", "Белгород",
    "Владимир", "Архангельск", "Чита", "Калуга",
    "Симферополь", "Смоленск", "Волжский", "Курган", "Орел",
    "Вологда", "Саранск", "Мурманск", "Якутск", "Тамбов"
]

# === 3. РЕГИОНАЛЬНЫЕ ДОМЕНЫ ===
REGIONAL_DOMAINS = {
    "74.ru": "Челябинская область", "chel.kp.ru": "Челябинская область",
    "e1.ru": "Свердловская область", "ural.kp.ru": "Свердловская область",
    "nsk.kp.ru": "Новосибирская область", "ngs.ru": "Новосибирская область",
    "krsk.kp.ru": "Красноярский край", "ngs24.ru": "Красноярский край",
    "perm.kp.ru": "Пермский край",
    "ufa.kp.ru": "Башкортостан", "ufa1.ru": "Башкортостан", "mkset.ru": "Башкортостан",
    "kazan.kp.ru": "Татарстан", "116.ru": "Татарстан",
    "nnov.kp.ru": "Нижегородская область", "nn.ru": "Нижегородская область",
    "samara.kp.ru": "Самарская область", "63.ru": "Самарская область",
    "volgograd.kp.ru": "Волгоградская область", "v1.ru": "Волгоградская область",
    "rostov.kp.ru": "Ростовская область", "161.ru": "Ростовская область",
    "kuban.kp.ru": "Краснодарский край", "93.ru": "Краснодарский край",
    "crimea.kp.ru": "Крым", "stav.kp.ru": "Ставропольский край",
    "mosregtoday.ru": "Московская область", "47news.ru": "Ленинградская область",
    "klops.ru": "Калининградская область", "kaliningrad.kp.ru": "Калининградская область",
    "hab.kp.ru": "Хабаровский край", "vlad.kp.ru": "Приморский край",
    "sakhalin.kp.ru": "Сахалинская область", "kamchatka.kp.ru": "Камчатский край",
    "kuzbass.kp.ru": "Кемеровская область", "altai.kp.ru": "Алтайский край",
    "irk.kp.ru": "Иркутская область", "chita.kp.ru": "Забайкальский край"
}

# === 4. RSS ЛЕНТЫ ===
RSS_FEEDS = [
    {"name": "РИА Новости", "url": "https://ria.ru/export/rss2/index.xml", "timeout": 15},
    {"name": "ТАСС", "url": "https://tass.ru/rss/v2.xml", "timeout": 15},
    {"name": "Интерфакс", "url": "https://www.interfax.ru/rss.asp", "timeout": 15},
    {"name": "Ведомости", "url": "https://www.vedomosti.ru/rss/news", "timeout": 15},
    {"name": "Известия", "url": "https://iz.ru/export/rss", "timeout": 15},
    {"name": "Коммерсантъ", "url": "https://www.kommersant.ru/RSS/main.xml", "timeout": 30},
    {"name": "CNews", "url": "https://www.cnews.ru/inc/rss/news.xml", "timeout": 15},
    {"name": "Российская газета", "url": "https://rg.ru/xml/index.xml", "timeout": 15},
    {"name": "Lenta.ru", "url": "https://lenta.ru/rss", "timeout": 15},
    {"name": "PrimaMedia (Владивосток)", "url": "https://primamedia.ru/rss/", "timeout": 15},
    {"name": "HabInfo (Хабаровск)", "url": "https://habinfo.ru/rss/", "timeout": 15},
    {"name": "AmurMedia (Хабаровск)", "url": "https://amurmedia.ru/rss/", "timeout": 15},
    {"name": "SakhalinMedia (Сахалин)", "url": "https://sakhalinmedia.ru/rss/", "timeout": 15},
    {"name": "KamchatkaMedia (Камчатка)", "url": "https://kamchatkamedia.ru/rss/", "timeout": 15},
]

def fetch_with_retry(url: str, timeout: int = 15, max_retries: int = 3) -> requests.Response:
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        status_forcelist=[408, 429, 500, 502, 503, 504],
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=timeout)

def extract_region_from_url(url: str) -> Tuple[bool, str]:
    try:
        domain = urllib.parse.urlparse(url).netloc.replace('www.', '')
        for reg_domain, region_name in REGIONAL_DOMAINS.items():
            if reg_domain in domain:
                return True, region_name
    except:
        pass
    return False, ""

def is_regional_news(title: str, summary: str, url: str) -> Tuple[bool, str]:
    text = (title + " " + summary).lower()
    for region in RUSSIAN_REGIONS:
        if region.lower() in text:
            return True, region
    found_in_url, region_from_url = extract_region_from_url(url)
    if found_in_url:
        return True, region_from_url
    return False, ""

def contains_ai_keywords(text: str) -> Tuple[bool, List[str]]:
    """
    Проверяет текст на наличие ИИ-ключевых слов.
    Короткие ключи (<=3 символов) — IoT, LLM — проверяются как целые слова
    (граница слова \b), чтобы не совпадать с другими словами:
      IoT ≠ Patriot, LLM ≠ SmallTalk.
    Длинные фразы — "искусственный интеллект", "машинное обучение" —
    проверяются обычным вхождением подстроки.
    """
    if not text:
        return False, []

    found = []
    for keyword in AI_KEYWORDS:
        kw_stripped = keyword.strip().lower()

        if len(kw_stripped) <= 3 and keyword.upper().replace("-", "") == kw_stripped.upper():
            # Короткая аббревиатура — ищем как целое слово (граница слова)
            pattern = r'\b' + re.escape(kw_stripped) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                found.append(keyword)
        else:
            # Длинная фраза — обычное вхождение подстроки
            if kw_stripped in text.lower():
                found.append(keyword)

    return len(found) > 0, found


def is_ai_context_valid(title: str, summary: str, found_keywords: List[str]) -> bool:
    """
    Проверяет, что найденные ИИ-ключи действительно в технологическом контексте.

    Алгоритм:
    1. Считаем, сколько слов из AI_CONTEXT_WORDS найдено в тексте.
    2. Если среди найденных ключей есть короткие (IoT, LLM) — требую >= 2
       контекстных слов (короткие ключи часто ложноположительные).
    3. Для длинных фраз ("искусственный интеллект") — достаточно >= 1
       контекстного слова.
    4. Если найден AI_CONTEXT_REQUIRED_KEYWORDS ("госуслуги", "биометрия" и т.п.),
       они считаются как 0.5 контекстных слова каждый (максимум 1).

    Отсекает ложноположительные, где ИИ-ключи встречаются вне технологического
    контекста: новости про Patriot, госуслуги без связи с ИИ и т.п.
    """
    if not found_keywords:
        return False

    text = title + " " + summary
    text_lower = text.lower()

    # Считаем найденные контекстные слова
    context_count = 0
    for word in AI_CONTEXT_WORDS:
        if word in text_lower:
            context_count += 1

    # Проверяем, есть ли среди найденных ключей короткие (IoT, LLM)
    has_short_keyword = any(k in AI_SHORT_KEYWORDS for k in found_keywords)

    # AI_CONTEXT_REQUIRED_KEYWORDS ("госуслуги", "биометрия" и т.п.) дают
    # дополнительный бонус, но не больше 1 балла
    context_required_count = sum(1 for k in AI_CONTEXT_REQUIRED_KEYWORDS if k.lower() in text_lower)
    context_bonus = min(context_required_count * 0.5, 1)

    total_score = context_count + context_bonus

    if has_short_keyword:
        # Короткие ключи — повышенная планка (IoT ≠ Patriot)
        return total_score >= 2
    else:
        # Длинные фразы — достаточно минимального контекста
        return total_score >= 1


def fetch_rss_feed(feed_info: Dict) -> List[Dict]:
    try:
        print(f"📡 Загрузка {feed_info['name']}...")
        response = fetch_with_retry(feed_info['url'], feed_info.get('timeout', 15))
        if response.status_code != 200:
            print(f"❌ Ошибка HTTP {response.status_code} для {feed_info['name']}")
            return []
        
        feed = feedparser.parse(response.text)
        items = []
        cutoff_time = datetime.now() - timedelta(days=1)
        
        for entry in feed.entries[:50]:
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])
            
            if published and published < cutoff_time:
                continue
            
            summary = entry.summary if hasattr(entry, 'summary') else ""
            text = entry.title + " " + summary
            
            has_keyword, found_keywords = contains_ai_keywords(text)
            if not has_keyword:
                continue

            # Проверяем контекст: найденные ключи должны быть в технологическом
            # окружении. Отсекает ложноположительные (Patriot→IoT, госуслуги без ИИ).
            if not is_ai_context_valid(entry.title, summary, found_keywords):
                continue

            is_regional, region_name = is_regional_news(entry.title, summary, entry.link)
            if not is_regional:
                continue
            
            items.append({
                'title': entry.title,
                'url': entry.link,
                'published': published.strftime('%d.%m.%Y %H:%M') if published else 'Дата не указана',
                'source': feed_info['name'],
                'keywords': found_keywords,
                'region': region_name
            })
            print(f"✅ Найдено: {entry.title[:80]}... [ключи: {found_keywords}]")
        
        return items
    except requests.exceptions.Timeout:
        print(f"⏱️ Таймаут при загрузке {feed_info['name']}")
        return []
    except Exception as e:
        print(f"❌ Ошибка при загрузке {feed_info['name']}: {e}")
        return []

def search_all_feeds() -> List[Dict]:
    all_results = []
    seen_urls = set()
    
    print("\n" + "="*70)
    print("🔍 ПОИСК ПО RSS ЛЕНТАМ")
    print("="*70)
    print(f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"📡 RSS лент: {len(RSS_FEEDS)}")
    print(f"🏙️ Регионов в базе: {len(RUSSIAN_REGIONS)}")
    print(f"🔗 Рег. доменов: {len(REGIONAL_DOMAINS)}")
    print(f"🔑 Ключевых слов: {len(AI_KEYWORDS)}")
    print("="*70)
    
    for feed in RSS_FEEDS:
        items = fetch_rss_feed(feed)
        for item in items:
            if item['url'] not in seen_urls:
                all_results.append(item)
                seen_urls.add(item['url'])
        time.sleep(1)
    
    return all_results

def format_telegram_message(results: List[Dict]) -> str:
    if not results:
        return f"""❌ РЕГИОНАЛЬНЫХ НОВОСТЕЙ ПО ТЕМЕ НЕ НАЙДЕНО

Дата: {datetime.now().strftime('%d.%m.%Y')}
Проверено RSS лент: {len(RSS_FEEDS)}
Ключевых слов: {len(AI_KEYWORDS)}
Регионов в базе: {len(RUSSIAN_REGIONS)}"""
    
    by_region = {}
    for item in results:
        region = item['region']
        if region not in by_region:
            by_region[region] = []
        by_region[region].append(item)
    
    text = f"""📊 НОВОСТИ ПО ТЕМЕ "ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ"
Дата: {datetime.now().strftime('%d.%m.%Y')}
📰 Всего найдено: {len(results)}
🗺️ Регионов с новостями: {len(by_region)}
🔑 Ключевых слов: {len(AI_KEYWORDS)}

"""
    
    for i, item in enumerate(results[:20], 1):
        title = item['title'][:150] + "..." if len(item['title']) > 150 else item['title']
        keywords = ", ".join(item['keywords'])
        text += f"\n{i}. {title}\n"
        text += f"   🗺️ {item['region']}\n"
        text += f"   🕒 {item['published']}\n"
        text += f"   📍 {item['source']}\n"
        text += f"   🔑 {keywords}\n"
        text += f"   🔗 {item['url']}\n"
    
    return text

def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for i, part in enumerate(parts, 1):
            response = requests.post(
                url,
                json={
                    "chat_id": CHAT_ID,
                    "text": f"📊 Новости (часть {i}/{len(parts)})\n\n{part}"
                },
                timeout=10
            )
            print(f"Telegram статус части {i}: {response.status_code}")
            time.sleep(1)
    else:
        response = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )
        print(f"Telegram статус: {response.status_code}")

def handler(event, context):
    print("="*70)
    print("🚀 RSS ПАРСЕР НОВОСТЕЙ ОБ ИИ")
    print("="*70)
    
    if not TELEGRAM_TOKEN:
        return {"statusCode": 500, "body": "❌ Отсутствует TELEGRAM_TOKEN"}
    
    results = search_all_feeds()
    message = format_telegram_message(results)
    send_telegram_message(message)
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "found": len(results),
            "regions": len(set(r['region'] for r in results))
        })
    }

# === ДОБАВЬ ЭТОТ БЛОК В САМЫЙ КОНЕФ ФАЙЛА (Я ЕГО УЖЕ ДОБАВИЛ ВЫШЕ) ===
if __name__ == "__main__":
    # Запуск функции handler без параметров (event, context не нужны для локального запуска)
    try:
        result = handler(None, None)
        print(f"Задача завершена. Статус: {result.get('statusCode')}")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
