# -*- coding: utf-8 -*-
import aiohttp
import json
import re
import logging
from datetime import date, datetime
 virtues от BeautifulSoup import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"

class HerzenParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def _get(self, url: str) -> str:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=20) as r:
                    if r.status != 200:
                        logger.error(f"Сайт вернул статус {r.status} для {url}")
                        return ""
                    return await r.text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.error(f"Ошибка запроса к {url}: {e}")
                return ""

    async def get_all_groups(self) -> list:
        """Парсим список всех групп для твоего поиска в модалке"""
        try:
            html = await self._get(f"{BASE_URL}/schedule")
            if not html: return []
            soup = BeautifulSoup(html, "html.parser")
            groups = []
            seen = set()
            # Ищем все ссылки на расписания групп
            for a in soup.find_all("a", href=True):
                m = re.search(r"/schedule/(\d+)", a["href"])
                if m:
                    gid = m.group(1) # Оставляем строкой для стабильности API
                    name = a.get_text(strip=True)
                    if name and gid not in seen and len(name) > 1:
                        seen.add(gid)
                        groups.append({"id": gid, "name": name})
            return groups
        except Exception as e:
            logger.error(f"get_all_groups error: {e}")
            return []

    async def get_schedule_for_date(self, group_id: str, target_date_str: str) -> list:
        """
        Принимает group_id (str) и target_date_str (YYYY-MM-DD).
        Возвращает список для твоего index.html.
        """
        try:
            html = await self._get(f"{BASE_URL}/schedule/{group_id}/classes")
            if not html: return []
            
            all_lessons = self._extract_from_snapshot(html)
            
            # Фильтруем по дате (в снапшоте она обычно YYYY-MM-DD или DD.MM.YYYY)
            filtered = []
            for l in all_lessons:
                if l.get("_date") == target_date_str:
                    # Удаляем техническое поле перед отправкой на фронт
                    lesson_data = l.copy()
                    lesson_data.pop("_date", None)
                    filtered.append(lesson_data)
            
            logger.info(f"Найдено {len(filtered)} пар для группы {group_id} на {target_date_str}")
            return filtered
        except Exception as e:
            logger.error(f"get_schedule_for_date error: {e}")
            return []

    def _extract_from_snapshot(self, html: str) -> list:
        """Твой метод извлечения JSON из атрибута wire:snapshot"""
        soup = BeautifulSoup(html, "html.parser")
        snapshot_json = None
        
        tag = soup.find(attrs={"wire:snapshot": True})
        if tag:
            snapshot_json = tag["wire:snapshot"]
        else:
            m = re.search(r'wire:snapshot="([^"]+)"', html)
            if m:
                snapshot_json = m.group(1).replace("&quot;", '"')

        if not snapshot_json:
            return []

        try:
            snapshot = json.loads(snapshot_json)
            # В структуре Livewire данные лежат в data.schedule
            schedule_raw = snapshot.get("data", {}).get("schedule", [])
            return self._parse_schedule_json(schedule_raw)
        except Exception as e:
            logger.error(f"Ошибка парсинга снапшота: {e}")
            return []

    def _parse_schedule_json(self, schedule_raw: list) -> list:
        lessons = []
        for day_entry in schedule_raw:
            # Если day_entry это список занятий для конкретного дня
            items = day_entry if isinstance(day_entry, list) else [day_entry]
            for item in items:
                if not isinstance(item, dict): continue
                lesson = self._parse_lesson_item(item)
                if lesson:
                    lessons.append(lesson)
        return lessons

    def _parse_lesson_item(self, item: dict) -> dict | None:
        # Извлекаем базовые поля
        time_start = item.get("TIME_START", "")
        time_end = item.get("TIME_END", "")
        subject = item.get("PNAME") or item.get("NAME_DISC") or ""
        date_raw = item.get("SCHEDULE_DATE", "")

        if not time_start or not subject: return None

        # Преподаватель
        teacher_id = item.get("ID_TEACHER")
        teacher_name = ""
        # Ищем имя в ROWS (как ты и нашел)
        rows = item.get("ROWS", [])
        if rows and isinstance(rows, list):
            teacher_name = rows[0].get("TEACHER_NAME", "") if isinstance(rows[0], dict) else ""
        
        teacher_url = f"{BASE_URL}/teachers/{teacher_id}" if teacher_id else ""

        # Ссылка на Moodle (для синей кнопки в твоем UI)
        moodle_url = item.get("E_COURSE_URL", "")
        if moodle_url:
            moodle_url = moodle_url.replace("\\/", "/")

        # Локация
        room = item.get("ROOM_NAME", "") or ""
        zv = item.get("ZV_NAME", "")
        if zv and str(zv).lower() != "null":
            room = f"{room}, {zv}".strip(", ")

        # Дистанционка (для фиолетового бейджа)
        is_video = bool(item.get("IS_VIDEO_LECTURE", 0))
        is_remote = is_video or "дистанц" in subject.lower() or "видеолекц" in subject.lower()

        # Нормализация даты к YYYY-MM-DD для фильтрации
        date_norm = ""
        if date_raw:
            if "-" in date_raw: # 2026-03-11
                date_norm = date_raw[:10]
            elif "." in date_raw: # 11.03.2026
                parts = date_raw.split(".")
                if len(parts) == 3:
                    date_norm = f"{parts[2]}-{parts[1]}-{parts[0]}"

        return {
            "time_start": time_start,
            "time_end": time_end,
            "subject": subject.strip(),
            "type": self._map_type(item.get("LECTYPE", "") or str(item.get("ID_LECTYPE", ""))),
            "teacher": teacher_name.strip(),
            "teacher_url": teacher_url,
            "moodle_url": moodle_url,
            "room": room.strip(),
            "is_remote": is_remote,
            "note": (item.get("NOTE") or "").strip(),
            "_date": date_norm
        }

    def _map_type(self, raw: str) -> str:
        raw = raw.lower()
        if "лек" in raw or raw == "1": return "Лекция"
        if "практ" in raw or raw == "2": return "Практика"
        if "сем" in raw or raw == "3": return "Семинар"
        if "лаб" in raw or raw == "4": return "Лаб. работа"
        return "Занятие"
