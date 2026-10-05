import html
import re
import os
import sys
import time
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QFileDialog,
    QMessageBox, QAbstractItemView, QMenu, QSplitter, QListWidget,
    QListWidgetItem, QGroupBox, QInputDialog, QApplication,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QRectF, QModelIndex, QEvent
from PyQt6.QtGui import QIcon, QAction, QColor, QTextDocument

from core.scanner import FileScanner, PRESET_RULES, format_file_size
from core.file_operator import FileOperator
from core.natural_parser import NaturalRuleParser
from ui.styles import DARK_THEME

# 多分组彩色高亮配色方案
HIGHLIGHT_PALETTE = [
    {"color": "#F59E0B", "bg": "rgba(245, 158, 11, 0.25)", "border": "#F59E0B"},  # 第1组: 金黄/琥珀
    {"color": "#06B6D4", "bg": "rgba(6, 182, 212, 0.25)", "border": "#06B6D4"},   # 第2组: 青色/湖蓝
    {"color": "#10B981", "bg": "rgba(16, 185, 129, 0.25)", "border": "#10B981"},  # 第3组: 翠绿
    {"color": "#F43F5E", "bg": "rgba(244, 63, 94, 0.25)", "border": "#F43F5E"},   # 第4组: 玫红
    {"color": "#A855F7", "bg": "rgba(168, 85, 247, 0.25)", "border": "#A855F7"},  # 第5组: 紫色
    {"color": "#F97316", "bg": "rgba(249, 115, 22, 0.25)", "border": "#F97316"},  # 第6组: 活力橙
    {"color": "#3B82F6", "bg": "rgba(59, 130, 246, 0.25)", "border": "#3B82F6"},  # 第7组: 亮蓝
]

def build_highlighted_html(text: str, match_key: str = "", pattern_str: str = "", group_idx: int = 1) -> str:
    """根据匹配特征与所属分组，将匹配条件（如 1234567）以醒目的彩底微章在文件名/匹配原因中突出高亮"""
    if not text:
        return ""
    theme = HIGHLIGHT_PALETTE[(group_idx - 1) % len(HIGHLIGHT_PALETTE)] if group_idx > 0 else HIGHLIGHT_PALETTE[0]
    
    target_regex = None
    if match_key and match_key != ".*":
        try:
            target_regex = re.compile(f"({re.escape(match_key)})", re.IGNORECASE)
        except re.error:
            pass
    if not target_regex and pattern_str and pattern_str != ".*" and not pattern_str.startswith("__COMMON__:"):
        try:
            target_regex = re.compile(f"({pattern_str})", re.IGNORECASE)
        except re.error:
            pass

    if not target_regex or not target_regex.search(text):
        return f"<span style='color: #E2E8F0;'>{html.escape(text)}</span>"

    parts = []
    last_end = 0
    for m in target_regex.finditer(text):
        start, end = m.span()
        if start > last_end:
            parts.append(f"<span style='color: #E2E8F0;'>{html.escape(text[last_end:start])}</span>")
        matched_str = html.escape(m.group(0))
        parts.append(
            f"<span style='color: {theme['color']}; background-color: {theme['bg']}; "
            f"border: 1px solid {theme['border']}; font-weight: bold; border-radius: 3px; "
            f"padding: 1px 4px;'>{matched_str}</span>"
        )
        last_end = end
    if last_end < len(text):
        parts.append(f"<span style='color: #E2E8F0;'>{html.escape(text[last_end:])}</span>")

    return "".join(parts)

class HTMLItemDelegate(QStyledItemDelegate):
    """支持表格单元格以 HTML 富文本方式渲染彩色高亮标签并支持剪切置灰反馈的 Delegate"""
    def paint(self, painter, option, index: QModelIndex):
        painter.save()
        is_cut = index.data(Qt.ItemDataRole.UserRole + 1)
        if is_cut:
            painter.setOpacity(0.55)

        html_text = index.data(Qt.ItemDataRole.UserRole)
        if html_text and ("<span" in html_text or "<b" in html_text):
            options = QStyleOptionViewItem(option)
            self.initStyleOption(options, index)

            # 绘制单元格背景与选择高亮（完整保持原有交替行底色和鼠标悬停/选定高亮）
            options.widget.style().drawPrimitive(
                QStyle.PrimitiveElement.PE_PanelItemViewItem, options, painter, options.widget
            )

            doc = QTextDocument()
            doc.setDefaultFont(options.font)
            doc.setHtml(html_text)

            text_rect = options.rect
            y_offset = (text_rect.height() - doc.size().height()) / 2
            painter.translate(text_rect.left() + 6, text_rect.top() + max(0, y_offset))
            clip = QRectF(0, 0, text_rect.width() - 12, text_rect.height())
            doc.drawContents(painter, clip)
        else:
            super().paint(painter, option, index)
        painter.restore()

