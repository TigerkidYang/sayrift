package app.localtypeless.android.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.ripple
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** The desktop's Glass palette (ui/theme.py, dark): one violet-to-cyan accent on a night base. */
object G {
    val Base = Color(0xFF07080D)
    val Glass = Color(0x14FFFFFF)
    val GlassHi = Color(0x1FFFFFFF)
    val Hair = Color(0x1FFFFFFF)
    val Ink = Color(0xFFF3F4F8)
    val Muted = Color(0xFFA4A7B8)
    val Faint = Color(0xFF6D7082)
    val Violet = Color(0xFF9B82FF)
    val Cyan = Color(0xFF2FD3E0)
    val Good = Color(0xFF4EE3B0)
    val Warn = Color(0xFFFFC266)
    val Bad = Color(0xFFFF7A8A)
    val Accent = Brush.linearGradient(listOf(Violet, Cyan))
}

/** The aurora, still: an animated full-screen gradient costs battery for nothing (and crashed the emulator). */
@Composable
fun Aurora(modifier: Modifier = Modifier) {
    Canvas(modifier.fillMaxSize()) {
        val blobs = listOf(
            Triple(Offset(0.18f, 0.08f), 0.72f, Color(0xFF4A35C9)),
            Triple(Offset(0.95f, 0.62f), 0.8f, Color(0xFF0E7F8F)),
            Triple(Offset(0.62f, -0.04f), 0.5f, Color(0xFF8A2F7A)),
        )
        blobs.forEach { (c, r, color) ->
            val center = Offset(c.x * size.width, c.y * size.height)
            val radius = r * maxOf(size.width, size.height)
            drawCircle(Brush.radialGradient(listOf(color.copy(alpha = 0.42f), color.copy(alpha = 0.14f), Color.Transparent), center, radius), radius, center)
        }
    }
}

@Composable
fun Orb(size: Dp, modifier: Modifier = Modifier) {
    val s = size.value
    Box(
        modifier.size(size).clip(CircleShape).background(
            Brush.radialGradient(
                0f to Color.White, 0.14f to Color(0xFFD9CEFF), 0.44f to G.Violet, 0.8f to G.Cyan, 1f to Color(0xFF0B3B52),
                center = Offset(s * 0.36f * density(), s * 0.3f * density()), radius = s * 0.78f * density(),
            )
        )
    )
}

@Composable
private fun density() = androidx.compose.ui.platform.LocalDensity.current.density

/** A frosted panel. */
@Composable
fun Card(
    modifier: Modifier = Modifier,
    padding: PaddingValues = PaddingValues(18.dp),
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(22.dp)
    Column(
        modifier.fillMaxWidth().clip(shape).background(G.Glass).border(1.dp, G.Hair, shape)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(padding),
        content = content,
    )
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(text, color = G.Faint, fontSize = 12.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.6.sp,
        modifier = modifier.padding(start = 6.dp, top = 6.dp, bottom = 8.dp))
}

@Composable
fun Title(text: String, modifier: Modifier = Modifier) {
    Text(text, color = G.Ink, fontSize = 28.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.4).sp, modifier = modifier)
}

@Composable
fun Body(text: String, modifier: Modifier = Modifier, color: Color = G.Muted, size: Int = 14) {
    Text(text, color = color, fontSize = size.sp, lineHeight = (size * 1.5).sp, modifier = modifier)
}

enum class ButtonStyle { Primary, Secondary, Quiet }

