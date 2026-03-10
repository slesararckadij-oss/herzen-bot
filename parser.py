import aiohttp
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

class HerzenParser:
    def __init__(self):
        # Базовый домен
        self.host = "https://guide.herzen.spb.ru"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

    async def get_all_groups(self):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                # Пробуем основной адрес (без static, если со static дает 404)
                # На сайте Герцена сейчас актуально именно это:
                main_url = f"{self.host}/static/index.php?p=schedule" 
                # Если не сработает, попробуем прямой:
                fallback_url = f"{self.host}/static/schedule.php"

                logger.info(f"Пробую загрузить группы с: {main_url}")
                
                async with session.get(main_url, timeout=15) as resp:
                    if resp.status == 404:
                        logger.warning("Основной URL дал 404, пробуем запасной...")
                        async with session.get(fallback_url, timeout=15) as resp2:
                            html = await resp2.text()
                            status = resp2.status
                    else:
                        html = await resp.text()
                        status = resp.status

                if status != 200:
                    logger.error(f"Сайт вообще не отдает расписание. Статус: {status}")
                    return []

                soup = BeautifulSoup(html, "html.parser")
                
                # Находим ссылки на факультеты
                # Они могут быть как полные, так и относительные
                fac_links = soup.find_all('a', href=re.compile(r"id_fac=\d+"))
                logger.info(f"Найдено ссылок на факультеты: {len(fac_links)}")

                all_groups = []
                seen_ids = set()

                # Идем по факультетам
                for fac in fac_links[:12]: # Лимит 12, чтобы Render не уснул
                    href = fac['href']
                    # Исправляем путь, если он относительный
                    if href.startswith('?'):
                        f_url = f"{self.host}/static/schedule.php{href}"
                    elif href.startswith('schedule.php'):
                        f_url = f"{self.host}/static/{href}"
                    else:
                        f_url = href if href.startswith('http') else f"{self.host}{href}"

                    async with session.get(f_url, timeout=10) as f_resp:
                        if f_resp.status != 200: continue
                        f_html = await f_resp.text()
                        f_soup = BeautifulSoup(f_html, "html.parser")
                        
                        # Группы
                        g_links = f_soup.find_all('a', href=re.compile(r"id_group=\d+"))
                        for g in g_links:
                            g_id = re.search(r"id_group=(\d+)", g['href']).group(1)
                            g_name = g.get_text(strip=True)
                            if g_id not in seen_ids and len(g_name) > 2:
                                seen_ids.add(g_id)
                                all_groups.append({"id": g_id, "name": g_name})

                logger.info(f"Финальный сбор: {len(all_groups)} групп.")
                return sorted(all_groups, key=lambda x: x['name'])

            except Exception as e:
                logger.error(f"Ошибка в процессе парсинга: {e}")
                return []
