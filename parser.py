# -*- coding: utf-8 -*-
import aiohttp
import json
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"

class HerzenParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }

    async def _get(self, url: str) -> str:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                # Предварительный заход для получения кук
                await session.get(f"{BASE_URL}/schedule", timeout=10)
                async with session.get(url, timeout=20) as r:
                    if r.status != 200: return ""
                    return await r.text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.error(f"Request error: {e}")
                return ""

    async def get_all_groups(self) -> list:
        html = await self._get(f"{BASE_URL}/schedule")
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        for a in soup.find_all("a", href=True):
            m = re.search(r"/schedule/(\d+)", a["href"])
            if m:
                gid, name = m.group(1), a.get_text(strip=True)
                if name and gid not in seen:
                    seen.add(gid)
                    groups.append({"id": gid, "name": name})
        return groups

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        # Универсальная обработка даты (строка или объект)
        if isinstance(target_date, str):
            date_str = target_date
        else:
            date_str = target_date.strftime("%Y-%m-%d")

        html = await self._get(f"{BASE_URL}/schedule/{group_id}/classes")
        if not html: return []

        # 1. Пробуем быстрый JSON-снапшот
        all_lessons = self._extract_from_snapshot(html)
        
        # 2. Если пусто, включаем "умный" парсинг HTML
        if not all_lessons:
            logger.info("Snapshot empty, using fallback HTML parser")
            all_lessons = self._fallback_parse_html(html, date_str)

        filtered = []
        for l in all_lessons:
            if l.get("_date") == date_str:
                res = l.copy()
                res.pop("_date", None)
                filtered.append(res)
        
        return filtered

    def _extract_from_snapshot(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find(attrs={"wire:snapshot": True})
        js_raw = tag["wire:snapshot"] if tag else None
        if not js_raw:
            m = re.search(r'wire:snapshot="([^"]+)"', html)
            if m: js_raw = m.group(1).replace("&quot;", '"')
        
        if not js_raw: return []

        try:
            data = json.loads(js_raw).get("data", {}).get("schedule", [])
            lessons = []
            for day in data:
                items = day if isinstance(day, list) else [day]
                for item in items:
                    if isinstance(item, dict):
                        parsed = self._parse_json_item(item)
                        if parsed: lessons.append(parsed)
            return lessons
        except Exception: return []

    def _parse_json_item(self, item: dict) -> dict | None:
        subject = item.get("PNAME") or item.get("NAME_DISC") or ""
        time_s = item.get("TIME_START", "")
        if not subject or not time_s: return None

        date_raw = item.get("SCHEDULE_DATE", "")
        date_norm = ""
        if "-" in date_raw: date_norm = date_raw[:10]
        elif "." in date_raw:
            p = date_raw.split(".")
            if len(p) == 3: date_norm = f"{p[2]}-{p[1]}-{p[0]}"

        rows = item.get("ROWS", [])
        teacher = rows[0].get("TEACHER_NAME", "") if rows and isinstance(rows[0], dict) else ""
        t_id = item.get("ID_TEACHER")
        
        return {
            "time_start": time_s,
            "time_end": item.get("TIME_END", ""),
            "subject": subject.strip(),
            "type": self._map_type(item.get("LECTYPE", "") or str(item.get("ID_LECTYPE", ""))),
            "teacher": teacher.strip(),
            "teacher_url": f"{BASE_URL}/teachers/{t_id}" if t_id else "",
            "moodle_url": (item.get("E_COURSE_URL") or "").replace("\\/", "/"),
            "room": (item.get("ROOM_NAME") or "").strip(),
            "is_remote": any(x in subject.lower() for x in ["дистанц", "видео", "online"]),
            "note": (item.get("NOTE") or "").strip(),
            "_date": date_norm
        }

    def _fallback_parse_html(self, html: str, target_date_str: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        lessons = []
        try:
            d_obj = datetime.strptime(target_date_str, "%Y-%m-%d")
            site_date = d_obj.strftime("%d.%m.%Y")
        except: site_date = target_date_str

        # Поиск блока дня
        day_block = None
        for tag in soup.find_all(['div', 'li', 'span']):
            if site_date in tag.get_text():
                day_block = tag.find_parent(['div', 'ol']) or tag.parent
                break
        
        if not day_block: return []

        # Поиск строк расписания (li)
        for li in day_block.find_all('li', recursive=True):
            text = li.get_text(separator=" ", strip=True)
            times = re.findall(r'\d{1,2}:\d{2}', text)
            if not times: continue

            # Ссылки
            moodle = li.find('a', href=re.compile(r'moodle'))
            teacher_link = li.find('a', href=re.compile(r'teachers|atlas'))
            
            # Извлечение чистого названия
            sub = text
            for t in times: sub = sub.replace(t, "")
            # Убираем лишние слова из названия для красоты
            sub = re.sub(r'(лекц|практ|семин|Занятие|ауд\.|корпус)', '', sub, flags=re.I).strip()

            lessons.append({
                "time_start": times[0],
                "time_end": times[1] if len(times) > 1 else "",
                "subject": sub.split("Примечание")[0].strip(),
                "type": "Занятие",
                "teacher": teacher_link.get_text(strip=True) if teacher_link else "",
                "teacher_url": teacher_link['href'] if teacher_link else "",
                "moodle_url": moodle['href'] if moodle else "",
                "room": re.search(r'ауд\.\s*[\w\d, ]+', text, re.I).group(0) if "ауд." in text else "",
                "is_remote": any(x in text.lower() for x in ["дистанц", "видео", "online"]),
                "_date": target_date_str
            })
        return lessons

    def _map_type(self, raw: str) -> str:
        raw = raw.lower()
        if "лек" in raw or raw == "1": return "Лекция"
        if "практ" in raw or raw == "2": return "Практика"
        if "сем" in raw or raw == "3": return "Семинар"
        return "Занятие"