@Composable
fun Button(
    label: String,
    modifier: Modifier = Modifier,
    style: ButtonStyle = ButtonStyle.Secondary,
    icon: ImageVector? = null,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(16.dp)
    val bg: Brush = when (style) {
        ButtonStyle.Primary -> if (enabled) SolidColor(Color(0xFFEEF0F6)) else SolidColor(Color(0x33FFFFFF))
        ButtonStyle.Secondary -> SolidColor(Color(0x1AFFFFFF))
        ButtonStyle.Quiet -> SolidColor(Color.Transparent)
    }
    val fg = when {
        style == ButtonStyle.Primary && enabled -> Color(0xFF0B0C12)
        !enabled -> G.Faint
        style == ButtonStyle.Quiet -> G.Muted
        else -> G.Ink
    }
    Row(
        modifier.heightIn(min = 46.dp).clip(shape).background(bg)
            .let { if (style == ButtonStyle.Secondary) it.border(1.dp, G.Hair, shape) else it }
            .clickable(enabled = enabled, onClick = onClick).padding(horizontal = 18.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (icon != null) {
            Icon(icon, null, tint = fg, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(label, color = fg, fontSize = 15.sp, fontWeight = FontWeight.Medium, maxLines = 1)
    }
}

@Composable
fun Toggle(on: Boolean, onChange: (Boolean) -> Unit) {
    val offset by animateDpAsState(if (on) 20.dp else 0.dp, label = "toggle")
    val track by animateColorAsState(if (on) G.Violet else Color(0x24FFFFFF), label = "track")
    Box(
        Modifier.size(width = 46.dp, height = 26.dp).clip(RoundedCornerShape(13.dp))
            .background(if (on) G.Accent else SolidColor(track))
            .clickable { onChange(!on) }.padding(3.dp),
    ) { Box(Modifier.padding(start = offset).size(20.dp).clip(CircleShape).background(Color.White)) }
}

/** Two to four options side by side. */
@Composable
fun <T> Segmented(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier.clip(RoundedCornerShape(14.dp)).background(Color(0x14FFFFFF)).padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        options.forEach { (value, label) ->
            val on = value == selected
            Box(
                Modifier.clip(RoundedCornerShape(11.dp)).background(if (on) Color(0x2EFFFFFF) else Color.Transparent)
                    .clickable { onSelect(value) }.padding(horizontal = 14.dp, vertical = 7.dp),
                contentAlignment = Alignment.Center,
            ) { Text(label, color = if (on) G.Ink else G.Muted, fontSize = 13.sp, fontWeight = FontWeight.Medium) }
        }
    }
}

@Composable
fun Chip(label: String, selected: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(12.dp)
    Box(
        Modifier.clip(shape).background(if (selected) Color(0x2EFFFFFF) else Color(0x0FFFFFFF))
            .border(1.dp, if (selected) Color(0x40FFFFFF) else G.Hair, shape)
            .clickable(onClick = onClick).heightIn(min = 34.dp).padding(horizontal = 14.dp),
        contentAlignment = Alignment.Center,
    ) { Text(label, color = if (selected) G.Ink else G.Muted, fontSize = 13.sp, fontWeight = FontWeight.Medium) }
}

@Composable
fun Field(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    secret: Boolean = false,
    minLines: Int = 1,
    singleLine: Boolean = false,
    leading: ImageVector? = null,
    keyboard: KeyboardOptions = KeyboardOptions.Default,
    actions: KeyboardActions = KeyboardActions.Default,
    trailing: @Composable (RowScope.() -> Unit)? = null,
) {
    val shape = RoundedCornerShape(16.dp)
    Row(
        modifier.fillMaxWidth().clip(shape).background(Color(0x12FFFFFF)).border(1.dp, G.Hair, shape)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = if (minLines > 1) Alignment.Top else Alignment.CenterVertically,
    ) {
        if (leading != null) {
            Icon(leading, null, tint = G.Faint, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(10.dp))
        }
        Box(Modifier.weight(1f)) {
            if (value.isEmpty()) Text(placeholder, color = G.Faint, fontSize = 15.sp, lineHeight = 22.sp)
            BasicTextField(
                value = value,
                onValueChange = onChange,
                textStyle = TextStyle(color = G.Ink, fontSize = 15.sp, lineHeight = 22.sp),
                cursorBrush = SolidColor(G.Violet),
                minLines = minLines,
                singleLine = singleLine,
                keyboardOptions = keyboard,
                keyboardActions = actions,
                visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        trailing?.invoke(this)
    }
}

/** A settings row: icon, title and subtitle, and something on the right. */
@Composable
fun SettingRow(
    title: String,
    subtitle: String? = null,
    icon: ImageVector? = null,
    iconTint: Color = G.Muted,
    onClick: (() -> Unit)? = null,
    trailing: @Composable (() -> Unit)? = null,
) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            Box(Modifier.size(34.dp).clip(RoundedCornerShape(11.dp)).background(Color(0x14FFFFFF)), contentAlignment = Alignment.Center) {
                Icon(icon, null, tint = iconTint, modifier = Modifier.size(18.dp))
            }
            Spacer(Modifier.width(14.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(title, color = G.Ink, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (subtitle != null) Text(subtitle, color = G.Faint, fontSize = 12.5.sp, lineHeight = 17.sp)
        }
        if (trailing != null) {
            Spacer(Modifier.width(10.dp))
            trailing()
        }
    }
}

/** Rows inside one card, with hairlines between them. */
@Composable
fun Group(content: @Composable ColumnScope.() -> Unit) {
    Card(padding = PaddingValues(vertical = 4.dp), content = content)
}

@Composable
fun Divider(inset: Dp = 64.dp) {
    Box(Modifier.fillMaxWidth().padding(start = inset).height(1.dp).background(Color(0x0FFFFFFF)))
}

@Composable
fun StatusDot(color: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(8.dp).clip(CircleShape).background(color))
}

@Composable
fun Tag(text: String, color: Color = G.Muted) {
    Box(Modifier.clip(RoundedCornerShape(7.dp)).background(color.copy(alpha = 0.14f)).padding(horizontal = 7.dp, vertical = 2.dp)) {
        Text(text, color = color, fontSize = 11.sp, fontWeight = FontWeight.Medium)
    }
}

/** A small text action, e.g. "全部" next to a section label. */
@Composable
fun LinkText(text: String, onClick: () -> Unit) {
    Text(text, color = G.Violet, fontSize = 13.sp, fontWeight = FontWeight.Medium,
        modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable(onClick = onClick).padding(horizontal = 8.dp, vertical = 6.dp))
}

@Composable
fun IconButton(icon: ImageVector, description: String, tint: Color = G.Muted, onClick: () -> Unit) {
    Box(
        Modifier.size(40.dp).clip(CircleShape)
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = ripple(bounded = false), onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, description, tint = tint, modifier = Modifier.size(21.dp)) }
}
