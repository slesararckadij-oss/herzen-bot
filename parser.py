# -*- coding: utf-8 -*-
import aiohttp
import re
import logging
from datetime import datetime, date
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"

WEEKDAYS_RU = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}


class HerzenParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def _get(self, url: str) -> str:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 200:
                        return await r.text(encoding="utf-8", errors="replace")
                    logger.warning(f"HTTP {r.status} for {url}")
                    return ""
            except Exception as e:
                logger.error(f"Request error for {url}: {e}")
                return ""

    async def get_all_groups(self):
        html = await self._get(f"{BASE_URL}/schedule")
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        for a in soup.find_all("a", href=re.compile(r"/schedule/(\d+)/classes")):
            m = re.search(r"/schedule/(\d+)/classes", a["href"])
            if not m:
                continue
            g_id = m.group(1)
            name = a.get_text(strip=True)
            if g_id not in seen and name:
                seen.add(g_id)
                groups.append({"id": g_id, "name": name})
        return sorted(groups, key=lambda x: x["name"])

    def _date_in_range(self, target: date, note: str) -> bool:
        """
        Проверяет, попадает ли target в диапазон из примечания.
        Форматы: "2.02—11.05" (диапазон) или "25.05" (одна дата).
        Год берём из target.
        """
        note = note.strip()
        year = target.year

        range_match = re.match(r"(\d{1,2})\.(\d{1,2})\s*[—\-–]\s*(\d{1,2})\.(\d{1,2})", note)
        if range_match:
            d1, m1, d2, m2 = map(int, range_match.groups())
            start = date(year, m1, d1)
            end = date(year, m2, d2)
            if end < start:
                end = date(year + 1, m2, d2)
            return start <= target <= end

        single_match = re.match(r"(\d{1,2})\.(\d{1,2})$", note)
        if single_match:
            d1, m1 = map(int, single_match.groups())
            return target == date(year, m1, d1)

        return True

    async def get_schedule_for_date(self, group_id: str, target_date: str):
        """
        target_date: строка в формате YYYY-MM-DD
        Возвращает список занятий на эту дату.
        """
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
        target_weekday = target.weekday()

        url = f"{BASE_URL}/schedule/{group_id}/classes"
        html = await self._get(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        lessons = []

        day_blocks = soup.find_all("div", class_=re.compile(r"p-5.*rounded-lg|rounded-lg.*p-5"))
        if not day_blocks:
            day_blocks = soup.find_all("div", class_=lambda c: c and "p-5" in c and "rounded-lg" in c)

        for block in day_blocks:
            time_el = block.find("time")
            if not time_el:
                continue
            day_name = time_el.get_text(strip=True).lower()
            block_weekday = WEEKDAYS_RU.get(day_name)
            if block_weekday is None or block_weekday != target_weekday:
                continue

            items = block.find_all("li")
            for item in items:
                text = item.get_text(" ", strip=True)

                time_match = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", text)
                if not time_match:
                    continue

                note_el = item.find("span", class_="italic")
                note = ""
                if note_el:
                    note_text = note_el.parent.get_text(strip=True) if note_el.parent else ""
                    note_clean = re.sub(r"Примечание\s*:?\s*", "", note_text).strip()
                    note_clean = re.sub(r"[^0-9.—\-–]", "", note_clean)
                    note = note_clean

                if note and not self._date_in_range(target, note):
                    continue

                teacher_tag = item.find("a", href=re.compile(r"atlas\.herzen|teachers"))
                moodle_tag = item.find("a", href=re.compile(r"moodle|clms"))

                subject_div = item.find("div", class_=re.compile(r"font-semibold|font-bold|text-lg"))
                if subject_div:
                    subject = subject_div.get_text(strip=True)
                else:
                    sub_part = text.split(time_match.group(0))[-1]
                    subject = sub_part.split("ауд.")[0].split("лекц")[0].split("практ")[0].strip()
                    subject = re.sub(r"^\d+\.", "", subject).strip()

                subject = re.sub(r"\s+", " ", subject).strip()
                if len(subject) < 3:
                    continue

                lesson_type = "Занятие"
                if "лекц" in text.lower():
                    lesson_type = "Лекция"
                elif "практ" in text.lower():
                    lesson_type = "Практика"
                elif "семин" in text.lower():
                    lesson_type = "Семинар"

                room = "—"
                room_match = re.search(r"ауд\.?\s*([^\n,<]{2,40})", text, re.IGNORECASE)
                if room_match:
                    room = "ауд. " + room_match.group(1).strip().rstrip(".")

                teacher_href = ""
                if teacher_tag:
                    href = teacher_tag.get("href", "")
                    teacher_href = href if href.startswith("http") else f"{BASE_URL}{href}"

                lessons.append({
                    "time_start": time_match.group(1),
                    "time_end": time_match.group(2),
                    "subject": subject,
                    "type": lesson_type,
                    "teacher": teacher_tag.get_text(strip=True) if teacher_tag else "Не указан",
                    "teacher_url": teacher_href,
                    "room": room,
                    "moodle_url": moodle_tag["href"] if moodle_tag else "",
                    "note": note,
                })

        return sorted(lessons, key=lambda x: x["time_start"])
