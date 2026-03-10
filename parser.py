# -*- coding: utf-8 -*-
import aiohttp
from bs4 import BeautifulSoup
import logging
import re
from datetime import date

logger = logging.getLogger(__name__)

BASE_URL = "https://guide.herzen.spb.ru"

WEEKDAY_MAP = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}

RU_WEEKDAY = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
}

class HerzenParser:
    async def _get(self, url: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.text(encoding="utf-8")

    async def get_all_groups(self):
        """Получает все группы Герцена с сайта"""
        try:
            html = await self._get(f"{BASE_URL}/schedule")
            soup = BeautifulSoup(html, "html.parser")
            groups = []

            # На сайте группы лежат в <select name="group"> или <option>
            for opt in soup.find_all("option"):
                val = opt.get("value")
                name = opt.get_text(strip=True)
                if val and val.isdigit() and name:
                    groups.append({"id": int(val), "name": name})
            return groups
        except Exception as e:
            logger.error(f"get_all_groups error: {e}")
            return []

    async def get_schedule_week(self, group_id: int, week_start: date) -> dict:
        """Расписание на неделю"""
        try:
            url = f"{BASE_URL}/static/schedule_view.php?id_group={group_id}&sem=1"
            html = await self._get(url)
            return self._parse_schedule_html(html, week_start)
        except Exception as e:
            logger.error(f"get_schedule_week error: {e}")
            return {}

    async def get_schedule_for_date(self, group_id: int, target_date: date):
        week_data = await self.get_schedule_week(group_id, target_date)
        day_key = WEEKDAY_MAP.get(target_date.weekday(), "sunday")
        return week_data.get(day_key, [])

    def _parse_schedule_html(self, html: str, ref_date: date) -> dict:
        """Парсинг HTML таблицы расписания"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        schedule = {}
        table = soup.find("table")
        if not table:
            return {}

        current_day = None
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            row_text = row.get_text(" ", strip=True).lower()
            for day_ru, day_idx in RU_WEEKDAY.items():
                if day_ru in row_text and len(row_text) < 30:
                    current_day = list(WEEKDAY_MAP.values())[day_idx]
                    if current_day not in schedule:
                        schedule[current_day] = []
                    break
            else:
                if current_day:
                    lesson = self._parse_row(cells)
                    if lesson:
                        schedule[current_day].append(lesson)
        return schedule

    def _parse_row(self, cells):
        texts = [c.get_text(" ", strip=True) for c in cells]
        full = " ".join(texts)
        match = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", full)
        if not match:
            return None
        time_start, time_end = match.groups()
        lesson_type = "Занятие"
        for t in ["Лекция", "Практика", "Семинар", "Лаб"]:
            if t.lower() in full.lower():
                lesson_type = t
                break
        subject = re.sub(r"\d{1,2}:\d{2}", "", full).strip()
        teacher_match = re.search(r"([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)", full)
        teacher = teacher_match.group(1) if teacher_match else ""
        room_match = re.search(r"ауд[.\s]*(\S+)", full, re.I)
        room = room_match.group(0) if room_match else ""
        return {
            "time_start": time_start,
            "time_end": time_end,
            "subject": subject,
            "type": lesson_type,
            "teacher": teacher,
            "room": room,
        }
