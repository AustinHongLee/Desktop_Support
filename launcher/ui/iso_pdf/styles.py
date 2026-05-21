from __future__ import annotations


def workbench_stylesheet() -> str:
    return """
    QDialog {
        background: #eef3f7;
        color: #18212b;
        font-family: "Microsoft JhengHei UI", "Segoe UI", Arial;
        font-size: 13px;
    }
    QScrollArea#ControlScroller {
        background: transparent;
        border: 0;
    }
    QScrollArea#ControlScroller QWidget#ControlPanel {
        background: transparent;
    }
    QFrame#Header {
        background: #ffffff;
        border: 1px solid #c8d4df;
        border-radius: 6px;
    }
    QLabel#DialogTitle {
        color: #101820;
        font-size: 18px;
        font-weight: 700;
    }
    QLabel#PillLabel {
        background: #e7f0f8;
        color: #16324f;
        border: 1px solid #b8cad9;
        border-radius: 4px;
        padding: 5px 10px;
        font-weight: 600;
    }
    QLabel#WorkflowStepChip {
        background: #f0f2f5;
        color: #3f4855;
        border: 1px solid #cbd0d6;
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 700;
    }
    QLabel#WorkflowStepChip[state="ready"] {
        background: #bbf7d0;
        color: #15803d;
        border-color: #86efac;
    }
    QLabel#WorkflowStepChip[state="warn"] {
        background: #fde68a;
        color: #92400e;
        border-color: #fcd34d;
    }
    QLabel#WorkflowStepChip[state="running"] {
        background: #e0e7ff;
        color: #3730a3;
        border-color: #a5b4fc;
    }
    QLabel#WorkflowStepChip[state="empty"] {
        background: #f0f2f5;
        color: #6b7280;
        border-color: #d8dde3;
    }
    QLabel#FieldLabel {
        color: #455565;
        font-weight: 600;
        margin-top: 4px;
    }
    QLabel#TableSummary {
        color: #455565;
        font-weight: 600;
    }
    QCheckBox {
        color: #17202a;
        spacing: 8px;
    }
    QLabel#PreviewInfo, QLabel#VisionInfo {
        color: #263746;
        background: #f5f8fb;
        border: 1px solid #d0dbe5;
        border-radius: 4px;
        padding: 6px;
    }
    QLabel#VisionInfo {
        background: #eef7ed;
        border-color: #bad7b8;
        color: #24472a;
        font-weight: 600;
    }
    QLabel#CornerPreview {
        background: #ffffff;
        color: #17202a;
        border: 1px solid #c8d4df;
        border-radius: 4px;
        padding: 4px;
    }
    QLabel#PdfPreviewImage {
        background: #ffffff;
        color: #5d6a78;
        border: 1px solid #c8d4df;
        border-radius: 4px;
        padding: 4px;
        font-weight: 600;
    }
    QGroupBox {
        background: #ffffff;
        border: 1px solid #c8d4df;
        border-radius: 6px;
        margin-top: 10px;
        font-weight: 600;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 5px;
        color: #22313f;
    }
    QLineEdit, QTableWidget {
        background: #ffffff;
        color: #17202a;
        border: 1px solid #becbd6;
        border-radius: 4px;
    }
    QLineEdit, QComboBox {
        padding: 6px;
        min-height: 22px;
    }
    QComboBox {
        background: #ffffff;
        color: #17202a;
        border: 1px solid #becbd6;
        border-radius: 4px;
    }
    QPlainTextEdit {
        background: #101722;
        color: #dce9f5;
        border: 1px solid #263546;
        border-radius: 4px;
        font-family: Consolas, "Courier New", monospace;
        padding: 6px;
    }
    QPdfView {
        background: #f8fafc;
        border: 1px solid #c8d4df;
        border-radius: 4px;
    }
    QTabWidget::pane {
        border: 1px solid #c8d4df;
        border-radius: 4px;
        background: #ffffff;
        top: -1px;
    }
    QTabBar::tab {
        background: #e8eef4;
        color: #22313f;
        border: 1px solid #c8d4df;
        border-bottom: 0;
        padding: 7px 11px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        font-weight: 600;
    }
    QTabBar::tab:selected {
        background: #ffffff;
        color: #102033;
    }
    QWidget#AutopilotPage {
        background: transparent;
    }
    QLabel#AutopilotValue {
        background: #f5f8fb;
        color: #263746;
        border: 1px solid #d0dbe5;
        border-radius: 4px;
        padding: 8px;
        min-height: 44px;
        font-weight: 600;
    }
    QFrame#AutopilotActionPanel {
        background: #ffffff;
        border: 1px solid #c8d4df;
        border-radius: 6px;
    }
    QPushButton#AutopilotRunButton {
        min-width: 260px;
        min-height: 40px;
        font-size: 15px;
        font-weight: 800;
    }
    QPushButton#AutopilotRunButton:disabled {
        background: #d8dde3;
        color: #6b7280;
        border-color: #c7ced6;
    }
    QLabel#AutopilotSummary {
        background: #f5f8fb;
        color: #263746;
        border: 1px solid #d0dbe5;
        border-radius: 4px;
        padding: 8px;
        font-weight: 700;
    }
    QLabel#AutopilotSummary[state="ready"] {
        background: #dcfce7;
        color: #166534;
        border-color: #86efac;
    }
    QLabel#AutopilotSummary[state="warn"],
    QLabel#AutopilotSummary[state="pending"] {
        background: #fef3c7;
        color: #92400e;
        border-color: #fcd34d;
    }
    QLabel#AutopilotSummary[state="blocked"] {
        background: #fee2e2;
        color: #991b1b;
        border-color: #fca5a5;
    }
    QLabel#AutopilotSummary[state="running"] {
        background: #e0e7ff;
        color: #3730a3;
        border-color: #a5b4fc;
    }
    QFrame#ChecklistRow {
        background: #f8fafc;
        border: 1px solid #d6e0ea;
        border-radius: 5px;
    }
    QLabel#ChecklistState {
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 12px;
        font-weight: 800;
    }
    QLabel#ChecklistState[state="ready"] {
        background: #bbf7d0;
        color: #15803d;
    }
    QLabel#ChecklistState[state="warn"] {
        background: #fde68a;
        color: #92400e;
    }
    QLabel#ChecklistState[state="blocked"] {
        background: #fecaca;
        color: #991b1b;
    }
    QLabel#ChecklistState[state="running"] {
        background: #e0e7ff;
        color: #3730a3;
    }
    QLabel#ChecklistState[state="pending"] {
        background: #e5e7eb;
        color: #4b5563;
    }
    QLabel#ChecklistTitle {
        color: #17202a;
        font-weight: 800;
    }
    QLabel#ChecklistDetail {
        color: #455565;
        font-weight: 600;
    }
    QTableWidget {
        gridline-color: #d8e1ea;
        selection-background-color: #cfe4f5;
        selection-color: #102033;
    }
    QTableWidget::item {
        padding: 3px;
    }
    QTableWidget::item:alternate {
        background: #f6f9fb;
    }
    QTableWidget::item:selected {
        background: #d7e8f7;
        color: #17202a;
    }
    QHeaderView::section {
        background: #e8eef4;
        color: #1b2a38;
        border: 0;
        border-right: 1px solid #c8d4df;
        border-bottom: 1px solid #c8d4df;
        padding: 7px 6px;
        font-weight: 600;
    }
    QSplitter::handle {
        background: #d7e1ea;
    }
    QSplitter::handle:horizontal {
        width: 7px;
    }
    QSplitter::handle:vertical {
        height: 7px;
    }
    QPushButton {
        background: #f8fafc;
        color: #17202a;
        border: 1px solid #aeb9c4;
        border-radius: 4px;
        padding: 7px 10px;
        min-height: 24px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #e5eef7;
    }
    QPushButton[primary="true"] {
        background: #1f6feb;
        color: #ffffff;
        border-color: #1f6feb;
    }
    QPushButton[primary="true"]:hover {
        background: #1b5fca;
    }
    """
