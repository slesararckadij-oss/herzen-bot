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
            if g_id not in seen:
                seen.add(g_id)
                groups.append({"id": g_id, "name": a.get_text(strip=True)})
        return sorted(groups, key=lambda x: x['name'])

    async def get_schedule_for_date(self, group_id, target_date):
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/by-dates")
        if not html: return []
        
        # Превращаем 2026-03-11 в 11.03.2026
        d, m, y = target_date.split('-')[2], target_date.split('-')[1], target_date.split('-')[0]
        site_date = f"{d}.{m}.{y}"
        
        soup = BeautifulSoup(html, "html.parser")
        lessons = []
        
        # Находим конкретный заголовок даты
        date_header = soup.find(string=re.compile(re.escape(site_date)))
        if not date_header: return []

        # Берем родительский контейнер, где лежит дата, и идем по следующим элементам
        curr = date_header.find_parent(["div", "tr", "li"])
        if not curr: curr = date_header

        # Ищем все элементы до следующей даты
        for sibling in curr.find_all_next():
            # Если встретили другую дату — стоп
            if re.search(r"\d{2}\.\d{2}\.\d{4}", sibling.get_text()[:12]):
                if site_date not in sibling.get_text(): break
            
            text = sibling.get_text(" ", strip=True)
            time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
            
            if time_match and "ауд." in text.lower():
                # Чтобы не дублировать один и тот же блок (так как find_all_next заходит внутрь)
                if any(l['time_start'] == time_match.group(1) for l in lessons): continue
                
                teacher = sibling.find("a", href=re.compile(r"teachers"))
                moodle = sibling.find("a", href=re.compile(r"moodle"))
                
                # Чистка названия
                subject = text.split(time_match.group(0))[-1].split("ауд.")[0].strip()
                subject = re.sub(r"^\d+\.", "", subject).strip()

                lessons.append({
                    "time_start": time_match.group(1),
                    "time_end": time_match.group(2),
                    "subject": subject if len(subject) > 2 else "Дисциплина",
                    "type": "Лекция" if "лекц" in text.lower() else ("Практика" if "практ" in text.lower() else "Занятие"),
                    "teacher": teacher.get_text(strip=True) if teacher else "Не указан",
                    "teacher_url": f"{BASE_URL}{teacher['href']}" if teacher else "",
                    "room": "ауд." + text.split("ауд.")[-1].split(",")[0].strip(),
                    "moodle_url": moodle["href"] if moodle else ""
                })
        return lessons
