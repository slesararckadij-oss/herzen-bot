package app.dayline

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.*
import android.content.res.Configuration
import android.os.Build
import android.widget.RemoteViews
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.ui.graphics.toArgb
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

class MorningWidget : AppWidgetProvider() {
    override fun onUpdate(c: Context, manager: AppWidgetManager, ids: IntArray) { refresh(c, Store(c).read()) }
    companion object {
        fun refresh(c: Context, s: DayState) {
            val manager = AppWidgetManager.getInstance(c)
            val ids = manager.getAppWidgetIds(ComponentName(c, MorningWidget::class.java))
            if (ids.isEmpty()) return
            val top = topStories(s.news)
            val today = LocalDate.now()
            for (id in ids) {
                val views = RemoteViews(c.packageName, R.layout.morning_widget)
                views.setTextViewText(R.id.widget_date, today.format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale.forLanguageTag("ru"))))
                views.setTextViewText(R.id.widget_tasks, "${s.tasks.count { !it.done }} задач · ${s.habits.count { today.toString() in it.completed }}/${s.habits.count { today.dayOfWeek.value in it.days }} привычек")
                views.setTextViewText(R.id.widget_news, top.firstOrNull()?.title ?: "Новости появятся после обновления дайджеста")
                val alarm = s.alarms.filter { it.enabled }.minByOrNull { nextAlarmTime(it.hour, it.minute, it.days).toInstant() }
                views.setTextViewText(R.id.widget_alarm, alarm?.let { "Будильник %02d:%02d".format(it.hour, it.minute) } ?: "Будильники выключены")
                if (Build.VERSION.SDK_INT >= 31) {
                    val dark = c.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
                    val colors = if (dark) dynamicDarkColorScheme(c) else dynamicLightColorScheme(c)
                    views.setInt(R.id.widget_root, "setBackgroundColor", colors.surfaceContainer.toArgb())
                    views.setTextColor(R.id.widget_brand, colors.primary.toArgb())
                    listOf(R.id.widget_date, R.id.widget_tasks, R.id.widget_news, R.id.widget_alarm).forEach { views.setTextColor(it, colors.onSurface.toArgb()) }
                }
                val open = PendingIntent.getActivity(c, id, Intent(c, MainActivity::class.java).putExtra("tab", 0), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                val task = PendingIntent.getActivity(c, id + 10000, Intent(c, MainActivity::class.java).putExtra("tab", 1).putExtra("addTask", true), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                views.setOnClickPendingIntent(R.id.widget_root, open); views.setOnClickPendingIntent(R.id.widget_add, task)
                manager.updateAppWidget(id, views)
            }
        }
    }
}
