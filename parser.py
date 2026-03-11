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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

    async def _get(self, url: str) -> str:
        """Запрос с автоматическим закрытием сессии для Render"""
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
                gid = m.group(1)
                if gid not in seen:
                    seen.add(gid); groups.append({"id": gid, "name": name})
        return groups

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        """Исправляет ошибку strftime и ищет пары даже в 'кривом' HTML"""
        # Фикс ошибки: 'str' object has no attribute 'strftime'
        if isinstance(target_date, str):
            date_str = target_date
        else:
            date_str = target_date.strftime("%Y-%m-%d")
        
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/classes")
        if not html: return []

        # 1. Пробуем вытащить данные из JSON
        lessons = self._extract_from_snapshot(html, date_str)
        
        # 2. Если пусто (как на скринах пользователя), включаем HTML парсер
        if not lessons:
            logger.info(f"JSON empty for {date_str}, trying HTML fallback")
            lessons = self._fallback_parse_html(html, date_str)

        return lessons

    def _extract_from_snapshot(self, html: str, target_date_str: str) -> list:
        try:
            m = re.search(r'wire:snapshot="([^"]+)"', html)
            if not m: return []
            data = json.loads(m.group(1).replace("&quot;", '"'))
            schedule = data.get("data", {}).get("schedule", [])
            result = []
            for day in schedule:
                items = day if isinstance(day, list) else [day]
                for item in items:
                    if not isinstance(item, dict): continue
                    raw_d = item.get("SCHEDULE_DATE", "")
                    norm_d = raw_d[:10] if "-" in raw_d else f"{raw_d[6:10]}-{raw_d[3:5]}-{raw_d[0:2]}"
                    if norm_d == target_date_str:
                        teacher = item.get("ROWS", [{}])[0].get("TEACHER_NAME", "") if item.get("ROWS") else ""
                        result.append({
                            "time_start": item.get("TIME_START", ""),
                            "time_end": item.get("TIME_END", ""),
                            "subject": (item.get("PNAME") or item.get("NAME_DISC") or "Занятие").strip(),
                            "type": "Занятие",
                            "teacher": teacher.strip(),
                            "room": (item.get("ROOM_NAME") or "").strip(),
                            "moodle_url": (item.get("E_COURSE_URL") or "").replace("\\/", "/"),
                            "is_remote": "дистанц" in str(item).lower()
                        })
            return result
        except: return []

    def _fallback_parse_html(self, html: str, target_date_str: str) -> list:
        """Ищет пары по тексту, если сайт скрыл JSON"""
        soup = BeautifulSoup(html, "html.parser")
        # Конвертируем 2026-03-11 -> 11.03.2026
        site_date = f"{target_date_str[8:10]}.{target_date_str[5:7]}.{target_date_str[0:4]}"
        lessons = []
        
        # Ищем любой узел, содержащий дату
        date_node = soup.find(string=re.compile(site_date))
        if not date_node: return []

        # Берем родительский контейнер (обычно это блок дня)
        container = date_node.find_parent(["div", "section", "li", "ol"]) or soup
        
        for li in container.find_all("li"):
            text = li.get_text(" ", strip=True)
            times = re.findall(r"\d{1,2}:\d{2}", text)
            if not times: continue

            moodle = li.find("a", href=re.compile(r"moodle"))
            t_link = li.find("a", href=re.compile(r"teachers|atlas"))

            lessons.append({
                "time_start": times[0],
                "time_end": times[1] if len(times) > 1 else "",
                "subject": text.split(times[-1])[-1].strip() or "Занятие",
                "type": "Занятие",
                "teacher": t_link.get_text(strip=True) if t_link else "",
                "moodle_url": moodle["href"] if moodle else "",
                "room": "ауд." + text.split("ауд.")[-1][:10].strip() if "ауд." in text else "",
                "is_remote": "дистанц" in text.lower()
            })
        return lessons
