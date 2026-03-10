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
        }

    async def get_all_groups(self):
        # Статичный список, чтобы избежать лишних запросов и 404
        return [{"id": "23307", "name": "2об_СПП/24"}]

    async def get_schedule_for_date(self, group_id, target_date):
        url = f"{self.host}/schedule/{group_id}/classes"
        logger.info(f"Запрос расписания: {url}")
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error(f"Сайт ответил статусом {resp.status}")
                        return []
                    html = await resp.text()
                
                soup = BeautifulSoup(html, "html.parser")
                lessons = []
                
                # Ищем элементы списка (занятия)
                items = soup.find_all("li", class_=re.compile(r"md:p-3|py-3"))
                
                for item in items:
                    # 1. Извлекаем время
                    time_match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", item.get_text())
                    if not time_match:
                        continue
                        
                    t_start = time_match.group(1)
                    t_end = time_match.group(2)

                    # 2. Извлекаем название предмета (ищем болд или крупный текст)
                    subject = "Дисциплина"
                    subject_tag = item.find(class_=re.compile(r"text-lg|font-bold"))
                    if subject_tag:
                        subject = subject_tag.get_text(strip=True)
                    
                    # Если название совпало со временем, берем следующий подходящий тег
                    if subject == f"{t_start}-{t_end}":
                        all_bold = item.find_all(class_=re.compile(r"text-lg|font-bold"))
                        if len(all_bold) > 1:
                            subject = all_bold[1].get_text(strip=True)

                    # 3. Преподаватель
                    teacher = ""
                    teacher_link = item.find("a", href=re.compile(r"teachers/\d+"))
                    if teacher_link:
                        teacher = teacher_link.get_text(strip=True)

                    # 4. Аудитория и тип
                    full_text = item.get_text(" ", strip=True)
                    l_type = "Занятие"
                    if "лекц" in full_text.lower(): l_type = "Лекция"
                    elif "практ" in full_text.lower(): l_type = "Практика"
                    
                    room = "—"
                    room_search = re.search(r"ауд\.\s*([\d\w/.\s-]+(?=,|$))", full_text)
                    if room_search:
                        room = room_search.group(0).strip()

                    lessons.append({
                        "time_start": t_start,
                        "time_end": t_end,
                        "subject": subject,
                        "type": l_type,
                        "teacher": teacher,
                        "room": room
                    })
                
                logger.info(f"Успешно распарсено {len(lessons)} занятий")
                return lessons
                
            except Exception as e:
                logger.error(f"Ошибка в get_schedule_for_date: {e}")
                return []
                
