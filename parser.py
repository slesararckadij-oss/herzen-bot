# -*- coding: utf-8 -*-
import aiohttp
import json
import re
import logging
from datetime import date
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"


class HerzenParser:

    async def _get(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r:
                return await r.text(encoding="utf-8", errors="replace")

    async def get_all_groups(self) -> list:
        try:
            html = await self._get(f"{BASE_URL}/schedule")
            soup = BeautifulSoup(html, "html.parser")
            groups = []
            seen = set()
            for a in soup.find_all("a", href=True):
                m = re.search(r"/schedule/(\d+)", a["href"])
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
            html = await self._get(f"{BASE_URL}/schedule/{group_id}/classes")
            all_lessons = self._extract_from_snapshot(html)
            date_str = target.strftime("%Y-%m-%d")
            filtered = [l for l in all_lessons if l.get("_date") == date_str]
            for l in filtered:
                l.pop("_date", None)
            logger.info(f"Got {len(filtered)} lessons for {date_str} (total {len(all_lessons)})")
            return filtered
        except Exception as e:
            logger.error(f"get_schedule_for_date error: {e}")
            return []

    def _extract_from_snapshot(self, html: str) -> list:
        """Вытащить все занятия из wire:snapshot на странице"""
        soup = BeautifulSoup(html, "html.parser")

        # Ищем элемент с wire:snapshot
        snapshot_json = None
        for tag in soup.find_all(attrs={"wire:snapshot": True}):
            snapshot_json = tag["wire:snapshot"]
            break

        if not snapshot_json:
            # Попробуем найти в тексте страницы
            m = re.search(r'wire:snapshot="([^"]+)"', html)
            if m:
                snapshot_json = m.group(1).replace("&quot;", '"')

        if not snapshot_json:
            logger.warning("wire:snapshot not found")
            return []

        try:
            snapshot = json.loads(snapshot_json)
            schedule_raw = snapshot.get("data", {}).get("schedule", [])
            return self._parse_schedule_json(schedule_raw)
        except Exception as e:
            logger.error(f"snapshot parse error: {e}")
            return []

    def _parse_schedule_json(self, schedule_raw: list) -> list:
        """Парсим массив занятий из JSON снапшота"""
        lessons = []

        # schedule_raw — список дней, каждый день содержит список занятий
        for day_entry in schedule_raw:
            if not isinstance(day_entry, (list, dict)):
                continue

            # Если это список занятий напрямую
            items = day_entry if isinstance(day_entry, list) else [day_entry]

            for item in items:
                if not isinstance(item, dict):
                    continue
                lesson = self._parse_lesson_item(item)
                if lesson:
                    lessons.append(lesson)

        return lessons

    def _parse_lesson_item(self, item: dict) -> dict | None:
        time_start = item.get("TIME_START", "")
        time_end = item.get("TIME_END", "")
        subject = item.get("PNAME", "") or item.get("NAME_DISC", "") or ""
        schedule_date = item.get("SCHEDULE_DATE", "")

        if not time_start or not subject:
            return None

        # Тип занятия
        ltype_raw = item.get("ID_LECTYPE", 0)
        ltype_name = item.get("LECTYPE", "") or ""
        lesson_type = self._map_type(ltype_name or str(ltype_raw))

        # Преподаватель
        teacher_id = item.get("ID_TEACHER")
        teacher_name = item.get("CONTROL_TYPE_NAME", "") or ""
        # Имя преподавателя часто в ROWS
        rows = item.get("ROWS", [])
        if rows and isinstance(rows, list) and len(rows) > 0:
            row = rows[0] if isinstance(rows[0], dict) else {}
            teacher_name = row.get("TEACHER_NAME", "") or teacher_name

        teacher_url = f"https://atlas.herzen.spb.ru/teachers/{teacher_id}" if teacher_id else ""

        # Moodle
        moodle_url = item.get("E_COURSE_URL", "") or ""
        if moodle_url:
            moodle_url = moodle_url.replace("\\/", "/")

        # Аудитория
        room = item.get("ROOM_NAME", "") or ""
        zv = item.get("ZV_NAME", "") or ""
        if zv and zv.upper() not in ("NULL", ""):
            room = f"{room}, {zv}".strip(", ")

        # Примечание
        note = item.get("NOTE", "") or ""

        # Дистанционное
        is_video = bool(item.get("IS_VIDEO_LECTURE", 0))
        is_remote = is_video or "дистанц" in subject.lower() or "видеолекц" in subject.lower()

        # Нормализуем дату к формату YYYY-MM-DD
        date_norm = ""
        if schedule_date:
            # Может быть "2026-03-11" или "11.03.2026"
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", schedule_date)
            if m:
                date_norm = schedule_date[:10]
            else:
                m2 = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", schedule_date)
                if m2:
                    date_norm = f"{m2.group(3)}-{m2.group(2)}-{m2.group(1)}"

        return {
            "time_start": time_start,
            "time_end": time_end,
            "subject": subject.strip(),
            "type": lesson_type,
            "teacher": teacher_name.strip(),
            "teacher_url": teacher_url,
            "moodle_url": moodle_url,
            "room": room.strip(),
            "is_remote": is_remote,
            "note": note.strip(),
            "_date": date_norm,
        }

    def _map_type(self, raw: str) -> str:
        raw = raw.lower()
        if "лекц" in raw or "лек" in raw or raw == "1": return "Лекция"
        if "практ" in raw or raw == "2": return "Практика"
        if "семин" in raw or raw == "3": return "Семинар"
        if "лаб" in raw or raw == "4": return "Лаб"
        if "зачёт" in raw or "зачет" in raw: return "Зачёт"
        if "экзамен" in raw: return "Экзамен"
        if "консульт" in raw: return "Консультация"
        return "Занятие"
