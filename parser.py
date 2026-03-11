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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
        # Пытаемся взять с новой страницы расписания, там меньше шансов поймать 404
        html = await self._get(f"{BASE_URL}/schedule/")
        if not html: html = await self._get(f"{BASE_URL}/static/schedule.php")
        
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        for a in soup.find_all("a", href=re.compile(r"id_group=(\d+)")):
            g_id = re.search(r"id_group=(\d+)", a["href"]).group(1)
            name = a.get_text(strip=True)
            if g_id not in seen and name:
                seen.add(g_id)
                groups.append({"id": g_id, "name": name})
        return sorted(groups, key=lambda x: x['name'])

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        # Формируем URL для просмотра по датам
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/by-dates")
        if not html: return []

        # Формат даты на сайте: DD.MM.YYYY
        day, month, year = target_date.split('-')[2], target_date.split('-')[1], target_date.split('-')[0]
        site_date = f"{day}.{month}.{year}"
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Ищем заголовок дня
        day_header = soup.find(string=re.compile(re.escape(site_date)))
        if not day_header: return []

        # Ищем ближайший контейнер с парами (обычно следующий за заголовком или родительский)
        parent = day_header.find_parent(["div", "li", "tr", "section"])
        # Ищем список пар после этой даты до следующей даты
        lessons_raw = []
        sibling = parent.find_next_sibling()
        while sibling and not any(char.isdigit() for char in sibling.get_text()[:10] if char == '.'):
            lessons_raw.append(sibling)
            sibling = sibling.find_next_sibling()
            if not sibling or len(lessons_raw) > 20: break

        lessons = []
        # Парсим накопленные блоки
        search_area = [parent] + lessons_raw
        for area in search_area:
            for item in area.find_all(["div", "li"], recursive=True):
                text = item.get_text(" ", strip=True)
                time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
                if time_match and len(text) > 15:
                    t_start, t_end = time_match.groups()
                    
                    # Извлекаем данные
                    moodle = item.find("a", href=re.compile(r"moodle|clms"))
                    teacher = item.find("a", href=re.compile(r"atlas|teacher"))
                    
                    # Чистим название (убираем время и номер пары)
                    cleaned = text.replace(time_match.group(0), "").strip()
                    cleaned = re.sub(r"^\d+\.", "", cleaned).strip()
                    
                    subject = cleaned.split("ауд.")[0].split("лекц")[0].split("практ")[0].strip()
                    room = "ауд. " + cleaned.split("ауд.")[-1].split(",")[0].strip() if "ауд." in cleaned else "—"

                    lessons.append({
                        "time_start": t_start,
                        "time_end": t_end,
                        "subject": subject or "Дисциплина",
                        "type": "Лекция" if "лекц" in text.lower() else ("Практика" if "практ" in text.lower() else "Занятие"),
                        "teacher": teacher.get_text(strip=True) if teacher else "Не указан",
                        "teacher_url": f"{BASE_URL}{teacher['href']}" if teacher else "",
                        "room": room,
                        "moodle_url": moodle["href"] if moodle else ""
                    })

        # Фильтр дублей
        final = []
        seen_keys = set()
        for l in lessons:
            key = f"{l['time_start']}-{l['subject']}"
            if key not in seen_keys:
                final.append(l)
                seen_keys.add(key)
        return final
