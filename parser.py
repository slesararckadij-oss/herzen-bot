# -*- coding: utf-8 -*-
import aiohttp
from bs4 import BeautifulSoup
from datetime import date, timedelta
import re
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://guide.herzen.spb.ru"

LESSON_TYPE_MAP = {
    "лекц": "Лекция",
    "лек": "Лекция",
    "практ": "Практика",
    "семин": "Семинар",
    "лаб": "Лаб",
    "зачёт": "Зачёт",
    "зачет": "Зачёт",
    "экзамен": "Экзамен",
    "консульт": "Консультация",
}


class HerzenParser:

    async def _get(self, url: str, params: dict = None) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params=params,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                return await r.text(encoding="utf-8", errors="replace")

    async def get_all_groups(self) -> list:
        try:
            html = await self._get(f"{BASE_URL}/schedule")
            soup = BeautifulSoup(html, "html.parser")
            groups = []
            seen = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                m = re.search(r"/schedule/(\d+)", href)
                if m:
                    gid = int(m.group(1))
                    name = a.get_text(strip=True)
                    if name and gid not in seen and len(name) > 1:
                        seen.add(gid)
                        groups.append({"id": gid, "name": name})
            return groups
        except Exception as e:
            logger.error(f"get_all_groups error: {e}")
            return []

    async def get_schedule_for_date(self, group_id: int, target: date) -> list:
        try:
            date_str = target.strftime("%Y-%m-%d")
            url = f"{BASE_URL}/schedule/{group_id}/classes"
            params = {
                "dateFrom": date_str,
                "dateTo": date_str,
            }
            html = await self._get(url, params=params)
            lessons = self._parse_day(html, target)
            logger.info(f"Parsed {len(lessons)} lessons for {date_str}")
            return lessons
        except Exception as e:
            logger.error(f"get_schedule_for_date error: {e}")
            return []

    def _parse_day(self, html: str, target: date) -> list:
        soup = BeautifulSoup(html, "html.parser")
        lessons = []

        date_str_full = target.strftime("%d.%m.%Y")
        date_str_nodot = target.strftime("%-d.%-m.%Y")

        time_tags = soup.find_all("time")
        target_block = None

        for tt in time_tags:
            tt_text = tt.get_text(strip=True)
            if date_str_full in tt_text or date_str_nodot in tt_text:
                parent = tt.find_parent("div")
                if parent:
                    target_block = parent
                break

        if target_block is None:
            target_block = soup

        for li in target_block.find_all("li"):
            lesson = self._parse_lesson_li(li)
            if lesson:
                lessons.append(lesson)

        if not lessons and target_block != soup:
            for li in soup.find_all("li"):
                lesson = self._parse_lesson_li(li)
                if lesson:
                    lessons.append(lesson)

        # Дедупликация
        seen = set()
        unique = []
        for l in lessons:
            key = (l["time_start"], l["subject"][:20])
            if key not in seen:
                seen.add(key)
                unique.append(l)

        return unique

    def _parse_lesson_li(self, li) -> dict | None:
        text_full = li.get_text(" ", strip=True)

        time_m = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", text_full)
        if not time_m:
            return None

        time_start = time_m.group(1)
        time_end = time_m.group(2)

        # Название предмета
        subject = ""
        subject_span = li.find("span", class_=re.compile(r"font-bold"))
        if subject_span:
            subject = subject_span.get_text(strip=True)

        if not subject or len(subject) < 4:
            return None

        # Тип занятия
        lesson_type = "Занятие"
        for elem in li.find_all(["div", "span"]):
            t = elem.get_text(strip=True).lower()
            if 2 <= len(t) <= 20:
                for key, val in LESSON_TYPE_MAP.items():
                    if t.startswith(key):
                        lesson_type = val
                        break

        # Преподаватель + ссылка
        teacher = ""
        teacher_url = ""
        for a in li.find_all("a", href=True):
            if "teachers" in a["href"]:
                teacher = a.get_text(strip=True)
                href = a["href"]
                if href.startswith("http"):
                    teacher_url = href
                else:
                    teacher_url = "https://atlas.herzen.spb.ru" + href if href.startswith("/") else href
                break

        # Ссылка на курс в Moodle (ищем ссылки на moodle)
        moodle_url = ""
        for a in li.find_all("a", href=True):
            if "moodle" in a["href"].lower() or "lms" in a["href"].lower():
                moodle_url = a["href"]
                break

        # Аудитория
        room = ""
        for elem in li.find_all(["div", "span"]):
            t = elem.get_text(strip=True)
            if "ауд" in t.lower() and len(t) < 60:
                room = t.strip()
                break
            elif re.search(r"корпус\s*\d+", t, re.I) and len(t) < 60:
                room = t.strip()
                break

        if not room:
            room_m = re.search(r"(ауд\.?\s*\d+[а-яё]?\s*(?:,|я,?)?\s*корпус\s*\d+[^,\n]*)", text_full, re.I)
            if not room_m:
                room_m = re.search(r"(корпус\s*\d+[^,\n]*)", text_full, re.I)
            if room_m:
                room = room_m.group(1).strip()

        is_remote = any(w in text_full.lower() for w in ["дистанц", "видеолекц", "онлайн"])

        note = ""
        note_m = re.search(r"Примечание:\s*([^\n<]+)", text_full)
        if note_m:
            note = note_m.group(1).strip()

        return {
            "time_start": time_start,
            "time_end": time_end,
            "subject": subject,
            "type": lesson_type,
            "teacher": teacher,
            "teacher_url": teacher_url,
            "moodle_url": moodle_url,
            "room": room,
            "is_remote": is_remote,
            "note": note,
        }
