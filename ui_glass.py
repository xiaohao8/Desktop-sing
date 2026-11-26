# -*- coding: utf-8 -*-
"""Liquid-glass buttons for Desktop-sing.

Qt style sheets cannot animate, so these buttons paint themselves: a frosted
translucent fill, a specular top highlight, a hairline rim and a soft shadow.
Hover and press feedback are driven by ``QPropertyAnimation`` so the surface
flows instead of snapping between states.

The widget deliberately does not call ``super().paintEvent()``: the glass
look is drawn from scratch, which keeps the rounded rim, the inner shine and
the animated states in one place. Style sheets still apply to size hints and
padding, they just no longer paint the button itself.
"""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QEvent, QPointF, QPropertyAnimation,
                            QRectF, Qt, Property)
from PySide6.QtGui import (QBrush, QColor, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QPushButton

# Variants ------------------------------------------------------------------
ACCENT = "accent"        # filled with the accent colour
GLASS = "glass"          # frosted translucent fill
GHOST = "ghost"          # transparent, hairline rim only
DANGER = "danger"        # danger tinted
SEGMENT = "segment"      # segmented control item


def qcolor(value, fallback: str = "#888888") -> QColor:
    """Parse a theme colour (``#RRGGBB`` or ``rgba(r,g,b,a)``) into a QColor."""
    if isinstance(value, QColor):
        return QColor(value)
    text = ("" if value is None else str(value)).strip()
    if text.startswith("#"):
        color = QColor(text)
        if color.isValid():
            return color
    lowered = text.lower()
    if lowered.startswith("rgba") or lowered.startswith("rgb"):
        try:
            inner = text[text.index("(") + 1:text.rindex(")")]
            parts = [p.strip() for p in inner.split(",")]
            red, green, blue = (int(float(parts[i])) for i in range(3))
            alpha = 255
            if len(parts) >= 4:
                raw = float(parts[3])
                alpha = int(round(raw * 255)) if raw <= 1.0 else int(raw)
            return QColor(red, green, blue, max(0, min(255, alpha)))
        except (ValueError, IndexError):
            pass
    color = QColor(text)
    if color.isValid():
        return color
    return QColor(fallback)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, float(t)))
    return QColor(
        int(round(a.red() + (b.red() - a.red()) * t)),
        int(round(a.green() + (b.green() - a.green()) * t)),
        int(round(a.blue() + (b.blue() - a.blue()) * t)),
        int(round(a.alpha() + (b.alpha() - a.alpha()) * t)),
    )


def _lighten(color: QColor, t: float) -> QColor:
    return _mix(color, QColor(255, 255, 255, color.alpha()), t)


def _darken(color: QColor, t: float) -> QColor:
    return _mix(color, QColor(0, 0, 0, color.alpha()), t)


