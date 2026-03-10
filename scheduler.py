import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def run_scheduler(bot, user_groups: dict, tz, notify_before: int = 15):
    from parser import HerzenParser
    logger.info("Scheduler started")
    notified = set()

    while True:
        try:
            now = datetime.now(tz)
            for user_id, data in list(user_groups.items()):
                if not data.get("notify", True):
                    continue
                group_id = data["group_id"]
                parser = HerzenParser()
                lessons = await parser.get_schedule_for_date(group_id, now.date())
                for lesson in lessons:
                    key = (user_id, str(now.date()), lesson["time_start"])
                    if key in notified:
                        continue
                    try:
                        h, m = map(int, lesson["time_start"].split(":"))
                        lesson_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    except Exception:
                        continue
                    diff = (lesson_dt - now).total_seconds() / 60
                    if 0 < diff <= notify_before:
                        notified.add(key)
                        text = (
                            f"🔔 <b>Через {int(diff)} мин — пара!</b>\n\n"
                            f"📚 {lesson['subject']}\n"
                            f"⏰ {lesson['time_start']} – {lesson['time_end']}\n"
                        )
                        if lesson.get("room"):
                            text += f"🏛 {lesson['room']}\n"
                        if lesson.get("teacher"):
                            text += f"👤 {lesson['teacher']}\n"
                        if lesson.get("is_remote"):
                            text += "💻 Дистанционно\n"
                        try:
                            await bot.send_message(user_id, text, parse_mode="HTML")
                        except Exception as e:
                            logger.warning(f"notify failed {user_id}: {e}")
            notified = {k for k in notified if k[1] == str(now.date())}
        except Exception as e:
            logger.error(f"scheduler error: {e}")
        await asyncio.sleep(60)
