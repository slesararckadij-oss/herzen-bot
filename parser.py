import aiohttp
from bs4 import BeautifulSoup
import re
import logging
from datetime import date

logger = logging.getLogger(__name__)
BASE_URL = "https://guide.herzen.spb.ru"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

class HerzenParser:
    def __init__(self):
        self._session = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS)
        return self._session

    async def _get(self, url: str) -> str:
        session = await self._get_session()
        try:
            async with session.get(url, timeout=15) as r:
                return await r.text(encoding="utf-8") if r.status == 200 else ""
        except Exception as e:
            logger.error(f"Request error: {e}")
            return ""

    async def get_all_groups(self) -> list[dict]:
        """Глубокий парсинг всех групп через факультеты"""
        try:
            html_main = await self._get(f"{BASE_URL}/static/schedule.php")
            if not html_main: return []
            
            soup_main = BeautifulSoup(html_main, "html.parser")
            fac_links = soup_main.find_all('a', href=re.compile(r"id_fac=\d+"))
            
            all_groups = []
            seen_ids = set()

            for fac in fac_links:
                fac_url = f"{BASE_URL}/static/{fac['href']}"
                html_fac = await self._get(fac_url)
                if not html_fac: continue
                
                soup_fac = BeautifulSoup(html_fac, "html.parser")
                group_links = soup_fac.find_all('a', href=re.compile(r"id_group=\d+"))
                
                for g_link in group_links:
                    group_id = re.search(r"id_group=(\d+)", g_link['href']).group(1)
                    name = g_link.get_text(strip=True)
                    if group_id not in seen_ids and len(name) > 2:
                        seen_ids.add(group_id)
                        all_groups.append({"id": group_id, "name": name})
            
            return sorted(all_groups, key=lambda x: x['name'])
        except Exception as e:
            logger.error(f"Parser error: {e}")
            return []

    async def get_schedule_for_date(self, group_id: str, target_date: date) -> list:
        """Парсинг расписания на конкретный день"""
        url = f"{BASE_URL}/static/schedule_view.php?id_group={group_id}"
        html = await self._get(url)
        if not html: return []
        
        soup = BeautifulSoup(html, "html.parser")
        lessons = []
        # Тут должна быть твоя логика парсинга таблицы <table>
        # Для примера вернем пустой список, если таблица не найдена
        return lessons
