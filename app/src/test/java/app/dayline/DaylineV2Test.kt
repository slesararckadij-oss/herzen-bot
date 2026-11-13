package app.dayline

import org.junit.Assert.*
import org.junit.Test
import java.time.*

class DaylineV2Test {
    @Test fun oldInstallDataMigratesWithoutDroppingContent() {
        val raw = """{"tasks":[{"id":"t1","text":"Сдать работу","done":false}],"notes":[{"id":"n1","title":"Лекция","body":"Старый конспект\\nДЗ до пятницы"}],"alarms":[{"id":1,"hour":7,"minute":30,"enabled":true}],"feeds":[{"id":"f1","name":"Мой источник","url":"https://example.com/rss"}],"digestEnabled":true,"digestHour":8,"digestMinute":15}"""
        val s = StateCodec.decode(raw)
        assertEquals("Сдать работу", s.tasks.single().text)
        assertTrue(s.notes.single().preview().contains("Старый конспект"))
        assertEquals((1..7).toSet(), s.alarms.single().days)
        assertEquals("", s.alarms.single().sound)
        assertEquals("Мой источник", s.feeds.single().name)
        assertEquals(15, s.digestMinute)
        assertEquals(s, StateCodec.decode(StateCodec.encode(s)))
    }
    @Test fun richNoteSurvivesStyleSwitchAndSerialization() {
        val blocks = listOf(Block("a", "heading", "План", bold = true), Block("b", "check", "Купить хлеб", checked = true, indent = 1), Block("c", "table", cells = listOf(listOf("Предмет", "ДЗ"), listOf("Математика", "№ 12"))))
        val n = Note("note", "Занятие", blocks = blocks, updated = 1)
        val s = DayState(notes = listOf(n), layout = "blocks")
        val decoded = StateCodec.decode(StateCodec.encode(s.copy(layout = "simple")))
        assertEquals(blocks, decoded.notes.single().blocks)
        assertEquals("simple", decoded.layout)
        assertTrue(decoded.notes.single().body.contains("Математика"))
        assertTrue(decoded.notes.single().body.contains("Купить хлеб"))
    }
    @Test fun intentionallyEmptySourceListStaysEmpty() {
        assertTrue(StateCodec.decode(StateCodec.encode(DayState(feeds = emptyList()))).feeds.isEmpty())
    }
    @Test fun habitSeriesSkipsUnscheduledDays() {
        val h = Habit("h", "Чтение", days = setOf(1,3,5), completed = setOf("2026-11-09", "2026-11-11"), created = "2026-11-01")
        assertEquals(2, habitStreak(h, LocalDate.parse("2026-11-13")))
        assertEquals(3, habitStreak(h.copy(completed = h.completed + "2026-11-13"), LocalDate.parse("2026-11-13")))
    }
    @Test fun missedScheduledDayBreaksSeries() {
        val h = Habit("h", "Вода", completed = setOf("2026-11-10", "2026-11-11"), created = "2026-11-01")
        assertEquals(0, habitStreak(h, LocalDate.parse("2026-11-13")))
    }
    @Test fun awardsAreBasedOnUniqueDays() {
        val days = (1..7).map { LocalDate.of(2026,11,it).toString() }.toSet()
        val h = Habit("h", "Спорт", completed = days)
        assertEquals(listOf(1,7), medals(h))
        assertEquals(listOf(1,7), medals(h.copy(completed = h.completed + days.first())))
    }
    @Test fun weeklyAlarmFindsNextSelectedDay() {
        val now = ZonedDateTime.parse("2026-11-13T08:00:00+03:00[Europe/Moscow]")
        assertEquals("2026-11-16", nextAlarmTime(7,30,setOf(1),now).toLocalDate().toString())
    }
    @Test fun taskSchedulesOnlyFutureReminders() {
        val now = ZonedDateTime.parse("2026-11-13T08:00:00+03:00[Europe/Moscow]")
        val t = Task(text = "ДЗ", dueDate = "2026-11-15", reminder = true)
        assertEquals(listOf(2,1,0), reminderInstants(t,now).map { it.first })
        assertEquals(listOf(1,0), reminderInstants(t,now.plusHours(2)).map { it.first })
        assertTrue(reminderInstants(t.copy(done = true),now).isEmpty())
        assertTrue(reminderInstants(t.copy(reminder = false),now).isEmpty())
    }
    @Test fun feedParsesRssDescriptionsAndDates() {
        val xml = """<rss version="2.0"><channel><item><title>Новость &amp; событие</title><link>https://example.com/news/1</link><pubDate>Fri, 13 Nov 2026 09:00:00 +0300</pubDate><description><![CDATA[<p>Короткая <b>сводка</b></p>]]></description></item></channel></rss>"""
        val a = parseFeed(xml,Feed("f","РБК","https://example.com/rss")).single()
        assertEquals("Новость & событие",a.title)
        assertEquals("Короткая сводка",a.summary)
        assertEquals(Instant.parse("2026-11-13T06:00:00Z").toEpochMilli(),a.published)
    }
    @Test fun atomAlternateLinkAndNestedTitleArePreserved() {
        val xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">Космос <b>сегодня</b></div></title><link rel="self" href="https://example.com/api/1"/><link rel="alternate" href="https://example.com/1"/><updated>2026-11-13T06:00:00Z</updated></entry></feed>"""
        val a = parseFeed(xml,Feed("f","Наука","https://example.com/rss")).single()
        assertEquals("https://example.com/1",a.url)
        assertEquals("Космос сегодня",a.title)
        assertTrue(a.published > 0)
    }
    @Test fun unsafeArticleLinkIsNotImported() {
        val xml = """<rss><channel><item><title>Вредная ссылка</title><link>javascript:alert(1)</link></item></channel></rss>"""
        assertTrue(parseFeed(xml,Feed("f","Тест","https://example.com/rss")).isEmpty())
    }
    @Test fun morningRankingDeduplicatesCoverageAndExcludesOldOrUndatedArticles() {
        val now = Instant.parse("2026-11-13T06:00:00Z").toEpochMilli()
        val a = Article("Central station closes after major fire", "https://a.test/1", "A", now-3600000)
        val b = Article("Major fire closes central station", "https://b.test/1", "B", now-1800000)
        val c = Article("Scientists discover distant planet", "https://a.test/2", "A", now-100000)
        val old = Article("Old story", "https://a.test/old", "A", now-13*3600000)
        val noDate = Article("Undated", "https://a.test/none", "A")
        val picked = topStories(listOf(a,b,c,old,noDate),now)
        assertEquals(2,picked.size)
        assertEquals(b,picked.first())
        assertTrue(c in picked)
        assertFalse(old in picked)
        assertFalse(noDate in picked)
    }
    @Test fun morningRankingReturnsAtMostThreeStories() {
        val now = Instant.now().toEpochMilli()
        val articles = (1..10).map { Article("Событие номер $it", "https://example.com/$it", "Источник", now-it*1000) }
        assertTrue(topStories(articles,now).size <= 3)
    }
}
