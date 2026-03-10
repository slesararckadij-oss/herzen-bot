import aiohttp
from bs4 import BeautifulSoup
from datetime import date
import re
import logging

# Настройка логов, чтобы видеть ошибки в консоли Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://guide.herzen.spb.ru"
# Юзер-агент, чтобы сайт не думал, что мы тупой бот
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
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    logger.error(f"Ошибка сайта: {r.status}")
                    return ""
                return await r.text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Ошибка запроса: {e}")
            return ""

    async def get_all_groups(self) -> list[dict]:
        """
        Парсим список групп правильно. 
        На сайте Герцена группы лежат в выпадающих списках или ссылках.
        """
        try:
            # Сначала заходим на главную расписания
            url = f"{BASE_URL}/static/schedule.php"
            html = await self._get(url)
            if not html:
                return []

            soup = BeautifulSoup(html, "html.parser")
            groups = []
            
            # Ищем все ссылки, которые ведут на расписание групп
            # Обычно они выглядят как schedule_view.php?id_group=12345
            links = soup.find_all('a', href=re.compile(r"id_group=\d+"))
            
            seen_ids = set()
            for link in links:
                name = link.get_text(strip=True)
                href = link.get('href', '')
                group_id_match = re.search(r"id_group=(\.d+)", href)
                
                if group_id_match:
                    group_id = group_id_match.group(1)
                    if group_id not in seen_ids and len(name) > 2:
                        seen_ids.add(group_id)
                        groups.append({
                            "id": group_id, 
                            "name": name
                        })
            
            logger.info(f"Найдено групп: {len(groups)}")
            return groups

        except Exception as e:
            logger.error(f"get_all_groups error: {e}")
            return []

    async def get_schedule_week(self, group_id: str, week_start: date) -> dict:
        """Подгружаем неделю. Важно: id_group должен быть числом из ссылки"""
        try:
            # Добавляем семестр (обычно 1 или 2)
            url = f"{BASE_URL}/static/schedule_view.php?id_group={group_id}"
            html = await self._get(url)
            if not html:
                return {}
            return self._parse_schedule_html(html, week_start)
        except Exception as e:
            logger.error(f"get_schedule_week error: {e}")
            return {}

    def _parse_schedule_html(self, html: str, ref_date: date) -> dict:
        """
        Тут должна быть логика парсинга таблицы. 
        Если она у тебя была 'наворочена' GPT — присылай её следующим куском, 
        я её перепишу под нормальный вид (карточки).
        """
        soup = BeautifulSoup(html, "html.parser")
        schedule = {}
        # ... (ждем твой код парсинга таблицы)
        return schedule

    async def close(self):
        if self._session:
            await self._session.close()