class ScanWorkerThread(QThread):
    progress_signal = pyqtSignal(str, int)          # current_dir, scanned_count
    finished_signal = pyqtSignal(list, float)        # results, elapsed_seconds
    error_signal = pyqtSignal(str)

    def __init__(self, scanner_params: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.params = scanner_params
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            start_time = time.time()
            scanner = FileScanner(
                scan_dirs=self.params["scan_dirs"],
                rule_mode=self.params["rule_mode"],
                pattern_str=self.params["pattern_str"],
                match_explanation=self.params.get("match_explanation", ""),
                match_target=self.params["match_target"],
                include_subdirs=self.params["include_subdirs"],
                include_dir_contents=self.params.get("include_dir_contents", True),
                only_duplicates=self.params.get("only_duplicates", False),
                min_size_bytes=self.params.get("min_size_bytes", 0),
                max_size_bytes=self.params.get("max_size_bytes", 0),
                file_extensions=self.params.get("file_extensions"),
                progress_callback=lambda d, c: self.progress_signal.emit(d, c),
                is_cancelled_callback=lambda: self._is_cancelled
            )
            results = scanner.scan()
            elapsed = time.time() - start_time
            self.finished_signal.emit(results, elapsed)
        except Exception as e:
            self.error_signal.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("冗余与重复文件智能自动处理工具 (FileCleaner Pro)")
        self.resize(1280, 820)
        self.setMinimumSize(1000, 650)

        # 状态数据
        self.scan_dirs: List[str] = []
        self.scan_results: List[Dict[str, Any]] = []
        self.scan_thread: Optional[ScanWorkerThread] = None

        # 剪贴板暂存（软件内置文件操作缓存）
        self.internal_clipboard: List[str] = []
        self.clipboard_operation: str = ""  # "copy" or "cut"

        self.init_ui()
        self.setStyleSheet(DARK_THEME)

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # 1. 顶部标题与简述
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_label = QLabel("📁 冗余与重复文件智能自动处理工具")
        title_label.setObjectName("titleLabel")
        subtitle_label = QLabel("支持多个文件夹批量检索 | 正则表达式/长串数字/重复数字/特殊符号匹配 | 复制、剪切、安全回收站、重命名完整处理")
        subtitle_label.setObjectName("subtitleLabel")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # 2. 上部配置控制面板（分为：待扫文件夹区域 + 过滤条件规则区域）
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 2.1 待扫描文件夹列表卡片 ---
        dir_box = QGroupBox("1. 搜寻目录配置 (支持添加多个文件夹)")
        dir_layout = QVBoxLayout(dir_box)
        dir_layout.setSpacing(8)

        self.dir_list_widget = QListWidget()
        self.dir_list_widget.setFixedHeight(120)
        dir_layout.addWidget(self.dir_list_widget)

        dir_btn_layout = QHBoxLayout()
        self.add_dir_btn = QPushButton("➕ 添加文件夹")
        self.add_dir_btn.clicked.connect(self.add_scan_directory)
        dir_btn_layout.addWidget(self.add_dir_btn)

        self.remove_dir_btn = QPushButton("➖ 移除选中")
        self.remove_dir_btn.setObjectName("secondaryBtn")
        self.remove_dir_btn.clicked.connect(self.remove_selected_directory)
        dir_btn_layout.addWidget(self.remove_dir_btn)

        self.clear_dirs_btn = QPushButton("清空目录")
        self.clear_dirs_btn.setObjectName("secondaryBtn")
        self.clear_dirs_btn.clicked.connect(self.clear_all_directories)
        dir_btn_layout.addWidget(self.clear_dirs_btn)

        dir_layout.addLayout(dir_btn_layout)
        top_splitter.addWidget(dir_box)

        # --- 2.2 规则与条件配置卡片 ---
        rule_box = QGroupBox("2. 冗余与重复匹配规则定制 (多重条件组合)")
        rule_layout = QVBoxLayout(rule_box)
        rule_layout.setSpacing(8)

        # 规则模式切换
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("搜寻模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "🧠 中文自然语言指令 (智能自动解释并转换)",
            "📋 常用预置规则 (长串数字/重复数字/特殊符号等)",
            "⚡ 自定义正则表达式 (高级精准匹配)",
            "👥 内容完全重复 (MD5哈希查重)",
            "📁 跨文件夹同名查重 (文件/文件夹)"
        ])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_row.addWidget(self.mode_combo, stretch=1)

        mode_row.addWidget(QLabel("检索对象:"))
        self.target_combo = QComboBox()
        self.target_combo.addItems(["仅文件", "仅文件夹", "文件和文件夹均处理"])
        self.target_combo.setCurrentIndex(2)  # 默认同时处理文件与文件夹
        mode_row.addWidget(self.target_combo)
        rule_layout.addLayout(mode_row)

        # 中文快捷输入建议标签
        self.natural_hint_row = QHBoxLayout()
        self.natural_hint_label = QLabel("💡 示例提示:「包含7位数字」「连续8位以上数字」「数字+符号+数字」「包含副本」")
        self.natural_hint_label.setStyleSheet("color: #38BDF8; font-size: 11px;")
        self.natural_hint_row.addWidget(self.natural_hint_label)
        rule_layout.addLayout(self.natural_hint_row)

        # 预置规则选择
        self.preset_row = QHBoxLayout()
        self.preset_label = QLabel("预置条件:")
        self.preset_combo = QComboBox()
        for r in PRESET_RULES:
            self.preset_combo.addItem(r["name"], r["pattern"])
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        self.preset_row.addWidget(self.preset_label)
        self.preset_row.addWidget(self.preset_combo, stretch=1)
        rule_layout.addLayout(self.preset_row)
        self.preset_row.setEnabled(False)
        self.preset_label.setVisible(False)
        self.preset_combo.setVisible(False)

        # 表达式输入框与解释展示
        self.pattern_row = QHBoxLayout()
        self.pattern_label = QLabel("条件输入:")
        self.pattern_input = QLineEdit()
        self.pattern_input.setText("包含7位数字")
        self.pattern_input.setPlaceholderText("可直接输入中文要求，如：包含7位数字、数字+符号+数字、8位以上数字")
        self.pattern_input.textChanged.connect(self.on_pattern_text_changed)
        self.pattern_row.addWidget(self.pattern_label)
        self.pattern_row.addWidget(self.pattern_input, stretch=1)
        rule_layout.addLayout(self.pattern_row)

        # 实时自动翻译与智能解释展示栏
        self.explain_row = QHBoxLayout()
        self.explain_title = QLabel("🤖 系统解释:")
        self.explain_title.setStyleSheet("color: #10B981; font-weight: bold;")
        self.explain_label = QLabel("准备就绪")
        self.explain_label.setStyleSheet("color: #F8FAFC; background-color: #1B2432; border: 1px solid #2563EB; border-radius: 4px; padding: 4px 8px; font-weight: 500;")
        self.explain_row.addWidget(self.explain_title)
        self.explain_row.addWidget(self.explain_label, stretch=1)
        rule_layout.addLayout(self.explain_row)

        # 初始化当前解释
        self.current_parsed_regex = r"\d{7}"
        self.current_parsed_explanation = "包含连续 7 位数字 (如 1234567)"
        self.explain_label.setText(f"{self.current_parsed_explanation}   [匹配模式: {self.current_parsed_regex}]")

        # 补充选项与操作按钮行
        options_row = QHBoxLayout()
        self.subdirs_checkbox = QCheckBox("递归包含子文件夹")
        self.subdirs_checkbox.setChecked(True)
        options_row.addWidget(self.subdirs_checkbox)

        self.dir_contents_checkbox = QCheckBox("包含所匹文件夹内部所有文件")
        self.dir_contents_checkbox.setChecked(False)
        self.dir_contents_checkbox.setToolTip("当某个文件夹名称符合条件时，是否将其内部包含的所有子文件/子目录也一并列出供批量操作（默认关闭，仅列出符合规则的项）")
        options_row.addWidget(self.dir_contents_checkbox)

        options_row.addWidget(QLabel("扩展名限制 (可选，如 .jpg,.mp4):"))
        self.ext_filter_input = QLineEdit()
        self.ext_filter_input.setPlaceholderText("留空不限")
        self.ext_filter_input.setMaximumWidth(120)
        options_row.addWidget(self.ext_filter_input)

        options_row.addWidget(QLabel("最小大小 (GB):"))
        self.min_size_gb_input = QLineEdit()
        self.min_size_gb_input.setPlaceholderText("如 1 或留空")
        self.min_size_gb_input.setMaximumWidth(90)
        self.min_size_gb_input.setToolTip("筛选大小不小于指定 G 的文件夹或文件（留空则不设下限）")
        options_row.addWidget(self.min_size_gb_input)

        self.only_duplicates_checkbox = QCheckBox("仅显示相互重复项 (排除孤立单项)")
        self.only_duplicates_checkbox.setChecked(True)
        self.only_duplicates_checkbox.setToolTip("开启后只选出两个或多个相互包含相同特征数字/关键词的项，自动排除无重复的孤立项")
        options_row.addWidget(self.only_duplicates_checkbox)

        options_row.addStretch()

        self.start_scan_btn = QPushButton("🔍 开始搜寻")
        self.start_scan_btn.setMinimumWidth(110)
        self.start_scan_btn.clicked.connect(self.start_scanning)
        options_row.addWidget(self.start_scan_btn)

        self.cancel_scan_btn = QPushButton("⏹ 停止")
        self.cancel_scan_btn.setObjectName("dangerBtn")
        self.cancel_scan_btn.setEnabled(False)
        self.cancel_scan_btn.clicked.connect(self.cancel_scanning)
        options_row.addWidget(self.cancel_scan_btn)

        # 回车快捷开始搜寻与修改条件即刻恢复开始按钮
        self.pattern_input.returnPressed.connect(self.start_scanning)
        self.min_size_gb_input.returnPressed.connect(self.start_scanning)
        self.ext_filter_input.returnPressed.connect(self.start_scanning)
        self.target_combo.currentIndexChanged.connect(lambda: self.start_scan_btn.setEnabled(True))
        self.subdirs_checkbox.toggled.connect(lambda: self.start_scan_btn.setEnabled(True))
        self.dir_contents_checkbox.toggled.connect(lambda: self.start_scan_btn.setEnabled(True))
        self.only_duplicates_checkbox.toggled.connect(lambda: self.start_scan_btn.setEnabled(True))
        self.min_size_gb_input.textChanged.connect(lambda: self.start_scan_btn.setEnabled(True))
        self.ext_filter_input.textChanged.connect(lambda: self.start_scan_btn.setEnabled(True))

        rule_layout.addLayout(options_row)
        top_splitter.addWidget(rule_box)

        top_splitter.setStretchFactor(0, 2)
        top_splitter.setStretchFactor(1, 3)
        main_layout.addWidget(top_splitter)

        # 3. 搜索结果展示与操作表格
        results_group = QGroupBox("3. 搜寻出符合要求的文件 / 文件夹清单 (可勾选、右键菜单、多重处理)")
        results_layout = QVBoxLayout(results_group)
        results_layout.setSpacing(8)

        # 结果表格顶部的即时快捷搜索/过滤栏
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("🔍 列表快捷筛选:"))
        self.table_filter_input = QLineEdit()
        self.table_filter_input.setPlaceholderText("在当前搜出条目中即时过滤（支持文件名、路径、匹配原因模糊筛选）...")
        self.table_filter_input.textChanged.connect(self.filter_table_items)
        filter_bar.addWidget(self.table_filter_input, stretch=1)

        self.btn_clear_filter = QPushButton("清空筛选")
        self.btn_clear_filter.setObjectName("secondaryBtn")
        self.btn_clear_filter.clicked.connect(lambda: self.table_filter_input.clear())
        filter_bar.addWidget(self.btn_clear_filter)

        self.filter_count_label = QLabel("")
        self.filter_count_label.setStyleSheet("color: #38BDF8; font-size: 11px;")
        filter_bar.addWidget(self.filter_count_label)
        results_layout.addLayout(filter_bar)

        # 结果表格
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels([
            "选择", "序号", "类型", "名称", "大小 (GB)", "匹配原因", "具体完整路径"
        ])
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.results_table.setColumnWidth(0, 58)   # 选择框
        self.results_table.setColumnWidth(1, 55)   # 序号
        self.results_table.setColumnWidth(2, 65)   # 类型
        self.results_table.setColumnWidth(3, 240)  # 名称
        self.results_table.setColumnWidth(4, 115)  # 大小 (GB)
        self.results_table.setColumnWidth(5, 230)  # 匹配原因
        self.results_table.setColumnWidth(6, 420)  # 具体路径
        self.results_table.verticalHeader().setDefaultSectionSize(40)

        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_context_menu)
        self.results_table.itemDoubleClicked.connect(self.on_item_double_clicked)

        # 注册自定义 HTML 富文本委托，支持特征彩色高亮与剪切置灰反馈
        self.html_delegate = HTMLItemDelegate(self.results_table)
        for col_idx in range(self.results_table.columnCount()):
            self.results_table.setItemDelegateForColumn(col_idx, self.html_delegate)

        # 快捷键支持 (Ctrl+X 剪切, Ctrl+C 复制, Ctrl+V 粘贴移动, Delete 删除)
        act_key_cut = QAction(self)
        act_key_cut.setShortcut("Ctrl+X")
        act_key_cut.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        act_key_cut.triggered.connect(self.action_batch_cut)
        self.results_table.addAction(act_key_cut)

        act_key_copy = QAction(self)
        act_key_copy.setShortcut("Ctrl+C")
        act_key_copy.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        act_key_copy.triggered.connect(self.action_batch_copy)
        self.results_table.addAction(act_key_copy)

        act_key_paste = QAction(self)
        act_key_paste.setShortcut("Ctrl+V")
        act_key_paste.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        act_key_paste.triggered.connect(self.action_batch_paste)
        self.results_table.addAction(act_key_paste)

        act_key_del = QAction(self)
        act_key_del.setShortcut("Delete")
        act_key_del.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        act_key_del.triggered.connect(self.action_batch_trash)
        self.results_table.addAction(act_key_del)

        results_layout.addWidget(self.results_table)

        # 表格下方快捷批量操作栏
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setObjectName("secondaryBtn")
        self.btn_select_all.clicked.connect(self.select_all_items)
        bottom_bar.addWidget(self.btn_select_all)

        self.btn_clear_sel = QPushButton("取消全选")
        self.btn_clear_sel.setObjectName("secondaryBtn")
        self.btn_clear_sel.clicked.connect(self.clear_all_selection)
        bottom_bar.addWidget(self.btn_clear_sel)

        bottom_bar.addWidget(QLabel("|  批量处理:"))

        # 复制
        self.btn_batch_copy = QPushButton("📋 复制所选项")
        self.btn_batch_copy.setObjectName("secondaryBtn")
        self.btn_batch_copy.clicked.connect(self.action_batch_copy)
        bottom_bar.addWidget(self.btn_batch_copy)

        # 剪切/移动
        self.btn_batch_cut = QPushButton("✂ 剪切/移动所选项")
        self.btn_batch_cut.setObjectName("secondaryBtn")
        self.btn_batch_cut.clicked.connect(self.action_batch_cut)
        bottom_bar.addWidget(self.btn_batch_cut)

        # 粘贴到指定目录
        self.btn_batch_paste = QPushButton("📥 粘贴到目标文件夹...")
        self.btn_batch_paste.setObjectName("successBtn")
        self.btn_batch_paste.setEnabled(False)
        self.btn_batch_paste.clicked.connect(self.action_batch_paste)
        bottom_bar.addWidget(self.btn_batch_paste)

        # 安全移到回收站
        self.btn_batch_trash = QPushButton("🗑 移至回收站")
        self.btn_batch_trash.setObjectName("dangerBtn")
        self.btn_batch_trash.clicked.connect(self.action_batch_trash)
        bottom_bar.addWidget(self.btn_batch_trash)

        bottom_bar.addStretch()

        self.status_label = QLabel("请添加搜寻文件夹并点击 [开始搜寻]")
        self.status_label.setStyleSheet("color: #94A3B8;")
        bottom_bar.addWidget(self.status_label)

        results_layout.addLayout(bottom_bar)
        main_layout.addWidget(results_group, stretch=1)

        # 4. 底部扫描进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

    # ----------------- 界面联动逻辑 -----------------
    def on_pattern_text_changed(self, text: str):
        self.start_scan_btn.setEnabled(True)
        if any(w in text for w in ['相同', '共同', '重复', '查重']):
            self.only_duplicates_checkbox.setChecked(True)
        mode_idx = self.mode_combo.currentIndex()
        if mode_idx == 0:  # 中文自然语言模式
            regex, explanation = NaturalRuleParser.parse(text)
            self.current_parsed_regex = regex
            self.current_parsed_explanation = explanation
            display_pattern = "智能特征自动比对提取" if regex.startswith("__COMMON__:") else regex
            self.explain_label.setText(f"{explanation}   [匹配模式: {display_pattern}]")
        elif mode_idx == 2:  # 自定义正则表达式
            self.current_parsed_regex = text.strip()
            self.current_parsed_explanation = f"自定义正则: {text.strip()}"
            self.explain_label.setText(f"正则表达式模式: {text.strip()}")
        elif mode_idx == 4:  # 同名查重（可选名称规则/过滤）
            val = text.strip()
            if not val:
                self.current_parsed_regex = ""
                self.current_parsed_explanation = "全部同名项 (不过滤名称)"
                self.explain_label.setText("💡 未设名称过滤：比对并列出所有重名项。可在右侧选择【仅文件】、【仅文件夹】或【全部】")
            else:
                regex, explanation = NaturalRuleParser.parse(val)
                self.current_parsed_regex = regex
                self.current_parsed_explanation = explanation
                display_pattern = "智能特征提取" if regex.startswith("__COMMON__:") else regex
                self.explain_label.setText(f"同名名称过滤: {explanation}   [模式: {display_pattern}]")

    def on_mode_changed(self, index: int):
        self.start_scan_btn.setEnabled(True)
        if index == 0:  # 中文自然语言模式
            self.preset_combo.setVisible(False)
            self.preset_label.setVisible(False)
            self.natural_hint_row.setEnabled(True)
            self.natural_hint_label.setVisible(True)
            self.pattern_label.setText("中文指令:")
            self.pattern_input.setEnabled(True)
            self.pattern_input.setPlaceholderText("可直接输入中文要求，如：相同的4个以上文字或数字、共同包含1234567、7位相同数字")
            if not self.pattern_input.text().strip():
                self.pattern_input.setText("包含7位数字")
            self.explain_row.setEnabled(True)
            self.explain_title.setVisible(True)
            self.explain_label.setVisible(True)
            self.on_pattern_text_changed(self.pattern_input.text())
        elif index == 1:  # 常用预置规则
            self.preset_combo.setVisible(True)
            self.preset_label.setVisible(True)
            self.natural_hint_label.setVisible(False)
            self.pattern_label.setText("匹配表达式:")
            self.pattern_input.setEnabled(True)
            self.explain_row.setEnabled(True)
            self.explain_title.setVisible(True)
            self.explain_label.setVisible(True)
            self.pattern_input.setText(self.preset_combo.currentData())
            self.current_parsed_regex = self.preset_combo.currentData()
            self.current_parsed_explanation = self.preset_combo.currentText()
            self.explain_label.setText(f"预置规则: {self.current_parsed_explanation}")
        elif index == 2:  # 自定义正则表达式
            self.preset_combo.setVisible(False)
            self.preset_label.setVisible(False)
            self.natural_hint_label.setVisible(False)
            self.pattern_label.setText("正则表达式:")
            self.pattern_input.setEnabled(True)
            self.explain_row.setEnabled(True)
            self.explain_title.setVisible(True)
            self.explain_label.setVisible(True)
            self.pattern_input.setPlaceholderText(r"输入正则表达式，如 \d{6,} 或 (\d)\1{6}")
            self.on_pattern_text_changed(self.pattern_input.text())
        elif index == 3:  # MD5哈希查重
            self.preset_combo.setVisible(False)
            self.preset_label.setVisible(False)
            self.natural_hint_label.setVisible(False)
            self.pattern_label.setText("匹配说明:")
            self.pattern_input.setEnabled(False)
            self.pattern_input.setText("扫描内容完全一致(MD5重复)的文件")
            self.explain_row.setEnabled(True)
            self.explain_title.setVisible(True)
            self.explain_label.setVisible(True)
            self.explain_label.setText("基于文件内容逐字节/MD5哈希对比查重，100% 精确")
        else:  # 跨文件夹同名查重
            self.preset_combo.setVisible(False)
            self.preset_label.setVisible(False)
            self.natural_hint_label.setVisible(False)
            self.pattern_label.setText("名称过滤(可选):")
            self.pattern_input.setEnabled(True)
            self.pattern_input.setPlaceholderText("留空查所有同名项；或输入关键字/中文规则/正则（如：包含7位数字、1234567）")
            self.explain_row.setEnabled(True)
            self.explain_title.setVisible(True)
            self.explain_label.setVisible(True)
            self.on_pattern_text_changed(self.pattern_input.text())

    def on_preset_changed(self, index: int):
        self.start_scan_btn.setEnabled(True)
        if 0 <= index < len(PRESET_RULES):
            if PRESET_RULES[index].get("only_duplicates"):
                self.only_duplicates_checkbox.setChecked(True)
        pattern = self.preset_combo.currentData()
        name = self.preset_combo.currentText()
        if pattern:
            self.pattern_input.setText(pattern)
            self.current_parsed_regex = pattern
            self.current_parsed_explanation = name
            self.explain_label.setText(f"预置规则: {name}   [匹配模式: {pattern}]")

    def add_scan_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择要搜寻的文件夹")
        if dir_path:
            dir_path = os.path.normpath(dir_path)
            if dir_path not in self.scan_dirs:
                self.scan_dirs.append(dir_path)
                self.dir_list_widget.addItem(dir_path)

    def remove_selected_directory(self):
        curr_row = self.dir_list_widget.currentRow()
        if curr_row >= 0:
            item = self.dir_list_widget.takeItem(curr_row)
            if item.text() in self.scan_dirs:
                self.scan_dirs.remove(item.text())

    def clear_all_directories(self):
        self.scan_dirs.clear()
        self.dir_list_widget.clear()

    # ----------------- 扫描流程 -----------------
    def start_scanning(self):
        if not self.scan_dirs:
            QMessageBox.warning(self, "提示", "请至少添加一个待搜寻的文件夹！")
            return

        mode_idx = self.mode_combo.currentIndex()
        # 0: 中文自然语言, 1: 预置规则, 2: 正则, 3: MD5哈希, 4: 同名查重
        if mode_idx == 0:
            rule_mode = "regex"
            raw_input = self.pattern_input.text().strip()
            if not raw_input:
                pattern, explanation = r".*", "检索该文件夹下的全部文件与子文件夹"
                match_explanation = "检索全部文件与文件夹"
            else:
                pattern, explanation = NaturalRuleParser.parse(raw_input)
                match_explanation = f"中文指令: {raw_input} -> {explanation}"
        elif mode_idx == 1:
            rule_mode = "preset"
            pattern = self.preset_combo.currentData()
            match_explanation = f"预置规则: {self.preset_combo.currentText()}"
        elif mode_idx == 2:
            rule_mode = "regex"
            pattern = self.pattern_input.text().strip()
            if not pattern:
                QMessageBox.warning(self, "提示", "请输入正则表达式！")
                return
            match_explanation = f"正则匹配: {pattern}"
        elif mode_idx == 3:
            rule_mode = "hash_duplicate"
            pattern = ""
            match_explanation = "MD5内容完全相同"
        else:
            rule_mode = "name_duplicate"
            raw_input = self.pattern_input.text().strip()
            if not raw_input:
                pattern = ""
                match_explanation = "同名重复项 (不过滤名称)"
            else:
                pattern, explanation = NaturalRuleParser.parse(raw_input)
                match_explanation = f"同名规则匹配: {explanation} ({pattern})"

        target_idx = self.target_combo.currentIndex()
        target_map = {0: "files", 1: "dirs", 2: "all"}
        match_target = target_map.get(target_idx, "all")

        # 扩展名限制
        ext_text = self.ext_filter_input.text().strip()
        ext_list = [e.strip() if e.strip().startswith(".") else f".{e.strip()}" for e in ext_text.split(",") if e.strip()] if ext_text else None

        # 大小限制 (GB)
        min_bytes = 0
        try:
            min_gb = self.min_size_gb_input.text().strip()
            if min_gb:
                min_bytes = int(float(min_gb) * (1024 ** 3))
        except ValueError:
            pass

        self.current_parsed_regex = pattern

        params = {
            "scan_dirs": self.scan_dirs,
            "rule_mode": rule_mode,
            "pattern_str": pattern,
            "match_explanation": match_explanation,
            "match_target": match_target,
            "include_subdirs": self.subdirs_checkbox.isChecked(),
            "include_dir_contents": self.dir_contents_checkbox.isChecked(),
            "only_duplicates": self.only_duplicates_checkbox.isChecked(),
            "min_size_bytes": min_bytes,
            "max_size_bytes": 0,
            "file_extensions": ext_list
        }

        # 1. 若上一次扫描线程仍在运行，优雅终止并断开旧信号，避免旧数据覆盖新搜索
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            try:
                self.scan_thread.finished_signal.disconnect()
                self.scan_thread.progress_signal.disconnect()
                self.scan_thread.error_signal.disconnect()
            except Exception:
                pass
            self.scan_thread.wait(200)

        # 2. 立即重置上一次旧搜索结果，给用户清晰的重新搜索反馈
        self.scan_results = []
        self.populate_results_table()

        self.start_scan_btn.setEnabled(False)
        self.cancel_scan_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # 跑马灯等待模式
        self.status_label.setText("正在根据新条件重新搜寻中...")

        self.scan_thread = ScanWorkerThread(params)
        self.scan_thread.progress_signal.connect(self.on_scan_progress)
        self.scan_thread.finished_signal.connect(self.on_scan_finished)
        self.scan_thread.error_signal.connect(self.on_scan_error)
        self.scan_thread.start()

    def cancel_scanning(self):
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.status_label.setText("已终止搜寻，可随时调整条件重新搜索")
        self.start_scan_btn.setEnabled(True)
        self.cancel_scan_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

    def on_scan_progress(self, current_dir: str, scanned_count: int):
        self.status_label.setText(f"已扫描 {scanned_count} 个条目 | 正在扫描: {os.path.basename(current_dir)}")

    def on_scan_finished(self, results: List[Dict[str, Any]], elapsed: float):
        self.start_scan_btn.setEnabled(True)
        self.cancel_scan_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

        self.scan_results = results
        self.populate_results_table()
        self.status_label.setText(f"搜寻完毕！共发现 {len(results)} 个符合条件的冗余/重复项，耗时 {elapsed:.2f} 秒")

    def on_scan_error(self, err_msg: str):
        self.start_scan_btn.setEnabled(True)
        self.cancel_scan_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "搜寻错误", f"搜寻过程中发生错误:\n{err_msg}")
        self.status_label.setText("搜寻遇到错误终止")

    # ----------------- 结果展示 -----------------
    def populate_results_table(self):
        self.table_filter_input.blockSignals(True)
        self.table_filter_input.clear()
        self.table_filter_input.blockSignals(False)
        self.filter_count_label.setText("")

        self.results_table.setRowCount(0)
        count = len(self.scan_results)
        if count == 0:
            return

        self.results_table.setRowCount(count)
        # 组别交替背景色（针对同名/哈希重复结果）
        group_bg_even = QColor("#131C2E")  # 微亮深蓝底
        group_bg_odd = QColor("#0F172A")   # 标准深灰底

        for i, item in enumerate(self.scan_results):
            grp = item.get("group", 0)
            use_group_tint = (grp > 0)
            row_bg = group_bg_even if (grp % 2 == 1) else group_bg_odd

            # Column 0: 勾选框
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb = QCheckBox()
            cb.setProperty("rowIndex", i)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb_layout.addWidget(cb)
            self.results_table.setCellWidget(i, 0, cb_container)

            # Column 1: 序号
            idx_item = QTableWidgetItem(str(i + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(i, 1, idx_item)

            # Column 2: 类型
            type_str = "📁 目录" if item.get("is_dir") else "📄 文件"
            type_item = QTableWidgetItem(type_str)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(i, 2, type_item)

            # Column 3: 名称（用不同颜色高亮标出符合条件的特征字符串）
            name_str = item.get("name", "")
            name_item = QTableWidgetItem(name_str)
            name_item.setToolTip(name_str)
            highlighted_name = build_highlighted_html(
                name_str,
                match_key=item.get("match_key", ""),
                pattern_str=getattr(self, "current_parsed_regex", ""),
                group_idx=grp
            )
            name_item.setData(Qt.ItemDataRole.UserRole, highlighted_name)
            self.results_table.setItem(i, 3, name_item)

            # Column 4: 大小
            size_item = QTableWidgetItem(item.get("size_str", ""))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.results_table.setItem(i, 4, size_item)

            # Column 5: 匹配原因（同样对特征关键字高亮强化）
            reason_str = item.get("match_reason", "")
            reason_item = QTableWidgetItem(reason_str)
            reason_item.setToolTip(reason_str)
            highlighted_reason = build_highlighted_html(
                reason_str,
                match_key=item.get("match_key", ""),
                pattern_str=getattr(self, "current_parsed_regex", ""),
                group_idx=grp
            )
            reason_item.setData(Qt.ItemDataRole.UserRole, highlighted_reason)
            self.results_table.setItem(i, 5, reason_item)

            # Column 6: 具体地址 (可双击或右键快速定位)
            path_item = QTableWidgetItem(item.get("path", ""))
            path_item.setToolTip(item.get("path", ""))
            self.results_table.setItem(i, 6, path_item)

            if use_group_tint:
                for col in range(1, 7):
                    cell = self.results_table.item(i, col)
                    if cell:
                        cell.setBackground(row_bg)

    def filter_table_items(self, text: str):
        query = text.strip().lower()
        visible_count = 0
        total_count = self.results_table.rowCount()
        for r in range(total_count):
            if not query:
                self.results_table.setRowHidden(r, False)
                visible_count += 1
            else:
                # 检查类型(2)、名称(3)、匹配原因(5)、具体路径(6)
                name_text = (self.results_table.item(r, 3).text() if self.results_table.item(r, 3) else "").lower()
                reason_text = (self.results_table.item(r, 5).text() if self.results_table.item(r, 5) else "").lower()
                path_text = (self.results_table.item(r, 6).text() if self.results_table.item(r, 6) else "").lower()
                
                matched = (query in name_text) or (query in reason_text) or (query in path_text)
                self.results_table.setRowHidden(r, not matched)
                if matched:
                    visible_count += 1

        if query:
            self.filter_count_label.setText(f"已过滤显示: {visible_count} / {total_count} 项")
        else:
            self.filter_count_label.setText("")

    # ----------------- 选择处理 -----------------
    def get_row_checkbox(self, row: int) -> Optional[QCheckBox]:
        widget = self.results_table.cellWidget(row, 0)
        if isinstance(widget, QWidget):
            return widget.findChild(QCheckBox)
        return None

    def get_effective_selected_rows(self) -> List[int]:
        """优先使用复选框选中的行，其次使用鼠标选中的高亮行（自动忽略被过滤隐藏的行）"""
        checked_rows = []
        for r in range(self.results_table.rowCount()):
            if self.results_table.isRowHidden(r):
                continue
            cb = self.get_row_checkbox(r)
            if cb and cb.isChecked():
                checked_rows.append(r)
        if checked_rows:
            return checked_rows
        return sorted(set(idx.row() for idx in self.results_table.selectedIndexes() if not self.results_table.isRowHidden(idx.row())))

    def get_selected_paths(self) -> List[str]:
        rows = self.get_effective_selected_rows()
        paths = []
        for r in rows:
            if 0 <= r < len(self.scan_results):
                paths.append(self.scan_results[r]["path"])
        return paths

    def select_all_items(self):
        for r in range(self.results_table.rowCount()):
            if not self.results_table.isRowHidden(r):
                cb = self.get_row_checkbox(r)
                if cb:
                    cb.setChecked(True)

    def clear_all_selection(self):
        for r in range(self.results_table.rowCount()):
            cb = self.get_row_checkbox(r)
            if cb:
                cb.setChecked(False)
        self.results_table.clearSelection()

    # ----------------- 文件处理操作 -----------------
    def on_item_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        if 0 <= row < len(self.scan_results):
            path = self.scan_results[row]["path"]
            FileOperator.open_in_explorer(path)

    def show_context_menu(self, pos: QPoint):
        item_at = self.results_table.itemAt(pos)
        clicked_row = item_at.row() if item_at else self.results_table.rowAt(pos.y())

        selected_rows = self.get_effective_selected_rows()
        if clicked_row >= 0 and clicked_row not in selected_rows:
            # 清除之前的选择与复选框，选中当前右击的单行
            for r in range(self.results_table.rowCount()):
                cb = self.get_row_checkbox(r)
                if cb:
                    cb.setChecked(False)
            self.results_table.clearSelection()
            self.results_table.selectRow(clicked_row)
            selected_rows = [clicked_row]

        if not selected_rows:
            return

        count = len(selected_rows)
        menu = QMenu(self)

        # 打开操作
        if count == 1:
            p = self.scan_results[selected_rows[0]]["path"]
            act_open = menu.addAction("📂 在资源管理器中打开并定位")
            act_open.triggered.connect(lambda: FileOperator.open_in_explorer(p))
            act_run = menu.addAction("🚀 直接打开此文件")
            act_run.triggered.connect(lambda: FileOperator.open_file_directly(p))
            menu.addSeparator()

        # 剪贴板文件操作
        act_copy = menu.addAction(f"📋 复制选中的 {count} 项 (Ctrl+C)")
        act_copy.triggered.connect(self.action_batch_copy)

        act_cut = menu.addAction(f"✂ 剪切 / 移动选中的 {count} 项... (Ctrl+X)")
        act_cut.triggered.connect(self.action_batch_cut)

        if self.internal_clipboard:
            op_label = "移动" if self.clipboard_operation == "cut" else "粘贴"
            act_paste = menu.addAction(f"📥 {op_label}已暂存的 {len(self.internal_clipboard)} 项到目标文件夹... (Ctrl+V)")
            act_paste.triggered.connect(self.action_batch_paste)

        menu.addSeparator()

        # 重命名 (单项)
        if count == 1:
            act_rename = menu.addAction("✏ 重命名...")
            act_rename.triggered.connect(lambda: self.action_rename_single(selected_rows[0]))
            menu.addSeparator()

        # 删除操作
        act_trash = menu.addAction(f"🗑 移至回收站 ({count}项，按Delete)")
        act_trash.triggered.connect(self.action_batch_trash)

        act_del = menu.addAction(f"💥 永久删除 ({count}项，不可恢复)")
        act_del.triggered.connect(self.action_batch_delete_permanently)

        menu.addSeparator()
        act_sel_all = menu.addAction("全选所有项")
        act_sel_all.triggered.connect(self.select_all_items)
        act_clear_sel = menu.addAction("取消选择")
        act_clear_sel.triggered.connect(self.clear_all_selection)

        menu.exec(self.results_table.viewport().mapToGlobal(pos))

    # --- 动作具体实现 ---
    def mark_cut_rows(self, cut_paths: List[str]):
        """标记被剪切的行，提供半透明置灰视觉反馈，提示已剪切待粘贴"""
        cut_set = set(os.path.normpath(p) for p in cut_paths)
        for r in range(self.results_table.rowCount()):
            if r < len(self.scan_results):
                item_path = os.path.normpath(self.scan_results[r].get("path", ""))
                is_cut = (item_path in cut_set)
                for col in range(self.results_table.columnCount()):
                    cell = self.results_table.item(r, col)
                    if cell:
                        cell.setData(Qt.ItemDataRole.UserRole + 1, is_cut)
        self.results_table.viewport().update()

    def action_batch_copy(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先在列表中勾选或点击选中要复制的文件/文件夹！")
            return

        # 同步写入 Windows 系统剪贴板
        FileOperator.set_system_clipboard(paths, is_cut=False)
        self.internal_clipboard = paths
        self.clipboard_operation = "copy"
        self.btn_batch_paste.setEnabled(True)
        self.btn_batch_paste.setText(f"📥 粘贴复制到目标文件夹 ({len(paths)}项)")

        dest_dir = QFileDialog.getExistingDirectory(
            self,
            f"请选择要将这 {len(paths)} 个条目复制到的目标文件夹 (如需去外部窗口按 Ctrl+V 粘贴可直接点取消)",
            ""
        )
        if dest_dir:
            self.execute_copy(paths, dest_dir)
        else:
            self.status_label.setText(
                f"已复制 {len(paths)} 个条目到系统剪贴板！您可直接在 Windows 文件夹按 Ctrl+V 粘贴，或点击下方的【粘贴复制到目标文件夹】。"
            )

    def action_batch_cut(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先在列表中勾选或点击选中要剪切/移动的文件/文件夹！")
            return

        # 1. 立即同步写入 Windows 系统剪贴板 (带 DROPEFFECT_MOVE 剪切移动标记，支持在资源管理器按 Ctrl+V 粘贴移动)
        FileOperator.set_system_clipboard(paths, is_cut=True)
        self.internal_clipboard = paths
        self.clipboard_operation = "cut"
        self.btn_batch_paste.setEnabled(True)
        self.btn_batch_paste.setText(f"📥 移动到目标文件夹 ({len(paths)}项)")

        # 2. 视觉反馈：将剪切的行在列表中半透明置灰
        self.mark_cut_rows(paths)

        # 3. 立即弹出目标文件夹选择对话框，直接实现一键移动
        dest_dir = QFileDialog.getExistingDirectory(
            self,
            f"请选择要将这 {len(paths)} 个条目移动到的目标文件夹 (如需去外部资源管理器按 Ctrl+V 粘贴可直接点取消)",
            ""
        )
        if dest_dir:
            self.execute_move(paths, dest_dir)
        else:
            self.status_label.setText(
                f"已剪切 {len(paths)} 个条目到系统剪贴板！您现在可以直接在 Windows 资源管理器按 Ctrl+V 粘贴移动，或点击下方的【移动到目标文件夹】。"
            )

    def execute_move(self, paths: List[str], dest_dir: str):
        dest_dir = os.path.normpath(dest_dir)
        count = len(paths)
        results = FileOperator.move_items(paths, dest_dir)
        success_count = sum(1 for _, ok, _ in results if ok)
        fail_count = count - success_count

        # 收集成功移动的路径，从结果列表中移出
        moved_success_paths = set(os.path.normpath(p) for p, ok, _ in results if ok)
        if moved_success_paths:
            self.scan_results = [
                item for item in self.scan_results
                if os.path.normpath(item["path"]) not in moved_success_paths
            ]
            self.populate_results_table()
            self.internal_clipboard = [
                p for p in self.internal_clipboard
                if os.path.normpath(p) not in moved_success_paths
            ]
            if not self.internal_clipboard:
                self.btn_batch_paste.setEnabled(False)
                self.btn_batch_paste.setText("📥 粘贴到目标文件夹...")

        if fail_count == 0:
            QMessageBox.information(self, "移动成功", f"已成功将全部 {success_count} 个条目移动到:\n{dest_dir}")
            self.status_label.setText(f"已成功移动 {success_count} 个条目到: {dest_dir}")
        else:
            err_details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, ok, err in results if not ok)
            QMessageBox.warning(
                self, "移动部分完成",
                f"移动结果:\n成功: {success_count} 个\n失败: {fail_count} 个\n\n失败详情:\n{err_details}"
            )
            self.status_label.setText(f"移动完成 (成功 {success_count} / 失败 {fail_count})")

    def execute_copy(self, paths: List[str], dest_dir: str):
        dest_dir = os.path.normpath(dest_dir)
        count = len(paths)
        results = FileOperator.copy_items(paths, dest_dir)
        success_count = sum(1 for _, ok, _ in results if ok)
        fail_count = count - success_count

        if fail_count == 0:
            QMessageBox.information(self, "复制成功", f"已成功将全部 {success_count} 个条目复制到:\n{dest_dir}")
            self.status_label.setText(f"已成功复制 {success_count} 个条目到: {dest_dir}")
        else:
            err_details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, ok, err in results if not ok)
            QMessageBox.warning(
                self, "复制部分完成",
                f"复制结果:\n成功: {success_count} 个\n失败: {fail_count} 个\n\n失败详情:\n{err_details}"
            )
            self.status_label.setText(f"复制完成 (成功 {success_count} / 失败 {fail_count})")

    def action_batch_paste(self):
        paths_to_paste = list(self.internal_clipboard)
        if not paths_to_paste:
            # 尝试从系统剪贴板读取文件
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if mime and mime.hasUrls():
                sys_paths = [u.toLocalFile() for u in mime.urls() if os.path.exists(u.toLocalFile())]
                if sys_paths:
                    paths_to_paste = sys_paths

        if not paths_to_paste:
            QMessageBox.information(self, "提示", "剪贴板中没有待粘贴的文件或文件夹！")
            return

        op_name = "移动" if self.clipboard_operation == "cut" else "复制"
        dest_dir = QFileDialog.getExistingDirectory(self, f"选择{op_name}的目标文件夹 (共 {len(paths_to_paste)} 项)")
        if not dest_dir:
            return

        if self.clipboard_operation == "cut":
            self.execute_move(paths_to_paste, dest_dir)
        else:
            self.execute_copy(paths_to_paste, dest_dir)

    def action_batch_trash(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选或选择要删除的文件！")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要将选中的 {len(paths)} 个文件/文件夹移到 Windows 回收站吗？\n(可在回收站中撤回还原)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        results = FileOperator.trash_items(paths)
        success_paths = set(p for p, ok, _ in results if ok)

        self.scan_results = [item for item in self.scan_results if item["path"] not in success_paths]
        self.populate_results_table()

        success_count = len(success_paths)
        fail_count = len(paths) - success_count
        self.status_label.setText(f"已将 {success_count} 个条目移到回收站" + (f"，{fail_count} 个失败" if fail_count > 0 else ""))

    def action_batch_delete_permanently(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选或选择要删除的文件！")
            return

        reply = QMessageBox.warning(
            self, "永久删除警告",
            f"⚠ 警告：确定要永久硬删除选中的 {len(paths)} 个文件/文件夹吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        results = FileOperator.delete_permanently(paths)
        success_paths = set(p for p, ok, _ in results if ok)

        self.scan_results = [item for item in self.scan_results if item["path"] not in success_paths]
        self.populate_results_table()

        success_count = len(success_paths)
        self.status_label.setText(f"已永久删除 {success_count} 个条目")

    def action_rename_single(self, row: int):
        if row < 0 or row >= len(self.scan_results):
            return
        item = self.scan_results[row]
        old_path = item["path"]
        old_name = item["name"]

        new_name, ok = QInputDialog.getText(self, "重命名", "请输入新的文件名/文件夹名:", text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            success, result_info = FileOperator.rename_item(old_path, new_name.strip())
            if success:
                item["name"] = new_name.strip()
                item["path"] = result_info
                self.populate_results_table()
                self.status_label.setText(f"重命名成功: {new_name.strip()}")
            else:
                QMessageBox.critical(self, "重命名失败", f"错误: {result_info}")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.check_and_sync_external_changes()

    def check_and_sync_external_changes(self):
        """当用户在外部资源管理器中完成粘贴/移动/删除后切回软件时，自动同步清理列表"""
        if not self.scan_results:
            return
        original_count = len(self.scan_results)
        valid_results = [item for item in self.scan_results if os.path.exists(item.get("path", ""))]
        if len(valid_results) != original_count:
            diff = original_count - len(valid_results)
            self.scan_results = valid_results
            self.populate_results_table()
            self.status_label.setText(f"检测到已在外部资源管理器中移动/删除了 {diff} 个条目，列表已自动同步更新")
