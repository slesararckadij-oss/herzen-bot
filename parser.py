import aiohttp
from bs4 import BeautifulSoup
from datetime import date, datetime
import re
import logging

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
    def __init__(self):
        self.session = None

    async def _get(self, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.text(encoding="utf-8")

    async def get_all_groups(self) -> list[dict]:
    async def get_all_groups(self) -> list[dict]:
    """Получить список групп РГПУ"""
    try:
        url = f"{BASE_URL}/static/schedule_view.php"
        html = await self._get(url)

        soup = BeautifulSoup(html, "html.parser")

        groups = []

        # ищем select с группами
        select = soup.find("select", {"name": "id_group"})
        if not select:
            return []

        for option in select.find_all("option"):
            value = option.get("value")
            name = option.get_text(strip=True)

            if value and value.isdigit() and name:
                groups.append({
                    "id": int(value),
                    "name": name
                })

        return groups

    except Exception as e:
        logger.error(f"get_all_groups error: {e}")
        return []

    async def get_schedule_week(self, group_id: int, week_start: date) -> dict:
        """Получить расписание на неделю"""
        try:
            # sem=1 или sem=2 — сейчас автоматически берём текущий семестр
            url = f"{BASE_URL}/static/schedule_view.php?id_group={group_id}&sem=1"
            html = await self._get(url)
            return self._parse_schedule_html(html, week_start)
        except Exception as e:
            logger.error(f"get_schedule_week error: {e}")
            return {}

    async def get_schedule_for_date(self, group_id: int, target_date: date) -> list:
        """Получить расписание на конкретную дату"""
        week_data = await self.get_schedule_week(group_id, target_date)
        day_key = WEEKDAY_MAP.get(target_date.weekday(), "sunday")
        return week_data.get(day_key, [])

    def _parse_schedule_html(self, html: str, ref_date: date) -> dict:
        """Парсит HTML страницы расписания"""
        soup = BeautifulSoup(html, "html.parser")
        schedule = {}

        current_day = None

        # Таблица расписания
        table = soup.find("table", class_=re.compile(r"schedule|rasp", re.I))
        if not table:
            # Попробуем любую таблицу
            table = soup.find("table")

        if not table:
            # Попробуем парсить без таблицы — блочная верстка
            return self._parse_blocks(soup)

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            row_text = row.get_text(" ", strip=True).lower()

            # Определяем строку с днём недели
            for day_ru, day_idx in RU_WEEKDAY.items():
                if day_ru in row_text and len(row_text) < 30:
                    current_day = WEEKDAY_MAP[day_idx]
                    if current_day not in schedule:
                        schedule[current_day] = []
                    break
            else:
                if current_day:
                    lesson = self._parse_row(cells)
                    if lesson:
                        schedule[current_day].append(lesson)

        return schedule

    def _parse_blocks(self, soup: BeautifulSoup) -> dict:
        """Альтернативный парсер для блочной верстки"""
        schedule = {}
        current_day = None

        for tag in soup.find_all(["div", "p", "h3", "h4", "tr", "td"]):
            text = tag.get_text(" ", strip=True).lower()

            for day_ru, day_idx in RU_WEEKDAY.items():
                if day_ru in text and len(text) < 40:
                    current_day = WEEKDAY_MAP[day_idx]
                    if current_day not in schedule:
                        schedule[current_day] = []
                    break

            if current_day and re.search(r"\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}", text):
                lesson = self._extract_lesson_from_text(tag.get_text(" ", strip=True))
                if lesson:
                    # Не дублировать
                    if lesson not in schedule[current_day]:
                        schedule[current_day].append(lesson)

        return schedule

    def _parse_row(self, cells: list) -> dict | None:
        """Парсит одну строку таблицы в урок"""
        texts = [c.get_text(" ", strip=True) for c in cells]
        full = " ".join(texts)
        return self._extract_lesson_from_text(full)

    def _extract_lesson_from_text(self, text: str) -> dict | None:
        """Извлекает данные урока из строки текста"""
        time_match = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", text)
        if not time_match:
            return None

        time_start = time_match.group(1)
        time_end = time_match.group(2)

        # Тип занятия
        lesson_type = "Занятие"
        for t in ["Лекция", "Практика", "Семинар", "Лаб"]:
            if t.lower() in text.lower():
                lesson_type = t
                break

        is_remote = any(w in text.lower() for w in ["дистанц", "видеолекц", "онлайн"])

        # Убираем время из текста, ищем название
        clean = re.sub(r"\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}", "", text).strip()
        clean = re.sub(r"\s+", " ", clean)

        # Аудитория
        room_match = re.search(r"ауд[.\s]*(\S+)", clean, re.I)
        room = room_match.group(0) if room_match else ""

        # Корпус
        corp_match = re.search(r"корпус\s+\d+[^,)]*", clean, re.I)
        if corp_match and room:
            room = corp_match.group(0) + ", " + room

        # Преподаватель (ФИО — три слова с заглавной)
        teacher_match = re.search(r"([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)", clean)
        teacher = teacher_match.group(1) if teacher_match else ""

        # Название предмета — убираем мусор
        subject = clean
        for rm in [room, teacher, "Лекция", "Практика", "Семинар", "Лаб", "дистанционное обучение", "видеолекция"]:
            if rm:
                subject = subject.replace(rm, "")
        subject = re.sub(r"\[.*?\]", "", subject)
        subject = re.sub(r"\s+", " ", subject).strip(" ,;")

        if len(subject) < 3:
            return None

        return {
            "time_start": time_start,
            "time_end": time_end,
            "subject": subject,
            "type": lesson_type,
            "teacher": teacher,
            "room": room,
            "is_remote": is_remote,
        }
