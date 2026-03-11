# -*- coding: utf-8 -*-
import aiohttp
import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"

class HerzenParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        }

    async def _get(self, url: str) -> str:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=15) as r:
                    if r.status != 200: return ""
                    return await r.text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.error(f"Network error: {e}")
                return ""

    async def get_all_groups(self) -> list:
        # Берем список групп с главной страницы расписания
        html = await self._get(f"{BASE_URL}/static/schedule.php")
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        # Ищем все ссылки, которые ведут на конкретные группы
        for a in soup.find_all("a", href=re.compile(r"id_group=\d+")):
            m = re.search(r"id_group=(\d+)", a["href"])
            if m and (name := a.get_text(strip=True)):
                g_id = m.group(1)
                if g_id not in seen:
                    seen.add(g_id)
                    groups.append({"id": g_id, "name": name})
        return sorted(groups, key=lambda x: x['name'])

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        date_str = target_date if isinstance(target_date, str) else target_date.strftime("%Y-%m-%d")
        # Переходим в раздел по датам
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/by-dates")
        if not html: return []

        # Формат даты на сайте: DD.MM.YYYY
        site_date = f"{date_str[8:10]}.{date_str[5:7]}.{date_str[:4]}"
        soup = BeautifulSoup(html, "html.parser")
        
        # Ищем текст с датой
        date_element = soup.find(string=re.compile(re.escape(site_date)))
        if not date_element: return []

        # Находим контейнер дня
        day_container = date_element.find_parent(["div", "section", "li", "td", "tr"])
        # Поднимаемся чуть выше, чтобы захватить весь список пар этого дня
        for _ in range(4):
            if day_container:
                # Если нашли тег, внутри которого есть список (ul/ol) или много div - это наш блок
                if day_container.find_all(["li", "tr"]): break
                day_container = day_container.parent
        
        if not day_container: return []

        lessons = []
        # Ищем строки с парами
        for item in day_container.find_all(["li", "tr", "div"], recursive=True):
            text = item.get_text(" ", strip=True)
            time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
            
            if time_match and len(text) > 10:
                t_start, t_end = time_match.groups()
                
                # Поиск ссылок
                moodle_a = item.find("a", href=re.compile(r"moodle|clms"))
                teacher_a = item.find("a", href=re.compile(r"atlas|teacher"))
                
                # Чистим название предмета
                sub_text = text.replace(time_match.group(0), "").strip()
                sub_text = re.sub(r"^\d+\.", "", sub_text).strip() # Удаляем номер пары
                
                # Отделяем предмет от аудитории
                subject = sub_text.split("ауд.")[0].split("лекц")[0].split("практ")[0].strip()
                subject = subject.replace("()", "").strip()

                if not subject or len(subject) < 3: continue

                t_url = teacher_a["href"] if teacher_a else ""
                if t_url and not t_url.startswith("http"):
                    t_url = f"{BASE_URL}{t_url}"

                lessons.append({
                    "time_start": t_start,
                    "time_end": t_end,
                    "subject": subject,
                    "type": "Лекция" if "лекц" in text.lower() else ("Практика" if "практ" in text.lower() else "Занятие"),
                    "teacher": teacher_a.get_text(strip=True) if teacher_a else "Преподаватель не указан",
                    "teacher_url": t_url,
                    "room": "ауд. " + sub_text.split("ауд.")[-1].split(",")[0].strip() if "ауд." in sub_text else "—",
                    "moodle_url": moodle_a["href"] if moodle_a else "",
                })

        # Убираем дубликаты
        unique = []
        seen = set()
        for l in lessons:
            k = f"{l['time_start']}-{l['subject']}"
            if k not in seen:
                seen.add(k)
                unique.append(l)
        return unique
