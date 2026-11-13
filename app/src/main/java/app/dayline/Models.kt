package app.dayline

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.*
import java.util.UUID

fun newId(): String = UUID.randomUUID().toString()
data class CheckItem(val id: String = newId(), val text: String, val done: Boolean = false)
data class Task(val id: String = newId(), val text: String, val done: Boolean = false, val dueDate: String = "", val reminder: Boolean = false, val reminderHour: Int = 9, val reminderMinute: Int = 0, val subtasks: List<CheckItem> = emptyList())
data class Block(val id: String = newId(), val kind: String = "text", val text: String = "", val checked: Boolean = false, val bold: Boolean = false, val italic: Boolean = false, val indent: Int = 0, val cells: List<List<String>> = emptyList())
data class Note(val id: String = newId(), val title: String = "", val body: String = "", val blocks: List<Block> = emptyList(), val updated: Long = System.currentTimeMillis()) {
    fun content(): List<Block> = blocks.ifEmpty { listOf(Block(text = body)) }
    fun preview(): String = if (blocks.isEmpty()) body else blocks.joinToString("\n") { b -> if (b.kind == "table") b.cells.joinToString("\n") { it.joinToString(" · ") } else b.text }
}
data class WakeAlarm(val id: Int, val hour: Int, val minute: Int, val enabled: Boolean = true, val sound: String = "", val soundName: String = "Системная мелодия", val vibrate: Boolean = true, val label: String = "Доброе утро", val days: Set<Int> = (1..7).toSet(), val morning: Boolean = true)
data class Habit(val id: String = newId(), val title: String, val emoji: String = "🌱", val days: Set<Int> = (1..7).toSet(), val completed: Set<String> = emptySet(), val created: String = LocalDate.now().toString())
data class Medal(val id: String, val habitId: String, val habitTitle: String, val target: Int, val earnedOn: String)
data class Feed(val id: String = newId(), val name: String, val url: String)
data class Article(val title: String, val url: String, val source: String, val published: Long = 0, val summary: String = "")
data class DayState(
    val tasks: List<Task> = emptyList(), val notes: List<Note> = emptyList(), val alarms: List<WakeAlarm> = emptyList(), val feeds: List<Feed> = listOf(Feed("rbc", "РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"), Feed("lenta", "Лента.ру", "https://lenta.ru/rss/news")),
    val digestEnabled: Boolean = false, val digestHour: Int = 8, val digestMinute: Int = 0,
    val habits: List<Habit> = emptyList(), val layout: String = "simple", val theme: String = "system", val news: List<Article> = emptyList(), val newsUpdated: Long = 0, val awards: List<Medal> = emptyList()
)

fun nextOccurrence(hour: Int, minute: Int, now: ZonedDateTime = ZonedDateTime.now()): ZonedDateTime = nextAlarmTime(hour, minute, (1..7).toSet(), now)
fun nextAlarmTime(hour: Int, minute: Int, days: Set<Int>, now: ZonedDateTime = ZonedDateTime.now()): ZonedDateTime {
    require(hour in 0..23 && minute in 0..59 && days.isNotEmpty() && days.all { it in 1..7 })
    for (offset in 0L..7L) {
        val candidate = now.toLocalDate().plusDays(offset).atTime(hour, minute).atZone(now.zone)
        if (candidate.dayOfWeek.value in days && candidate.isAfter(now)) return candidate
    }
    error("Нет следующего будильника")
}
fun habitStreak(h: Habit, today: LocalDate = LocalDate.now()): Int {
    if (h.days.isEmpty()) return 0
    var date = today; var streak = 0
    // Today's uncompleted habit does not break yesterday's series before the day ends.
    if (date.toString() !in h.completed) date = date.minusDays(1)
    while (!date.isBefore(LocalDate.parse(h.created))) {
        if (date.dayOfWeek.value in h.days) {
            if (date.toString() !in h.completed) break
            streak++
        }
        date = date.minusDays(1)
    }
    return streak
}
fun medals(h: Habit): List<Int> = listOf(1, 7, 30, 100).filter { h.completed.size >= it }
fun reminderInstants(task: Task, now: ZonedDateTime = ZonedDateTime.now()): List<Pair<Int, Long>> {
    if (!task.reminder || task.done || task.dueDate.isEmpty()) return emptyList()
    val due = runCatching { LocalDate.parse(task.dueDate) }.getOrNull() ?: return emptyList()
    return listOf(2, 1, 0).mapNotNull { offset ->
        val whenAt = due.minusDays(offset.toLong()).atTime(task.reminderHour, task.reminderMinute).atZone(now.zone)
        if (whenAt.isAfter(now)) offset to whenAt.toInstant().toEpochMilli() else null
    }
}

