from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    font_family: str
    font_size: str
    text: str
    muted_text: str
    panel: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    primary: str
    primary_hover: str
    primary_soft: str
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    danger: str
    danger_bg: str
    drop_bg: str
    surface_card: str = "#ffffff"
    surface_card_hover: str = "#f9fafb"
    surface_sunken: str = "#f3f4f6"
    shadow_rgba: str = "15, 23, 42, 0.08"
    layer_safe_fg: str = "#047857"
    layer_safe_bg: str = "#ecfdf5"
    layer_safe_border: str = "#a7f3d0"
    layer_process_fg: str = "#0369a1"
    layer_process_bg: str = "#f0f9ff"
    layer_process_border: str = "#bae6fd"
    layer_review_fg: str = "#b45309"
    layer_review_bg: str = "#fffbeb"
    layer_review_border: str = "#fde68a"
    layer_registry_fg: str = "#be123c"
    layer_registry_bg: str = "#fff1f2"
    layer_registry_border: str = "#fecdd3"
    layer_blocked_fg: str = "#475569"
    layer_blocked_bg: str = "#f8fafc"
    layer_blocked_border: str = "#cbd5e1"
    radius_sm: str = "6px"
    radius_md: str = "10px"
    radius_lg: str = "14px"
    radius_pill: str = "999px"


DEFAULT_LIGHT = Theme(
    name="graphite-light",
    font_family='"Segoe UI Variable Text", "Microsoft JhengHei UI", "Segoe UI", sans-serif',
    font_size="13px",
    text="#0c1320",
    muted_text="#6b7280",
    panel="#f5f6f8",
    surface="#ffffff",
    surface_alt="#f0f2f5",
    border="#cbd0d6",
    border_strong="#9aa0a8",
    primary="#4f46e5",
    primary_hover="#4338ca",
    primary_soft="#e0e7ff",
    success="#15803d",
    success_bg="#bbf7d0",
    warning="#b45309",
    warning_bg="#fde68a",
    danger="#b91c1c",
    danger_bg="#fecaca",
    drop_bg="#eef2ff",
)

ENGINEERING_BLUE_LIGHT = Theme(
    name="engineering-blue-2",
    font_family='"Segoe UI Variable Text", "Microsoft JhengHei UI", "Segoe UI", sans-serif',
    font_size="13px",
    text="#0c1320",
    muted_text="#64748b",
    panel="#eef2f6",
    surface="#ffffff",
    surface_alt="#f1f5f9",
    border="#cbd5e1",
    border_strong="#94a3b8",
    primary="#2563eb",
    primary_hover="#1d4ed8",
    primary_soft="#dbeafe",
    success="#15803d",
    success_bg="#bbf7d0",
    warning="#b45309",
    warning_bg="#fde68a",
    danger="#b91c1c",
    danger_bg="#fecaca",
    drop_bg="#dbeafe",
    surface_card="#ffffff",
    surface_card_hover="#f8fafc",
    surface_sunken="#e2e8f0",
    shadow_rgba="15, 23, 42, 0.08",
    layer_process_fg="#1d4ed8",
    layer_process_bg="#eff6ff",
    layer_process_border="#bfdbfe",
)

GRAPHITE_DARK = Theme(
    name="graphite-dark",
    font_family='"Segoe UI Variable Text", "Microsoft JhengHei UI", "Segoe UI", sans-serif',
    font_size="13px",
    text="#e2e8f0",
    muted_text="#94a3b8",
    panel="#0f172a",
    surface="#1e293b",
    surface_alt="#273449",
    border="#334155",
    border_strong="#64748b",
    primary="#818cf8",
    primary_hover="#6366f1",
    primary_soft="rgba(129, 140, 248, 0.18)",
    success="#34d399",
    success_bg="rgba(16, 185, 129, 0.16)",
    warning="#fbbf24",
    warning_bg="rgba(251, 191, 36, 0.16)",
    danger="#fb7185",
    danger_bg="rgba(244, 63, 94, 0.16)",
    drop_bg="rgba(129, 140, 248, 0.18)",
    surface_card="#1e293b",
    surface_card_hover="#273449",
    surface_sunken="#0b1220",
    shadow_rgba="0, 0, 0, 0.30",
    layer_safe_fg="#34d399",
    layer_safe_bg="rgba(16,185,129,0.12)",
    layer_safe_border="rgba(52,211,153,0.45)",
    layer_process_fg="#38bdf8",
    layer_process_bg="rgba(14,165,233,0.12)",
    layer_process_border="rgba(56,189,248,0.45)",
    layer_review_fg="#fbbf24",
    layer_review_bg="rgba(245,158,11,0.12)",
    layer_review_border="rgba(251,191,36,0.45)",
    layer_registry_fg="#fb7185",
    layer_registry_bg="rgba(244,63,94,0.12)",
    layer_registry_border="rgba(251,113,133,0.45)",
    layer_blocked_fg="#cbd5e1",
    layer_blocked_bg="rgba(148,163,184,0.12)",
    layer_blocked_border="rgba(203,213,225,0.45)",
)

