package app.dayline

import org.junit.Assert.*
import org.junit.Test
import java.time.ZonedDateTime

class SchedulingTest {
    @Test fun upcomingAlarmStaysToday() {
        val now = ZonedDateTime.parse("2026-11-13T06:00:00+03:00[Europe/Moscow]")
        val next = nextOccurrence(7, 30, now)
        assertEquals(13, next.dayOfMonth)
        assertEquals(7, next.hour)
        assertEquals(30, next.minute)
    }
    @Test fun pastAndEqualTimesMoveToTomorrow() {
        val now = ZonedDateTime.parse("2026-11-13T07:30:00+03:00[Europe/Moscow]")
        assertEquals(14, nextOccurrence(7, 30, now).dayOfMonth)
        assertEquals(14, nextOccurrence(6, 0, now).dayOfMonth)
    }
    @Test fun monthRollover() {
        val now = ZonedDateTime.parse("2026-12-31T23:59:00Z[UTC]")
        assertEquals("2027-01-01", nextOccurrence(0, 0, now).toLocalDate().toString())
    }
    @Test fun daylightSavingGapResolvesToFutureInstant() {
        val now = ZonedDateTime.parse("2026-03-29T00:00:00+01:00[Europe/Berlin]")
        assertTrue(nextOccurrence(2, 30, now).isAfter(now))
    }
    @Test fun sourceLinksRequireHttpsAndHost() {
        assertTrue(safeWebUrl("https://feeds.bbci.co.uk/news/world/rss.xml"))
        assertFalse(safeWebUrl("http://example.com/rss"))
        assertFalse(safeWebUrl("javascript:alert(1)"))
        assertFalse(safeWebUrl("https://user:password@example.com/rss"))
        assertFalse(safeWebUrl("not a URL"))
    }
}
