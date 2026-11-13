package app.dayline

/** A split is committed as one document change so autosave never sees half a list. */
data class ListEdit(val blocks: List<Block>, val focusId: String, val cursor: Int)
fun splitListOnEnter(blocks: List<Block>, id: String, text: String, cursor: Int): ListEdit? {
    val index = blocks.indexOfFirst { it.id == id }
    if (index < 0) return null
    val block = blocks[index]
    if (block.kind !in listOf("check", "bullet") || block.text == text) return null
    val prefix = block.text.commonPrefixWith(text).length
    var suffix = 0
    while (suffix < block.text.length - prefix && suffix < text.length - prefix && block.text[block.text.lastIndex - suffix] == text[text.lastIndex - suffix]) suffix++
    if ('\n' !in text.substring(prefix, text.length - suffix)) return null
    if (block.text.isBlank() && text.isBlank()) {
        val paragraph = block.copy(kind = "text", text = "", checked = false, indent = 0)
        return ListEdit(blocks.toMutableList().apply { set(index, paragraph) }, paragraph.id, 0)
    }
    val lines = text.split('\n')
    val replacements = lines.mapIndexed { line, value ->
        if (line == 0) block.copy(text = value) else block.copy(id = newId(), text = value, checked = false)
    }
    val position = cursor.coerceIn(0, text.length)
    val line = text.take(position).count { it == '\n' }.coerceAtMost(replacements.lastIndex)
    val column = position - (text.lastIndexOf('\n', (position - 1).coerceAtLeast(0)) + 1)
    val next = blocks.toMutableList().apply { removeAt(index); addAll(index, replacements) }
    return ListEdit(next, replacements[line].id, column.coerceIn(0, replacements[line].text.length))
}

fun rememberAwards(s: DayState): DayState {
    val earned = s.habits.flatMap { h -> medals(h).map { target ->
        Medal("${h.id}:$target", h.id, h.title, target, h.completed.sorted()[target - 1])
    } }
    return s.copy(awards = (s.awards + earned).distinctBy { it.id })
}
fun medalTitle(target: Int): String = when (target) { 1 -> "Первый шаг"; 7 -> "В своём ритме"; 30 -> "Уверенный рост"; else -> "Мастер привычки" }
