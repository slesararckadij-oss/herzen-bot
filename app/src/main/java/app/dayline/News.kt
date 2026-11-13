package app.dayline

import kotlinx.coroutines.*
import org.xmlpull.v1.XmlPullParser
import org.xmlpull.v1.XmlPullParserFactory
import java.io.StringReader
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.time.*
import java.time.format.DateTimeFormatter
import java.util.Locale

fun safeWebUrl(raw: String): Boolean = runCatching { val u = URI(raw); u.scheme == "https" && !u.host.isNullOrBlank() && u.userInfo == null }.getOrDefault(false)
fun plainHtml(text: String): String = text.replace(Regex("<[^>]+>"), " ").replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", "\"").replace("&#39;", "'").replace(Regex("\\s+"), " ").trim()
fun parseNewsDate(raw: String): Long {
    val value = raw.trim()
    runCatching { return Instant.parse(value).toEpochMilli() }
    runCatching { return OffsetDateTime.parse(value).toInstant().toEpochMilli() }
    for (format in listOf(DateTimeFormatter.RFC_1123_DATE_TIME, DateTimeFormatter.ofPattern("EEE, d MMM yyyy HH:mm:ss Z", Locale.ENGLISH))) runCatching { return ZonedDateTime.parse(value, format).toInstant().toEpochMilli() }
    return 0
}
fun parseFeed(xml: String, feed: Feed): List<Article> {
    val parser = XmlPullParserFactory.newInstance().newPullParser()
    parser.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, true)
    runCatching { parser.setFeature(XmlPullParser.FEATURE_PROCESS_DOCDECL, false) }
    parser.setInput(StringReader(xml))
    val result = mutableListOf<Article>()
    var entryDepth = -1; var fieldDepth = -1; var field = ""; var buffer = StringBuilder()
    var title = ""; var link = ""; var summary = ""; var published = 0L
    var event = parser.eventType
    while (event != XmlPullParser.END_DOCUMENT && result.size < 120) {
        when (event) {
            XmlPullParser.START_TAG -> {
                val name = parser.name
                if ((name == "item" || name == "entry") && entryDepth < 0) { entryDepth = parser.depth; title = ""; link = ""; summary = ""; published = 0 }
                else if (entryDepth >= 0 && parser.depth == entryDepth + 1) {
                    if (name in listOf("title", "link", "description", "summary", "pubDate", "published", "updated")) { field = name; fieldDepth = parser.depth; buffer = StringBuilder() }
                    if (name == "link" && (parser.getAttributeValue(null, "rel") ?: "alternate") == "alternate") parser.getAttributeValue(null, "href")?.let { link = it }
                }
            }
            XmlPullParser.TEXT, XmlPullParser.CDSECT -> if (fieldDepth >= 0) buffer.append(parser.text)
            XmlPullParser.END_TAG -> {
                if (parser.depth == fieldDepth) {
                    val value = buffer.toString().trim()
                    when (field) {
                        "title" -> title = plainHtml(value)
                        "link" -> if (safeWebUrl(value)) link = value
                        "description", "summary" -> if (summary.isEmpty()) summary = plainHtml(value).take(1200)
                        "pubDate", "published", "updated" -> if (published == 0L) published = parseNewsDate(value)
                    }
                    fieldDepth = -1; field = ""
                }
                if (parser.depth == entryDepth && parser.name in listOf("item", "entry")) {
                    if (title.isNotBlank() && safeWebUrl(link)) result.add(Article(title, link, feed.name, published, summary))
                    entryDepth = -1
                }
            }
        }
        event = parser.next()
    }
    return result.distinctBy { it.url }
}
private fun headlineTokens(a: Article): Set<String> = a.title.lowercase().replace('ё', 'е').split(Regex("[^\\p{L}\\p{N}]+"))
    .filter { it.length > 3 && it !in setOf("после", "перед", "который", "этого", "будет", "новости", "россии", "новый", "также", "сегодня") }.map { it.take(7) }.toSet()
fun topStories(articles: List<Article>, now: Long = System.currentTimeMillis(), hours: Int = 12): List<Article> {
    val fresh = articles.filter { it.published in (now - hours * 3600000L)..(now + 300000L) }.distinctBy { it.url }
    val tokens = fresh.associateWith(::headlineTokens)
    fun same(a: Article, b: Article): Boolean {
        val x = tokens.getValue(a); val y = tokens.getValue(b)
        return x.isNotEmpty() && y.isNotEmpty() && x.intersect(y).size.toDouble() / minOf(x.size, y.size) >= 0.55
    }
    val ranked = fresh.sortedByDescending { a ->
        val coverage = fresh.filter { it.source != a.source && same(a, it) }.map { it.source }.distinct().size
        coverage * 10.0 + (a.published - (now - hours * 3600000L)).toDouble() / (hours * 3600000L)
    }
    val picked = mutableListOf<Article>()
    for (a in ranked) if (picked.none { same(it, a) }) { picked.add(a); if (picked.size == 3) break }
    return picked
}
val feedPresets = listOf(
    Feed("rbc", "РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    Feed("lenta", "Лента.ру", "https://lenta.ru/rss/news"),
    Feed("habr", "Хабр · Технологии", "https://habr.com/ru/rss/all/all/?fl=ru"),
    Feed("tass", "ТАСС", "https://tass.ru/rss/v2.xml"),
    Feed("bbc", "BBC · Мир", "https://feeds.bbci.co.uk/news/world/rss.xml")
)
object News {
    suspend fun load(feeds: List<Feed>): Pair<List<Article>, List<String>> = withContext(Dispatchers.IO) {
        supervisorScope {
            val results = feeds.map { feed -> async {
                try {
                    require(safeWebUrl(feed.url)) { "Нужна HTTPS-ссылка" }
                    val c = URL(feed.url).openConnection() as HttpURLConnection
                    c.connectTimeout = 10000; c.readTimeout = 10000; c.setRequestProperty("User-Agent", "Dayline/0.2 RSS reader")
                    try {
                        check(c.responseCode == 200) { "HTTP ${c.responseCode}" }
                        val bytes = c.inputStream.use { input ->
                            val output = java.io.ByteArrayOutputStream(); val buffer = ByteArray(8192)
                            while (true) { val count = input.read(buffer); if (count < 0) break; output.write(buffer, 0, count); check(output.size() <= 2 * 1024 * 1024) { "Лента слишком большая" } }
                            output.toByteArray()
                        }
                        check(bytes.size <= 2 * 1024 * 1024) { "Лента слишком большая" }
                        val content = bytes.toString(Charsets.UTF_8)
                        val list = parseFeed(content, feed)
                        check(list.isNotEmpty()) { "В ленте нет статей. Проверьте адрес RSS." }
                        list to null
                    } finally { c.disconnect() }
                } catch (cancel: CancellationException) { throw cancel }
                catch (e: Exception) { emptyList<Article>() to "${feed.name}: ${e.message ?: "источник недоступен"}" }
            } }.awaitAll()
            results.flatMap { it.first }.distinctBy { it.url }.sortedByDescending { it.published }.take(100) to results.mapNotNull { it.second }
        }
    }
}