class GlassButton(QPushButton):
    """A capsule/round button painted in Apple's liquid-glass style."""

    def __init__(self, text: str = "", parent=None, variant: str = GLASS):
        super().__init__(text, parent)
        self._variant = variant
        self._theme = None
        self._hover = 0.0
        self._press = 0.0
        self._key_focus = False
        self._motion_ms = 140
        self._hover_anim = QPropertyAnimation(self, b"hoverT", self)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._press_anim = QPropertyAnimation(self, b"pressT", self)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

    # -- animated state ---------------------------------------------------
    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float):
        value = float(value)
        if abs(value - self._hover) < 0.002:
            return
        self._hover = value
        self.update()

    def _get_press(self) -> float:
        return self._press

    def _set_press(self, value: float):
        value = float(value)
        if abs(value - self._press) < 0.002:
            return
        self._press = value
        self.update()

    hoverT = Property(float, _get_hover, _set_hover)
    pressT = Property(float, _get_press, _set_press)

    # -- public API --------------------------------------------------------
    @property
    def variant(self) -> str:
        return self._variant

    def set_variant(self, variant: str):
        self._variant = variant
        self.update()

    def set_theme(self, theme):
        self._theme = theme
        self.update()

    def set_motion(self, milliseconds: int):
        """Animation length in ms; ``0`` snaps between states (reduced motion)."""
        self._motion_ms = max(0, int(milliseconds or 0))
        self._hover_anim.setDuration(self._motion_ms)
        self._press_anim.setDuration(self._motion_ms)

    # -- events ------------------------------------------------------------
    def enterEvent(self, event):
        self._animate(self._hover_anim, 1.0, "hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(self._hover_anim, 0.0, "hover")
        self._animate(self._press_anim, 0.0, "press")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._animate(self._press_anim, 1.0, "press")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._animate(self._press_anim, 0.0, "press")
        super().mouseReleaseEvent(event)

    def focusInEvent(self, event):
        # 只有键盘（Tab / Backtab）进入时才画焦点环：鼠标点开的按钮带一圈
        # 主色光晕，看起来像「选中」或「报错」，会让分段控件多出一层粉色。
        self._key_focus = event.reason() in (
            Qt.TabFocusReason, Qt.BacktabFocusReason)
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._key_focus = False
        self.update()
        super().focusOutEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.update()

    def _animate(self, animation: QPropertyAnimation, end: float, attr: str):
        if self._motion_ms <= 0:
            animation.stop()
            setattr(self, "_" + attr, float(end))
            self.update()
            return
        animation.stop()
        animation.setDuration(self._motion_ms)
        animation.setStartValue(float(getattr(self, "_" + attr)))
        animation.setEndValue(float(end))
        animation.start()

    # -- painting ----------------------------------------------------------
    def _is_dark(self) -> bool:
        theme = self._theme
        if theme is None:
            return True
        return getattr(theme, "appearance", "dark") == "dark"

    def _palette(self):
        theme = self._theme
        if theme is None:
            return {
                "surface": qcolor("#1C1C1E"),
                "accent": qcolor("#F06A4A"),
                "accent_pressed": qcolor("#A9341A"),
                "on_accent": qcolor("#FFF8F0"),
                "accent_soft": QColor(201, 67, 34, 41),
                "text": qcolor("#F3F0E9"),
                "text_muted": qcolor("#A6A6AB"),
                "text_secondary": qcolor("#B0ADA5"),
                "danger": qcolor("#F06A5E"),
                "focus": qcolor("#F06A4A"),
                "rim": QColor(255, 255, 255, 44),
                "track": qcolor("#0D0D0F"),
                "border_strong": QColor(255, 255, 255, 90),
            }
        return {
            "surface": qcolor(theme.surface_raised),
            "accent": qcolor(theme.accent_fill),
            "accent_pressed": qcolor(theme.accent_pressed),
            "on_accent": qcolor(theme.on_accent),
            "accent_soft": qcolor(theme.accent_soft),
            "text": qcolor(theme.text),
            "text_muted": qcolor(theme.text_muted),
            "text_secondary": qcolor(theme.text_secondary),
            "danger": qcolor(theme.danger),
            "focus": qcolor(theme.focus),
            "track": qcolor(theme.surface_sunken),
            "border_strong": qcolor(theme.border_strong),
            "rim": QColor(255, 255, 255, 52) if self._is_dark()
                   else QColor(0, 0, 0, 44),
        }

    def _radius(self, rect: QRectF) -> float:
        return max(4.0, rect.height() / 2.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        if rect.width() <= 2.0 or rect.height() <= 2.0:
            painter.end()
            return
        palette = self._palette()
        radius = self._radius(rect)
        hover = self._hover
        press = self._press
        enabled = self.isEnabled()

        self._paint_bloom(painter, rect, hover, press, enabled)
        self._paint_fill(painter, rect, radius, hover, press, enabled, palette)
        self._paint_rim(painter, rect, radius, hover, press, enabled, palette)
        self._paint_specular(painter, rect, radius, enabled)
        self._paint_content(painter, rect, hover, press, enabled, palette)
        self._paint_focus(painter, rect, radius, palette)
        painter.end()

    def _paint_bloom(self, painter, rect, hover, press, enabled):
        """Soft light halo instead of a hard drop shadow.

        A heavy shadow is what made earlier buttons read as glossy plastic;
        liquid glass floats on a diffuse glow, not on a solid cast shadow.
        Saturated fills skip the halo entirely — a glow around a red or
        orange pane reads as a neon sign rather than glass.
        """
        if not enabled or self._variant in (ACCENT, DANGER, SEGMENT):
            return
        dark = self._is_dark()
        strength = (0.55 + 0.45 * hover) * (1.0 - 0.5 * press)
        alpha = (0.05 if dark else 0.12) * strength
        spread = rect.height() * 0.55
        center = rect.center()
        glow = QRadialGradient(center, rect.width() * 0.5 + spread)
        glow.setColorAt(0.0, QColor(255, 255, 255, int(round(255 * alpha))))
        glow.setColorAt(0.55, QColor(255, 255, 255,
                                     int(round(255 * alpha * 0.35))))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, rect.width() * 0.5 + spread,
                            rect.height() * 0.5 + spread)

    def _paint_fill(self, painter, rect, radius, hover, press, enabled,
                    palette):
        variant = self._variant
        dark = self._is_dark()
        painter.setPen(Qt.NoPen)
        if variant == ACCENT:
            base = palette["accent"]
            if press > 0.0:
                base = _mix(base, palette["accent_pressed"], press)
            # A tinted pane of colour rather than a solid slab of plastic.
            if base.alpha() == 255:
                base.setAlpha(236 if dark else 244)
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0.0, _lighten(base, 0.14 + 0.10 * hover))
            gradient.setColorAt(0.55, base)
            gradient.setColorAt(1.0, _darken(base, 0.07))
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, radius, radius)
            return
        if variant == DANGER:
            danger = palette["danger"]
            alpha = int(round(18 + 34 * hover + 56 * press))
            fill = QColor(danger.red(), danger.green(), danger.blue(), alpha)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, radius, radius)
            return
        if variant == GHOST:
            alpha = int(round(8 + 20 * hover + 24 * press))
            painter.setBrush(QColor(255, 255, 255, alpha if dark else 0))
            painter.drawRoundedRect(rect, radius, radius)
            return
        # GLASS / SEGMENT
        if variant == SEGMENT:
            # iOS 分段控件：未选是凹槽底，已选是一块「抬起」的面板。
            # 旧实现把 accent_soft 的 RGB 直接给到 70% 不透明度，选中段
            # 变成橙底橙字（浅色下几乎是同色）。这里改成层级表达：
            # 底色区分轨道与滑块，选中态靠明度 + 描边 + 落影，不靠染色。
            if self.isChecked():
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 34 if dark else 20))
                painter.drawRoundedRect(rect.adjusted(0, 1.6, 0, 1.6),
                                        radius, radius)
                base = palette["surface"] if not dark \
                    else _lighten(palette["surface"], 0.10)
                top = _lighten(base, 0.02 if dark else 0.0)
                bottom = base
            else:
                base = palette["track"]
                if hover > 0:
                    base = _lighten(base, 0.05 + 0.03 * hover)
                top = _lighten(base, 0.06 if dark else 0.02)
                bottom = base
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0.0, top)
            gradient.setColorAt(1.0, bottom)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, radius, radius)
            return
        if dark:
            # A real translucent pane: whatever sits behind shows through.
            base = QColor(255, 255, 255, int(round(30 + 20 * hover)))
        else:
            base = QColor(255, 255, 255, int(round(178 + 40 * hover)))
        if variant == SEGMENT and self.isChecked():
            tint = palette["accent_soft"]
            base = QColor(tint.red(), tint.green(), tint.blue(),
                          max(base.alpha(), tint.alpha()))
        top = _lighten(base, 0.16 if dark else 0.25)
        bottom = _darken(base, 0.10 if dark else 0.04)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(0.60, base)
        gradient.setColorAt(1.0, bottom)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, radius, radius)

    def _paint_rim(self, painter, rect, radius, hover, press, enabled,
                   palette):
        """A bright hairline that catches the light on top and fades below."""
        variant = self._variant
        dark = self._is_dark()
        if variant == SEGMENT:
            # 选中滑块靠一圈实色描边定型；未选段只留一点顶部微光。
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(palette["border_strong"] if self.isChecked()
                                else QColor(255, 255, 255, 0), 1.0))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                    radius, radius)
            return
        if variant == ACCENT:
            top = QColor(255, 255, 255, int(round(96 + 60 * hover)))
            bottom = QColor(255, 255, 255, int(round(34 + 30 * hover)))
        elif variant == DANGER:
            danger = palette["danger"]
            top = QColor(danger.red(), danger.green(), danger.blue(),
                         int(round(170 + 70 * hover)))
            bottom = QColor(danger.red(), danger.green(), danger.blue(),
                            int(round(90 + 40 * hover)))
        elif variant == GHOST:
            rim = palette["rim"]
            top = QColor(rim.red(), rim.green(), rim.blue(),
                         int(round(rim.alpha() + 90 * hover)))
            bottom = QColor(rim.red(), rim.green(), rim.blue(),
                            int(round(rim.alpha() * 0.5 + 30 * hover)))
        else:
            rim = palette["rim"]
            top = QColor(rim.red(), rim.green(), rim.blue(),
                         int(round(rim.alpha() + 110 * hover)))
            bottom = QColor(rim.red(), rim.green(), rim.blue(),
                            int(round(rim.alpha() * 0.6 + 24 * hover)))
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(0.72, bottom)
        # Light refracts through the lower edge as well, so the rim picks up a
        # second, dimmer highlight before it closes.
        gradient.setColorAt(1.0, _lighten(bottom, 0.35))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QBrush(gradient), 1.0))
        area = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(area, radius, radius)

    def _paint_specular(self, painter, rect, radius, enabled):
        """Soft overhead light and a hint of thickness at the bottom edge."""
        if not enabled:
            return
        dark = self._is_dark()
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(path)
        # Overhead light across the upper half.
        sheen = 40 if dark else 150
        gradient = QLinearGradient(
            rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height()))
        gradient.setColorAt(0.0, QColor(255, 255, 255, int(sheen * 0.62)))
        gradient.setColorAt(0.38, QColor(255, 255, 255, 0))
        painter.fillRect(rect, gradient)
        # A wide, very soft reflection in the upper-left corner.
        glow = QRadialGradient(
            QPointF(rect.left() + rect.width() * 0.26,
                    rect.top() + rect.height() * 0.02),
            max(6.0, rect.height() * 1.05))
        glow.setColorAt(0.0, QColor(255, 255, 255, int(sheen * 0.26)))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawRect(rect)
        # Thickness: the lower edge falls into shadow.
        depth = QLinearGradient(
            QPointF(rect.left(), rect.bottom() - rect.height() * 0.34),
            rect.bottomLeft())
        depth.setColorAt(0.0, QColor(0, 0, 0, 0))
        depth.setColorAt(1.0, QColor(0, 0, 0, 40 if dark else 22))
        painter.setBrush(depth)
        painter.drawRect(rect)
        # Refraction: a thin bright line just inside the upper rim, the way
        # light bends along the edge of a real glass lens.
        inner = rect.adjusted(1.4, 1.4, -1.4, -1.4)
        edge = QLinearGradient(inner.topLeft(), inner.bottomLeft())
        edge.setColorAt(0.0, QColor(255, 255, 255, min(255, int(sheen * 1.6))))
        edge.setColorAt(0.26, QColor(255, 255, 255, 0))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QBrush(edge), 1.2))
        painter.drawRoundedRect(inner, max(2.0, radius - 1.4), max(2.0, radius - 1.4))
        painter.restore()

    def _content_color(self, palette):
        variant = self._variant
        if variant == ACCENT:
            return palette["on_accent"]
        if variant == DANGER:
            return palette["danger"]
        if variant == SEGMENT:
            return palette["text"] if self.isChecked() else palette["text_muted"]
        return palette["text"]

    def _paint_content(self, painter, rect, hover, press, enabled, palette):
        color = self._content_color(palette)
        if not enabled:
            color = QColor(color.red(), color.green(), color.blue(),
                           int(color.alpha() * 0.4))
        glyph = self.property("glyph")
        if glyph:
            self._paint_glyph(painter, rect, color, str(glyph), hover)
            return
        text = self.text()
        icon = self.icon()
        has_icon = not icon.isNull()
        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(text) if text else 0
        icon_size = self.iconSize()
        icon_width = icon_size.width() if has_icon else 0
        gap = 8 if (text and has_icon) else 0
        total = text_width + gap + icon_width
        x = rect.center().x() - total / 2.0
        if has_icon:
            painter.save()
            painter.setOpacity(1.0 if enabled else 0.45)
            icon_rect = QRectF(x, rect.center().y() - icon_size.height() / 2.0,
                               icon_size.width(), icon_size.height())
            icon.paint(painter, icon_rect.toRect(), Qt.AlignCenter,
                       QIcon.Normal if enabled else QIcon.Disabled)
            painter.restore()
            x += icon_width + gap
        if text:
            painter.setPen(QPen(color))
            painter.setFont(self.font())
            text_rect = QRectF(x, rect.center().y() - metrics.height() / 2.0,
                               text_width, metrics.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    def _paint_glyph(self, painter, rect, color, glyph, hover):
        center = rect.center()
        pen = QPen(color, 1.35, Qt.SolidLine, Qt.RoundCap)
        if glyph == "close":
            painter.setPen(pen)
            painter.drawLine(center.x() - 5, center.y() - 5,
                             center.x() + 5, center.y() + 5)
            painter.drawLine(center.x() + 5, center.y() - 5,
                             center.x() - 5, center.y() + 5)
            return
        if glyph == "max":
            painter.setPen(pen)
            painter.drawRoundedRect(QRectF(center.x() - 5, center.y() - 5,
                                           10, 10), 1.5, 1.5)
            return
        painter.setPen(pen)
        painter.drawLine(center.x() - 5, center.y() + 3,
                         center.x() + 5, center.y() + 3)

    def _paint_focus(self, painter, rect, radius, palette):
        if not self.hasFocus() or not self._key_focus:
            return
        focus = palette["focus"]
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(focus, 2.0))
        area = rect.adjusted(-1.5, -1.5, 1.5, 1.5)
        painter.drawRoundedRect(area, radius + 1.5, radius + 1.5)
