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
                if m.group(1) not in seen:
                    seen.add(m.group(1))
                    groups.append({"id": m.group(1), "name": name})
        return groups

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        date_str = target_date if isinstance(target_date, str) else target_date.strftime("%Y-%m-%d")
        # Используем основной URL, он наиболее полный
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/classes")
        if not html: return []

        logger.info(f"== Parsing Date: {date_str} ==")
        return self._parse_agnostic(html, date_str)

    def _parse_agnostic(self, html: str, target_date_str: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        # Формат даты на сайте обычно DD.MM.YYYY
        site_date = f"{target_date_str[8:10]}.{target_date_str[5:7]}.{target_date_str[:4]}"
        
        lessons = []
        # Ищем текст с датой в любом месте страницы
        date_element = soup.find(string=re.compile(re.escape(site_date)))
        
        if not date_element:
            logger.warning(f"Date {site_date} not found on page")
            return []

        # Берем родительский контейнер, где лежит эта дата и все пары дня
        container = date_element.find_parent(["div", "section", "li", "td"])
        # Если контейнер слишком маленький, поднимаемся выше до общего блока
        for _ in range(3):
            if container and len(container.get_text()) < 100:
                container = container.parent
        
        if not container: return []

        # Ищем все элементы, содержащие время формата HH:MM
        items = container.find_all(["li", "tr", "div"], recursive=True)
        for item in items:
            text = item.get_text(" ", strip=True)
            # Регулярка для времени (09:00 - 10:30 или 09:00-10:30)
            time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
            
            if time_match:
                # Проверка: чтобы не грести пары из других дней, 
                # проверяем, нет ли в этом конкретном блоке другой даты
                other_date = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
                if other_date and other_date.group(0) != site_date:
                    continue

                t_start, t_end = time_match.groups()
                
                # Извлекаем ссылки
                moodle_link = item.find("a", href=re.compile(r"moodle|clms"))
                teacher_link = item.find("a", href=re.compile(r"atlas|teacher"))
                
                # Чистим название предмета
                # Удаляем время и лишние префиксы вроде "1."
                sub_text = text.replace(time_match.group(0), "").strip()
                sub_text = re.sub(r"^\d+\.", "", sub_text).strip()
                
                # Пытаемся отделить название от аудитории
                subject = sub_text.split("ауд.")[0].split("лекц")[0].split("практ")[0].strip()
                room = "ауд. " + sub_text.split("ауд.")[-1].strip() if "ауд." in sub_text else ""

                lessons.append({
                    "time_start": t_start,
                    "time_end": t_end,
                    "subject": subject if len(subject) > 2 else "Занятие",
                    "type": "Лекция/Практика" if any(x in text.lower() for x in ["лекц", "практ"]) else "Занятие",
                    "teacher": teacher_link.get_text(strip=True) if teacher_link else "",
                    "teacher_url": teacher_link["href"] if teacher_link else "",
                    "room": room,
                    "moodle_url": moodle_link["href"] if moodle_link else "",
                    "is_remote": any(x in text.lower() for x in ["дистанц", "онлайн", "zoom", "bbb"])
                })

        # Убираем дубликаты, которые могли возникнуть из-за вложенности тегов
        unique_lessons = []
        seen_times = set()
        for l in lessons:
            key = f"{l['time_start']}-{l['subject']}"
            if key not in seen_times:
                seen_times.add(key)
                unique_lessons.append(l)
                
        return unique_lessons
