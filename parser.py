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
                    if r.status != 200:
                        return ""
                    return await r.text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.error(f"Network error: {e}")
                return ""

    async def get_all_groups(self) -> list:
        """Список групп — без изменений"""
        html = await self._get(f"{BASE_URL}/schedule")
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        groups, seen = [], set()
        for a in soup.find_all("a", href=True):
            m = re.search(r"/schedule/(\d+)", a["href"])
            if m and (name := a.get_text(strip=True)):
                gid = m.group(1)
                if gid not in seen:
                    seen.add(gid)
                    groups.append({"id": gid, "name": name})
        return groups

    async def get_schedule_for_date(self, group_id, target_date) -> list:
        """НОВАЯ версия — используем /by-dates"""
        if isinstance(target_date, str):
            date_str = target_date
        else:
            date_str = target_date.strftime("%Y-%m-%d")

        html = await self._get(f"{BASE_URL}/schedule/{group_id}/by-dates")
        if not html:
            return []

        # Старый JSON больше не работает — сразу переходим к новому парсеру
        logger.info(f"JSON empty for {date_str}, trying HTML fallback (by-dates)")
        lessons = self._parse_by_dates_html(html, date_str)
        return lessons

    def _parse_by_dates_html(self, html: str, target_date_str: str) -> list:
        """Новый парсер под актуальную страницу «По датам»"""
        soup = BeautifulSoup(html, "html.parser")
        ddmmyyyy = f"{target_date_str[8:10]}.{target_date_str[5:7]}.{target_date_str[:4]}"

        # Находим заголовок с нужной датой
        date_tag = soup.find(string=re.compile(re.escape(ddmmyyyy)))
        if not date_tag:
            return []

        lessons = []
        current = date_tag.find_parent()

        while current:
            if isinstance(current, str):
                current = current.next_sibling
                continue

            txt = current.get_text(strip=True)
            # Следующая дата — выходим
            if re.search(r"\d{2}\.\d{2}\.\d{4}", txt) and current != date_tag.find_parent():
                break

            # Это урок (начинается с номера + время)
            if re.match(r"^\d+\.", txt) and re.search(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}", txt):
                # Время
                t_match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", txt)
                if not t_match:
                    current = current.next_sibling
                    continue
                time_start, time_end = t_match.groups()

                # Предмет
                subj_match = re.search(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}\s+(.+?)(?:\s+Примечание:|\s+лекц|\s+практ|\s+зачёт)", txt)
                subject = subj_match.group(1).strip() if subj_match else "Занятие"

                # Тип
                typ_match = re.search(r"(лекц|практ|зачёт|зч/оц)", txt)
                typ = typ_match.group(1) if typ_match else "Занятие"

                # Аудитория
                room_match = re.search(r"ауд\.\s*([^,]+)", txt)
                room = f"ауд. {room_match.group(1).strip()}" if room_match else ""

                # Дистанционно
                is_remote = "дистанц" in txt.lower() or "видеолекция" in txt.lower()

                # Ссылки
                moodle_a = current.find("a", href=re.compile(r"moodle"))
                moodle_url = moodle_a["href"] if moodle_a else ""
                teacher_a = current.find("a", href=re.compile(r"atlas|teachers"))
                teacher = teacher_a.get_text(strip=True) if teacher_a else ""
                teacher_url = teacher_a["href"] if teacher_a else ""

                lessons.append({
                    "time_start": time_start,
                    "time_end": time_end,
                    "subject": subject,
                    "type": typ,
                    "teacher": teacher,
                    "teacher_url": teacher_url,   # теперь кликабельно в интерфейсе
                    "room": room,
                    "moodle_url": moodle_url,
                    "is_remote": is_remote
                })

            current = current.next_sibling

        return lessons
