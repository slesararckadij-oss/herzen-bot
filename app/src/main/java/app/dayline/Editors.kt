package app.dayline

import android.app.DatePickerDialog
import android.content.Intent
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun EditorPage(title: String, canSave: Boolean, onBack: () -> Unit, onSave: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    BackHandler(onBack = onBack)
    Scaffold(topBar = { TopAppBar(title = { Text(title) }, navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Отменить") } }, actions = { TextButton(enabled = canSave, onClick = onSave) { Text("Сохранить") } }) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(20.dp), content = content)
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun PickTime(hour: Int, minute: Int, onDismiss: () -> Unit, onPick: (Int, Int) -> Unit) {
    val state = rememberTimePickerState(hour, minute, true)
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Выбрать время") }, text = { TimeInput(state) }, confirmButton = { TextButton(onClick = { onPick(state.hour, state.minute) }) { Text("Готово") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } })
}
@Composable fun DaysSelector(days: Set<Int>, onChange: (Set<Int>) -> Unit) {
    val names = listOf("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
    Column {
        Text("Дни недели", style = MaterialTheme.typography.labelLarge)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            names.forEachIndexed { index, name ->
                val day = index + 1
                FilterChip(selected = day in days, onClick = { if (day !in days) onChange(days + day) else if (days.size > 1) onChange(days - day) }, label = { Text(name, style = MaterialTheme.typography.labelSmall) }, modifier = Modifier.weight(1f))
            }
        }
    }
}
@Composable fun TaskEditor(task: Task, onChange: (Task) -> Unit, onBack: () -> Unit, onSave: () -> Unit) {
    val context = LocalContext.current
    var time by remember { mutableStateOf(false) }
    EditorPage("Задача", task.text.isNotBlank(), onBack, onSave) {
        OutlinedTextField(task.text, { onChange(task.copy(text = it)) }, Modifier.fillMaxWidth(), label = { Text("Что нужно сделать?") }, minLines = 2)
        SectionHeader("Подзадачи", "Разбей большое дело на шаги")
        task.subtasks.forEach { item ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(item.done, { checked -> onChange(task.copy(subtasks = task.subtasks.map { if (it.id == item.id) it.copy(done = checked) else it })) })
                OutlinedTextField(item.text, { text -> onChange(task.copy(subtasks = task.subtasks.map { if (it.id == item.id) it.copy(text = text) else it })) }, Modifier.weight(1f), placeholder = { Text("Шаг") })
                IconButton(onClick = { onChange(task.copy(subtasks = task.subtasks.filterNot { it.id == item.id })) }) { Icon(Icons.Rounded.Close, "Удалить подзадачу") }
            }
        }
        TextButton(onClick = { onChange(task.copy(subtasks = task.subtasks + CheckItem(text = ""))) }) { Icon(Icons.Rounded.Add, null); Text("Подзадача") }
        HorizontalDivider()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text("Срок выполнения", style = MaterialTheme.typography.titleMedium); Text(task.dueDate.ifBlank { "Без срока" }, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            TextButton(onClick = { val d = runCatching { LocalDate.parse(task.dueDate) }.getOrDefault(LocalDate.now()); DatePickerDialog(context, { _, y, m, day -> onChange(task.copy(dueDate = LocalDate.of(y, m + 1, day).toString())) }, d.year, d.monthValue - 1, d.dayOfMonth).show() }) { Text("Выбрать") }
            if (task.dueDate.isNotEmpty()) IconButton(onClick = { onChange(task.copy(dueDate = "", reminder = false)) }) { Icon(Icons.Rounded.Close, "Убрать срок") }
        }
        ToggleRow("Напоминать о сроке", "За 2 дня, за день и в день срока", task.reminder, task.dueDate.isNotEmpty()) { onChange(task.copy(reminder = it)) }
        if (task.reminder) TextButton(onClick = { time = true }) { Text("Время уведомления: %02d:%02d".format(task.reminderHour, task.reminderMinute)) }
        Text("Напоминания приходят как уведомления, без громкого сигнала будильника. Энергосбережение Android может задержать доставку.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (time) PickTime(task.reminderHour, task.reminderMinute, { time = false }) { h, m -> onChange(task.copy(reminderHour = h, reminderMinute = m)); time = false }
}
@Composable fun AlarmEditor(alarm: WakeAlarm, onChange: (WakeAlarm) -> Unit, onBack: () -> Unit, onSave: () -> Unit) {
    val context = LocalContext.current
    var time by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    val ringtone = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val data = result.data
        @Suppress("DEPRECATION")
        val uri: Uri? = if (Build.VERSION.SDK_INT >= 33) data?.getParcelableExtra(RingtoneManager.EXTRA_RINGTONE_PICKED_URI, Uri::class.java) else data?.getParcelableExtra(RingtoneManager.EXTRA_RINGTONE_PICKED_URI)
        if (result.resultCode == android.app.Activity.RESULT_OK && uri != null) {
            val name = runCatching { RingtoneManager.getRingtone(context, uri)?.getTitle(context) }.getOrNull() ?: "Мелодия будильника"
            onChange(alarm.copy(sound = uri.toString(), soundName = name))
        }
    }
    val file = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) runCatching { context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION); onChange(alarm.copy(sound = uri.toString(), soundName = "Аудиофайл")) }.onFailure { message = "Не удалось получить доступ к файлу. Выберите другую мелодию." }
    }
    EditorPage("Настроить будильник", true, onBack, onSave) {
        Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.extraLarge, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(26.dp), horizontalAlignment = Alignment.CenterHorizontally) { Text("%02d:%02d".format(alarm.hour, alarm.minute), style = MaterialTheme.typography.displayLarge, fontWeight = FontWeight.Light, color = MaterialTheme.colorScheme.onPrimaryContainer); TextButton(onClick = { time = true }) { Text("Изменить время") } }
        }
        OutlinedTextField(alarm.label, { onChange(alarm.copy(label = it)) }, Modifier.fillMaxWidth(), label = { Text("Название") }, singleLine = true)
        DaysSelector(alarm.days) { onChange(alarm.copy(days = it)) }
        SectionHeader("Звук", alarm.soundName)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilledTonalButton(onClick = {
                runCatching { ringtone.launch(Intent(RingtoneManager.ACTION_RINGTONE_PICKER).putExtra(RingtoneManager.EXTRA_RINGTONE_TYPE, RingtoneManager.TYPE_ALARM).putExtra(RingtoneManager.EXTRA_RINGTONE_SHOW_DEFAULT, true).putExtra(RingtoneManager.EXTRA_RINGTONE_SHOW_SILENT, false).putExtra(RingtoneManager.EXTRA_RINGTONE_EXISTING_URI, if (alarm.sound.isBlank()) RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM) else Uri.parse(alarm.sound))) }.onFailure { message = "Системный выбор звука недоступен. Выберите аудиофайл." }
            }) { Text("Мелодии") }
            OutlinedButton(onClick = { file.launch(arrayOf("audio/*")) }) { Text("Свой файл") }
        }
        TextButton(onClick = { onChange(alarm.copy(sound = "", soundName = "Системная мелодия")) }) { Text("Использовать системную мелодию") }
        if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.error)
        ToggleRow("Вибрация", "Вместе со звуковым сигналом", alarm.vibrate) { onChange(alarm.copy(vibrate = it)) }
        ToggleRow("Мой день после подъёма", "После отключения открыть новости и планы", alarm.morning) { onChange(alarm.copy(morning = it)) }
        Text("Громкость берётся из системного уровня «Будильник». Повтор сигнала — через 5 минут.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (time) PickTime(alarm.hour, alarm.minute, { time = false }) { h, m -> onChange(alarm.copy(hour = h, minute = m)); time = false }
}
@Composable fun HabitEditor(habit: Habit, onChange: (Habit) -> Unit, onBack: () -> Unit, onSave: () -> Unit) {
    EditorPage("Привычка", habit.title.isNotBlank(), onBack, onSave) {
        Text("Маленькие действия. Большие перемены.", style = MaterialTheme.typography.headlineSmall)
        OutlinedTextField(habit.title, { onChange(habit.copy(title = it)) }, Modifier.fillMaxWidth(), label = { Text("Что хочешь делать регулярно?") }, placeholder = { Text("Например, читать 20 минут") })
        Text("Значок", style = MaterialTheme.typography.labelLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { listOf("🌱", "📚", "💪", "💧", "🧘", "🎯").forEach { emoji -> FilterChip(selected = habit.emoji == emoji, onClick = { onChange(habit.copy(emoji = emoji)) }, label = { Text(emoji) }) } }
        DaysSelector(habit.days) { onChange(habit.copy(days = it)) }
        Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.large) { Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text("Твои награды", style = MaterialTheme.typography.titleMedium); Text("🌱 Первый шаг · 1 выполнение\n🥉 В ритме · 7 выполнений\n🥈 Уверенный рост · 30 выполнений\n🥇 Мастер привычки · 100 выполнений"); Text("Одна отметка в день. Пропущенный запланированный день прерывает серию, но полученные медали остаются.", style = MaterialTheme.typography.bodySmall) } }
    }
}
@Composable fun ToggleRow(title: String, subtitle: String, checked: Boolean, enabled: Boolean = true, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { Column(Modifier.weight(1f).padding(end = 12.dp)) { Text(title, style = MaterialTheme.typography.titleMedium); Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }; Switch(checked, onChange, enabled = enabled) }
}
@Composable fun SectionHeader(title: String, subtitle: String = "") { Column { Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold); if (subtitle.isNotEmpty()) Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) } }
