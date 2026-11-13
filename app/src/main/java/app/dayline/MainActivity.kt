package app.dayline

import android.Manifest
import android.app.Application
import android.appwidget.AppWidgetManager
import android.content.*
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.net.Uri
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.*
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.*
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

class DayModel(app: Application) : AndroidViewModel(app) {
    private val store = Store(app)
    var state by mutableStateOf(store.read()); private set
    var tab by mutableIntStateOf(0)
    var noteDraft by mutableStateOf<Note?>(null)
    var viewedNoteId by mutableStateOf<String?>(null)
    var taskDraft by mutableStateOf<Task?>(null)
    var habitDraft by mutableStateOf<Habit?>(null)
    var alarmDraft by mutableStateOf<WakeAlarm?>(null)
    var loading by mutableStateOf(false); private set
    var newsErrors by mutableStateOf<List<String>>(emptyList()); private set
    var error by mutableStateOf<String?>(null)
    var reward by mutableStateOf<Pair<String, Int>?>(null)
    fun update(change: (DayState) -> DayState) { error = null; try { state = store.update(change) } catch (e: Exception) { error = e.message ?: "Не удалось сохранить данные" } }
    fun reload() { try { state = store.read() } catch (_: Exception) { error = "Не удалось прочитать данные. Не удаляйте приложение." } }
    fun openNote(n: Note) { viewedNoteId = n.id }
    fun editNote(n: Note = Note()) { noteDraft = n.copy(blocks = n.content()) }
    fun persistDraft() {
        val n = noteDraft ?: return
        if (n.title.isBlank() && n.preview().isBlank() && state.notes.none { it.id == n.id }) return
        val saved = n.copy(body = n.preview(), updated = System.currentTimeMillis())
        update { old -> old.copy(notes = if (old.notes.any { it.id == n.id }) old.notes.map { if (it.id == n.id) saved else it } else listOf(saved) + old.notes) }
    }
    fun refresh() {
        if (loading) return
        loading = true
        val feeds = state.feeds
        viewModelScope.launch {
            try {
                val (articles, errors) = News.load(feeds); newsErrors = errors
                if (articles.isNotEmpty()) update { old -> old.copy(news = articles.filter { a -> old.feeds.any { it.name == a.source } }, newsUpdated = System.currentTimeMillis()) }
            } catch (cancel: CancellationException) { throw cancel }
            catch (e: Exception) { newsErrors = listOf(e.message ?: "Не удалось обновить новости") }
            finally { loading = false }
        }
    }
}
class MainActivity : ComponentActivity() {
    private lateinit var model: DayModel
    private var hadExactAccess = false
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        model = ViewModelProvider(this)[DayModel::class.java]
        if (savedInstanceState == null) handleIntent(intent)
        hadExactAccess = Alarms.canSchedule(this); Alarms.channels(this)
        setContent { DaylineTheme(model.state.theme) { Dayline(model) } }
    }
    private fun handleIntent(i: Intent) { if (i.hasExtra("tab")) model.tab = i.getIntExtra("tab", 0).coerceIn(0, 4); if (i.getBooleanExtra("addTask", false)) model.taskDraft = Task(text = ""); if (i.getBooleanExtra("morning", false)) model.refresh() }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); handleIntent(intent) }
    override fun onResume() { super.onResume(); if (::model.isInitialized) model.reload(); val access = Alarms.canSchedule(this); if (access && !hadExactAccess) Alarms.restore(this); hadExactAccess = access }
    override fun onStop() { if (::model.isInitialized) model.persistDraft(); super.onStop() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun Dayline(vm: DayModel = viewModel()) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val s = vm.state; val colors = MaterialTheme.colorScheme
    val scrollStates = List(5) { rememberLazyListState() }
    var settings by remember { mutableStateOf(false) }
    var digestTime by remember { mutableStateOf(false) }
    var feedDialog by remember { mutableStateOf(false) }
    var taskPage by remember { mutableIntStateOf(0) }
    var search by remember { mutableStateOf("") }
    var deleteNote by remember { mutableStateOf<Note?>(null) }
    var deleteHabit by remember { mutableStateOf<Habit?>(null) }
    var permissionMessage by remember { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { if (!it) vm.error = "Уведомления выключены. Разрешите их в настройках телефона." }
    fun notifications() { if (!Alarms.allowedNotifications(context) && Build.VERSION.SDK_INT >= 33) permission.launch(Manifest.permission.POST_NOTIFICATIONS) }
    fun requestExact(): Boolean {
        notifications()
        if (!Alarms.canSchedule(context)) { permissionMessage = true; return false }
        return true
    }
    if (vm.error != null) AlertDialog(onDismissRequest = { vm.error = null }, title = { Text("Обрати внимание") }, text = { Text(vm.error ?: "") }, confirmButton = { TextButton(onClick = { vm.error = null }) { Text("Понятно") } })
    vm.reward?.let { (title, count) ->
        AlertDialog(onDismissRequest = { vm.reward = null }, icon = { Surface(shape = CircleShape, color = colors.tertiaryContainer) { Icon(Icons.Rounded.EmojiEvents, null, Modifier.padding(24.dp).size(54.dp), tint = colors.onTertiaryContainer) } }, title = { Text(when (count) { 1 -> "Первый шаг!"; 7 -> "Ты в ритме!"; 30 -> "Уверенный рост!"; else -> "Мастер привычки!" }) }, text = { Text("$title · $count выполнений. Эта медаль — за твоё постоянство.") }, confirmButton = { TextButton(onClick = { vm.reward = null }) { Text("Забрать медаль") } })
    }
    val note = vm.noteDraft
    if (note != null) {
        LaunchedEffect(note) { delay(700); vm.persistDraft() }
        NoteEditor(note, s.layout, { vm.noteDraft = it }, { mode -> vm.update { it.copy(layout = mode) } }, { vm.persistDraft(); if (vm.error == null) { vm.viewedNoteId = note.id.takeIf { id -> vm.state.notes.any { it.id == id } }; vm.noteDraft = null } })
        return
    }
    val viewedNote = s.notes.firstOrNull { it.id == vm.viewedNoteId }
    if (viewedNote != null) {
        NoteReader(viewedNote, { vm.viewedNoteId = null }, { vm.editNote(viewedNote) }) { id, checked ->
            vm.update { old -> old.copy(notes = old.notes.map { n -> if (n.id == viewedNote.id) n.copy(blocks = n.content().map { b -> if (b.id == id) b.copy(checked = checked) else b }, updated = System.currentTimeMillis()) else n }) }
        }
        return
    }
    vm.taskDraft?.let { t -> TaskEditor(t, { vm.taskDraft = it }, { vm.taskDraft = null }, {
        val cleaned = t.copy(text = t.text.trim(), subtasks = t.subtasks.filter { it.text.isNotBlank() })
        vm.update { old -> old.copy(tasks = if (old.tasks.any { it.id == t.id }) old.tasks.map { if (it.id == t.id) cleaned else it } else old.tasks + cleaned) }
        if (vm.error == null) { Alarms.task(context, cleaned); if (cleaned.reminder) notifications(); vm.taskDraft = null }
    }); return }
    vm.habitDraft?.let { h -> HabitEditor(h, { vm.habitDraft = it }, { vm.habitDraft = null }, { vm.update { old -> old.copy(habits = if (old.habits.any { it.id == h.id }) old.habits.map { if (it.id == h.id) h else it } else old.habits + h) }; if (vm.error == null) vm.habitDraft = null }); return }
    vm.alarmDraft?.let { a -> AlarmEditor(a, { vm.alarmDraft = it }, { vm.alarmDraft = null }, {
        if (requestExact()) {
            vm.update { old -> old.copy(alarms = if (old.alarms.any { it.id == a.id }) old.alarms.map { if (it.id == a.id) a else it } else old.alarms + a) }
            if (vm.error == null) { Alarms.schedule(context, a); vm.alarmDraft = null }
        }
    })
        if (permissionMessage) ExactPermission({ permissionMessage = false }) { context.startActivity(Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:${context.packageName}"))); permissionMessage = false }
        return
    }
    LaunchedEffect(vm.tab) { if (vm.tab in listOf(0, 4) && (s.newsUpdated == 0L || System.currentTimeMillis() - s.newsUpdated > 15 * 60000)) vm.refresh() }
    val names = listOf("Мой день", "Задачи", "Заметки", "Будильник", "Новости")
    val icons = listOf(Icons.Rounded.WbSunny, Icons.Rounded.CheckCircleOutline, Icons.Rounded.Description, Icons.Rounded.Alarm, Icons.Rounded.Newspaper)
    Scaffold(topBar = {
        TopAppBar(title = { Column { Text(names[vm.tab], fontWeight = FontWeight.Bold); Text(if (vm.tab == 0) LocalDate.now().format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale.forLanguageTag("ru"))) else "dayline", style = MaterialTheme.typography.labelSmall, color = colors.onSurfaceVariant) } }, actions = { IconButton(onClick = { settings = true }) { Icon(Icons.Rounded.Tune, "Оформление и настройки") } })
    }, bottomBar = {
        NavigationBar { names.forEachIndexed { index, label -> NavigationBarItem(selected = vm.tab == index, onClick = { vm.tab = index }, icon = { Icon(icons[index], label) }, label = { Text(label, maxLines = 1, style = MaterialTheme.typography.labelSmall) }) } }
    }, floatingActionButton = {
        if (vm.tab in 1..3 && !(vm.tab == 1 && taskPage == 2)) ExtendedFloatingActionButton(onClick = {
            when (vm.tab) {
                1 -> if (taskPage == 1) vm.habitDraft = Habit(title = "") else vm.taskDraft = Task(text = "")
                2 -> vm.editNote()
                3 -> vm.alarmDraft = WakeAlarm((1..900000).first { id -> s.alarms.none { it.id == id } }, 7, 30)
            }
        }, icon = { Icon(Icons.Rounded.Add, "Добавить") }, text = { Text(when (vm.tab) { 2 -> "Заметка"; 3 -> "Будильник"; else -> if (taskPage == 1) "Привычка" else "Задача" }) })
    }) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), state = scrollStates[vm.tab], contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 10.dp, bottom = 110.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            when (vm.tab) {
                0 -> {
                    item { HeroCard(s) { vm.tab = 1 } }
                    item { SectionHeader("Три главных за ночь", "За последние 12 часов · по свежести и освещению в разных источниках") }
                    val top = topStories(s.news)
                    if (vm.loading) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                    if (top.isEmpty()) item { EmptyCard("Тихое утро", if (s.feeds.isEmpty()) "Выбери источники на вкладке «Новости»." else "Свежих заголовков пока нет. Проверь обновление и доступность источников.", Icons.Rounded.WbTwilight) }
                    items(top, key = { "top-${it.url}" }) { ArticleCard(it, top.indexOf(it) + 1) }
                    if (vm.newsErrors.isNotEmpty()) item { Text(vm.newsErrors.joinToString("\n"), style = MaterialTheme.typography.bodySmall, color = colors.error) }
                    item { TextButton(onClick = { vm.tab = 4 }) { Text("Все новости и источники"); Icon(Icons.Rounded.ChevronRight, null) } }
                    val today = LocalDate.now()
                    val habits = s.habits.filter { today.dayOfWeek.value in it.days }
                    if (habits.isNotEmpty()) {
                        item { SectionHeader("Маленькие победы", "Твои привычки на сегодня") }
                        items(habits, key = { "home-${it.id}" }) { h -> HabitCard(h, { toggleHabit(vm, h) }, { vm.tab = 1; taskPage = 1 }, null, { vm.tab = 1; taskPage = 2 }) }
                    }
                    val tasks = s.tasks.filter { !it.done }.sortedBy { it.dueDate.ifEmpty { "9999" } }.take(3)
                    if (tasks.isNotEmpty()) {
                        item { SectionHeader("Следующие дела") }
                        items(tasks, key = { "home-task-${it.id}" }) { t -> TaskCard(t, { toggleTask(vm, t, context) }, { vm.taskDraft = t }, null) }
                    }
                    item { OutlinedButton(onClick = { val manager = AppWidgetManager.getInstance(context); if (Build.VERSION.SDK_INT >= 26 && manager.isRequestPinAppWidgetSupported) manager.requestPinAppWidget(ComponentName(context, MorningWidget::class.java), null, null) else vm.error = "Добавьте виджет Dayline через меню рабочего стола телефона." }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Rounded.Widgets, null); Spacer(Modifier.width(8.dp)); Text("Добавить виджет на рабочий стол") } }
                }
                1 -> {
                    item { ModeRow(listOf("Задачи", "Привычки", "Медали"), taskPage) { taskPage = it } }
                    if (taskPage == 0) {
                        val active = s.tasks.filterNot { it.done }.sortedBy { it.dueDate.ifEmpty { "9999" } }
                        if (s.tasks.isEmpty()) item { EmptyCard("Освободи голову", "Запиши дело, добавь шаги и срок. Мы напомним заранее.", Icons.Rounded.CheckCircleOutline) }
                        items(active, key = { it.id }) { t -> TaskCard(t, { toggleTask(vm, t, context) }, { vm.taskDraft = t }, { Alarms.removeTask(context, t); vm.update { it.copy(tasks = it.tasks.filterNot { x -> x.id == t.id }) } }) }
                        if (s.tasks.any { it.done }) item { SectionHeader("Готово · ${s.tasks.count { it.done }}") }
                        items(s.tasks.filter { it.done }, key = { it.id }) { t -> TaskCard(t, { toggleTask(vm, t, context) }, { vm.taskDraft = t }, { Alarms.removeTask(context, t); vm.update { it.copy(tasks = it.tasks.filterNot { x -> x.id == t.id }) } }) }
                    } else if (taskPage == 1) {
                        item { Surface(color = colors.tertiaryContainer, contentColor = legibleText(colors.tertiaryContainer, colors.onTertiaryContainer), shape = MaterialTheme.shapes.extraLarge) { Column(Modifier.fillMaxWidth().padding(24.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { Text("Каждый день — маленькая победа", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold); Text("Выполнено: ${s.habits.sumOf { it.completed.size }} · Медалей: ${s.awards.size}", color = legibleText(colors.tertiaryContainer, colors.onTertiaryContainer)) } } }
                        if (s.habits.isEmpty()) item { EmptyCard("С чего начнём?", "Вода, чтение или спорт — выбери свою привычку и дни недели.", Icons.Rounded.EmojiEvents) }
                        items(s.habits, key = { it.id }) { h -> HabitCard(h, { toggleHabit(vm, h) }, { vm.habitDraft = h }, { deleteHabit = h }, { taskPage = 2 }) }
                    } else {
                        item { SectionHeader("Моя коллекция", "Медали за твои достижения · всего ${s.awards.size}") }
                        if (s.awards.isEmpty()) item { EmptyCard("Первая медаль уже близко", "Отметь выполненную привычку. Здесь будут собраны твои награды.", Icons.Rounded.EmojiEvents) }
                        items(s.awards.sortedWith(compareByDescending<Medal> { it.earnedOn }.thenByDescending { it.target }), key = { it.id }) { medal -> MedalCard(medal) }
                        item { Text("Полученные медали остаются в коллекции при перерыве, отмене отметки и удалении привычки.", style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant) }
                        if (s.habits.isNotEmpty()) item { SectionHeader("Впереди новые победы") }
                        items(s.habits.filter { h -> listOf(1, 7, 30, 100).any { target -> s.awards.none { it.habitId == h.id && it.target == target } } }, key = { "next-${it.id}" }) { h ->
                            val target = listOf(1, 7, 30, 100).first { count -> s.awards.none { it.habitId == h.id && it.target == count } }
                            Card { Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text(h.title, style = MaterialTheme.typography.titleMedium); Text("${medalTitle(target)} · ${h.completed.size}/$target выполнений", style = MaterialTheme.typography.bodySmall); LinearProgressIndicator(progress = { (h.completed.size.toFloat() / target).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth()) } }
                        }
                    }
                }
                2 -> {
                    item {
                        OutlinedTextField(search, { search = it }, Modifier.fillMaxWidth(), leadingIcon = { Icon(Icons.Rounded.Search, null) }, placeholder = { Text("Найти в заметках") }, singleLine = true, shape = RoundedCornerShape(28.dp))
                        Spacer(Modifier.height(8.dp)); ModeRow(listOf("Простой", "Блоки"), if (s.layout == "blocks") 1 else 0) { mode -> vm.update { it.copy(layout = if (mode == 1) "blocks" else "simple") } }
                    }
                    val notes = s.notes.filter { search.isBlank() || it.title.contains(search, true) || it.preview().contains(search, true) }.sortedByDescending { it.updated }
                    if (notes.isEmpty()) item { EmptyCard(if (search.isEmpty()) "Место для твоих идей" else "Ничего не найдено", "Конспекты, покупки, планы — полноценная страница вместо маленького окна.", Icons.Rounded.EditNote) }
                    if (s.layout == "simple") {
                        items(notes.chunked(2), key = { it.first().id }) { row ->
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                row.forEach { n ->
                                    Box(Modifier.weight(1f)) { NoteCard(n, true, { vm.openNote(n) }, { deleteNote = n }) }
                                }
                                if (row.size == 1) Spacer(Modifier.weight(1f))
                            }
                        }
                    } else items(notes, key = { it.id }) { n -> NoteCard(n, false, { vm.openNote(n) }, { deleteNote = n }) }
                }
                3 -> {
                    item { Text("Просыпайся в своём ритме", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold) }
                    if (!Alarms.canSchedule(context)) item { ElevatedCard(onClick = { permissionMessage = true }) { Text("Нужно разрешение на точные будильники", Modifier.padding(18.dp), color = colors.error) } }
                    if (s.alarms.isEmpty()) item { EmptyCard("Завтра начинается сегодня", "Выбери время, дни недели и любимый звук.", Icons.Rounded.Alarm) }
                    items(s.alarms, key = { it.id }) { a ->
                        Card(onClick = { vm.alarmDraft = a }, colors = CardDefaults.cardColors(containerColor = if (a.enabled) colors.primaryContainer else colors.surfaceContainerLow), shape = MaterialTheme.shapes.extraLarge) {
                            Row(Modifier.fillMaxWidth().padding(22.dp), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) { Text("%02d:%02d".format(a.hour, a.minute), style = MaterialTheme.typography.displayMedium, fontWeight = FontWeight.Light); Text(a.label, style = MaterialTheme.typography.titleMedium); Text(daysLabel(a.days), style = MaterialTheme.typography.bodySmall); Text(a.soundName, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                                Column(horizontalAlignment = Alignment.End) {
                                    Switch(a.enabled, { enabled -> if (!enabled || requestExact()) { val next = a.copy(enabled = enabled); vm.update { it.copy(alarms = it.alarms.map { x -> if (x.id == a.id) next else x }) }; Alarms.schedule(context, next) } })
                                    IconButton(onClick = { Alarms.cancel(context, a.id); vm.update { it.copy(alarms = it.alarms.filterNot { x -> x.id == a.id }) } }) { Icon(Icons.Rounded.DeleteOutline, "Удалить будильник") }
                                }
                            }
                        }
                    }
                    item { Text("Если Android ограничивает фоновые приложения, разреши Dayline работу без ограничений батареи.", style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant) }
                    if (Build.VERSION.SDK_INT >= 34) item { TextButton(onClick = { context.startActivity(Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT, Uri.parse("package:${context.packageName}"))) }) { Text("Разрешить экран поверх блокировки") } }
                }
                4 -> {
                    item { Row(verticalAlignment = Alignment.CenterVertically) { Column(Modifier.weight(1f)) { SectionHeader("Твой выпуск", "${s.feeds.size} источников · новости и короткие описания") }; FilledTonalIconButton(onClick = { vm.refresh() }, enabled = !vm.loading) { Icon(Icons.Rounded.Refresh, "Обновить новости") } } }
                    item { Card { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        ToggleRow("Утренний дайджест", "Около %02d:%02d ежедневно".format(s.digestHour, s.digestMinute), s.digestEnabled) { enabled -> notifications(); vm.update { it.copy(digestEnabled = enabled) }; Alarms.digest(context, vm.state) }
                        TextButton(onClick = { digestTime = true }) { Text("Настроить время") }
                        Text("Три свежих события за 12 часов. Доставка может задержаться без сети или при энергосбережении.", style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
                    } } }
                    item { SectionHeader("Выбери источники") }
                    item { Column {
                        feedPresets.forEach { preset -> val checked = s.feeds.any { it.url == preset.url }; Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked, { selected -> vm.update { old -> old.copy(feeds = if (selected) old.feeds + preset else old.feeds.filterNot { it.url == preset.url }, news = old.news.filterNot { it.source == preset.name }) } }); Column(Modifier.weight(1f)) { Text(preset.name); Text(preset.url.substringAfter("https://").substringBefore('/'), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant) } } }
                        s.feeds.filter { custom -> feedPresets.none { it.url == custom.url } }.forEach { f -> Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.RssFeed, null, Modifier.padding(12.dp)); Text(f.name, Modifier.weight(1f)); IconButton(onClick = { vm.update { old -> old.copy(feeds = old.feeds.filterNot { it.id == f.id }, news = old.news.filterNot { it.source == f.name }) } }) { Icon(Icons.Rounded.Close, "Удалить источник") } } }
                        TextButton(onClick = { feedDialog = true }) { Icon(Icons.Rounded.Add, null); Text("Свой RSS-источник") }
                    } }
                    if (vm.loading) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                    if (vm.newsErrors.isNotEmpty()) item { Surface(color = colors.errorContainer, shape = MaterialTheme.shapes.large) { Column(Modifier.padding(16.dp)) { Text("Не все источники доступны", fontWeight = FontWeight.SemiBold); Text(vm.newsErrors.joinToString("\n"), style = MaterialTheme.typography.bodySmall) } } }
                    if (s.newsUpdated > 0) item { Text("Последнее успешное обновление: ${java.time.Instant.ofEpochMilli(s.newsUpdated).atZone(java.time.ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("d MMM, HH:mm", Locale.forLanguageTag("ru")))}", style = MaterialTheme.typography.labelSmall, color = colors.onSurfaceVariant) }
                    val top = topStories(s.news)
                    if (top.isNotEmpty()) { item { SectionHeader("В центре внимания", "Свежие события без повторов") }; items(top, key = { "news-top-${it.url}" }) { ArticleCard(it, top.indexOf(it) + 1) } }
                    item { SectionHeader("Вся лента", "Здесь остаются и статьи без даты публикации") }
                    if (s.news.isEmpty() && !vm.loading) item { EmptyCard("Пока нет новостей", "Выбери источники и нажми обновление. Если сайт недоступен, здесь появится причина.", Icons.Rounded.RssFeed) }
                    items(s.news, key = { it.url }) { ArticleCard(it) }
                }
            }
        }
    }

    if (settings) ModalBottomSheet(onDismissRequest = { settings = false }) { Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        SectionHeader("Сделай Dayline своим")
        Text("Цвета берутся из палитры Android 12+. На более ранних версиях используется тёплая стандартная тема.", style = MaterialTheme.typography.bodySmall)
        Text("Тема", style = MaterialTheme.typography.labelLarge); ModeRow(listOf("Системная", "Светлая", "Тёмная"), listOf("system", "light", "dark").indexOf(s.theme).coerceAtLeast(0)) { index -> vm.update { it.copy(theme = listOf("system", "light", "dark")[index]) } }
        Text("Оформление заметок", style = MaterialTheme.typography.labelLarge); ModeRow(listOf("Простой", "Блоки"), if (s.layout == "blocks") 1 else 0) { index -> vm.update { it.copy(layout = if (index == 1) "blocks" else "simple") } }
        Text("Оба режима открывают одни и те же заметки. Текст, таблицы и списки сохраняются при переключении.", style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
        Text("Dayline 0.3 · Всё личное хранится на телефоне", style = MaterialTheme.typography.labelSmall)
    } }
    if (digestTime) PickTime(s.digestHour, s.digestMinute, { digestTime = false }) { h, m -> vm.update { it.copy(digestHour = h, digestMinute = m) }; Alarms.digest(context, vm.state); digestTime = false }
    if (permissionMessage) ExactPermission({ permissionMessage = false }) { context.startActivity(Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:${context.packageName}"))); permissionMessage = false }
    if (feedDialog) FeedDialog({ feedDialog = false }) { f -> vm.update { it.copy(feeds = it.feeds + f) }; feedDialog = false }
    if (deleteNote != null) ConfirmDelete("Удалить заметку?", { deleteNote = null }) { val id = deleteNote?.id; vm.update { it.copy(notes = it.notes.filterNot { n -> n.id == id }) }; deleteNote = null }
    if (deleteHabit != null) ConfirmDelete("Удалить привычку и историю?", { deleteHabit = null }) { val id = deleteHabit?.id; vm.update { it.copy(habits = it.habits.filterNot { h -> h.id == id }) }; deleteHabit = null }
}

private fun toggleTask(vm: DayModel, t: Task, c: Context) { val next = t.copy(done = !t.done); vm.update { it.copy(tasks = it.tasks.map { old -> if (old.id == t.id) next else old }) }; Alarms.task(c, next) }
private fun toggleHabit(vm: DayModel, h: Habit) {
    val today = LocalDate.now().toString()
    var earned: Int? = null
    vm.update { old -> old.copy(habits = old.habits.map { current ->
        if (current.id != h.id) current else {
            val next = current.copy(completed = if (today in current.completed) current.completed - today else current.completed + today)
            earned = medals(next).filter { count -> old.awards.none { it.habitId == h.id && it.target == count } }.maxOrNull()
            next
        }
    }) }
    if (vm.error == null) earned?.let { vm.reward = h.title to it }
}
fun dueLabel(raw: String): String = runCatching {
    val date = LocalDate.parse(raw)
    when (date) { LocalDate.now() -> "Срок сегодня"; LocalDate.now().plusDays(1) -> "Срок завтра"; else -> "До " + date.format(DateTimeFormatter.ofPattern("d MMMM", Locale.forLanguageTag("ru"))) }
}.getOrDefault(raw)
fun daysLabel(days: Set<Int>): String = if (days.size == 7) "Каждый день" else if (days == (1..5).toSet()) "По будням" else days.sorted().joinToString(", ") { listOf("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")[it - 1] }

@Composable fun ModeRow(labels: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceContainer, RoundedCornerShape(24.dp)).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        labels.forEachIndexed { i, text -> Surface(onClick = { onSelect(i) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(20.dp), color = if (i == selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surfaceContainer, contentColor = if (i == selected) MaterialTheme.colorScheme.onSecondaryContainer else MaterialTheme.colorScheme.onSurfaceVariant) { Text(text, Modifier.padding(vertical = 12.dp), style = MaterialTheme.typography.labelLarge, textAlign = androidx.compose.ui.text.style.TextAlign.Center) } }
    }
}
@Composable fun HeroCard(s: DayState, onClick: () -> Unit) {
    val active = s.tasks.count { !it.done }; val today = LocalDate.now(); val habits = s.habits.filter { today.dayOfWeek.value in it.days }
    Card(onClick = onClick, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer), shape = MaterialTheme.shapes.extraLarge) {
        Column(Modifier.fillMaxWidth().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(Icons.Rounded.WbSunny, null, Modifier.size(32.dp)); Text("Хороший день\nначинается с тебя", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
            Text("$active ${if (active == 1) "дело" else "дел"} впереди · ${habits.count { today.toString() in it.completed }}/${habits.size} привычек", style = MaterialTheme.typography.bodyMedium)
        }
    }
}
@Composable fun EmptyCard(title: String, message: String, icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Surface(shape = MaterialTheme.shapes.extraLarge, color = MaterialTheme.colorScheme.surfaceContainerLow) { Column(Modifier.fillMaxWidth().padding(26.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) { Icon(icon, null, Modifier.size(34.dp), tint = MaterialTheme.colorScheme.primary); Text(title, style = MaterialTheme.typography.titleLarge); Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium) } }
}
@Composable fun TaskCard(t: Task, onToggle: () -> Unit, onEdit: () -> Unit, onDelete: (() -> Unit)?) {
    Card(onClick = onEdit, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow), shape = MaterialTheme.shapes.large) {
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(t.done, { onToggle() }); Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                Text(t.text, style = MaterialTheme.typography.titleMedium, textDecoration = if (t.done) androidx.compose.ui.text.style.TextDecoration.LineThrough else null)
                if (t.subtasks.isNotEmpty()) Text("${t.subtasks.count { it.done }}/${t.subtasks.size} шагов", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (t.dueDate.isNotEmpty()) Text("${dueLabel(t.dueDate)}${if (t.reminder) " · напоминания включены" else ""}", style = MaterialTheme.typography.labelSmall, color = if (!t.done && t.dueDate < LocalDate.now().toString()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
            }
            if (onDelete != null) IconButton(onClick = onDelete) { Icon(Icons.Rounded.DeleteOutline, "Удалить задачу", Modifier.size(20.dp)) }
        }
    }
}
@Composable fun HabitCard(h: Habit, onToggle: () -> Unit, onEdit: () -> Unit, onDelete: (() -> Unit)?, onMedals: (() -> Unit)? = null) {
    val colors = MaterialTheme.colorScheme
    val today = LocalDate.now()
    val done = today.toString() in h.completed
    val scheduled = today.dayOfWeek.value in h.days
    Card(onClick = onEdit, shape = MaterialTheme.shapes.extraLarge, colors = CardDefaults.cardColors(containerColor = colors.surfaceContainerLow, contentColor = legibleText(colors.surfaceContainerLow, colors.onSurface))) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(h.emoji, style = MaterialTheme.typography.headlineMedium)
                Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                    Text(h.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text("Серия: ${habitStreak(h)} · Всего: ${h.completed.size}", style = MaterialTheme.typography.labelMedium, color = legibleText(colors.surfaceContainerLow, colors.onSurfaceVariant))
                }
                Checkbox(done, { onToggle() }, enabled = scheduled || done)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                (6 downTo 0).forEach { back ->
                    val day = today.minusDays(back.toLong())
                    val hit = day.toString() in h.completed
                    val background = if (hit) colors.primaryContainer else colors.surfaceContainerHighest
                    val foreground = legibleText(background, if (hit) colors.onPrimaryContainer else colors.onSurfaceVariant)
                    Surface(shape = RoundedCornerShape(12.dp), color = background, contentColor = foreground, modifier = Modifier.size(34.dp)) {
                        Box(contentAlignment = Alignment.Center) { Text(if (hit) "✓" else day.dayOfMonth.toString(), style = MaterialTheme.typography.labelMedium) }
                    }
                }
            }
            Text(if (scheduled) "Сегодня по плану · ${daysLabel(h.days)}" else "Сегодня выходной · ${daysLabel(h.days)}", style = MaterialTheme.typography.labelSmall, color = legibleText(colors.surfaceContainerLow, colors.onSurfaceVariant))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                if (onMedals != null) TextButton(onClick = onMedals) { Icon(Icons.Rounded.EmojiEvents, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Мои медали") }
                Spacer(Modifier.weight(1f))
                if (onDelete != null) IconButton(onClick = onDelete) { Icon(Icons.Rounded.DeleteOutline, "Удалить привычку") }
            }
        }
    }
}
@Composable fun MedalCard(medal: Medal) {
    val colors = MaterialTheme.colorScheme
    val background = colors.primaryContainer
    val foreground = legibleText(background, colors.onPrimaryContainer)
    Card(shape = MaterialTheme.shapes.extraLarge, colors = CardDefaults.cardColors(containerColor = background, contentColor = foreground)) {
        Row(Modifier.fillMaxWidth().padding(22.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(shape = CircleShape, color = colors.surface, contentColor = legibleText(colors.surface, colors.onSurface)) { Icon(Icons.Rounded.EmojiEvents, null, Modifier.padding(18.dp).size(36.dp)) }
            Column(Modifier.weight(1f).padding(start = 18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(medalTitle(medal.target), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                Text(medal.habitTitle, style = MaterialTheme.typography.bodyMedium)
                Text("Выполнено: ${medal.target} · ${medal.earnedOn}", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
@Composable fun NoteCard(n: Note, simple: Boolean, onEdit: () -> Unit, onDelete: () -> Unit) {
    Card(onClick = onEdit, shape = if (simple) RoundedCornerShape(22.dp) else RoundedCornerShape(12.dp), colors = CardDefaults.cardColors(containerColor = if (simple) MaterialTheme.colorScheme.secondaryContainer.copy(alpha = .45f) else MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (!simple) Icon(Icons.Rounded.Description, null, tint = MaterialTheme.colorScheme.primary)
            Text(n.title.ifBlank { "Без названия" }, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, maxLines = 3, overflow = TextOverflow.Ellipsis)
            Text(n.preview().ifBlank { "Пустая заметка" }, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = if (simple) 7 else 2, overflow = TextOverflow.Ellipsis)
            val checks = n.blocks.filter { it.kind == "check" }
            Row(verticalAlignment = Alignment.CenterVertically) { Text(if (checks.isNotEmpty()) "☑ ${checks.count { it.checked }}/${checks.size}" else if (n.blocks.any { it.kind == "table" }) "▦ Таблица" else "Заметка", Modifier.weight(1f), style = MaterialTheme.typography.labelSmall); IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) { Icon(Icons.Rounded.DeleteOutline, "Удалить заметку", Modifier.size(18.dp)) } }
        }
    }
}
@Composable fun ArticleCard(a: Article, rank: Int? = null) {
    val context = androidx.compose.ui.platform.LocalContext.current
    Card(onClick = { runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(a.url))) } }, shape = MaterialTheme.shapes.large, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) { if (rank != null) { Text("0$rank", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold); Spacer(Modifier.width(12.dp)) }; Text(a.source, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary); Spacer(Modifier.weight(1f)); Icon(Icons.Rounded.OpenInNew, "Открыть оригинал", Modifier.size(16.dp)) }
            Text(a.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            if (a.summary.isNotBlank()) Text(a.summary, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 3, overflow = TextOverflow.Ellipsis)
            Text(if (a.published > 0) java.time.Instant.ofEpochMilli(a.published).atZone(java.time.ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("d MMM, HH:mm", Locale.forLanguageTag("ru"))) else "Дата не указана источником", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
@Composable fun ExactPermission(onDismiss: () -> Unit, onOpen: () -> Unit) { AlertDialog(onDismissRequest = onDismiss, title = { Text("Разреши точные будильники") }, text = { Text("Android требует отдельное разрешение. Включи «Будильники и напоминания», вернись и нажми «Сохранить».") }, confirmButton = { TextButton(onClick = onOpen) { Text("Открыть настройки") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Позже") } }) }
@Composable fun ConfirmDelete(title: String, onDismiss: () -> Unit, onDelete: () -> Unit) { AlertDialog(onDismissRequest = onDismiss, title = { Text(title) }, text = { Text("Это действие нельзя отменить.") }, confirmButton = { TextButton(onClick = onDelete) { Text("Удалить") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Оставить") } }) }
@Composable fun FeedDialog(onDismiss: () -> Unit, onAdd: (Feed) -> Unit) {
    var name by remember { mutableStateOf("") }; var url by remember { mutableStateOf("") }; var error by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Свой RSS или Atom") }, text = { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { OutlinedTextField(name, { name = it }, label = { Text("Название") }, singleLine = true); OutlinedTextField(url, { url = it; error = "" }, label = { Text("https://…") }, singleLine = true); Text("Нужен адрес новостной ленты, а не главной страницы сайта.", style = MaterialTheme.typography.bodySmall); if (error.isNotEmpty()) Text(error, color = MaterialTheme.colorScheme.error) } }, confirmButton = { TextButton(enabled = name.isNotBlank(), onClick = { if (safeWebUrl(url.trim())) onAdd(Feed(name = name.trim(), url = url.trim())) else error = "Введите корректную HTTPS-ссылку" }) { Text("Добавить") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } })
}
