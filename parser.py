import aiohttp
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

class HerzenParser:
    def __init__(self):
        self.host = "https://guide.herzen.spb.ru"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

    async def get_all_groups(self):
        # Оставляем список групп статичным, чтобы не ловить 404
        return [{"id": "23307", "name": "2об_СПП/24"}]

    async def get_schedule_for_date(self, group_id, target_date):
        url = f"{self.host}/schedule/{group_id}/classes"
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200: return []
                    html = await resp.text()
                
                soup = BeautifulSoup(html, "html.parser")
                lessons = []
                
                # По твоему скриншоту: занятия лежат внутри элементов <li>
                # Каждый блок занятия — это li внутри ol
                items = soup.find_all("li", class_=re.compile(r"p-3|py-3"))
                
                for item in items:
                    # 1. Извлекаем время (оно в блоке с шириной 110px)
                    time_div = item.find("div", style=re.compile(r"width:\s*110px"))
                    if not time_div: continue
                    time_text = time_div.get_text(strip=True) # "9:40-11:10"
                    
                    # 2. Извлекаем название предмета (оно в font-bold)
                    subject_tag = item.find("span", class_=re.compile(r"font-bold"))
                    if not subject_tag: 
                        # Если нет в span, ищем в ссылке (иногда это ссылка на Moodle)
                        subject_tag = item.find("a", class_=re.compile(r"font-bold"))
                    
                    subject = subject_tag.get_text(strip=True) if subject_tag else "Предмет"
                    
                    # 3. Извлекаем тип (лекц / практ) - это просто текст в div
                    lesson_type = "Занятие"
                    if "лекц" in item.get_text().lower(): lesson_type = "Лекция"
                    if "практ" in item.get_text().lower(): lesson_type = "Практика"
                    
                    # 4. Извлекаем аудиторию и препода
                    # Препод обычно в ссылке на atlas.herzen.spb.ru/teachers
                    teacher_tag = item.find("a", href=re.compile(r"teachers"))
                    teacher = teacher_tag.get_text(strip=True) if teacher_tag else ""
                    
                    # Аудитория часто идет в конце текста
                    room = "—"
                    room_match = re.search(r"ауд\.\s*([\d\w,\s\(\)]+)", item.get_text())
                    if room_match:
                        room = room_match.group(0)

                    time_parts = time_text.split("-")
                    
                    lessons.append({
                        "time_start": time_parts[0].strip(),
                        "time_end": time_parts[1].strip() if len(time_parts) > 1 else "",
                        "subject": subject,
                        "type": lesson_type,
                        "teacher": teacher,
                        "room": room
                    })
                
                logger.info(f"Найдено занятий: {len(lessons)}")
                return lessons
            except Exception as e:
                logger.error(f"Ошибка парсинга: {e}")
                return []