THEME_OPTIONS = (
    ("graphite-light", "Graphite（推薦）"),
    ("graphite-dark", "Graphite Dark"),
    ("engineering-blue-2", "Engineering Blue 2.0"),
)
_THEMES = {
    DEFAULT_LIGHT.name: DEFAULT_LIGHT,
    GRAPHITE_DARK.name: GRAPHITE_DARK,
    ENGINEERING_BLUE_LIGHT.name: ENGINEERING_BLUE_LIGHT,
}


def theme_by_name(name: str | None) -> Theme:
    return _THEMES.get(str(name or ""), DEFAULT_LIGHT)


def dock_stylesheet(theme: Theme = DEFAULT_LIGHT) -> str:
    return f"""
    DockWindow {{
        background: {theme.panel};
        color: {theme.text};
        border: 1px solid #e3e6ea;
        font-family: {theme.font_family};
        font-size: {theme.font_size};
    }}
    DockWindow[dropTarget="true"] {{
        background: {theme.drop_bg};
        border: 2px solid {theme.primary};
    }}
    QLabel {{
        color: {theme.text};
        padding-left: 4px;
        padding-right: 4px;
    }}
    QLabel#DockTitle {{
        font-weight: 700;
    }}
    QLabel#ContextLabel {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-left: 5px solid {theme.border_strong};
        border-radius: 6px;
        padding: 5px 10px;
        font-weight: 600;
    }}
    QLabel#ContextLabel[sourceKind="explorer"] {{
        background: {theme.success_bg};
        border-left-color: {theme.success};
    }}
    QLabel#ContextLabel[sourceKind="manual"] {{
        background: {theme.warning_bg};
        border-left-color: {theme.warning};
    }}
    QLabel#ContextLabel[sourceKind="recent"] {{
        background: {theme.surface_alt};
        border-left-color: {theme.border_strong};
    }}
    QLabel#ContextLabel[sourceKind="drop"] {{
        background: {theme.primary_soft};
        border-left-color: {theme.primary};
    }}
    QLabel#ContextLabel[sourceKind="empty"] {{
        background: {theme.danger_bg};
        border-left-color: {theme.danger};
    }}
    QLabel#DropHint {{
        background: {theme.primary_soft};
        color: {theme.primary};
        border: 1px dashed {theme.primary};
        border-radius: 8px;
        padding: 7px 14px;
        font-weight: 700;
    }}
    QToolButton {{
        background: transparent;
        color: {theme.text};
        border: 1px solid transparent;
        border-radius: 6px;
        padding-left: 8px;
        padding-right: 8px;
    }}
    QToolButton:hover {{
        background: {theme.surface_alt};
        border-color: {theme.border};
    }}
    QToolButton[role="primary"] {{
        background: {theme.primary};
        border-color: {theme.primary};
        color: #ffffff;
        font-weight: 700;
    }}
    QToolButton[role="primary"]:hover {{
        background: {theme.primary_hover};
        border-color: {theme.primary_hover};
    }}
    QToolButton[role="iso"] {{
        background: #dcfce7;
        border-color: #86efac;
        color: #14532d;
        font-weight: 800;
    }}
    QToolButton[role="iso"]:hover {{
        background: #bbf7d0;
        border-color: #22c55e;
        color: #052e16;
    }}
    QToolButton#DockTail {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-top: 2px solid {theme.primary};
        border-radius: 5px;
        font-weight: 700;
        padding: 0 8px;
    }}
    QToolButton#DockTail[tailOrientation="vertical"] {{
        padding: 0;
        border-top: 1px solid {theme.border};
        border-left: 2px solid {theme.primary};
        border-radius: 4px;
    }}
    QToolButton#DockTail[tailOrientation="horizontal"] {{
        padding: 0 8px;
        border-top: 2px solid {theme.primary};
    }}
    QToolButton#DockTail[sourceKind="explorer"] {{
        border-top-color: {theme.success};
        border-left-color: {theme.success};
    }}
    QToolButton#DockTail[sourceKind="drop"] {{
        border-top-color: {theme.primary};
        border-left-color: {theme.primary};
    }}
    QToolButton#DockTail[sourceKind="manual"] {{
        border-top-color: {theme.warning};
        border-left-color: {theme.warning};
    }}
    QToolButton#DockTail[sourceKind="recent"] {{
        border-top-color: {theme.border_strong};
        border-left-color: {theme.border_strong};
    }}
    QToolButton#DockTail[sourceKind="empty"] {{
        border-top-color: {theme.danger};
        border-left-color: {theme.danger};
    }}
    QToolButton#DockTail[activeJobs="true"] {{
        background: {theme.warning_bg};
        border-top-color: {theme.warning};
        border-left-color: {theme.warning};
    }}
    QToolButton#DockTail[movingTail="true"] {{
        background: {theme.primary_soft};
        border-color: {theme.primary};
        color: {theme.primary};
    }}
    QToolButton#DockTail:hover {{
        background: {theme.primary_soft};
        border-color: {theme.primary};
    }}
    QMenu {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        font-family: {theme.font_family};
        font-size: {theme.font_size};
    }}
    QMenu::item {{
        padding: 7px 24px 7px 22px;
    }}
    QMenu::item:selected {{
        background: {theme.primary_soft};
        color: {theme.text};
    }}
    QMenu::separator {{
        height: 1px;
        background: {theme.border};
        margin: 5px 8px;
    }}
    """


