# -*- coding: utf-8 -*-
import aiohttp
import json
import re
import logging
from datetime import date, datetime
from bs4 import BeautifulSoup

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
        # Используем одну сессию для сохранения кук (важно для Livewire)
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                # Сначала заходим на главную, чтобы получить куки сессии
                await session.get(f"{BASE_URL}/schedule", timeout=10)
                async with session.get(url, timeout=20) as r:
                    if r.status != 200:
                        logger.error(f"Сайт вернул статус {r.status} для {url}")
                        return ""
                    return await r.text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.error(f"Ошибка запроса к {url}: {e}")
                return ""

    async def get_all_groups(self) -> list:
        try:
            html = await self._get(f"{BASE_URL}/schedule")
            if not html: return []
            soup = BeautifulSoup(html, "html.parser")
            groups = []
            seen = set()
            for a in soup.find_all("a", href=True):
                m = re.search(r"/schedule/(\d+)", a["href"])
                if m:
                    gid = m.group(1)
                    name = a.get_text(strip=True)
                    if name and gid not in seen and len(name) > 1:
                        seen.add(gid)
                        groups.append({"id": gid, "name": name})
            return groups
        except Exception as e:
            logger.error(f"get_all_groups error: {e}")
            return []

    async def get_schedule_for_date(self, group_id, target_date):
        """
        target_date может быть строкой 'YYYY-MM-DD' или объектом date/datetime
        """
        try:
            # Исправляем ошибку 'str' object has no attribute 'strftime'
            if isinstance(target_date, str):
                date_str = target_date
            else:
                date_str = target_date.strftime("%Y-%m-%d")

            html = await self._get(f"{BASE_URL}/schedule/{group_id}/classes")
            if not html: return []
            
            all_lessons = self._extract_from_snapshot(html)
            
            # Если снапшот не найден, попробуем обычный парсинг как запасной вариант
            if not all_lessons:
                logger.warning("Snapshot не найден, пробуем обычный парсинг HTML")
                all_lessons = self._fallback_parse_html(html, date_str)

            filtered = []
            for l in all_lessons:
                if l.get("_date") == date_str:
                    lesson_data = l.copy()
                    lesson_data.pop("_date", None)
                    filtered.append(lesson_data)
            
            logger.info(f"Got {len(filtered)} lessons for {date_str}")
            return filtered
        except Exception as e:
            logger.error(f"get_schedule_for_date error: {e}")
            return []

    def _extract_from_snapshot(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find(attrs={"wire:snapshot": True})
        snapshot_json = tag["wire:snapshot"] if tag else None
        
        if not snapshot_json:
            m = re.search(r'wire:snapshot="([^"]+)"', html)
            if m: snapshot_json = m.group(1).replace("&quot;", '"')

        if not snapshot_json:
            logger.warning("wire:snapshot not found")
            return []

        try:
            snapshot = json.loads(snapshot_json)
            schedule_raw = snapshot.get("data", {}).get("schedule", [])
            return self._parse_schedule_json(schedule_raw)
        except Exception as e:
            logger.error(f"Snapshot parse error: {e}")
            return []

    def _fallback_parse_html(self, html: str, target_date_str: str) -> list:
        """Запасной метод, если Livewire снапшот не отдается"""
        soup = BeautifulSoup(html, "html.parser")
        lessons = []
        # Конвертируем YYYY-MM-DD в формат сайта DD.MM.YYYY
        d_obj = datetime.strptime(target_date_str, "%Y-%m-%d")
        site_date = d_obj.strftime("%d.%m.%Y")

        day_blocks = soup.find_all("div", class_=re.compile(r"p-5|rounded-lg"))
        for block in day_blocks:
            time_tag = block.find("time")
            if not time_tag or site_date not in time_tag.text: continue

            items = block.find_all("li")
            for item in items:
                # Извлекаем время
                time_div = item.find("div", style=re.compile(r"width:\s*110px"))
                t_text = time_div.text.strip().split("-") if time_div else ["00:00", "00:00"]
                
                # Извлекаем предмет
                subject_tag = item.find("a", href=re.compile(r"moodle"))
                subject = subject_tag.text.strip() if subject_tag else item.find("span", class_="italic").text.strip()
                
                lessons.append({
                    "time_start": t_text[0],
                    "time_end": t_text[1] if len(t_text) > 1 else "",
                    "subject": subject,
                    "type": "Занятие",
                    "teacher": "",
                    "room": "",
                    "is_remote": "дистанц" in item.text.lower(),
                    "_date": target_date_str
                })
        return lessons

    def _parse_schedule_json(self, schedule_raw: list) -> list:
        lessons = []
        for day in schedule_raw:
            items = day if isinstance(day, list) else [day]
            for item in items:
                if not isinstance(item, dict): continue
                l = self._parse_lesson_item(item)
                if l: lessons.append(l)
        return lessons

    def _parse_lesson_item(self, item: dict) -> dict | None:
        # Твой текущий метод парсинга элемента JSON остается без изменений, 
        # он у тебя уже хорошо написан.
        try:
            time_start = item.get("TIME_START", "")
            subject = item.get("PNAME") or item.get("NAME_DISC") or ""
            if not time_start or not subject: return None

            date_raw = item.get("SCHEDULE_DATE", "")
            date_norm = ""
            if date_raw:
                if "-" in date_raw: date_norm = date_raw[:10]
                else:
                    p = date_raw.split(".")
                    if len(p) == 3: date_norm = f"{p[2]}-{p[1]}-{p[0]}"

            return {
                "time_start": time_start,
                "time_end": item.get("TIME_END", ""),
                "subject": subject.strip(),
                "type": "Занятие",
                "teacher": "",
                "room": item.get("ROOM_NAME", ""),
                "is_remote": "дистанц" in subject.lower(),
                "_date": date_norm
            }
        except: return None