object StateCodec {
    private fun JSONObject.objects(key: String): List<JSONObject> { val a = optJSONArray(key) ?: JSONArray(); return (0 until a.length()).map { a.getJSONObject(it) } }
    private fun JSONObject.strings(key: String): List<String> { val a = optJSONArray(key) ?: JSONArray(); return (0 until a.length()).map { a.getString(it) } }
    private fun JSONObject.days(): Set<Int> { val a = optJSONArray("days") ?: return (1..7).toSet(); return (0 until a.length()).map { a.getInt(it) }.filter { it in 1..7 }.toSet().ifEmpty { (1..7).toSet() } }
    private fun arr(items: List<JSONObject>) = JSONArray(items)
    fun decode(raw: String): DayState {
        val j = JSONObject(raw)
        return rememberAwards(DayState(
            tasks = j.objects("tasks").map { t -> Task(t.getString("id"), t.getString("text"), t.optBoolean("done"), t.optString("dueDate"), t.optBoolean("reminder"), t.optInt("reminderHour", 9), t.optInt("reminderMinute", 0), t.objects("subtasks").map { CheckItem(it.getString("id"), it.getString("text"), it.optBoolean("done")) }) },
            notes = j.objects("notes").map { n -> Note(n.getString("id"), n.optString("title"), n.optString("body"), n.objects("blocks").map { b ->
                val a = b.optJSONArray("cells") ?: JSONArray()
                val cells = (0 until a.length()).map { row -> val r = a.getJSONArray(row); (0 until r.length()).map { r.getString(it) } }
                Block(b.getString("id"), b.optString("kind", "text"), b.optString("text"), b.optBoolean("checked"), b.optBoolean("bold"), b.optBoolean("italic"), b.optInt("indent").coerceIn(0, 2), cells)
            }, n.optLong("updated", 0)) },
            alarms = j.objects("alarms").map { WakeAlarm(it.getInt("id"), it.getInt("hour"), it.getInt("minute"), it.optBoolean("enabled", true), it.optString("sound"), it.optString("soundName", "Системная мелодия"), it.optBoolean("vibrate", true), it.optString("label", "Доброе утро"), it.days(), it.optBoolean("morning", true)) },
            feeds = if (j.has("feeds")) j.objects("feeds").map { Feed(it.getString("id"), it.getString("name"), it.getString("url")) } else DayState().feeds,
            digestEnabled = j.optBoolean("digestEnabled"), digestHour = j.optInt("digestHour", 8), digestMinute = j.optInt("digestMinute", 0),
            habits = j.objects("habits").map { Habit(it.getString("id"), it.getString("title"), it.optString("emoji", "🌱"), it.days(), it.strings("completed").toSet(), it.optString("created", LocalDate.now().toString())) },
            layout = j.optString("layout", "simple"), theme = j.optString("theme", "system"),
            news = j.objects("news").map { Article(it.getString("title"), it.getString("url"), it.getString("source"), it.optLong("published"), it.optString("summary")) }, newsUpdated = j.optLong("newsUpdated"),
            awards = j.objects("awards").map { Medal(it.getString("id"), it.getString("habitId"), it.getString("habitTitle"), it.getInt("target"), it.getString("earnedOn")) }
        ))
    }
    fun encode(s: DayState): String = JSONObject().put("schema", 3)
        .put("tasks", arr(s.tasks.map { t -> JSONObject().put("id", t.id).put("text", t.text).put("done", t.done).put("dueDate", t.dueDate).put("reminder", t.reminder).put("reminderHour", t.reminderHour).put("reminderMinute", t.reminderMinute).put("subtasks", arr(t.subtasks.map { JSONObject().put("id", it.id).put("text", it.text).put("done", it.done) })) }))
        .put("notes", arr(s.notes.map { n -> JSONObject().put("id", n.id).put("title", n.title).put("body", n.preview()).put("updated", n.updated).put("blocks", arr(n.blocks.map { b -> JSONObject().put("id", b.id).put("kind", b.kind).put("text", b.text).put("checked", b.checked).put("bold", b.bold).put("italic", b.italic).put("indent", b.indent).put("cells", JSONArray(b.cells.map { JSONArray(it) })) })) }))
        .put("alarms", arr(s.alarms.map { JSONObject().put("id", it.id).put("hour", it.hour).put("minute", it.minute).put("enabled", it.enabled).put("sound", it.sound).put("soundName", it.soundName).put("vibrate", it.vibrate).put("label", it.label).put("days", JSONArray(it.days.sorted())).put("morning", it.morning) }))
        .put("feeds", arr(s.feeds.map { JSONObject().put("id", it.id).put("name", it.name).put("url", it.url) }))
        .put("habits", arr(s.habits.map { JSONObject().put("id", it.id).put("title", it.title).put("emoji", it.emoji).put("days", JSONArray(it.days.sorted())).put("completed", JSONArray(it.completed.sorted())).put("created", it.created) }))
        .put("awards", arr(s.awards.map { JSONObject().put("id", it.id).put("habitId", it.habitId).put("habitTitle", it.habitTitle).put("target", it.target).put("earnedOn", it.earnedOn) }))
        .put("news", arr(s.news.take(100).map { JSONObject().put("title", it.title).put("url", it.url).put("source", it.source).put("published", it.published).put("summary", it.summary) }))
        .put("digestEnabled", s.digestEnabled).put("digestHour", s.digestHour).put("digestMinute", s.digestMinute).put("layout", s.layout).put("theme", s.theme).put("newsUpdated", s.newsUpdated).toString()
}

class Store(context: Context) {
    private val app = context.applicationContext
    private val prefs = app.getSharedPreferences("dayline", Context.MODE_PRIVATE)
    fun read(): DayState = synchronized(lock) { prefs.getString("state", null)?.let(StateCodec::decode) ?: DayState() }
    fun update(transform: (DayState) -> DayState): DayState = synchronized(lock) {
        val old = prefs.getString("state", null)
        val next = rememberAwards(transform(old?.let(StateCodec::decode) ?: DayState()))
        val editor = prefs.edit()
        if (old != null && !prefs.contains("backup_v1")) editor.putString("backup_v1", old)
        check(editor.putString("state", StateCodec.encode(next)).commit()) { "Не удалось сохранить данные" }
        runCatching { MorningWidget.refresh(app, next) }
        next
    }
    fun write(s: DayState) { update { s } }
    companion object { private val lock = Any() }
}
