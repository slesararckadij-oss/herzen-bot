# -*- coding: utf-8 -*-
import aiohttp
import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"

class HerzenParser:
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    async def _get(self, url: str) -> str:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=15) as r:
                    return await r.text(encoding="utf-8", errors="replace") if r.status == 200 else ""
            except Exception: return ""

    async def get_all_groups(self):
        html = await self._get(f"{BASE_URL}/static/schedule.php")
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        for a in soup.find_all("a", href=re.compile(r"id_group=(\d+)")):
            g_id = re.search(r"id_group=(\d+)", a["href"]).group(1)
            name = a.get_text(strip=True)
            if g_id not in seen and name:
                seen.add(g_id)
                groups.append({"id": g_id, "name": name})
        return sorted(groups, key=lambda x: x['name'])

    async def get_schedule_for_date(self, group_id, target_date):
        # target_date приходит как YYYY-MM-DD
        y, m, d = target_date.split('-')
        # Сайт Герцена принимает дату в формате DD.MM.YYYY через параметры
        url = f"{BASE_URL}/schedule/{group_id}/classes?date={d}.{m}.{y}"
        
        html = await self._get(url)
        if not html: return []
        
        soup = BeautifulSoup(html, "html.parser")
        lessons = []
        
        # Ищем все блоки с парами. На этой странице они обычно в <li> или в таблице
        items = soup.find_all(["li", "tr"], class_=re.compile(r"level|lesson|class"))
        if not items:
            items = soup.find_all(["li", "tr"]) # Запасной вариант

        for item in items:
            text = item.get_text(" ", strip=True)
            time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
            
            if time_match and len(text) > 20:
                # Проверка на дубли
                if any(l['time_start'] == time_match.group(1) for l in lessons): continue
                
                teacher = item.find("a", href=re.compile(r"teachers|atlas"))
                moodle = item.find("a", href=re.compile(r"moodle|clms"))
                
                # Вытягиваем название предмета
                sub_part = text.split(time_match.group(0))[-1]
                subject = sub_part.split("ауд.")[0].split("лекц")[0].split("практ")[0].strip()
                subject = re.sub(r"^\d+\.", "", subject).strip()

                if len(subject) < 3: continue

                lessons.append({
                    "time_start": time_match.group(1),
                    "time_end": time_match.group(2),
                    "subject": subject,
                    "type": "Лекция" if "лекц" in text.lower() else ("Практика" if "практ" in text.lower() else "Занятие"),
                    "teacher": teacher.get_text(strip=True) if teacher else "Не указан",
                    "teacher_url": f"{BASE_URL}{teacher['href']}" if teacher and not teacher['href'].startswith('http') else (teacher['href'] if teacher else ""),
                    "room": "ауд. " + text.split("ауд.")[-1].split(",")[0].strip() if "ауд." in text.lower() else "—",
                    "moodle_url": moodle["href"] if moodle else ""
                })
        
        return sorted(lessons, key=lambda x: x['time_start'])
