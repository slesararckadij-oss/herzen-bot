package app.dayline

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.text.selection.DisableSelection
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun NoteReader(note: Note, onBack: () -> Unit, onEdit: () -> Unit, onCheck: (String, Boolean) -> Unit) {
    BackHandler(onBack = onBack)
    val colors = MaterialTheme.colorScheme
    Scaffold(topBar = {
        TopAppBar(title = { Text("Заметка", style = MaterialTheme.typography.titleMedium) }, navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "К заметкам") } }, actions = { TextButton(onClick = onEdit) { Icon(Icons.Rounded.Edit, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Редактировать") } })
    }) { padding ->
        SelectionContainer {
            Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(top = 20.dp, bottom = 64.dp)) {
                Text(note.title.ifBlank { "Без названия" }, style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(22.dp))
                note.content().filterNot { it.kind in listOf("check", "bullet") && it.text.isBlank() }.forEach { block ->
                    if (block.kind == "table") {
                        Column(Modifier.padding(vertical = 12.dp).horizontalScroll(rememberScrollState())) {
                            block.cells.forEachIndexed { row, cells ->
                                Row {
                                    cells.forEach { text ->
                                        Surface(color = if (row == 0) colors.surfaceContainer else colors.background, border = BorderStroke(1.dp, colors.outlineVariant)) {
                                            Box(Modifier.width(140.dp).defaultMinSize(minHeight = 48.dp).padding(12.dp)) { Text(text.ifEmpty { " " }, style = MaterialTheme.typography.bodyMedium, fontWeight = if (row == 0) FontWeight.SemiBold else FontWeight.Normal) }
                                        }
                                    }
                                }
                            }
                        }
                    } else {
                        val list = block.kind in listOf("check", "bullet")
                        val heading = block.kind == "heading"
                        Row(Modifier.fillMaxWidth().padding(start = (block.indent * 20).dp, top = if (heading) 18.dp else if (list) 0.dp else 5.dp, bottom = if (heading) 10.dp else if (list) 0.dp else 5.dp), verticalAlignment = Alignment.Top) {
                            if (block.kind == "check") DisableSelection { Checkbox(block.checked, { onCheck(block.id, it) }, Modifier.size(40.dp)) }
                            if (block.kind == "bullet") Text("•", Modifier.width(24.dp).padding(top = 7.dp), style = MaterialTheme.typography.bodyLarge)
                            Text(block.text.ifEmpty { " " }, modifier = Modifier.weight(1f).padding(vertical = if (list) 7.dp else 0.dp), style = if (heading) MaterialTheme.typography.titleLarge else MaterialTheme.typography.bodyLarge,
                                fontWeight = if (heading || block.bold) FontWeight.Bold else FontWeight.Normal,
                                fontStyle = if (block.italic) FontStyle.Italic else FontStyle.Normal,
                                textDecoration = if (block.kind == "check" && block.checked) TextDecoration.LineThrough else null,
                                color = if (block.kind == "check" && block.checked) colors.onSurfaceVariant else colors.onSurface)
                        }
                    }
                }
            }
        }
    }
}
