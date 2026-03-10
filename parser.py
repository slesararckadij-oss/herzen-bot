import aiohttp
from bs4 import BeautifulSoup
import re

class HerzenParser:
    def __init__(self):
        self.host = "https://guide.herzen.spb.ru"
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    async def get_all_groups(self):
        return [{"id": "23307", "name": "2об_СПП/24"}]

    async def get_schedule_for_date(self, group_id, target_date):
        url = f"{self.host}/schedule/{group_id}/classes"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    html = await resp.text()
                
                soup = BeautifulSoup(html, "html.parser")
                lessons = []
                
                # Ищем все блоки, которые похожи на контейнеры пар
                # В новом атласе это часто div с отступами py-2 или py-3
                containers = soup.find_all("div", class_=re.compile(r"py-[23]"))
                
                for c in containers:
                    text = c.get_text(" ", strip=True)
                    # Ищем время в формате 00:00-00:00
                    time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
                    if time_match:
                        # Название обычно в font-bold или просто первый крупный текст после времени
                        subject_tag = c.find(class_=re.compile(r"font-bold|text-lg"))
                        subject = subject_tag.get_text(strip=True) if subject_tag else "Дисциплина"
                        
                        # Аудитория
                        room = "—"
                        if "ауд." in text.lower():
                            room_part = text.lower().split("ауд.")[1].split(",")[0]
                            room = "ауд." + room_part

                        lessons.append({
                            "time_start": time_match.group(1),
                            "time_end": time_match.group(2),
                            "subject": subject,
                            "type": "Занятие",
                            "teacher": "",
                            "room": room
                        })
                
                # Убираем дубликаты (они могут возникнуть из-за вложенных div)
                unique_lessons = []
                seen = set()
                for l in lessons:
                    key = f"{l['time_start']}-{l['subject']}"
                    if key not in seen:
                        unique_lessons.append(l)
                        seen.add(key)
                
                return unique_lessons
            except Exception as e:
                print(f"Error: {e}")
                return []
