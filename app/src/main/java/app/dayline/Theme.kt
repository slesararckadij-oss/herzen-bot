package app.dayline

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.LocalContext

@Composable fun DaylineTheme(preference: String = "system", content: @Composable () -> Unit) {
    val dark = when (preference) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val context = LocalContext.current
    val colors = if (Build.VERSION.SDK_INT >= 31) {
        if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
    } else if (dark) darkColorScheme(primary = Color(0xFFFFB77E), secondary = Color(0xFFE4BFA5), tertiary = Color(0xFFB7CD9E))
    else lightColorScheme(primary = Color(0xFF8B500C), secondary = Color(0xFF745943), tertiary = Color(0xFF52663F))
    MaterialTheme(colorScheme = colors) { ThemedSystemBars(); content() }
}

@Composable fun ThemedSystemBars() {
    val view = androidx.compose.ui.platform.LocalView.current
    val colors = MaterialTheme.colorScheme
    if (!view.isInEditMode) androidx.compose.runtime.SideEffect {
        val activity = view.context as? android.app.Activity
        activity?.window?.let { window ->
            @Suppress("DEPRECATION")
            window.statusBarColor = colors.background.toArgb()
            @Suppress("DEPRECATION")
            window.navigationBarColor = colors.surfaceContainer.toArgb()
            val dark = colors.background.luminance() < 0.5f
            androidx.core.view.WindowCompat.getInsetsController(window, view).apply { isAppearanceLightStatusBars = !dark; isAppearanceLightNavigationBars = !dark }
        }
    }
}