def palette_stylesheet(theme: Theme = DEFAULT_LIGHT) -> str:
    return f"""
    QDialog {{
        background: {theme.panel};
        color: {theme.text};
        font-family: {theme.font_family};
        font-size: {theme.font_size};
    }}
    QLabel {{
        color: {theme.muted_text};
    }}
    QLabel#PaletteContextBar {{
        background: {theme.surface};
        color: {theme.muted_text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 7px 10px;
    }}
    QLabel#PalettePreviewTitle {{
        color: {theme.text};
        font-size: 16px;
        font-weight: 700;
    }}
    QLabel#PalettePreviewMeta {{
        color: {theme.primary};
        font-size: 12px;
        font-weight: 700;
    }}
    QLabel#PalettePreviewSection {{
        color: {theme.muted_text};
        font-size: 11px;
        font-weight: 700;
        padding-top: 8px;
    }}
    QLabel#PalettePreviewDescription {{
        color: {theme.text};
        line-height: 145%;
    }}
    QLabel#PalettePreviewHint {{
        color: {theme.text};
        background: {theme.surface_alt};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 7px 9px;
    }}
    QLabel#KeyboardHint {{
        color: {theme.primary};
        background: {theme.primary_soft};
        border: 1px solid {theme.primary};
        border-radius: 6px;
        padding: 7px 9px;
        font-weight: 700;
    }}
    QFrame#PalettePreview {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 8px;
    }}
    QLineEdit {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 9px 10px;
        selection-background-color: {theme.primary};
        selection-color: #ffffff;
    }}
    QLineEdit:focus {{
        border: 2px solid {theme.primary};
    }}
    QListWidget {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 6px;
        outline: 0;
    }}
    QListWidget::item {{
        padding: 0;
        border-radius: 6px;
    }}
    QListWidget::item:disabled {{
        background: transparent;
        color: {theme.muted_text};
        font-weight: 700;
    }}
    QListWidget::item:selected {{
        background: {theme.primary_soft};
        color: {theme.text};
        border-left: 3px solid {theme.primary};
    }}
    QWidget#PaletteGroupHeader {{
        background: {theme.surface_alt};
        border-radius: 6px;
    }}
    QLabel#PaletteGroupHeaderText {{
        color: {theme.muted_text};
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#PaletteCountPill {{
        background: {theme.surface};
        color: {theme.muted_text};
        border: 1px solid {theme.border};
        border-radius: 999px;
        padding: 1px 7px;
        font-size: 11px;
        font-weight: 700;
    }}
    QWidget#PaletteActionRow {{
        background: transparent;
    }}
    QLabel#PaletteActionTitle {{
        color: {theme.text};
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#PaletteActionDescription {{
        color: {theme.muted_text};
        font-size: 12px;
    }}
    QLabel#PaletteShortcutPill {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 4px;
        padding: 2px 7px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#PaletteCategoryPill {{
        background: {theme.primary_soft};
        color: {theme.primary};
        border: 1px solid {theme.primary};
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#PaletteRecentPill {{
        background: {theme.warning_bg};
        color: {theme.warning};
        border: 1px solid {theme.warning};
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    """


