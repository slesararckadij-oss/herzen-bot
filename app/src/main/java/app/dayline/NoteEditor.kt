package app.dayline

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.takeOrElse
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.*
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun NoteEditor(note: Note, mode: String, onChange: (Note) -> Unit, onMode: (String) -> Unit, onClose: () -> Unit) {
    var selected by remember(note.id) { mutableStateOf(note.blocks.firstOrNull()?.id) }
    var menu by remember { mutableStateOf(false) }
    var focusBlock by remember { mutableStateOf<String?>(null) }
    val listState = rememberLazyListState()
    LaunchedEffect(focusBlock) {
        val index = note.blocks.indexOfFirst { it.id == focusBlock }
        if (index >= 0) listState.animateScrollToItem(index + 1)
    }
    val colors = MaterialTheme.colorScheme
    val blockMode = mode == "blocks"
    fun changeBlock(block: Block) { onChange(note.copy(blocks = note.blocks.map { if (it.id == block.id) block else it })) }
    fun add(kind: String) {
        val block = Block(kind = kind, cells = if (kind == "table") List(2) { List(2) { "" } } else emptyList())
        val list = note.blocks.toMutableList(); val at = list.indexOfFirst { it.id == selected }; list.add(if (at < 0) list.size else at + 1, block)
        selected = block.id; focusBlock = block.id; onChange(note.copy(blocks = list))
    }
    val active = note.blocks.firstOrNull { it.id == selected }
    BackHandler(onBack = onClose)
    Scaffold(topBar = {
        TopAppBar(title = { Text("Заметка", style = MaterialTheme.typography.titleMedium) }, navigationIcon = { IconButton(onClick = onClose) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Сохранить и вернуться") } }, actions = { TextButton(onClick = onClose) { Text("Готово") } })
    }, bottomBar = {
        Surface(tonalElevation = 3.dp) {
            Column(Modifier.navigationBarsPadding().imePadding()) {
                HorizontalDivider()
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { add("text") }) { Icon(Icons.Rounded.Add, "Добавить текст") }
                    TextButton(onClick = { add("heading") }) { Text("H", fontWeight = FontWeight.Black) }
                    IconButton(onClick = { add("check") }) { Icon(Icons.Rounded.Checklist, "Добавить чек-лист") }
                    IconButton(onClick = { add("bullet") }) { Icon(Icons.Rounded.FormatListBulleted, "Добавить список") }
                    IconButton(onClick = { add("table") }) { Icon(Icons.Rounded.TableChart, "Добавить таблицу") }
                    VerticalDivider(Modifier.height(24.dp))
                    TextButton(enabled = active != null && active.kind != "table", onClick = { active?.let { changeBlock(it.copy(bold = !it.bold)) } }) { Text("B", fontWeight = FontWeight.Black, color = if (active?.bold == true) colors.primary else colors.onSurface) }
                    TextButton(enabled = active != null && active.kind != "table", onClick = { active?.let { changeBlock(it.copy(italic = !it.italic)) } }) { Text("I", fontStyle = FontStyle.Italic, color = if (active?.italic == true) colors.primary else colors.onSurface) }
                }
            }
        }
    }) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), state = listState, contentPadding = PaddingValues(horizontal = 22.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = !blockMode, onClick = { onMode("simple") }, label = { Text("Простой") })
                    FilterChip(selected = blockMode, onClick = { onMode("blocks") }, label = { Text("Блоки") })
                }
                Text(if (blockMode) "Страница из блоков · текст, списки, таблицы" else "Свободная страница · инструменты внизу", style = MaterialTheme.typography.labelMedium, color = colors.onSurfaceVariant)
                Spacer(Modifier.height(20.dp))
                EditorField(note.title, { onChange(note.copy(title = it)) }, "Без названия", MaterialTheme.typography.headlineLarge.copy(fontWeight = FontWeight.Bold), Modifier.fillMaxWidth())
                Spacer(Modifier.height(16.dp)); HorizontalDivider(); Spacer(Modifier.height(12.dp))
            }
            itemsIndexed(note.blocks, key = { _, b -> b.id }) { index, b ->
                val chosen = selected == b.id
                val focusRequester = remember(b.id) { FocusRequester() }
                LaunchedEffect(focusBlock, b.id) { if (focusBlock == b.id && b.kind != "table") focusRequester.requestFocus() }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                    if (blockMode) Icon(Icons.Rounded.DragIndicator, null, Modifier.padding(top = 12.dp, end = 6.dp).size(18.dp), tint = colors.outline)
                    Column(Modifier.weight(1f).then(if (blockMode && chosen) Modifier.background(colors.surfaceContainerLow, RoundedCornerShape(10.dp)).padding(8.dp) else Modifier)) {
                        if (b.kind == "table") {
                            Column(Modifier.fillMaxWidth().onFocusChanged { if (it.hasFocus) selected = b.id }.clickable { selected = b.id }) {
                                Column(Modifier.horizontalScroll(rememberScrollState())) {
                                    b.cells.forEachIndexed { row, cells ->
                                        Row {
                                            cells.forEachIndexed { col, value ->
                                                OutlinedTextField(value, { text -> changeBlock(b.copy(cells = b.cells.mapIndexed { ri, rr -> rr.mapIndexed { ci, cc -> if (ri == row && ci == col) text else cc } })) }, Modifier.width(145.dp).padding(2.dp).onFocusChanged { if (it.hasFocus) selected = b.id }, placeholder = { Text(if (row == 0) "Заголовок" else "Ячейка") }, textStyle = MaterialTheme.typography.bodyMedium.copy(fontWeight = if (row == 0) FontWeight.Bold else FontWeight.Normal), maxLines = 5)
                                            }
                                        }
                                    }
                                }
                                Row(Modifier.horizontalScroll(rememberScrollState())) {
                                    TextButton(onClick = { changeBlock(b.copy(cells = b.cells + listOf(List(b.cells.firstOrNull()?.size ?: 2) { "" }))) }) { Text("+ Строка") }
                                    TextButton(enabled = (b.cells.firstOrNull()?.size ?: 0) < 6, onClick = { changeBlock(b.copy(cells = b.cells.map { it + "" })) }) { Text("+ Столбец") }
                                    TextButton(enabled = b.cells.size > 1, onClick = { changeBlock(b.copy(cells = b.cells.dropLast(1))) }) { Text("− Строка") }
                                    TextButton(enabled = (b.cells.firstOrNull()?.size ?: 0) > 1, onClick = { changeBlock(b.copy(cells = b.cells.map { it.dropLast(1) })) }) { Text("− Столбец") }
                                }
                            }
                        } else {
                            Row(Modifier.padding(start = (b.indent * 20).dp), verticalAlignment = Alignment.Top) {
                                if (b.kind == "check") Checkbox(b.checked, { changeBlock(b.copy(checked = it)) }, Modifier.size(42.dp))
                                if (b.kind == "bullet") Text("•", Modifier.padding(top = 10.dp, end = 12.dp), style = MaterialTheme.typography.titleMedium)
                                val style = (if (b.kind == "heading") MaterialTheme.typography.titleLarge else MaterialTheme.typography.bodyLarge).copy(
                                    color = if (b.checked && b.kind == "check") colors.onSurfaceVariant else colors.onSurface,
                                    fontWeight = if (b.bold || b.kind == "heading") FontWeight.Bold else FontWeight.Normal,
                                    fontStyle = if (b.italic) FontStyle.Italic else FontStyle.Normal,
                                    textDecoration = if (b.checked && b.kind == "check") TextDecoration.LineThrough else null
                                )
                                EditorField(b.text, { changeBlock(b.copy(text = it)) }, when (b.kind) { "heading" -> "Заголовок"; "check" -> "Пункт списка"; "bullet" -> "Элемент списка"; else -> if (index == 0) "Начни писать…" else "Текст" }, style, Modifier.weight(1f).focusRequester(focusRequester).padding(vertical = 10.dp).onFocusChanged { if (it.isFocused) selected = b.id })
                            }
                        }
                        if (chosen) Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically) {
                            Box {
                                TextButton(onClick = { menu = true }) { Text(when (b.kind) { "heading" -> "Заголовок ▾"; "check" -> "Чек-лист ▾"; "bullet" -> "Список ▾"; "table" -> "Таблица ▾"; else -> "Текст ▾" }, style = MaterialTheme.typography.labelSmall) }
                                DropdownMenu(menu, { menu = false }) {
                                    if (b.kind != "table") listOf("text" to "Текст", "heading" to "Заголовок", "check" to "Чек-лист", "bullet" to "Список").forEach { (kind, name) -> DropdownMenuItem(text = { Text(name) }, onClick = { changeBlock(b.copy(kind = kind)); menu = false }) }
                                    DropdownMenuItem(text = { Text("Удалить блок") }, onClick = { val next = note.blocks.filterNot { it.id == b.id }; onChange(note.copy(blocks = next.ifEmpty { listOf(Block()) })); menu = false })
                                }
                            }
                            if (b.kind in listOf("check", "bullet")) {
                                IconButton(enabled = b.indent > 0, onClick = { changeBlock(b.copy(indent = b.indent - 1)) }) { Icon(Icons.Rounded.FormatIndentDecrease, "Уменьшить отступ", Modifier.size(18.dp)) }
                                IconButton(enabled = b.indent < 2, onClick = { changeBlock(b.copy(indent = b.indent + 1)) }) { Icon(Icons.Rounded.FormatIndentIncrease, "Сделать подпункт", Modifier.size(18.dp)) }
                            }
                            if (blockMode) {
                                IconButton(enabled = index > 0, onClick = { val next = note.blocks.toMutableList(); next.add(index - 1, next.removeAt(index)); onChange(note.copy(blocks = next)) }) { Icon(Icons.Rounded.KeyboardArrowUp, "Блок выше") }
                                IconButton(enabled = index < note.blocks.lastIndex, onClick = { val next = note.blocks.toMutableList(); next.add(index + 1, next.removeAt(index)); onChange(note.copy(blocks = next)) }) { Icon(Icons.Rounded.KeyboardArrowDown, "Блок ниже") }
                            }
                        }
                    }
                }
            }
            item { TextButton(onClick = { add("text") }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Rounded.Add, null); Spacer(Modifier.width(8.dp)); Text("Продолжить заметку") }; Text("Сохраняется автоматически на устройстве", style = MaterialTheme.typography.labelSmall, color = colors.onSurfaceVariant, modifier = Modifier.padding(vertical = 16.dp)) }
        }
    }
}

@Composable private fun EditorField(value: String, onChange: (String) -> Unit, placeholder: String, style: TextStyle, modifier: Modifier) {
    val color = MaterialTheme.colorScheme.onSurface
    BasicTextField(value, onChange, modifier, textStyle = style.copy(color = style.color.takeOrElse { color }), cursorBrush = androidx.compose.ui.graphics.SolidColor(MaterialTheme.colorScheme.primary), decorationBox = { field -> Box { if (value.isEmpty()) Text(placeholder, style = style.copy(color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = .6f))); field() } })
}
