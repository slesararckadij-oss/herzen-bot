    async def get_schedule_for_date(self, group_id, target_date):
        url = f"{self.host}/schedule/{group_id}/classes"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    html = await resp.text()
                
                soup = BeautifulSoup(html, "html.parser")
                lessons = []
                
                # Каждое занятие лежит в <li>. Это самая надежная точка входа.
                items = soup.find_all("li", class_=re.compile(r"md:p-3|py-3"))
                
                for item in items:
                    # 1. Время (ищем блок, где есть текст с тире, например 9:40-11:10)
                    # Обычно это первый div внутри li
                    time_div = item.find("div", string=re.compile(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}"))
                    if not time_div:
                        # Если напрямую не нашел, ищем в тексте первого дива
                        first_div = item.find("div")
                        if first_div:
                            time_match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", first_div.get_text())
                            time_start = time_match.group(1) if time_match else "00:00"
                            time_end = time_match.group(2) if time_match else "00:00"
                        else: continue
                    else:
                        t_parts = time_div.get_text(strip=True).split("-")
                        time_start, time_end = t_parts[0], t_parts[1]

                    # 2. Предмет (на скрине это div с классом text-lg font-bold или ссылка внутри него)
                    subject = "Дисциплина"
                    subject_tag = item.find(class_=re.compile(r"text-lg|font-bold"))
                    if subject_tag:
                        subject = subject_tag.get_text(strip=True)

                    # 3. Преподаватель (ищем ссылку, содержащую 'teachers')
                    teacher = ""
                    teacher_tag = item.find("a", href=re.compile(r"teachers/\d+"))
                    if teacher_tag:
                        teacher = teacher_tag.get_text(strip=True)

                    # 4. Аудитория и тип (ищем в тексте li, исключая время и предмет)
                    # Тип обычно "лекц" или "практ"
                    full_text = item.get_text(" ", strip=True)
                    l_type = "Занятие"
                    if "лекц" in full_text.lower(): l_type = "Лекция"
                    elif "практ" in full_text.lower(): l_type = "Практика"
                    
                    # Аудитория (ищем подстроку "ауд.")
                    room = "—"
                    room_match = re.search(r"ауд\.\s*([\d\w/.\s-]+(?=,|$))", full_text)
                    if room_match:
                        room = room_match.group(0).strip()

                    # Проверка, чтобы не дублировать время в названии
                    if subject == f"{time_start}-{time_end}":
                        # Если парсер ошибся и взял время как предмет, ищем предмет дальше
                        next_bold = item.find_all(class_=re.compile(r"font-bold"))
                        if len(next_bold) > 1:
                            subject = next_bold[1].get_text(strip=True)

                    lessons.append({
                        "time_start": time_start,
                        "time_end": time_end,
                        "subject": subject,
                        "type": l_type,
                        "teacher": teacher,
                        "room": room
                    })
                
                return lessons
            except Exception as e:
                print(f"Ошибка парсинга: {e}")
                return []
