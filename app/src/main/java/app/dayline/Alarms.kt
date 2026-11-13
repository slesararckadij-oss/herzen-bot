package app.dayline

import android.Manifest
import android.app.*
import android.app.job.*
import android.content.*
import android.content.pm.PackageManager
import android.media.*
import android.net.Uri
import android.os.*
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.WbSunny
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import java.time.LocalTime
import java.time.format.DateTimeFormatter

object Alarms {
    const val DIGEST = 900001
    fun manager(c: Context): AlarmManager = c.getSystemService(AlarmManager::class.java)
    fun canSchedule(c: Context) = Build.VERSION.SDK_INT < 31 || manager(c).canScheduleExactAlarms()
    private fun pending(c: Context, id: Int): PendingIntent = PendingIntent.getBroadcast(c, id, Intent(c, AlarmReceiver::class.java).putExtra("id", id), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    fun cancel(c: Context, id: Int) = manager(c).cancel(pending(c, id))
    fun schedule(c: Context, a: WakeAlarm, delayMinutes: Int? = null) {
        cancel(c, a.id)
        if (!a.enabled || !canSchedule(c)) return
        val time = delayMinutes?.let { System.currentTimeMillis() + it * 60000L } ?: nextAlarmTime(a.hour, a.minute, a.days).toInstant().toEpochMilli()
        val show = PendingIntent.getActivity(c, a.id, Intent(c, MainActivity::class.java).putExtra("tab", 3), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        try { manager(c).setAlarmClock(AlarmManager.AlarmClockInfo(time, show), pending(c, a.id)) } catch (_: SecurityException) { /* Permission may be revoked while settings are open. */ }
    }
    fun digest(c: Context, s: DayState) {
        cancel(c, DIGEST)
        if (s.digestEnabled) manager(c).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, nextOccurrence(s.digestHour, s.digestMinute).toInstant().toEpochMilli(), pending(c, DIGEST))
    }
    private fun taskPending(c: Context, task: Task, offset: Int): PendingIntent = PendingIntent.getBroadcast(c, 0,
        Intent(c, AlarmReceiver::class.java).setAction("app.dayline.TASK").setData(Uri.parse("dayline://task/${task.id}/$offset")).putExtra("task", task.id).putExtra("offset", offset), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    fun task(c: Context, task: Task) {
        listOf(2, 1, 0).forEach { manager(c).cancel(taskPending(c, task, it)) }
        reminderInstants(task).forEach { (offset, instant) -> manager(c).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, instant, taskPending(c, task, offset)) }
    }
    fun removeTask(c: Context, t: Task) { listOf(2, 1, 0).forEach { manager(c).cancel(taskPending(c, t, it)) }; c.getSystemService(NotificationManager::class.java).cancel(t.id, 44) }
    fun restore(c: Context) { val s = Store(c).read(); s.alarms.forEach { schedule(c, it) }; s.tasks.forEach { task(c, it) }; digest(c, s); MorningWidget.refresh(c, s) }
    fun channels(c: Context) {
        c.getSystemService(NotificationManager::class.java).apply {
            createNotificationChannel(NotificationChannel("wake", "Будильники", NotificationManager.IMPORTANCE_HIGH).apply { setSound(null, null); lockscreenVisibility = Notification.VISIBILITY_PUBLIC })
            createNotificationChannel(NotificationChannel("digest", "Утренний дайджест", NotificationManager.IMPORTANCE_DEFAULT))
            createNotificationChannel(NotificationChannel("tasks", "Сроки задач", NotificationManager.IMPORTANCE_HIGH))
        }
    }
    fun allowedNotifications(c: Context) = Build.VERSION.SDK_INT < 33 || c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
}
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, intent: Intent) {
        Alarms.channels(c)
        if (intent.action == "app.dayline.TASK") {
            val t = Store(c).read().tasks.firstOrNull { it.id == intent.getStringExtra("task") && !it.done && it.reminder } ?: return
            if (!Alarms.allowedNotifications(c)) return
            val offset = intent.getIntExtra("offset", 0)
            val open = PendingIntent.getActivity(c, t.id.hashCode(), Intent(c, MainActivity::class.java).putExtra("tab", 1), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val text = when (offset) { 2 -> "До срока осталось 2 дня"; 1 -> "Срок завтра — самое время закончить"; else -> "Срок сегодня" }
            c.getSystemService(NotificationManager::class.java).notify(t.id, 44, NotificationCompat.Builder(c, "tasks").setSmallIcon(android.R.drawable.ic_menu_agenda).setContentTitle(t.text).setContentText("$text · ${t.dueDate}").setContentIntent(open).setAutoCancel(true).build())
            return
        }
        val id = intent.getIntExtra("id", -1)
        if (id == Alarms.DIGEST) {
            Alarms.digest(c, Store(c).read())
            requestDigest(c)
        } else {
            val alarm = Store(c).read().alarms.firstOrNull { it.id == id && it.enabled } ?: return
            Alarms.schedule(c, alarm)
            c.startForegroundService(Intent(c, AlarmService::class.java).putExtra("id", id))
        }
    }
}
fun requestDigest(c: Context) {
    c.getSystemService(JobScheduler::class.java).schedule(JobInfo.Builder(700, ComponentName(c, DigestJob::class.java)).setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setOverrideDeadline(60000).build())
}
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, i: Intent) { if (i.action in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_TIME_CHANGED, Intent.ACTION_TIMEZONE_CHANGED, Intent.ACTION_MY_PACKAGE_REPLACED)) Alarms.restore(c) }
}
class AlarmService : Service() {
    private var player: MediaPlayer? = null
    private var wake: PowerManager.WakeLock? = null
    private var vibrator: Vibrator? = null
    private var audioFocus: AudioFocusRequest? = null
    private val handler = Handler(Looper.getMainLooper())
    override fun onBind(intent: Intent?) = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "STOP") { stopSelf(); return START_NOT_STICKY }
        Alarms.channels(this)
        val id = intent?.getIntExtra("id", -1) ?: -1
        val alarm = Store(this).read().alarms.firstOrNull { it.id == id }
        val screen = PendingIntent.getActivity(this, 0, Intent(this, RingActivity::class.java).putExtra("id", id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val dismiss = PendingIntent.getService(this, 1, Intent(this, AlarmService::class.java).setAction("STOP"), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        startForeground(42, NotificationCompat.Builder(this, "wake").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle(alarm?.label ?: "Доброе утро").setContentText("Пора начинать свой день").setCategory(NotificationCompat.CATEGORY_ALARM).setPriority(NotificationCompat.PRIORITY_MAX).setOngoing(true).setContentIntent(screen).setFullScreenIntent(screen, true).addAction(0, "Выключить", dismiss).build())
        player?.release()
        val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
        audioFocus?.let { getSystemService(AudioManager::class.java).abandonAudioFocusRequest(it) }
        audioFocus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT).setAudioAttributes(attributes).setOnAudioFocusChangeListener { }.build().also { getSystemService(AudioManager::class.java).requestAudioFocus(it) }
        fun play(uri: Uri): MediaPlayer = MediaPlayer().apply {
            try { setAudioAttributes(attributes); setDataSource(this@AlarmService, uri); isLooping = true; prepare(); start() } catch (e: Exception) { release(); throw e }
        }
        val fallback = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM) ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        player = runCatching { play(alarm?.sound?.takeIf { it.isNotBlank() }?.let(Uri::parse) ?: fallback) }.getOrElse { runCatching { play(fallback) }.getOrNull() }
        vibrator?.cancel()
        if (alarm?.vibrate != false) {
            @Suppress("DEPRECATION")
            val v = if (Build.VERSION.SDK_INT >= 31) getSystemService(VibratorManager::class.java).defaultVibrator else getSystemService(Vibrator::class.java)
            vibrator = v; v.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 700, 500), 0))
        }
        wake?.let { if (it.isHeld) it.release() }
        wake = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dayline:alarm").apply { acquire(10 * 60 * 1000L) }
        handler.removeCallbacksAndMessages(null); handler.postDelayed({ stopSelf() }, 10 * 60 * 1000L)
        return START_NOT_STICKY
    }
    override fun onDestroy() { handler.removeCallbacksAndMessages(null); player?.release(); vibrator?.cancel(); audioFocus?.let { getSystemService(AudioManager::class.java).abandonAudioFocusRequest(it) }; wake?.let { if (it.isHeld) it.release() }; super.onDestroy() }
}
class RingActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(true); setTurnScreenOn(true) }
        else { @Suppress("DEPRECATION") window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON) }
        val s = Store(this).read(); val a = s.alarms.firstOrNull { it.id == intent.getIntExtra("id", -1) }
        setContent { DaylineTheme(s.theme) {
            Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                Column(Modifier.fillMaxSize().padding(32.dp).navigationBarsPadding().statusBarsPadding(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primaryContainer) { Icon(Icons.Rounded.WbSunny, null, Modifier.padding(28.dp).size(56.dp), tint = MaterialTheme.colorScheme.onPrimaryContainer) }
                    Spacer(Modifier.height(32.dp)); Text(LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm")), style = MaterialTheme.typography.displayLarge, fontWeight = FontWeight.Light)
                    Text(a?.label ?: "Доброе утро", style = MaterialTheme.typography.headlineSmall)
                    Spacer(Modifier.height(48.dp))
                    Button(modifier = Modifier.fillMaxWidth().height(58.dp), onClick = {
                        stopService(Intent(this@RingActivity, AlarmService::class.java))
                        if (a?.morning != false) { requestDigest(this@RingActivity); startActivity(Intent(this@RingActivity, MainActivity::class.java).putExtra("tab", 0).putExtra("morning", true).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)) }
                        finish()
                    }) { Text(if (a?.morning != false) "Начать день · мой обзор" else "Выключить будильник") }
                    Spacer(Modifier.height(12.dp))
                    OutlinedButton(modifier = Modifier.fillMaxWidth().height(56.dp), onClick = { a?.let { Alarms.schedule(this@RingActivity, it, 5) }; stopService(Intent(this@RingActivity, AlarmService::class.java)); finish() }) { Text("Ещё 5 минут") }
                }
            }
        } }
    }
}
class DigestJob : JobService() {
    private var job: Job? = null
    override fun onStartJob(params: JobParameters): Boolean {
        job = CoroutineScope(Dispatchers.Main).launch {
            try {
                val s = Store(this@DigestJob).read()
                val (articles, errors) = News.load(s.feeds)
                val updated = Store(this@DigestJob).update { old -> old.copy(news = if (articles.isEmpty()) old.news else articles, newsUpdated = if (articles.isEmpty()) old.newsUpdated else System.currentTimeMillis()) }
                val top = topStories(articles)
                if (updated.digestEnabled && Alarms.allowedNotifications(this@DigestJob)) {
                    Alarms.channels(this@DigestJob)
                    val open = PendingIntent.getActivity(this@DigestJob, 8, Intent(this@DigestJob, MainActivity::class.java).putExtra("tab", 0), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                    val text = if (top.isEmpty()) "Свежих новостей за последние 12 часов пока нет. Откройте обзор, чтобы проверить источники." else top.joinToString("\n\n") { "• ${it.title}" }
                    getSystemService(NotificationManager::class.java).notify(43, NotificationCompat.Builder(this@DigestJob, "digest").setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("Три главных к утру").setContentText(top.firstOrNull()?.title ?: errors.firstOrNull() ?: "Открыть мой день").setStyle(NotificationCompat.BigTextStyle().bigText(text)).setContentIntent(open).setAutoCancel(true).build())
                }
            } finally { jobFinished(params, false) }
        }
        return true
    }
    override fun onStopJob(params: JobParameters): Boolean { job?.cancel(); return true }
}