def job_monitor_stylesheet(theme: Theme = DEFAULT_LIGHT) -> str:
    return f"""
    QDialog {{
        background: {theme.panel};
        color: {theme.text};
        font-family: {theme.font_family};
        font-size: {theme.font_size};
    }}
    QFrame#JobHero {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-left: 5px solid {theme.primary};
        border-radius: 8px;
    }}
    QFrame#JobHero[state="ok"] {{
        border-left-color: {theme.success};
    }}
    QFrame#JobHero[state="error"] {{
        border-left-color: {theme.danger};
    }}
    QLabel#JobStatus {{
        border: 1px solid {theme.primary};
        border-radius: 999px;
        padding: 5px 12px;
        font-weight: 700;
        background: {theme.primary_soft};
        color: {theme.primary};
    }}
    QLabel#JobStatus[state="ok"] {{
        background: {theme.success_bg};
        border-color: {theme.success};
        color: {theme.success};
    }}
    QLabel#JobStatus[state="error"] {{
        background: {theme.danger_bg};
        border-color: {theme.danger};
        color: {theme.danger};
    }}
    QLabel#JobSummary {{
        color: {theme.text};
        font-size: 16px;
        font-weight: 700;
    }}
    QLabel#JobElapsed {{
        color: {theme.muted_text};
        font-weight: 700;
    }}
    QLabel#JobSubstatus {{
        color: {theme.muted_text};
    }}
    QProgressBar#JobProgress {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 5px;
        height: 12px;
        text-align: center;
    }}
    QProgressBar#JobProgress::chunk {{
        background: {theme.primary};
        border-radius: 4px;
    }}
    QPlainTextEdit {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 8px;
        selection-background-color: {theme.primary};
        selection-color: #ffffff;
    }}
    QTabWidget::pane {{
        border: 1px solid {theme.border};
        border-radius: 6px;
        background: {theme.surface};
    }}
    QTabBar::tab {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-bottom: none;
        padding: 7px 14px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }}
    QTabBar::tab:selected {{
        background: {theme.surface};
        font-weight: 700;
    }}
    QPushButton {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{
        background: {theme.primary_soft};
        border-color: {theme.primary};
    }}
    """


def preferences_stylesheet(theme: Theme = DEFAULT_LIGHT) -> str:
    return f"""
    QDialog {{
        background: {theme.panel};
        color: {theme.text};
        font-family: {theme.font_family};
        font-size: {theme.font_size};
    }}
    QLabel {{
        color: {theme.text};
    }}
    QLabel#PreferenceHint {{
        color: {theme.muted_text};
    }}
    QGroupBox {{
        border: 1px solid {theme.border};
        border-radius: 8px;
        margin-top: 12px;
        padding: 14px 10px 10px 10px;
        background: {theme.surface};
        font-weight: 700;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: {theme.text};
    }}
    QComboBox, QSpinBox {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 5px 8px;
        min-height: 24px;
    }}
    QComboBox:focus, QSpinBox:focus {{
        border: 2px solid {theme.primary};
    }}
    QCheckBox {{
        color: {theme.text};
        spacing: 8px;
    }}
    QTableWidget, QPlainTextEdit {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 4px;
        gridline-color: {theme.border};
        selection-background-color: {theme.primary_soft};
        selection-color: {theme.text};
    }}
    QHeaderView::section {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        padding: 6px;
        font-weight: 700;
    }}
    QPushButton {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 7px 14px;
    }}
    QPushButton:hover {{
        background: {theme.primary_soft};
        border-color: {theme.primary};
    }}
    QPushButton:default {{
        background: {theme.primary};
        color: #ffffff;
        border-color: {theme.primary};
        font-weight: 700;
    }}
    QFrame#ResultMetric {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 8px;
    }}
    QFrame#ResultMetric[state="ok"] {{
        border-color: {theme.success};
        background: {theme.success_bg};
    }}
    QFrame#ResultMetric[state="warn"] {{
        border-color: {theme.warning};
        background: {theme.warning_bg};
    }}
    QFrame#ResultMetric[state="blocked"] {{
        border-color: {theme.danger};
        background: {theme.danger_bg};
    }}
    QFrame#ResultMetric[state="info"] {{
        border-color: {theme.primary};
        background: {theme.primary_soft};
    }}
    QLabel#ResultMetricValue {{
        font-size: 24px;
        font-weight: 800;
        color: {theme.text};
    }}
    QLabel#ResultMetricTitle {{
        color: {theme.muted_text};
        font-weight: 700;
    }}
    """


