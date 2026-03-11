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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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
        html = await self._get(f"{BASE_URL}/schedule")
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        for a in soup.find_all("a", href=True):
            m = re.search(r"/schedule/(\d+)", a["href"])
            if m and (name := a.get_text(strip=True)):
                if m.group(1) not in seen:
                    seen.add(m.group(1))
                    groups.append({"id": m.group(1), "name": name})
        return groups

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        date_str = target_date if isinstance(target_date, str) else target_date.strftime("%Y-%m-%d")
        # Пробуем загрузить страницу "по датам", она обычно более стабильна для парсинга
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/by-dates")
        if not html: return []

        logger.info(f"== Parsing Date: {date_str} ==")
        
        # Пытаемся найти дату в формате DD.MM.YYYY
        day, month, year = date_str[8:10], date_str[5:7], date_str[:4]
        site_date = f"{day}.{month}.{year}"
        
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. Поиск блока дня
        day_block = None
        # Ищем любой тег, содержащий нашу дату
        for element in soup.find_all(string=re.compile(re.escape(site_date))):
            parent = element.find_parent(["div", "li", "tr", "section"])
            if parent:
                day_block = parent
                break
        
        if not day_block:
            logger.warning(f"Date {site_date} not found, checking alternative containers...")
            day_block = soup # Если не нашли блок, ищем по всей странице

        lessons = []
        # 2. Поиск строк с временем (основной признак пары)
        # Ищем паттерны типа 09:00 - 10:30
        for row in day_block.find_all(["div", "li", "tr"]):
            text = row.get_text(" ", strip=True)
            time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
            
            if time_match:
                # Проверка: не является ли это строкой из другого дня?
                all_dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
                if all_dates and site_date not in all_dates:
                    continue
                
                t_start, t_end = time_match.groups()
                
                # Чистим текст от времени и лишних цифр
                clean_name = text.replace(time_match.group(0), "").strip()
                clean_name = re.sub(r"^\d+\.", "", clean_name).strip() # убираем "1."
                
                # Извлекаем ссылки на преподавателя и Moodle
                teacher_a = row.find("a", href=re.compile(r"atlas|teacher"))
                moodle_a = row.find("a", href=re.compile(r"moodle"))

                lessons.append({
                    "time_start": t_start,
                    "time_end": t_end,
                    "subject": clean_name.split("ауд.")[0].split("лекц")[0].split("практ")[0].strip() or "Занятие",
                    "type": "Лекция/Практика" if any(x in text.lower() for x in ["лекц", "практ"]) else "Занятие",
                    "teacher": teacher_a.get_text(strip=True) if teacher_a else "",
                    "teacher_url": teacher_a["href"] if teacher_a else "",
                    "room": "ауд. " + text.split("ауд.")[-1].split(",")[0].strip() if "ауд." in text else "",
                    "moodle_url": moodle_a["href"] if moodle_a else "",
                    "is_remote": any(x in text.lower() for x in ["дистанц", "видео", "zoom", "bbb"])
                })

        # Фильтруем дубликаты
        final = []
        seen = set()
        for l in lessons:
            key = f"{l['time_start']}-{l['subject']}"
            if key not in seen:
                seen.add(key)
                final.append(l)

        logger.info(f"Found {len(final)} lessons for {site_date}")
        return final
