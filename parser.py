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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
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
        html = await self._get(f"{BASE_URL}/schedule/{group_id}/by-dates")
        if not html: return []

        site_date = f"{date_str[8:10]}.{date_str[5:7]}.{date_str[:4]}"
        soup = BeautifulSoup(html, "html.parser")
        
        date_element = soup.find(string=re.compile(re.escape(site_date)))
        if not date_element: return []

        container = date_element.find_parent(["div", "section", "li", "td"])
        for _ in range(3):
            if container and len(container.get_text()) < 100: container = container.parent
        
        lessons = []
        if not container: return []

        for item in container.find_all(["li", "tr", "div"], recursive=True):
            text = item.get_text(" ", strip=True)
            time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
            
            if time_match and len(text) > 15:
                t_start, t_end = time_match.groups()
                moodle_a = item.find("a", href=re.compile(r"moodle|clms"))
                teacher_a = item.find("a", href=re.compile(r"atlas|teacher"))
                
                sub_text = text.replace(time_match.group(0), "").strip()
                sub_text = re.sub(r"^\d+\.", "", sub_text).strip()
                subject = sub_text.split("ауд.")[0].split("лекц")[0].split("практ")[0].strip()
                
                # Фильтр пустых карточек
                if not subject or (subject.lower() == "занятие" and not teacher_a):
                    continue

                t_url = teacher_a["href"] if teacher_a else ""
                if t_url and not t_url.startswith("http"):
                    t_url = f"{BASE_URL}{t_url}"

                lessons.append({
                    "time_start": t_start,
                    "time_end": t_end,
                    "subject": subject,
                    "type": "Лекция/Практика" if any(x in text.lower() for x in ["лекц", "практ"]) else "Занятие",
                    "teacher": teacher_a.get_text(strip=True) if teacher_a else "",
                    "teacher_url": t_url,
                    "room": "ауд. " + sub_text.split("ауд.")[-1].split(",")[0].strip() if "ауд." in sub_text else "",
                    "moodle_url": moodle_a["href"] if moodle_a else "",
                    "is_remote": any(x in text.lower() for x in ["дистанц", "zoom", "bbb"])
                })

        unique = []
        seen = set()
        for l in lessons:
            k = f"{l['time_start']}-{l['subject']}"
            if k not in seen:
                seen.add(k)
                unique.append(l)
        return unique
