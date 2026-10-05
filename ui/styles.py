DARK_THEME = """
/* 全局深色高质感样式 */
QMainWindow, QWidget#centralWidget {
    background-color: #0F0F14;
    color: #F8FAFC;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}

QGroupBox {
    background-color: #171720;
    border: 1px solid #272738;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    padding-bottom: 12px;
    padding-left: 12px;
    padding-right: 12px;
    font-weight: bold;
    color: #38BDF8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #171720;
}

QLabel {
    color: #CBD5E1;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #FFFFFF;
}

QLabel#subtitleLabel {
    font-size: 12px;
    color: #94A3B8;
}

QLineEdit {
    background-color: #1F1F2C;
    border: 1px solid #333348;
    border-radius: 6px;
    padding: 6px 12px;
    color: #F8FAFC;
}

QLineEdit:focus {
    border: 1px solid #38BDF8;
    background-color: #242436;
}

QComboBox {
    background-color: #1F1F2C;
    border: 1px solid #333348;
    border-radius: 6px;
    padding: 6px 12px;
    color: #F8FAFC;
    min-width: 120px;
}

QComboBox:hover {
    border: 1px solid #4B5563;
}

QComboBox QAbstractItemView {
    background-color: #1F1F2C;
    color: #F8FAFC;
    selection-background-color: #2563EB;
    border: 1px solid #333348;
    padding: 4px;
}

/* 按钮样式 */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #38BDF8);
    color: #FFFFFF;
    font-weight: bold;
    border-radius: 6px;
    padding: 7px 14px;
    border: none;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1D4ED8, stop:1 #0284C7);
}

QPushButton:pressed {
    background: #1E40AF;
}

QPushButton#secondaryBtn {
    background-color: #262636;
    color: #E2E8F0;
    border: 1px solid #3E3E56;
    font-weight: normal;
}

QPushButton#secondaryBtn:hover {
    background-color: #323248;
    border-color: #38BDF8;
    color: #FFFFFF;
}

QPushButton#dangerBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #EF4444);
    color: #FFFFFF;
}

QPushButton#dangerBtn:hover {
    background: #B91C1C;
}

QPushButton#successBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10B981);
    color: #FFFFFF;
}

QPushButton#successBtn:hover {
    background: #047857;
}

/* 列表与表格样式 */
QListWidget, QTableWidget {
    background-color: #14141C;
    border: 1px solid #272738;
    border-radius: 8px;
    gridline-color: #20202E;
    color: #E2E8F0;
    selection-background-color: #1D4ED8;
    selection-color: #FFFFFF;
}

QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #1E1E2A;
}

QTableWidget::item:selected {
    background-color: #1E3A8A;
    color: #FFFFFF;
    font-weight: 500;
}

QHeaderView::section {
    background-color: #1C1C28;
    color: #94A3B8;
    padding: 8px 10px;
    font-weight: bold;
    border: none;
    border-right: 1px solid #28283C;
    border-bottom: 1px solid #2B2B3E;
}

QHeaderView::section:hover {
    background-color: #252538;
    color: #38BDF8;
}

/* 复选框样式（大尺寸、高对比清晰勾选） */
QCheckBox {
    color: #CBD5E1;
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 22px;
    height: 22px;
    border: 2px solid #4B5563;
    border-radius: 5px;
    background-color: #1E1E2A;
}

QCheckBox::indicator:hover {
    border: 2px solid #38BDF8;
    background-color: #25283A;
}

QCheckBox::indicator:checked {
    background-color: #2563EB;
    border: 2px solid #60A5FA;
    image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>');
}

/* 进度条 */
QProgressBar {
    border: 1px solid #2B2B3E;
    border-radius: 6px;
    background-color: #181822;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
    font-size: 11px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #38BDF8);
    border-radius: 5px;
}

/* 右键上下文菜单 */
QMenu {
    background-color: #181824;
    border: 1px solid #323248;
    border-radius: 8px;
    padding: 6px 0px;
    color: #F8FAFC;
    font-size: 13px;
}

QMenu::item {
    padding: 8px 24px 8px 16px;
    background-color: transparent;
}

QMenu::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}

QMenu::separator {
    height: 1px;
    background-color: #28283A;
    margin: 4px 8px;
}

/* 滚动条 */
QScrollBar:vertical {
    border: none;
    background: #14141C;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #2E2E42;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #464664;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
