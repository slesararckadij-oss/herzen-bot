import aiohttp
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

class HerzenParser:
    def __init__(self):
        # Базовый URL без лишних слешей
        self.base_url = "https://guide.herzen.spb.ru"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://guide.herzen.spb.ru/static/schedule.php"
        }

    async def get_all_groups(self):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                # ВНИМАНИЕ: правильный путь к главной странице расписания
                main_url = f"{self.base_url}/static/schedule.php"
                logger.info(f"Запрос к: {main_url}")
                
                async with session.get(main_url, timeout=15) as resp:
                    if resp.status != 200:
                        logger.error(f"Ошибка {resp.status} по адресу {main_url}")
                        return []
                    html = await resp.text()

                soup = BeautifulSoup(html, "html.parser")
                # Ищем ссылки на факультеты. На сайте они выглядят как href="schedule.php?id_fac=... "
                fac_links = soup.find_all('a', href=re.compile(r"id_fac=\d+"))
                
                all_groups = []
                seen_ids = set()

                # Пройдемся по первым 15 факультетам (чтобы Render не отвалился по лимиту времени)
                for fac in fac_links[:15]:
                    # Формируем чистый URL факультета
                    fac_href = fac['href']
                    if not fac_href.startswith('http'):
                        fac_url = f"{self.base_url}/static/{fac_href}"
                    else:
                        fac_url = fac_href

                    async with session.get(fac_url, timeout=10) as f_resp:
                        if f_resp.status != 200: continue
                        f_html = await f_resp.text()
                        f_soup = BeautifulSoup(f_html, "html.parser")
                        
                        # Группы имеют вид schedule_view.php?id_group=...
                        g_links = f_soup.find_all('a', href=re.compile(r"id_group=\d+"))
                        
                        for g in g_links:
                            match = re.search(r"id_group=(\d+)", g['href'])
                            if match:
                                g_id = match.group(1)
                                g_name = g.get_text(strip=True)
                                if g_id not in seen_ids and len(g_name) > 2:
                                    seen_ids.add(g_id)
                                    all_groups.append({"id": g_id, "name": g_name})

                logger.info(f"Успешно собрано групп: {len(all_groups)}")
                return sorted(all_groups, key=lambda x: x['name'])
                
            except Exception as e:
                logger.error(f"Критическая ошибка парсинга: {e}")
                return []