def safe_cleanup_stylesheet(theme: Theme = DEFAULT_LIGHT) -> str:
    return f"""
    SafeCleanupDialog {{
        background: {theme.panel};
        color: {theme.text};
        font-family: {theme.font_family};
        font-size: {theme.font_size};
    }}
    QLabel {{
        color: {theme.text};
    }}
    QLabel#H1 {{
        color: {theme.text};
        font-size: 20px;
        font-weight: 700;
    }}
    QLabel#H2 {{
        color: {theme.text};
        font-size: 15px;
        font-weight: 700;
    }}
    QLabel#Muted {{
        color: {theme.muted_text};
    }}
    QLabel#Mono {{
        color: {theme.muted_text};
        font-family: "Cascadia Code", "Consolas", monospace;
        font-size: 12px;
    }}
    QFrame#Card {{
        background: {theme.surface_card};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_md};
    }}
    QFrame#Card[hovered="true"] {{
        background: {theme.surface_card_hover};
        border-color: {theme.border_strong};
    }}
    QFrame#FooterWrap {{
        background: {theme.surface};
        border-top: 1px solid {theme.border};
    }}
    RiskBadge[layer="safe"] {{
        background: {theme.layer_safe_bg};
        color: {theme.layer_safe_fg};
        border: 1px solid {theme.layer_safe_border};
        border-radius: {theme.radius_pill};
        padding: 2px 10px;
        font-weight: 700;
    }}
    RiskBadge[layer="process"] {{
        background: {theme.layer_process_bg};
        color: {theme.layer_process_fg};
        border: 1px solid {theme.layer_process_border};
        border-radius: {theme.radius_pill};
        padding: 2px 10px;
        font-weight: 700;
    }}
    RiskBadge[layer="review"] {{
        background: {theme.layer_review_bg};
        color: {theme.layer_review_fg};
        border: 1px solid {theme.layer_review_border};
        border-radius: {theme.radius_pill};
        padding: 2px 10px;
        font-weight: 700;
    }}
    RiskBadge[layer="registry"] {{
        background: {theme.layer_registry_bg};
        color: {theme.layer_registry_fg};
        border: 1px solid {theme.layer_registry_border};
        border-radius: {theme.radius_pill};
        padding: 2px 10px;
        font-weight: 700;
    }}
    RiskBadge[layer="blocked"] {{
        background: {theme.layer_blocked_bg};
        color: {theme.layer_blocked_fg};
        border: 1px solid {theme.layer_blocked_border};
        border-radius: {theme.radius_pill};
        padding: 2px 10px;
        font-weight: 700;
    }}
    QPushButton {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_md};
        padding: 8px 14px;
    }}
    QPushButton:hover {{
        background: {theme.primary_soft};
        border-color: {theme.primary};
    }}
    QPushButton:disabled {{
        color: {theme.muted_text};
        background: {theme.surface_sunken};
        border-color: {theme.border};
    }}
    QPushButton#Primary {{
        background: {theme.primary};
        color: #ffffff;
        border: none;
        border-radius: {theme.radius_md};
        padding: 10px 20px;
        font-weight: 700;
    }}
    QPushButton#Primary:hover {{
        background: {theme.primary_hover};
    }}
    QPushButton#Ghost {{
        background: transparent;
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_md};
        padding: 8px 14px;
    }}
    QPushButton#Ghost:hover {{
        background: {theme.surface_alt};
        border-color: {theme.border_strong};
    }}
    QLineEdit {{
        background: {theme.surface_card};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_sm};
        padding: 8px 10px;
        selection-background-color: {theme.primary};
        selection-color: #ffffff;
    }}
    QLineEdit:focus {{
        border: 2px solid {theme.primary};
    }}
    QCheckBox {{
        color: {theme.text};
        spacing: 8px;
    }}
    QProgressBar {{
        background: {theme.surface_sunken};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_sm};
        color: {theme.muted_text};
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {theme.primary};
        border-radius: {theme.radius_sm};
    }}
    QTabWidget::pane {{
        border: 0;
        background: transparent;
    }}
    QTabBar::tab {{
        padding: 8px 16px;
        margin-right: 4px;
        border: none;
        border-bottom: 2px solid transparent;
        color: {theme.muted_text};
        background: transparent;
    }}
    QTabBar::tab:selected {{
        color: {theme.primary};
        border-bottom: 2px solid {theme.primary};
        font-weight: 700;
    }}
    QTreeWidget, QPlainTextEdit {{
        background: {theme.surface_card};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_sm};
        selection-background-color: {theme.primary_soft};
        selection-color: {theme.text};
    }}
    QHeaderView::section {{
        background: {theme.surface_alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        padding: 6px;
        font-weight: 700;
    }}
    """
