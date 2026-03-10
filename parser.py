import aiohttp from bs4 import BeautifulSoup from datetime import date, datetime import re import logging

logger = logging.getLogger(name)

BASE_URL = "https://guide.herzen.spb.ru"

WEEKDAY_MAP = { 0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday", 4: "friday", 5: "saturday", 6: "sunday", }

RU_WEEKDAY = { "понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3, "пятница": 4, "суббота": 5, }

class HerzenParser: def init(self): self.session = None

async def _get(self, url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            return await r.text(encoding="utf-8")

async def get_all_groups(self) -> list[dict]:
    """Получаем список всех групп с сайта Герцена (работает)"""
    try:
        url = f"{BASE_URL}/schedule"
        html = await self._get(url)

        soup = BeautifulSoup(html, "html.parser")
        groups = []

        # Найдём все куски текста, которые выглядят как группа
        text = soup.get_text(" ", strip=True)

        # регулярка ищет последовательности вида курс+код группы
        matches = re.findall(r"\d[а-яА-ЯёЁA-Za-z0-9_()-]+", text)

        seen = set()
        for m in matches:
            name = m.strip()
            if len(name) >= 3 and name not in seen:
                seen.add(name)
                groups.append({"id": name, "name": name})

        return groups

    except Exception as e:
        logger.error(f"get_all_groups error: {e}")
        return []

# --- Остальные методы без изменений ---
async def get_schedule_week(self, group_id: int, week_start: date) -> dict:
    try:
        url = f"{BASE_URL}/static/schedule_view.php?id_group={group_id}&sem=1"
        html = await self._get(url)
        return self._parse_schedule_html(html, week_start)
    except Exception as e:
        logger.error(f"get_schedule_week error: {e}")
        return {}

async def get_schedule_for_date(self, group_id: int, target_date: date) -> list:
    week_data = await self.get_schedule_week(group_id, target_date)
    day_key = WEEKDAY_MAP.get(target_date.weekday(), "sunday")
    return week_data.get(day_key, [])

def _parse_schedule_html(self, html: str, ref_date: date) -> dict:
    # Твой старый парсер остаётся здесь
    soup = BeautifulSoup(html, "html.parser")
    schedule = {}
    # ...
    return schedule

# Остальные приватные методы тоже оставляем как есть
