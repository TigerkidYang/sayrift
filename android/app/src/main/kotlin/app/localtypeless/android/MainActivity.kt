package app.localtypeless.android

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoStories
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.ui.Aurora
import app.localtypeless.android.ui.DictionaryScreen
import app.localtypeless.android.ui.G
import app.localtypeless.android.ui.HistoryScreen
import app.localtypeless.android.ui.KeyScreen
import app.localtypeless.android.ui.Onboarding
import app.localtypeless.android.ui.SettingsScreen
import app.localtypeless.android.ui.TodayScreen
import app.localtypeless.android.ui.UsageScreen

/** Bumped whenever the activity resumes: permission and service states are re-read after a trip to Settings. */
val LocalResume = staticCompositionLocalOf { 0 }

enum class Tab(val label: String, val icon: ImageVector) {
    TODAY("今天", Icons.Outlined.WbSunny),
    HISTORY("历史", Icons.Outlined.History),
    DICTIONARY("词典", Icons.Outlined.AutoStories),
    SETTINGS("设置", Icons.Outlined.Settings),
}

/** Pages pushed over the tabs. */
enum class Page { USAGE, KEY }

class MainActivity : ComponentActivity() {
    companion object {
        /** Open at a page: "key" or "usage" (from the overlay's error, e.g. no key yet). */
        const val EXTRA_PAGE = "page"
    }

    private val resume = mutableIntStateOf(0)
    private val requested = mutableStateOf<Page?>(null)

    /** Take the page request out of the intent, so a rotation or a restore doesn't open it a second time. */
    private fun readPage(intent: android.content.Intent?) {
        requested.value = when (intent?.getStringExtra(EXTRA_PAGE)) {
            "key" -> Page.KEY
            "usage" -> Page.USAGE
            else -> null
        }
        intent?.removeExtra(EXTRA_PAGE)
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        readPage(intent)
    }
    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { resume.intValue++ }

    val app get() = application as App

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) readPage(intent)
        // Light status and navigation bar icons: the app is always dark.
        enableEdgeToEdge(SystemBarStyle.dark(android.graphics.Color.TRANSPARENT), SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        setContent {
            CompositionLocalProvider(LocalResume provides resume.intValue) {
                Box(Modifier.fillMaxSize().background(G.Base)) {
                    Aurora()
                    // Re-running the guide from Settings is a visit, not a reset: Back leaves it and "onboarded" stays.
                    var onboarded by remember { mutableStateOf(app.prefs.onboarded) }
                    var rerun by rememberSaveable { mutableStateOf(false) }
                    AnimatedContent(onboarded && !rerun, transitionSpec = { fadeIn() togetherWith fadeOut() }, label = "root") { done ->
                        if (done) Main(onRestartGuide = { app.prefs.guideStep = null; rerun = true })
                        else Onboarding(this@MainActivity, canLeave = rerun,
                            onDone = { app.prefs.onboarded = true; onboarded = true; rerun = false })
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        resume.intValue++
    }

    fun requestMicAndNotifications() {
        val wanted = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }
        permissions.launch(wanted.toTypedArray())
    }

    @Composable
    private fun Main(onRestartGuide: () -> Unit) {
        var tab by rememberSaveable { mutableStateOf(Tab.TODAY) }
        var page by rememberSaveable { mutableStateOf<Page?>(null) }
        val want = requested.value
        androidx.compose.runtime.LaunchedEffect(want) { if (want != null) { page = want; requested.value = null } }
        BackHandler(enabled = page != null || tab != Tab.TODAY) {
            if (page != null) page = null else tab = Tab.TODAY
        }
        Box(Modifier.fillMaxSize()) {
            AnimatedContent(page to tab, transitionSpec = { fadeIn() togetherWith fadeOut() }, label = "page") { (p, t) ->
                when {
                    p == Page.USAGE -> UsageScreen(this@MainActivity, onBack = { page = null })
                    p == Page.KEY -> KeyScreen(this@MainActivity, onBack = { page = null })
                    t == Tab.TODAY -> TodayScreen(this@MainActivity, onOpenHistory = { tab = Tab.HISTORY }, onOpenKey = { page = Page.KEY })
                    t == Tab.HISTORY -> HistoryScreen(this@MainActivity)
                    t == Tab.DICTIONARY -> DictionaryScreen(this@MainActivity)
                    else -> SettingsScreen(this@MainActivity, onOpenUsage = { page = Page.USAGE }, onOpenKey = { page = Page.KEY },
                        onRestartGuide = onRestartGuide)
                }
            }
            if (page == null) NavBar(tab, { tab = it }, Modifier.align(Alignment.BottomCenter))
        }
    }
}

/** The desktop's centred capsule navigation, at the bottom where a thumb reaches it. */
@Composable
private fun NavBar(selected: Tab, onSelect: (Tab) -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(28.dp)
    Row(
        modifier.navigationBarsPadding().padding(bottom = 12.dp).clip(shape).background(Color(0xF7101119))
            .border(1.dp, G.Hair, shape).padding(horizontal = 6.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Tab.entries.forEach { t ->
            val on = t == selected
            Column(
                Modifier.clip(RoundedCornerShape(22.dp)).background(if (on) Color(0x1FFFFFFF) else Color.Transparent)
                    .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onSelect(t) }
                    .padding(horizontal = 18.dp, vertical = 7.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(t.icon, t.label, tint = if (on) G.Ink else G.Faint, modifier = Modifier.size(21.dp))
                Spacer(Modifier.height(2.dp))
                Text(t.label, color = if (on) G.Ink else G.Faint, fontSize = 11.sp, fontWeight = if (on) FontWeight.Medium else FontWeight.Normal)
            }
        }
    }
}

/** Space the floating navigation covers at the bottom of every tab. */
val NavBarSpace = 96.dp
