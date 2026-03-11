# -*- coding: utf-8 -*-
import aiohttp
import json
import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"

class HerzenParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
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
        html = await self._get(f"{BASE_URL}/schedule")
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        for a in soup.find_all("a", href=True):
            m = re.search(r"/schedule/(\d+)", a["href"])
            if m and (name := a.get_text(strip=True)):
                gid = m.group(1)
                if gid not in seen:
                    seen.add(gid)
                    groups.append({"id": gid, "name": name})
        return groups

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        # Приводим дату к строке YYYY-MM-DD
        date_str = target_date if isinstance(target_date, str) else target_date.strftime("%Y-%m-%d")
        
        # Используем обычный URL занятий (он самый стабильный)
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/classes")
        if not html: return []

        logger.info(f"Parsing schedule for {date_str}")
        return self._parse_universal_html(html, date_str)

    def _parse_universal_html(self, html: str, target_date_str: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        # Формат на сайте: 11.03.2026
        ddmmyyyy = f"{target_date_str[8:10]}.{target_date_str[5:7]}.{target_date_str[:4]}"
        
        lessons = []
        
        # Ищем блок, где упоминается наша дата
        # На сайте Герцена расписание часто лежит в <li> или <div>
        day_elements = soup.find_all(["li", "div", "tr"], string=re.compile(re.escape(ddmmyyyy)))
        
        if not day_elements:
            # Если не нашли по тексту, ищем во всей странице элементы, похожие на пары
            # (это план Б, если структура совсем поплыла)
            day_elements = [soup]

        for element in day_elements:
            # Ищем родителя, который содержит список пар (обычно это <ul> или большой <div>)
            parent = element.find_parent(["ul", "ol", "div", "body"])
            if not parent: continue
            
            # Находим все строки, где есть время (например, 09:00 - 10:30)
            items = parent.find_all(["li", "div", "p"])
            for item in items:
                text = item.get_text(" ", strip=True)
                
                # Проверяем, что в этой строке есть время и она относится к нашей дате
                # (или мы уже внутри контейнера этой даты)
                time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
                if time_match:
                    # Извлекаем данные
                    t_start, t_end = time_match.groups()
                    
                    # Чистим текст от номера пары и времени, чтобы достать название
                    clean_text = re.sub(r"^\d+\.", "", text) # убираем "1."
                    clean_text = clean_text.replace(f"{t_start}-{t_end}", "").strip()
                    
                    # Ссылки
                    moodle_a = item.find("a", href=re.compile(r"moodle"))
                    teacher_a = item.find("a", href=re.compile(r"atlas|teachers"))
                    
                    # Убираем "Занятие" и "лекц/практ" из названия предмете
                    subject = clean_text.split("лекц")[0].split("практ")[0].split("ауд.")[0].strip()

                    lessons.append({
                        "time_start": t_start,
                        "time_end": t_end,
                        "subject": subject or "Занятие",
                        "type": "Лекция/Практика" if "лекц" in text or "практ" in text else "Занятие",
                        "teacher": teacher_a.get_text(strip=True) if teacher_a else "",
                        "teacher_url": teacher_a["href"] if teacher_a else "",
                        "room": "ауд. " + text.split("ауд.")[-1].split(",")[0].strip() if "ауд." in text else "",
                        "moodle_url": moodle_a["href"] if moodle_a else "",
                        "is_remote": any(x in text.lower() for x in ["дистанц", "видеолекция", "zoom", "bbb"])
                    })
            
            # Если нашли пары для этой даты, выходим из цикла поиска по элементам
            if lessons: break
            
        return lessons
