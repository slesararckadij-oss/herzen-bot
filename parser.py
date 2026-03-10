import aiohttp
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

class HerzenParser:
    def __init__(self):
        self.host = "https://guide.herzen.spb.ru"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": "https://guide.herzen.spb.ru/"
        }

    async def get_all_groups(self):
        # Используем CookieJar, чтобы сайт думал, что мы реальный юзер с сессией
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(headers=self.headers, cookie_jar=jar) as session:
            try:
                # ШАГ 1: Заходим на главную атласа, чтобы получить куки
                logger.info("Заходим на главную для получения сессии...")
                async with session.get(f"{self.host}/static/index.php", timeout=10) as r:
                    await r.text()

                # ШАГ 2: Пробуем зайти в раздел расписания
                # Я перебрал все варианты, этот — самый прямой
                target_url = f"{self.host}/static/schedule.php"
                logger.info(f"Пробую пробиться сюда: {target_url}")
                
                async with session.get(target_url, timeout=10) as resp:
                    if resp.status != 200:
                        # Если опять 404, пробуем альтернативный вход через параметры
                        alt_url = f"{self.host}/static/index.php?p=schedule"
                        logger.warning(f"Прямой путь не подошел ({resp.status}), пробую {alt_url}")
                        async with session.get(alt_url, timeout=10) as resp_alt:
                            html = await resp_alt.text()
                            status = resp_alt.status
                    else:
                        html = await resp.text()
                        status = resp.status

                if status != 200:
                    logger.error(f"Сайт непробиваем. Статус: {status}")
                    return []

                soup = BeautifulSoup(html, "html.parser")
                
                # Ищем факультеты (теперь ищем любые ссылки, где есть id_fac)
                fac_links = soup.find_all('a', href=re.compile(r"id_fac=\d+"))
                
                # Если ссылок нет, попробуем поискать в выпадающем списке (select)
                if not fac_links:
                    logger.info("Ссылок не нашли, ищем выпадающее меню...")
                    fac_options = soup.find_all('option', value=re.compile(r"\d+"))
                    # Имитируем ссылки из опций
                    fac_links = [{'href': f"schedule.php?id_fac={opt['value']}"} for opt in fac_options if 'id_fac' not in opt.get('name', '')]

                all_groups = []
                seen_ids = set()

                # Чтобы Render не сдох, берем первые 8 факультетов
                for fac in fac_links[:8]:
                    href = fac['href']
                    f_url = f"{self.host}/static/{href}" if 'http' not in href else href
                    
                    async with session.get(f_url, timeout=10) as f_resp:
                        if f_resp.status != 200: continue
                        f_html = await f_resp.text()
                        f_soup = BeautifulSoup(f_html, "html.parser")
                        
                        g_links = f_soup.find_all('a', href=re.compile(r"id_group=\d+"))
                        for g in g_links:
                            g_id = re.search(r"id_group=(\d+)", g['href']).group(1)
                            g_name = g.get_text(strip=True)
                            if g_id not in seen_ids:
                                seen_ids.add(g_id)
                                all_groups.append({"id": g_id, "name": g_name})

                logger.info(f"Победа! Найдено групп: {len(all_groups)}")
                return sorted(all_groups, key=lambda x: x['name'])

            except Exception as e:
                logger.error(f"Парсер упал: {e}")
                return []
