import sys
import random
import time
import platform
import os
import json
import re
from urllib.parse import urlparse
from PyQt6.QtCore import QUrl, QFileInfo, Qt, QTimer, QSize, pyqtSignal, QObject, QCoreApplication, QStandardPaths, QRunnable, QThreadPool
from PyQt6.QtWidgets import (QApplication, QMainWindow, QToolBar, QLineEdit,
                             QTabWidget, QProgressBar, QMenu, QFileDialog, QInputDialog,
                             QComboBox, QMessageBox, QSlider, QLabel, QWidget,
                             QCheckBox, QSplitter, QDialog, QGridLayout, QListWidget,
                             QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QListWidgetItem, QPlainTextEdit, QStyle, QSplashScreen)
from PyQt6.QtGui import QAction, QKeySequence, QColor, QPalette, QImage, QPainter, QPixmap, QIcon, QBrush

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineDownloadRequest, QWebEngineProfile, QWebEnginePage
from PyQt6.QtGui import QDesktopServices
# テーマ変更を通知するためのグローバルシグナルクラス
class ThemeSignal(QObject):
    theme_changed = pyqtSignal(str)
theme_signal = ThemeSignal()

class CustomWebEnginePage(QWebEnginePage):
    """
    新しいタブで開くリクエスト（例: target="_blank"）を処理するためのカスタムクラス。
    """
    new_tab_requested = pyqtSignal(QWebEnginePage)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.featurePermissionRequested.connect(self.handle_feature_permission)

    def createWindow(self, _type):
        # 新しいページオブジェクトを作成し、プロファイルは現在のページから継承する
        new_page = CustomWebEnginePage(self.profile(), self)
        # メインウィンドウにこの新しいページをタブとして追加するように要求
        self.new_tab_requested.emit(new_page)
        return new_page

    def handle_feature_permission(self, url, feature):
        """
        ウェブページからの機能利用許可リクエストを処理する。
        特にフルスクリーンリクエストを許可する。
        """
        if feature == QWebEnginePage.Feature.FullScreen:
            self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)

class WorkerSignals(QObject):
    """
    バックグラウンドワーカーからのシグナルを定義するクラス。
    QRunnableはQObjectを継承しないため、シグナルを直接持てない。
    """
    favicon_ready = pyqtSignal(str, QIcon) # url, icon

class FaviconFetcher(QRunnable):
    """
    バックグラウンドでファビコンを取得するためのワーカークラス。
    """
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = WorkerSignals()

    def run(self):
        import requests
        from io import BytesIO
        from PIL import Image
        from PIL.ImageQt import ImageQt

        icon = QIcon()
        try:
            domain = urlparse(self.url).netloc
            favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
            response = requests.get(favicon_url, timeout=2)
            if response.status_code == 200:
                img_data = BytesIO(response.content)
                resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
                img = Image.open(img_data).resize((16, 16), resample_filter)
                icon = QIcon(QPixmap.fromImage(ImageQt(img.convert("RGBA"))))
        except Exception:
            pass # ファビコン取得失敗は無視
        self.signals.favicon_ready.emit(self.url, icon)

class InitialSetupDialog(QDialog):
    """
    初回起動時に表示される設定ダイアログ。
    ホーム画面URLとデフォルト検索エンジンを設定。
    """
    def __init__(self, parent=None, initial_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Project-NOWB 初回設定")
        self.setFixedSize(450, 250) # 初回設定なのでコンパクトに

        self.initial_settings = initial_settings or {}
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # ホームページ設定
        home_group = QGroupBox("ホームページ設定")
        home_layout = QVBoxLayout()
        home_layout.addWidget(QLabel("起動時に表示するURL:"))
        self.home_url_input = QLineEdit(self.initial_settings.get('home_url', 'https://start.popmix-os.net'))
        home_layout.addWidget(self.home_url_input)
        home_group.setLayout(home_layout)
        main_layout.addWidget(home_group)

        # 検索エンジン設定
        search_group = QGroupBox("デフォルト検索エンジン")
        search_layout = QVBoxLayout()
        search_layout.addWidget(QLabel("使用する検索エンジン:"))
        self.search_engine_combo = QComboBox()
        self.search_engine_options = {
            "Google": "https://www.google.com/search?q=",
            "Bing": "https://www.bing.com/search?q=",
            "DuckDuckGo": "https://duckduckgo.com/?q=",
        }
        self.search_engine_combo.addItems(self.search_engine_options.keys())
        # デフォルト選択
        default_engine = self.initial_settings.get('search_engine_name', 'Google')
        if default_engine in self.search_engine_options:
            self.search_engine_combo.setCurrentText(default_engine)
        search_layout.addWidget(self.search_engine_combo)
        search_group.setLayout(search_layout)
        main_layout.addWidget(search_group)

        # OKボタン
        button_layout = QHBoxLayout()
        ok_button = QPushButton("設定を保存して開始")
        ok_button.clicked.connect(self.accept)
        button_layout.addStretch(1)
        button_layout.addWidget(ok_button)
        main_layout.addLayout(button_layout)

    def get_settings(self):
        """ダイアログから設定を取得して返す"""
        selected_engine_name = self.search_engine_combo.currentText()
        return {
            'home_url': self.home_url_input.text(),
            'search_engine_name': selected_engine_name,
            'search_engine_url': self.search_engine_options[selected_engine_name]
        }

class SettingsDialog(QDialog):
    """
    設定画面を実装するための専用ダイアログ。
    """
    def __init__(self, parent=None, settings_data=None, browser_version="未設定"): # browser_version引数を追加
        super().__init__(parent)
        self.setWindowTitle("Project-NOWB 設定")
        self.setFixedSize(600, 650) # 少し大きめのウィンドウサイズ
        self.settings_data = settings_data or {}
        self.browser_version = browser_version # バージョン情報をインスタンス変数に保存
        self.init_ui()

    def init_ui(self):
        main_layout = QGridLayout(self)

        # --- ホームページ設定グループ ---
        home_group = QGroupBox("ホームページ設定")
        home_layout = QVBoxLayout()
        self.home_url_input = QLineEdit(self.settings_data.get('home_url', 'https://start.popmix-os.net'))
        home_layout.addWidget(QLabel("URL:"))
        home_layout.addWidget(self.home_url_input)
        home_group.setLayout(home_layout)
        main_layout.addWidget(home_group, 0, 0)

        # --- 集中ポーション (ブロックサイト) グループ ---
        blocked_group = QGroupBox("集中ポーション (ブロックサイト)")
        blocked_layout = QVBoxLayout()
        
        self.blocked_list = QListWidget()
        self.blocked_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.blocked_list.addItems(self.settings_data.get('blocked_sites', []))
        
        self.add_blocked_button = QPushButton("追加")
        self.add_blocked_button.clicked.connect(self.add_blocked_site)
        self.remove_blocked_button = QPushButton("削除")
        self.remove_blocked_button.clicked.connect(self.remove_blocked_site)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_blocked_button)
        button_layout.addWidget(self.remove_blocked_button)
        
        blocked_layout.addWidget(self.blocked_list)
        blocked_layout.addLayout(button_layout)
        blocked_group.setLayout(blocked_layout)
        main_layout.addWidget(blocked_group, 1, 0)
        
        # --- 検索エンジン設定グループ ---
        search_group = QGroupBox("検索エンジン設定")
        search_layout = QVBoxLayout()
        self.search_engine_combo = QComboBox()
        self.search_engine_combo.addItems(self.settings_data.get('search_engines', {}).keys())
        # 現在のデフォルト検索エンジンを設定
        current_default_engine_name = next((name for name, url in self.settings_data.get('search_engines', {}).items() if url == self.settings_data.get('current_search_engine_url')), "Google")
        self.search_engine_combo.setCurrentText(current_default_engine_name)

        search_layout.addWidget(QLabel("デフォルト検索エンジン:"))
        search_layout.addWidget(self.search_engine_combo)
        search_group.setLayout(search_layout)
        main_layout.addWidget(search_group, 0, 1)

        # --- お気に入りサイト管理グループ ---
        favorites_group = QGroupBox("お気に入りサイト管理")
        favorites_layout = QVBoxLayout()
        
        self.favorites_list = QListWidget()
        for name, url in self.settings_data.get('favorite_sites', {}).items():
            self.favorites_list.addItem(f"{name}: {url}")
            
        self.add_fav_button = QPushButton("追加")
        self.add_fav_button.clicked.connect(self.add_favorite_site)
        self.remove_fav_button = QPushButton("削除")
        self.remove_fav_button.clicked.connect(self.remove_favorite_site)
        
        fav_button_layout = QHBoxLayout()
        fav_button_layout.addWidget(self.add_fav_button)
        fav_button_layout.addWidget(self.remove_fav_button)
        
        favorites_layout.addWidget(self.favorites_list)
        favorites_layout.addLayout(fav_button_layout)
        favorites_group.setLayout(favorites_layout)
        main_layout.addWidget(favorites_group, 1, 1)
        
        # --- UI/カスタマイズ設定グループ ---
        ui_group = QGroupBox("UI/カスタマイズ設定")
        ui_layout = QGridLayout()
        
        # 背景画像設定
        self.bg_image_path_input = QLineEdit(self.settings_data.get('background_image', ''))
        self.bg_image_button = QPushButton("参照...")
        self.bg_image_button.clicked.connect(self.select_background_image)
        ui_layout.addWidget(QLabel("背景画像:"), 0, 0)
        ui_layout.addWidget(self.bg_image_path_input, 0, 1)
        ui_layout.addWidget(self.bg_image_button, 0, 2)

        # カスタムCSS設定
        self.custom_css_input = QPlainTextEdit(self.settings_data.get('custom_css', ''))
        self.custom_css_input.setPlaceholderText("ここにカスタムCSSを入力してください。例: body { background-color: #f0f0f0; }")
        ui_layout.addWidget(QLabel("カスタムCSS:"), 1, 0, 1, 3)
        ui_layout.addWidget(self.custom_css_input, 2, 0, 1, 3)
        
        # セッション復元設定
        self.restore_session_checkbox = QCheckBox("起動時に前回のセッションを復元する")
        self.restore_session_checkbox.setChecked(self.settings_data.get('restore_last_session', True))
        self.restore_session_checkbox.setToolTip("このオプションを有効にすると、次回起動時に最後に開いていたタブが復元されます。")
        ui_layout.addWidget(self.restore_session_checkbox, 3, 0, 1, 3)

        ui_group.setLayout(ui_layout)
        main_layout.addWidget(ui_group, 2, 0, 1, 2)

        # --- OK/キャンセルボタン ---
        button_box = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        button_box.addStretch(1)
        button_box.addWidget(ok_button)
        button_box.addWidget(cancel_button)
        main_layout.addLayout(button_box, 3, 0, 1, 2) # バージョンラベルの1つ上の行に配置

        # --- バージョン情報表示 (最下部に配置) ---
        version_label = QLabel(f"バージョン: **Project-NOWB {self.browser_version}**")
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom) # 右下寄せ
        main_layout.addWidget(version_label, 4, 0, 1, 2) # 最下行、2列にまたがって配置


    def add_blocked_site(self):
        text, ok = QInputDialog.getText(self, "ブロックサイトの追加", "ブロックするURLを入力してください (例: twitter.com):")
        if ok and text:
            self.blocked_list.addItem(text)
    
    def remove_blocked_site(self):
        selected_items = self.blocked_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.blocked_list.takeItem(self.blocked_list.row(item))

    def add_favorite_site(self):
        name, ok_name = QInputDialog.getText(self, "お気に入りの追加", "名前:")
        if not ok_name or not name: return
        url, ok_url = QInputDialog.getText(self, "お気に入りの追加", "URL:")
        if not ok_url or not url: return
        self.favorites_list.addItem(f"{name}: {url}")

    def remove_favorite_site(self):
        selected_items = self.favorites_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.favorites_list.takeItem(self.favorites_list.row(item))

    def select_background_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "背景画像の選択", "", "Image Files (*.png *.jpg *.jpeg *.gif)")
        if file_path:
            self.bg_image_path_input.setText(file_path)

    def get_settings(self):
        """ダイアログから設定を取得して返す"""
        new_blocked_sites = [self.blocked_list.item(i).text() for i in range(self.blocked_list.count())]
        new_favorites = {}
        for i in range(self.favorites_list.count()):
            item_text = self.favorites_list.item(i).text()
            if ': ' in item_text:
                name, url = item_text.split(": ", 1)
                new_favorites[name] = url
            else:
                new_favorites[item_text] = item_text # 名前とURLが同じ場合
        
        selected_engine_name = self.search_engine_combo.currentText()
        # search_engines辞書からURLを取得し、新しい設定として返す
        search_engines_data = self.settings_data.get('search_engines', {
            "Google": "https://www.google.com/search?q=",
            "Bing": "https://www.bing.com/search?q=",
            "DuckDuckGo": "https://duckduckgo.com/?q=",
        })
        selected_engine_url = search_engines_data.get(selected_engine_name, "https://www.google.com/search?q=")

        return {
            'home_url': self.home_url_input.text(),
            'blocked_sites': new_blocked_sites,
            'search_engine_name': selected_engine_name, # 新しく選択された検索エンジンの名前
            'current_search_engine_url': selected_engine_url, # 新しく選択された検索エンジンのURL
            'favorite_sites': new_favorites,
            'background_image': self.bg_image_path_input.text(),
            'custom_css': self.custom_css_input.toPlainText(),
            'restore_last_session': self.restore_session_checkbox.isChecked(),
        }

class DownloadItemWidget(QWidget):
    """個々のダウンロードアイテムを表示・管理するウィジェット。"""
    def __init__(self, download_request, parent=None):
        super().__init__(parent)
        self.download_request = download_request
        self.is_paused = False
        self.last_update_time = time.time()
        self.last_bytes_received = 0

        self.init_ui()
        self.setup_connections()
        self.update_state(self.download_request.state())
        # Manually trigger an initial progress update
        self.update_progress(self.download_request.receivedBytes(), self.download_request.totalBytes())

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # ファイル情報エリア
        info_layout = QVBoxLayout()
        self.file_name_label = QLabel(os.path.basename(self.download_request.downloadFileName()))
        self.file_name_label.setWordWrap(True)
        self.status_label = QLabel("準備中...")
        info_layout.addWidget(self.file_name_label)
        info_layout.addWidget(self.status_label)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(15)
        info_layout.addWidget(self.progress_bar)

        # ボタンエリア
        button_widget = QWidget()
        self.button_layout = QHBoxLayout(button_widget)
        self.button_layout.setContentsMargins(0,0,0,0)
        self.pause_resume_button = QPushButton()
        self.pause_resume_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.pause_resume_button.setToolTip("一時停止")
        self.pause_resume_button.setFixedSize(24, 24)

        self.cancel_button = QPushButton()
        self.cancel_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        self.cancel_button.setToolTip("キャンセル")
        self.cancel_button.setFixedSize(24, 24)

        self.open_folder_button = QPushButton()
        self.open_folder_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.open_folder_button.setToolTip("フォルダを開く")
        self.open_folder_button.setFixedSize(24, 24)
        self.open_folder_button.setVisible(False)

        self.button_layout.addWidget(self.pause_resume_button)
        self.button_layout.addWidget(self.cancel_button)
        self.button_layout.addWidget(self.open_folder_button)
        self.button_layout.addStretch()

        layout.addLayout(info_layout, 4)
        layout.addWidget(button_widget, 1)

    def setup_connections(self):
        # The 'downloadProgress' signal seems to be unavailable in some PyQt6 environments.
        # Using 'receivedBytesChanged' and 'totalBytesChanged' is a more robust alternative.
        self.download_request.receivedBytesChanged.connect(self.on_progress_changed)
        self.download_request.totalBytesChanged.connect(self.on_total_bytes_changed)
        self.download_request.stateChanged.connect(self.update_state)
        self.pause_resume_button.clicked.connect(self.toggle_pause_resume)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.open_folder_button.clicked.connect(self.open_folder)

    def on_progress_changed(self):
        """Handles progress updates when received bytes change."""
        self.update_progress(self.download_request.receivedBytes(), self.download_request.totalBytes())

    def on_total_bytes_changed(self):
        """Handles update when total bytes are determined."""
        self.update_progress(self.download_request.receivedBytes(), self.download_request.totalBytes())

    def format_size(self, size_bytes):
        """
        ファイルサイズを人間が読みやすい形式（KB, MB, GBなど）に変換します。
        numpyへの依存をなくし、軽量化しました。
        """
        if size_bytes <= 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB")
        i = 0
        if size_bytes > 0:
            while size_bytes >= 1024 and i < len(size_name) - 1:
                size_bytes /= 1024.0
                i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

    def update_progress(self, bytes_received, bytes_total):
        current_time = time.time()
        time_diff = current_time - self.last_update_time
        bytes_diff = bytes_received - self.last_bytes_received

        if time_diff > 0.5: # 0.5秒ごとに速度を更新
            speed = bytes_diff / time_diff
            speed_str = f"{self.format_size(speed)}/s"
            self.last_update_time = current_time
            self.last_bytes_received = bytes_received
            self._last_speed_str = speed_str
        else:
            speed_str = getattr(self, '_last_speed_str', '計算中...')

        if bytes_total > 0:
            progress = int((bytes_received / bytes_total) * 100)
            self.progress_bar.setValue(progress)
            status_text = f"{self.format_size(bytes_received)} / {self.format_size(bytes_total)} ({speed_str})"
        else:
            status_text = f"{self.format_size(bytes_received)} ({speed_str})"
        
        self.status_label.setText(status_text)

    def update_state(self, state):
        if state == QWebEngineDownloadRequest.DownloadState.DownloadInProgress:
            self.pause_resume_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            self.pause_resume_button.setToolTip("一時停止")
            self.is_paused = False
        # The integer value for DownloadPaused (4) is used directly to avoid an
        # AttributeError in some PyQt6/QtWebEngine environments where the Python
        # wrapper for this specific enum value seems to be missing.
        elif state == 4: # Corresponds to QWebEngineDownloadRequest.DownloadState.DownloadPaused
            self.pause_resume_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.pause_resume_button.setToolTip("再開")
            self.status_label.setText("一時停止中")
            self.is_paused = True
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self.status_label.setText("ダウンロード完了")
            self.progress_bar.setValue(100)
            self.pause_resume_button.setVisible(False)
            self.cancel_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
            self.cancel_button.setToolTip("ファイルを開く")
            try:
                self.cancel_button.clicked.disconnect()
            except TypeError:
                pass
            self.cancel_button.clicked.connect(self.open_file)
            self.open_folder_button.setVisible(True)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            self.status_label.setText("キャンセルされました")
            self.progress_bar.setFormat("キャンセル")
            self.pause_resume_button.setVisible(False)
            self.cancel_button.setVisible(False)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            self.status_label.setText("中断されました")
            self.progress_bar.setFormat("エラー")
            self.pause_resume_button.setVisible(False)

    def toggle_pause_resume(self):
        if self.is_paused:
            self.download_request.resume()
        else:
            self.download_request.pause()

    def cancel_download(self):
        self.download_request.cancel()

    def open_file(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.download_request.downloadFileName()))

    def open_folder(self):
        dir_path = os.path.dirname(self.download_request.downloadFileName())
        QDesktopServices.openUrl(QUrl.fromLocalFile(dir_path))

class DownloadManagerDialog(QDialog):
    """ダウンロードをリスト表示し、管理するためのダイアログ。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ダウンロード")
        self.setMinimumSize(600, 400)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        self.download_list = QListWidget()
        self.download_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        main_layout.addWidget(self.download_list)

        button_layout = QHBoxLayout()
        clear_button = QPushButton("完了した項目をクリア")
        clear_button.clicked.connect(self.clear_completed)
        button_layout.addStretch()
        button_layout.addWidget(clear_button)
        main_layout.addLayout(button_layout)

    def add_download(self, download_request):
        if hasattr(download_request, '_is_handled') and download_request._is_handled:
            return
        download_request._is_handled = True

        default_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        suggested_path = os.path.join(default_dir, download_request.suggestedFileName())
        
        file_path, _ = QFileDialog.getSaveFileName(self.parent(), "ファイルを保存", suggested_path)
        
        if file_path:
            download_request.setDownloadFileName(file_path)
            
            item_widget = DownloadItemWidget(download_request)
            list_item = QListWidgetItem(self.download_list)
            list_item.setSizeHint(item_widget.sizeHint())
            
            self.download_list.insertItem(0, list_item)
            self.download_list.setItemWidget(list_item, item_widget)
            
            download_request.accept()
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            download_request.cancel()

    def clear_completed(self):
        for i in range(self.download_list.count() - 1, -1, -1):
            list_item = self.download_list.item(i)
            item_widget = self.download_list.itemWidget(list_item)
            state = item_widget.download_request.state()
            if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted or \
               state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled or \
               state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
                self.download_list.takeItem(i)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

class UnloadedTabPlaceholder(QWidget):
    """
    まだロードされていないタブのプレースホルダー。
    クリックされると実際のWebEngineViewに置き換えられる。
    起動時のセッション復元を高速化するために使用する。
    """
    def __init__(self, url, title, parent=None):
        super().__init__(parent)
        self.url = QUrl(url)
        self.title = title if title else url

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # テーマに合わせて色が変わるようにする
        palette = self.palette()
        text_color = palette.color(QPalette.ColorRole.Text)
        
        label = QLabel(f"タブはまだ読み込まれていません\n\n<b>{self.title}</b>\n\n<p style='color: {text_color.name()};'>クリックして読み込みます</p>")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        
        layout.addWidget(label)
        self.setAutoFillBackground(True)


class FullFeaturedBrowser(QMainWindow):
    window_closed = pyqtSignal(object)

    def __init__(self, is_private=False, parent_settings=None):
        super().__init__()
        self.is_private_window = is_private
        self.settings_file = 'project_nowb_settings.json'

        # Download Managerのインスタンス化
        self.download_manager = DownloadManagerDialog(self)
        
        # ここにバージョン情報を定義
        self.browser_version = "V1.0.0-Alpha1.B3"

        # current_search_engine_url を、save_settings() が呼び出される前にデフォルト値で初期化します。
        self.current_search_engine_url = "https://www.google.com/search?q=" 
        
        if self.is_private_window:
            self.setWindowTitle("㊙️ プライベートブラウジング - Project-NOWB")
            self.settings = parent_settings
            self.private_profile = QWebEngineProfile(f"private_{id(self)}", self)
            self.private_profile.downloadRequested.connect(self.handle_download)
        else:
            # デフォルトプロファイルのダウンロードリクエストをハンドル。
            # 複数ウィンドウが開かれても、各インスタンスが自身のハンドラを接続する。
            # ハンドラ側で重複処理を防ぐ。
            QWebEngineProfile.defaultProfile().downloadRequested.connect(self.handle_download)
            self.private_windows = []
            # 初回起動設定の処理
            if not os.path.exists(self.settings_file):
                # 初回起動時に使用するデフォルト設定を settings_data に直接セット
                self.settings_data = {
                    'first_run_completed': False, # まだ完了していない
                    'home_url': 'https://start.popmix-os.net',
                    'search_engines': {
                        "Google": "https://www.google.com/search?q=",
                        "Bing": "https://www.bing.com/search?q=",
                        "DuckDuckGo": "https://duckduckgo.com/?q=",
                    },
                    'current_search_engine_url': self.current_search_engine_url, # 上記で初期化されたデフォルト値を使用
                    'blocked_sites': ['twitter.com', 'facebook.com', 'tiktok.com'],
                    'favorite_sites': {
                        "Popmix-OS Start": "https://start.popmix-os.net",
                        "GitHub": "https://github.com",
                        "YouTube": "http://youtube.com",
                        "Wikipedia": "https://www.wikipedia.org"
                    },
                    'background_image': '',
                    'custom_css': '',
                    'window_size': [1024, 768],
                    'window_pos': [100, 100],
                    'web_panel_url': 'https://www.bing.com/chat',
                    'web_panel_visible': False,
                    'splitter_sizes': [800, 250]
                }
                # セッション管理用の設定も追加
                self.settings_data.update({
                    'restore_last_session': True,
                    'last_session': []
                })

                # save_settings() を呼び出す前に self.settings を self.settings_data に設定
                # これにより save_settings() が self.settings にアクセスできるようになります。
                self.settings = self.settings_data.copy() # settings_data の内容を settings にコピー

                # 初回セットアップダイアログを実行
                self.run_initial_setup() 
                
                # run_initial_setup() 内で設定が更新されるため、再度 settings_data をロードし直します。
                self.settings_data = self.load_settings()
                # ロードされたデータから self.settings と current_search_engine_url を更新します。
                self.settings = self.settings_data.copy()
                self.current_search_engine_url = self.settings_data.get('current_search_engine_url', self.settings['search_engines']["Google"])

            else:
                # ファイルが存在する場合は既存の設定をロード
                self.settings_data = self.load_settings()
                self.settings = self.settings_data.copy() # self.settings が確実に設定されるようにします
                # ロードされた設定から current_search_engine_url を更新します
                self.current_search_engine_url = self.settings_data.get('current_search_engine_url', self.settings['search_engines']["Google"])
        
        self.is_preaching_mode_active = False
        self.blocked_timer = QTimer()
        self.blocked_timer.setSingleShot(True)
        self.blocked_timer.timeout.connect(self.unblock_sites)
        
        self.sleep_timer = QTimer()
        self.sleep_timer.setInterval(300000) # 5分
        self.sleep_timer.timeout.connect(self.activate_sleep_mode)
        self.sleep_timer.start()

        self.tab_groups = {}
        self.tab_group_counter = 0
        self.notes = {}
        
        self.auto_scroll_timer = QTimer()
        self.auto_scroll_timer.setInterval(50) # 50ms間隔
        self.auto_scroll_timer.timeout.connect(self.perform_auto_scroll)
        self.scroll_speed = 10 # 10px per tick
        
        self.is_retro_mode_active = False
        self.is_rain_mode_active = False
        self.rain_timer = QTimer()
        self.rain_timer.setInterval(100) # 雨滴の間隔
        self.threadpool = QThreadPool.globalInstance()
        self.is_html_fullscreen = False # HTML5 APIによるフルスクリーン状態か
        
        # --- メインウィンドウの設定 ---
        if not self.is_private_window:
            self.setWindowTitle("Project-NOWB")
            self.setGeometry(self.settings['window_pos'][0], self.settings['window_pos'][1],
                             self.settings['window_size'][0], self.settings['window_size'][1])
        else:
            self.setGeometry(150, 150, 1024, 768) # プライベートウィンドウのデフォルトサイズ

        # --- メインコンテンツとウェブパネル用のスプリッター ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        # --- タブウィジェットの設定 ---
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_current_tab)
        self.tabs.currentChanged.connect(self.handle_tab_changed) # 起動高速化のため、タブの遅延読み込みを処理するハンドラに接続
        self.splitter.addWidget(self.tabs)

        # --- ウェブパネルの設定 ---
        self.web_panel = QWebEngineView()
        self.web_panel.setObjectName("web_panel")
        self.splitter.addWidget(self.web_panel)

        # 設定からウェブパネルのURLと表示状態を読み込む
        if not self.is_private_window:
            web_panel_url = self.settings.get('web_panel_url', 'https://www.bing.com/chat')
            self.web_panel.setUrl(QUrl(web_panel_url))
            
            is_visible = self.settings.get('web_panel_visible', False)
            self.web_panel.setVisible(is_visible)
            
            # スプリッターのサイズを復元
            splitter_sizes = self.settings.get('splitter_sizes', [800, 250])
            self.splitter.setSizes(splitter_sizes)
        else:
            # プライベートウィンドウではウェブパネルは非表示
            self.web_panel.setVisible(False)
        # --- ナビゲーションツールバー ---
        self.nav_toolbar = QToolBar("Navigation")
        # Windows/LinuxはCtrl、MacはCmd
        mod_key = "Ctrl"
        if platform.system() == "Darwin":
            mod_key = "Cmd"
        
        self.addToolBar(self.nav_toolbar)

        back_btn = QAction("戻る", self)
        back_btn.triggered.connect(lambda: self.tabs.currentWidget().back())
        self.nav_toolbar.addAction(back_btn)

        forward_btn = QAction("進む", self)
        forward_btn.triggered.connect(lambda: self.tabs.currentWidget().forward())
        self.nav_toolbar.addAction(forward_btn)

        reload_btn = QAction("リロード", self)
        reload_btn.triggered.connect(lambda: self.tabs.currentWidget().reload())
        self.nav_toolbar.addAction(reload_btn)

        home_btn = QAction("ホーム", self)
        home_btn.triggered.connect(self.navigate_home)
        self.nav_toolbar.addAction(home_btn)

        # --- 新規タブボタンの追加 (URLバーの左隣) ---
        new_tab_button = QAction("＋", self)  # 「＋」をボタンのテキストとして使用
        new_tab_button.setToolTip("新しいタブを開く")
        new_tab_button.triggered.connect(lambda: self.add_new_tab(QUrl(self.settings['home_url'])))
        self.nav_toolbar.addAction(new_tab_button)

        # --- URLバー ---
        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self.navigate_or_search)
        self.nav_toolbar.addWidget(self.url_bar)

        # --- 検索エンジンセレクター ---
        self.search_engine_combo = QComboBox()
        self.search_engine_combo.addItems(self.settings['search_engines'].keys())
        # 初回起動で設定された検索エンジンを初期選択
        initial_search_engine_name = next((name for name, url in self.settings['search_engines'].items() if url == self.current_search_engine_url), "Google")
        self.search_engine_combo.setCurrentText(initial_search_engine_name)

        self.search_engine_combo.currentTextChanged.connect(self.update_search_engine)
        self.nav_toolbar.addWidget(self.search_engine_combo)
        
        # --- プログレスバー ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(8)
        self.progress_bar.setVisible(False)
        self.nav_toolbar.addWidget(self.progress_bar)

        # --- 音量コントロール ---
        self.nav_toolbar.addSeparator()
        self.nav_toolbar.addWidget(QLabel("音量:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 1) # 0でミュート、1でミュート解除
        self.volume_slider.setValue(1)    # デフォルトはミュート解除
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.nav_toolbar.addWidget(self.volume_slider)
        
        # --- ハンバーガーメニューボタン ---
        custom_icon_path = 'menu_icon.png' # 使用したいアイコンファイルのパス
        if os.path.exists(custom_icon_path):
            menu_icon = QIcon(custom_icon_path)
            print(f"カスタムアイコン '{custom_icon_path}' を使用します。")
        else:
            menu_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMenuButton)
            print(f"警告: アイコンファイル '{custom_icon_path}' が見つかりませんでした。デフォルトのアイコンを使用します。")

        self.hamburger_menu_button = QAction(menu_icon, "メニュー", self)
        self.hamburger_menu_button.setToolTip("メニューを開く")
        self.hamburger_menu = QMenu(self)
        self.hamburger_menu_button.setMenu(self.hamburger_menu)
        self.nav_toolbar.addSeparator()
        self.nav_toolbar.addAction(self.hamburger_menu_button)

        # --- ステータスバー ---
        self.status_bar = self.statusBar()
        self.status_label = QLabel("準備完了。")
        self.status_bar.addWidget(self.status_label)
        
        # --- ハンバーガーメニューコンテンツの構築 ---
        self.setup_hamburger_menu()
        
        # お気に入りツールバー
        self.favorites_toolbar = QToolBar("お気に入り")
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self.favorites_toolbar)
        self.update_favorite_sites_toolbar()
        
        # イースターエッグ
        self.set_easter_eggs()
        
        # --- 最初のタブを追加 ---
        if self.is_private_window:
            self.add_new_tab(QUrl(self.settings['home_url']), 'プライベートタブ')
        elif self.settings.get('restore_last_session', True):
            last_session_urls = self.settings.get('last_session', [])
            if last_session_urls:
                # 起動高速化のため、最初のタブだけを即時ロード
                self.add_new_tab(QUrl(last_session_urls[0]))
                # 残りのタブはプレースホルダーとして追加
                for url in last_session_urls[1:]:
                    self.add_unloaded_tab(url, "読み込み待機中...")
            else:
                # 復元するセッションがない場合はホームページを開く
                self.add_new_tab(QUrl(self.settings['home_url']), 'ホームページ')
        else:
            # セッション復元が無効な場合はホームページを開く
            self.add_new_tab(QUrl(self.settings['home_url']), 'ホームページ')

        if self.is_private_window:
            self.history_menu.setEnabled(False)
            self.bookmarks_menu.setEnabled(False)

        # --- UIの初期化 ---
        self.update_palette_from_system_theme()
        theme_signal.theme_changed.connect(self.update_palette)
        self.update_background_image()
        
    def run_initial_setup(self):
        """
        初回起動時に初期設定ダイアログを表示し、設定を保存する。
        """
        # 初回起動時に渡す初期設定は、現在の settings_data の値を使用
        initial_settings = {
            'home_url': self.settings_data.get('home_url', 'https://start.popmix-os.net'),
            'search_engine_name': next((name for name, url in self.settings_data.get('search_engines', {}).items() if url == self.settings_data.get('current_search_engine_url')), "Google")
        }
        
        dialog = InitialSetupDialog(self, initial_settings)
        if dialog.exec():
            # OKが押された場合
            new_initial_settings = dialog.get_settings()
            
            # 設定データに反映 (settings_data を直接更新)
            self.settings_data['first_run_completed'] = True
            self.settings_data['home_url'] = new_initial_settings['home_url']
            self.settings_data['current_search_engine_url'] = new_initial_settings['search_engine_url']
            self.settings_data['search_engine_name'] = new_initial_settings['search_engine_name'] # 設定名を保存

            # self.settings も settings_data の最新情報で更新
            self.settings = self.settings_data.copy()
            # self.current_search_engine_url も更新
            self.current_search_engine_url = self.settings_data['current_search_engine_url']

            self.save_settings() # 新しい設定を保存
            QMessageBox.information(self, "設定完了", "初回設定が完了しました！ブラウザを開始します。")
        else:
            # キャンセルされた場合、デフォルト設定で続行
            QMessageBox.warning(self, "警告", "設定が行われなかったため、デフォルト設定で開始します。")
            self.settings_data['first_run_completed'] = True # デフォルト設定でも初回起動完了とする

            # self.settings と self.current_search_engine_url も更新
            self.settings = self.settings_data.copy()
            self.current_search_engine_url = self.settings_data['current_search_engine_url']
            
            self.save_settings() # デフォルト設定を保存


    def setup_hamburger_menu(self):
        """
        ハンバーガーメニューにアクションを追加する。
        """
        mod_key = "Ctrl"
        if platform.system() == "Darwin":
            mod_key = "Cmd"
            
        # ファイルメニュー
        file_menu = self.hamburger_menu.addMenu("ファイル")
        new_tab_action = QAction("新しいタブ", self)
        new_tab_action.triggered.connect(lambda: self.add_new_tab())
        file_menu.addAction(new_tab_action)
        
        private_window_action = QAction("プライベートウィンドウを開く", self)
        private_window_action.triggered.connect(self.open_private_window)
        file_menu.addAction(private_window_action)
        
        save_pdf_action = QAction("ページをPDFで保存", self)
        save_pdf_action.triggered.connect(self.save_page_as_pdf)
        file_menu.addAction(save_pdf_action)
        
        screenshot_action = QAction("スクリーンショット", self)
        screenshot_action.setShortcut(QKeySequence(f"{mod_key}+Shift+S"))
        screenshot_action.triggered.connect(self.take_screenshot)
        file_menu.addAction(screenshot_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("終了", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 表示メニュー
        view_menu = self.hamburger_menu.addMenu("表示")
        zoom_in_action = QAction("拡大", self)
        zoom_in_action.setShortcut(QKeySequence(f"{mod_key}++"))
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("縮小", self)
        zoom_out_action.setShortcut(QKeySequence(f"{mod_key}+-"))
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)

        reset_zoom_action = QAction("ズームをリセット", self)
        reset_zoom_action.setShortcut(QKeySequence(f"{mod_key}+0"))
        reset_zoom_action.triggered.connect(self.reset_zoom)
        view_menu.addAction(reset_zoom_action)
        
        view_menu.addSeparator()

        # ウェブパネルの表示/非表示アクション
        self.toggle_web_panel_action = QAction("ウェブパネルを表示", self)
        self.toggle_web_panel_action.setCheckable(True)
        # 初期状態を設定から反映
        if not self.is_private_window:
            is_visible = self.settings.get('web_panel_visible', False)
            self.toggle_web_panel_action.setChecked(is_visible)
            self.toggle_web_panel_action.setText("ウェブパネルを非表示" if is_visible else "ウェブパネルを表示")
        else:
            self.toggle_web_panel_action.setEnabled(False) # プライベートウィンドウでは無効化
        self.toggle_web_panel_action.toggled.connect(self.toggle_web_panel)
        view_menu.addAction(self.toggle_web_panel_action)
        
        view_menu.addSeparator()
        
        fullscreen_action = QAction("全画面表示", self)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        dev_tools_action = QAction("開発者ツール", self)
        dev_tools_action.triggered.connect(self.open_dev_tools)
        view_menu.addAction(dev_tools_action)

        nostalgia_action = QAction("ノスタルジアフィルター", self)
        nostalgia_action.setCheckable(True)
        nostalgia_action.toggled.connect(self.toggle_nostalgia_filter)
        view_menu.addAction(nostalgia_action)

        cyberpunk_action = QAction("サイバーパンクモード", self)
        cyberpunk_action.setCheckable(True)
        cyberpunk_action.toggled.connect(self.toggle_cyberpunk_mode)
        view_menu.addAction(cyberpunk_action)

        retro_pixel_action = QAction("レトロピクセルモード", self)
        retro_pixel_action.setCheckable(True)
        retro_pixel_action.toggled.connect(self.toggle_retro_pixel_mode)
        view_menu.addAction(retro_pixel_action)
        
        auto_scroll_menu = view_menu.addMenu("自動スクロール")
        scroll_start_action = QAction("開始", self)
        scroll_start_action.triggered.connect(self.start_auto_scroll)
        auto_scroll_menu.addAction(scroll_start_action)
        
        scroll_stop_action = QAction("停止", self)
        scroll_stop_action.triggered.connect(self.stop_auto_scroll)
        auto_scroll_menu.addAction(scroll_stop_action)
        
        set_speed_action = QAction("速度設定", self)
        set_speed_action.triggered.connect(self.set_scroll_speed)
        auto_scroll_menu.addAction(set_speed_action)

        # ツールメニュー
        tools_menu = self.hamburger_menu.addMenu("ツール")
        download_action = QAction("ダウンロード", self)
        download_action.triggered.connect(self.show_download_manager)
        tools_menu.addAction(download_action)

        find_in_page_action = QAction("ページ内検索", self)
        find_in_page_action.setShortcut(QKeySequence(f"{mod_key}+F"))
        find_in_page_action.triggered.connect(self.find_in_page)
        tools_menu.addAction(find_in_page_action)

        # ウェブパネルのURL設定アクション
        set_web_panel_url_action = QAction("ウェブパネルのURLを設定", self)
        set_web_panel_url_action.triggered.connect(self.set_web_panel_url)
        if self.is_private_window:
            set_web_panel_url_action.setEnabled(False)
        tools_menu.addAction(set_web_panel_url_action)

        qr_code_action = QAction("QRコード生成", self)
        qr_code_action.triggered.connect(self.generate_qr_code)
        tools_menu.addAction(qr_code_action)
        
        translate_action = QAction("ページを翻訳 (日本語へ)", self)
        translate_action.triggered.connect(self.translate_page)
        tools_menu.addAction(translate_action)

        tab_group_menu = tools_menu.addMenu("タブグループ")
        create_group_action = QAction("新しいグループを作成", self)
        create_group_action.triggered.connect(self.create_tab_group)
        tab_group_menu.addAction(create_group_action)
        self.tab_group_menu = tab_group_menu

        notes_action = QAction("シンプルメモ帳", self)
        notes_action.triggered.connect(self.show_notes_dialog)
        tools_menu.addAction(notes_action)

        ai_chat_action = QAction("AIアシスタントに質問", self)
        ai_chat_action.triggered.connect(self.start_ai_chat)
        tools_menu.addAction(ai_chat_action)
        
        summarize_action = QAction("AIによる要約", self)
        summarize_action.triggered.connect(self.summarize_page)
        tools_menu.addAction(summarize_action)

        analyze_mood_action = QAction("ウェブサイトのムード分析", self)
        analyze_mood_action.triggered.connect(self.analyze_website_mood)
        tools_menu.addAction(analyze_mood_action)
        
        analyze_sentiment_action = QAction("ページ内感情分析", self)
        analyze_sentiment_action.triggered.connect(self.analyze_sentiment)
        tools_menu.addAction(analyze_sentiment_action)
        
        # お気に入り/ブックマーク
        self.bookmarks_menu = self.hamburger_menu.addMenu("ブックマーク")
        self.bookmarks = self.settings['favorite_sites']
        self.update_bookmarks_menu()

        # 履歴
        self.history_menu = self.hamburger_menu.addMenu("履歴")
        self.history = []
        self.update_history_menu()

        # お楽しみメニュー
        fun_menu = self.hamburger_menu.addMenu("お楽しみ")
        preaching_mode_action = QAction("集中ポーション (ON/OFF)", self)
        preaching_mode_action.setCheckable(True)
        preaching_mode_action.triggered.connect(self.toggle_preaching_mode)
        fun_menu.addAction(preaching_mode_action)
        
        timemachine_action = QAction("タイムマシンモード", self)
        timemachine_action.triggered.connect(self.activate_timemachine)
        fun_menu.addAction(timemachine_action)

        time_travel_action = QAction("タイムトラベルモード", self)
        time_travel_action.triggered.connect(self.toggle_time_travel_mode)
        fun_menu.addAction(time_travel_action)

        clean_robot_action = QAction("お掃除ロボット起動", self)
        clean_robot_action.triggered.connect(self.activate_cleaning_robot)
        fun_menu.addAction(clean_robot_action)

        rain_sound_action = QAction("バーチャル雨音モード (ON/OFF)", self)
        rain_sound_action.setCheckable(True)
        rain_sound_action.toggled.connect(self.toggle_rain_sound_mode)
        fun_menu.addAction(rain_sound_action)
        
        mission_mode_action = QAction("ミッションモード", self)
        mission_mode_action.triggered.connect(self.start_mission_mode)
        fun_menu.addAction(mission_mode_action)

        # 設定メニュー
        settings_action = QAction("設定を開く", self)
        settings_action.triggered.connect(self.show_settings_dialog)
        self.hamburger_menu.addSeparator()
        self.hamburger_menu.addAction(settings_action)

    def handle_new_tab_request(self, page):
        """
        CustomWebEnginePageからの新しいタブ作成リクエストを処理する。
        """
        # createWindowを呼び出した側で後からURLが設定されるため、「読み込み中...」というラベルでタブを作成する。
        self.add_new_tab(page_to_set=page, label="読み込み中...")

    def load_settings(self):
        """設定をファイルから読み込む。"""
        if self.is_private_window:
            return {}
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("設定ファイルが破損しています。新しく作成します。", file=sys.stderr)
                return {}
        return {}

    def save_settings(self):
        """設定をファイルに保存する。"""
        if self.is_private_window:
            return
        # ウィンドウが最大化または全画面表示でない場合にのみサイズと位置を保存
        if not self.isMaximized() and not self.isFullScreen():
            self.settings['window_size'] = [self.size().width(), self.size().height()]
            self.settings['window_pos'] = [self.pos().x(), self.pos().y()]
        
        # current_search_engine_url も保存する
        self.settings['current_search_engine_url'] = self.current_search_engine_url
        
        # スプリッターのサイズを保存
        if hasattr(self, 'splitter'):
            self.settings['splitter_sizes'] = self.splitter.sizes()

        # 現在開いているタブのURLを保存
        # self.tabsが初期化されているか確認
        if hasattr(self, 'tabs') and self.settings.get('restore_last_session', True):
            urls = []
            for i in range(self.tabs.count()):
                widget = self.tabs.widget(i)
                if isinstance(widget, QWebEngineView):
                    urls.append(widget.url().toString())
                elif isinstance(widget, UnloadedTabPlaceholder):
                    urls.append(widget.url.toString())
            self.settings['last_session'] = urls

        # self.settings の内容を settings_data にコピーしてから保存
        self.settings_data.update(self.settings)

        with open(self.settings_file, 'w') as f:
            json.dump(self.settings_data, f, indent=4)

    def closeEvent(self, event):
        """ウィンドウが閉じられたときに設定を保存する。"""
        if not self.is_private_window:
            # 管理しているすべてのプライベートウィンドウを閉じる
            # イテレート中にリストを変更する可能性があるため、リストのコピーを作成
            # 終了前にセッションを保存
            self.save_settings()
        else:
            # プライベートウィンドウの場合はセッションをクリア
            for p_win in list(self.private_windows):
                p_win.close()
            self.save_settings()
        
        self.window_closed.emit(self)
        event.accept()

    def changeEvent(self, event):
        """ウィンドウの状態変化を監視し、ESCキーによるフルスクリーン解除を処理する。"""
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            if self.is_html_fullscreen and not (self.windowState() & Qt.WindowState.WindowFullScreen):
                # Escキーでフルスクリーンが解除された場合、UIを復元
                self._exit_html_fullscreen(request=None)

    def _exit_html_fullscreen(self, request):
        """HTML5フルスクリーンモードを終了し、UIを復元する。"""
        if self.is_html_fullscreen:
            self.is_html_fullscreen = False
            self.nav_toolbar.setVisible(True)
            self.tabs.tabBar().setVisible(True)
            self.favorites_toolbar.setVisible(True)
            self.status_bar.setVisible(True)
            self.showNormal()
            if request:
                request.accept()

    def handle_fullscreen_request(self, request, originating_page):
        """ウェブページからのフルスクリーン要求を処理する。"""
        # 現在表示されているタブからの要求でなければ無視
        if originating_page != self.tabs.currentWidget().page():
            request.reject()
            return

        if request.toggleOn():
            # フルスクリーンに移行
            if not self.is_html_fullscreen:
                self.is_html_fullscreen = True
                self.nav_toolbar.setVisible(False)
                self.tabs.tabBar().setVisible(False)
                self.favorites_toolbar.setVisible(False)
                self.status_bar.setVisible(False)
                self.showFullScreen()
            request.accept()
        else:
            # フルスクリーンを終了
            self._exit_html_fullscreen(request)

    def update_palette_from_system_theme(self):
        """
        システムテーマに基づいてパレットを更新する (macOSのみ)。
        """
        if platform.system() == "Darwin":
            palette = QApplication.instance().palette()
            self.setPalette(palette)
            self.update_palette_based_on_color(palette.color(QPalette.ColorRole.Window))
            
    def update_palette_based_on_color(self, color):
        """
        基本色に基づいてライト/ダークモードを判定し、パレットを更新する。
        """
        if color.lightnessF() < 0.5: # 明度が0.5未満ならダークモード
            theme_signal.theme_changed.emit('dark')
        else: # 明度が0.5以上ならライトモード
            theme_signal.theme_changed.emit('light')
            
    def update_palette(self, theme_mode):
        """
        グローバルシグナルから受け取ったテーマモードに基づいてパレットを更新する。
        """
        palette = QApplication.instance().palette()
        if theme_mode == "dark":
            palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(50, 50, 50))
            palette.setColor(QPalette.ColorRole.Text, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.Button, QColor(60, 60, 60))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(50, 50, 50)) # ツールチップ背景
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(240, 240, 240)) # ツールチップ文字
            palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0)) # 明るいテキスト (エラーなど)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215)) # 選択されたアイテムの背景 (例: メニュー項目)
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255)) # 選択されたアイテムの文字
            palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150)) # プレースホルダーテキスト
            
            # QSSを使ってメニューの背景色と文字色を設定
            self.setStyleSheet("""
                QMenu {
                    background-color: #282828; /* 暗いグレーの背景 */
                    color: #F0F0F0; /* 明るいグレーの文字色 */
                    border: 1px solid #3A3A3A; /* ボーダー */
                }
                QMenu::item {
                    padding: 5px 15px 5px 25px; /* アイテムのパディング */
                }
                QMenu::item:selected {
                    background-color: #0078D7; /* 選択時の背景色 */
                    color: #FFFFFF; /* 選択時の文字色 */
                }
                QMenu::separator {
                    height: 1px;
                    background: #505050;
                    margin: 5px 0px;
                }
            """)

        else: # "light"
            # デフォルトのパレットに戻す
            palette = QApplication.instance().style().standardPalette()
            # ライトモードではQSSをリセット
            self.setStyleSheet("") 
        
        QApplication.instance().setPalette(palette)
        self.setPalette(palette)
    
    def update_background_image(self):
        """
        設定された背景画像をブラウザの背景に設定する。
        """
        image_path = self.settings.get('background_image', '')
        if os.path.exists(image_path):
            style = f"""
                QMainWindow {{
                    background-image: url({image_path});
                    background-repeat: no-repeat;
                    background-position: center;
                    background-attachment: fixed;
                    background-size: cover;
                }}
            """
            self.setStyleSheet(style)
        else:
            self.setStyleSheet("") # 背景画像を削除

    def toggle_web_panel(self, visible):
        """ウェブパネルの表示/非表示を切り替える。"""
        if self.is_private_window:
            self.web_panel.setVisible(False)
            self.toggle_web_panel_action.setChecked(False)
            return
            
        self.web_panel.setVisible(visible)
        # メニューのテキストを更新
        self.toggle_web_panel_action.setText("ウェブパネルを非表示" if visible else "ウェブパネルを表示")
        # 設定に保存
        self.settings['web_panel_visible'] = visible
        self.save_settings()

    def set_web_panel_url(self):
        """ウェブパネルに表示するURLを設定する。"""
        if self.is_private_window:
            QMessageBox.information(self, "情報", "プライベートウィンドウではウェブパネルのURLは変更できません。")
            return

        current_url = self.settings.get('web_panel_url', '')
        new_url, ok = QInputDialog.getText(self, "ウェブパネルのURL設定", "URLを入力してください:", text=current_url)
        
        if ok and new_url:
            self.web_panel.setUrl(QUrl(new_url))
            self.settings['web_panel_url'] = new_url
            self.save_settings()
            self.statusBar().showMessage("ウェブパネルのURLを更新しました。", 3000)

    def handle_tab_changed(self, index):
        """タブが変更されたときに呼び出される。プレースホルダーを実際のウェブビューに置き換える。"""
        if index < 0:
            return

        widget = self.tabs.widget(index)
        if isinstance(widget, UnloadedTabPlaceholder):
            url = widget.url
            title = widget.title

            # シグナルを一時的に切断して再帰呼び出しや予期せぬ動作を防ぐ
            self.tabs.currentChanged.disconnect(self.handle_tab_changed)

            # プレースホルダーを削除
            self.tabs.removeTab(index)
            
            # 新しいウェブビューを作成して同じ位置に挿入
            browser, _ = self._create_browser_view(url, title)
            self.tabs.insertTab(index, browser, title)
            self.tabs.setCurrentIndex(index)

            # シグナルを再接続
            self.tabs.currentChanged.connect(self.handle_tab_changed)
        
        # 既存の処理も呼び出す
        self.update_url_bar_on_tab_change(index)
        self.reset_sleep_timer()

    def add_unloaded_tab(self, url_str, label):
        """ロードされていないタブのプレースホルダーを追加する。"""
        # URLから仮のタイトルを生成
        parsed_url = urlparse(url_str)
        title = parsed_url.hostname or label
        
        placeholder = UnloadedTabPlaceholder(url_str, title)
        index = self.tabs.addTab(placeholder, title)
        self.tabs.setTabToolTip(index, url_str)

    def _create_browser_view(self, qurl=None, label="新規", page_to_set=None):
        """
        QWebEngineViewインスタンスを作成し、各種設定とシグナル接続を行って返す。
        add_new_tabとhandle_tab_changedから呼び出される共通ロジック。
        """
        # createWindowからのリクエストを処理
        if page_to_set:
            browser = QWebEngineView()
            browser.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
            browser.setPage(page_to_set)
            # 元のタブがプライベートモードかチェックしてラベルを設定
            if page_to_set.profile().isOffTheRecord():
                label = "㊙️ " + "読み込み中..."
                browser.setToolTip("プライベートモードです。")
            else:
                label = "読み込み中..."
        # 通常のタブ作成リクエスト
        else:
            # 起動時のURLが'about:home'の場合、独自のHomeWebViewインスタンスを作成
            # ここに集中ポーションのチェックを追加
            if qurl and qurl.toString() == "about:home":
                qurl = QUrl(self.settings['home_url'])
                label = "ホーム"

            if qurl is None: qurl = QUrl(self.settings['home_url'])
            
            if self.is_preaching_mode_active:
                current_url_str = qurl.toString()
                for blocked_site in self.settings['blocked_sites']:
                    if blocked_site in current_url_str:
                        QMessageBox.warning(self, "集中ポーションが発動中！", "さぼっちゃダメ！作業に戻りましょう！")
                        return None, None # タブ作成を中止
            
            browser = QWebEngineView()

            if self.is_private_window:
                page = CustomWebEnginePage(self.private_profile, browser)
                browser.setPage(page)
                label = "㊙️ " + label
                browser.setToolTip("プライベートモードです。")
            else:
                page = CustomWebEnginePage(QWebEngineProfile.defaultProfile(), browser)
                browser.setPage(page)

            # ページを設定した後にURLをロードする（HomeWebViewを除く）
            # これにより、起動時にページが白紙になる問題が修正されます。
            browser.setUrl(qurl)

        browser.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        page = browser.page()
        page.new_tab_requested.connect(self.handle_new_tab_request)
        page.fullScreenRequested.connect(lambda req, p=page: self.handle_fullscreen_request(req, p))
        # ウェブページのカスタムCSSを適用
        page.runJavaScript(f"var style = document.createElement('style'); style.innerHTML = `{self.settings['custom_css']}`; document.head.appendChild(style);")

        browser.urlChanged.connect(lambda q: self.update_url_bar(q, browser))
        browser.titleChanged.connect(lambda title, b=browser: self.update_tab_text(title, b))
        browser.loadProgress.connect(self.update_progress_bar)
        browser.urlChanged.connect(self.add_to_history)
        
        if self.is_retro_mode_active:
            self.apply_retro_pixel_filter(browser)
            
        # ステータスバーの更新はURL変更時とロード完了時に行う
        browser.urlChanged.connect(lambda q, b=browser: self.update_status_bar(b))
        browser.loadFinished.connect(lambda ok, b=browser: self.update_status_bar(b))
        return browser, label

    def add_new_tab(self, qurl=None, label="新規", page_to_set=None):
        """新しいタブを作成し、タブウィジェットに追加する。"""
        browser, final_label = self._create_browser_view(qurl, label, page_to_set)
        if browser is None:
            return
        
        i = self.tabs.addTab(browser, final_label)
        self.tabs.setCurrentIndex(i)
        
        self.show_philosophy_on_new_tab()

    def update_tab_text(self, title, browser):
        """Safely update tab text, handling cases where the tab widget might be deleted."""
        try:
            # indexOf returns -1 if the widget is not found
            index = self.tabs.indexOf(browser)
            if index != -1:
                self.tabs.setTabText(index, title)
        except RuntimeError:
            # This can happen during shutdown if self.tabs is already deleted.
            pass


    def update_status_bar(self, browser):
        """
        現在のページ情報をステータスバーに表示する。
        """
        title = browser.title()
        url = browser.url().toString()
        status_text = f"ページ情報: {title} | {url}"
        self.status_label.setText(status_text)

    def show_download_manager(self):
        """ダウンロードマネージャーダイアログを表示する。"""
        self.download_manager.show()
        self.download_manager.raise_()
        self.download_manager.activateWindow()

    def open_private_window(self):
        """新しいプライベートブラウジングウィンドウを開く。"""
        if self.is_private_window:
            return # プライベートウィンドウからさらにプライベートウィンドウは開かない

        private_window = FullFeaturedBrowser(is_private=True, parent_settings=self.settings)
        self.private_windows.append(private_window)
        private_window.window_closed.connect(self.remove_private_window_from_list)
        private_window.show()

    def remove_private_window_from_list(self, window):
        if window in self.private_windows:
            self.private_windows.remove(window)

    def close_current_tab(self, index):
        if self.tabs.count() < 2:
            return
        
        widget_to_close = self.tabs.widget(index)
        if widget_to_close:
            # シグナルを切断して、削除中に発行されるのを防ぎ、クラッシュを回避します。
            # これにより、すでに削除されたウィジェットへのアクセスを防ぎます。
            try:
                widget_to_close.urlChanged.disconnect()
                widget_to_close.titleChanged.disconnect()
                widget_to_close.loadProgress.disconnect()
                widget_to_close.loadFinished.disconnect()
                page = widget_to_close.page()
                # CustomWebEnginePageにのみ存在するシグナルは、インスタンスの型をチェックしてから切断します。
                if isinstance(page, CustomWebEnginePage):
                    page.new_tab_requested.disconnect()
                page.fullScreenRequested.disconnect()
            except TypeError:
                # シグナルに接続がない場合にこの例外が発生しますが、
                # 無視しても問題ありません。
                pass

            # JavaScriptを実行してメディアの再生を停止し、リソースを解放
            widget_to_close.page().runJavaScript("document.querySelectorAll('video, audio').forEach(media => { media.pause(); media.src = ''; });")
            # ウィジェットを後で安全に削除するようにスケジュール
            widget_to_close.deleteLater()

        self.tabs.removeTab(index)
        self.update_tab_groups_menu()
    def reset_sleep_timer(self): self.sleep_timer.start()
    def activate_sleep_mode(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.setUrl(QUrl("about:blank"))
            self.tabs.setTabText(self.tabs.currentIndex(), "ZZZ...")
            self.statusBar().showMessage("スリープモード: 😴 Zzz... 何か操作をすると復帰します。", 10000)
    def navigate_or_search(self):
        text = self.url_bar.text()
        if not text:
            # ランダムサイトジャンプ機能
            self.jump_to_random_site()
            return
            
        if self.is_preaching_mode_active:
            for blocked_site in self.settings['blocked_sites']:
                if blocked_site in text:
                    QMessageBox.warning(self, "集中ポーションが発動中！", "さぼっちゃダメ！作業に戻りましょう！")
                    return
        if text.startswith("about:"):
            # about:home などのカスタムURLを処理
            if text == "about:home":
                self.add_new_tab(QUrl("about:home"))
            else:
                self.tabs.currentWidget().setUrl(QUrl(text))
            return
        if text.startswith("http") or "." in text:
            qurl = QUrl(text)
            if qurl.scheme() == "": qurl.setScheme("http")
            self.tabs.currentWidget().setUrl(qurl)
        else:
            search_url = self.current_search_engine_url + text
            self.tabs.currentWidget().setUrl(QUrl(search_url))
    def update_search_engine(self, engine_name): 
        # self.settings['search_engines'] に対応するURLがあることを確認
        self.current_search_engine_url = self.settings['search_engines'].get(engine_name, self.settings['search_engines']["Google"])
        # settings_dataにも現在の検索エンジンURLを保存
        self.settings_data['current_search_engine_url'] = self.current_search_engine_url


    def navigate_home(self):
        """
        ホームボタンを押した際に設定されているホームURLに遷移する。
        """
        self.tabs.currentWidget().setUrl(QUrl(self.settings['home_url']))

    def update_url_bar(self, q, browser):
        try:
            if self.tabs.currentWidget() == browser: self.url_bar.setText(q.toString())
        except RuntimeError:
            # self.tabs or self.url_bar might be deleted during shutdown.
            pass

    def update_url_bar_on_tab_change(self, index):
        current_browser = self.tabs.currentWidget()
        if current_browser: self.url_bar.setText(current_browser.url().toString())
    def update_progress_bar(self, progress):
        if progress < 100:
            self.progress_bar.setValue(progress)
            self.progress_bar.setVisible(True)
        else: self.progress_bar.setVisible(False)
    def set_volume(self, volume):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            current_browser.page().setAudioMuted(volume == 0)
            if volume > 0: self.statusBar().showMessage("音量: ミュート解除", 2000)
            else: self.statusBar().showMessage("音量: ミュート", 2000)
    def zoom_in(self): self.tabs.currentWidget().setZoomFactor(self.tabs.currentWidget().zoomFactor() + 0.1)
    def zoom_out(self): self.tabs.currentWidget().setZoomFactor(self.tabs.currentWidget().zoomFactor() - 0.1)
    def reset_zoom(self): self.tabs.currentWidget().setZoomFactor(1.0)
    def toggle_fullscreen(self):
        if self.isFullScreen():
            # HTMLフルスクリーンモードであれば、それを終了させる
            if self.is_html_fullscreen:
                self._exit_html_fullscreen(request=None)
            else: # 通常のフルスクリーンモードであれば、それを終了させる
                self.showNormal()
        else: # 通常のフルスクリーンに移行
            self.showFullScreen()
    def open_dev_tools(self): QMessageBox.information(self, "開発者ツール", "この環境では開発者ツールは利用できません。")
    def save_page_as_pdf(self):
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        file_path, _ = QFileDialog.getSaveFileName(self, "PDFとして保存", "", "PDF Files (*.pdf)")
        if file_path:
            if not file_path.endswith(".pdf"): file_path += ".pdf"
            current_browser.page().printToPdf(file_path)
            self.statusBar().showMessage(f"ページをPDFで保存しました: {file_path}", 5000)
    def take_screenshot(self):
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        image = QImage(current_browser.size(), QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        current_browser.render(painter)
        painter.end()
        file_path, _ = QFileDialog.getSaveFileName(self, "スクリーンショットを保存", "", "Images (*.png *.jpg)")
        if file_path:
            image.save(file_path)
            self.statusBar().showMessage(f"スクリーンショットを保存しました: {file_path}", 5000)
    def find_in_page(self):
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        text, ok = QInputDialog.getText(self, "ページ内検索", "検索するキーワードを入力してください:")
        if ok and text:
            current_browser.findText(text)
            self.statusBar().showMessage(f"ページ内で '{text}' を検索中...", 3000)
    def generate_qr_code(self):
        import qrcode
        from PIL.ImageQt import ImageQt

        current_url = self.tabs.currentWidget().url().toString()
        if not current_url:
            QMessageBox.warning(self, "QRコード生成", "無効なURLです。")
            return
        qr_img = qrcode.make(current_url)
        img_qt = ImageQt(qr_img.convert("RGBA"))
        pixmap = QPixmap.fromImage(img_qt)
        msg = QMessageBox(self)
        msg.setWindowTitle("QRコード")
        msg.setText(f"現在のURLのQRコード:\n{current_url}")
        msg.setIconPixmap(pixmap)
        msg.exec()
    def translate_page(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            js_code = """
                if (typeof google !== 'undefined' && google.translate) {
                    google.translate.translateInit(function() {
                        google.translate.translatePage('ja');
                    });
                } else {
                    alert('翻訳機能は利用できません。');
                }
            """
            current_browser.page().runJavaScript(js_code)
            self.statusBar().showMessage("ページの翻訳を試みています...", 3000)
            QMessageBox.information(self, "自動翻訳", "これはシミュレートされた機能です。")
    def create_tab_group(self):
        tabs_to_group = [self.tabs.widget(i).url().toString() for i in range(self.tabs.count())]
        if not tabs_to_group: return
        group_name, ok = QInputDialog.getText(self, "タブグループを作成", "グループ名を入力してください:")
        if ok and group_name:
            group_id = f"group_{self.tab_group_counter}"
            self.tab_groups[group_id] = {'name': group_name, 'tabs': tabs_to_group}
            self.tab_group_counter += 1
            self.statusBar().showMessage(f"タブグループ '{group_name}' が作成されました。", 3000)
            self.update_tab_groups_menu()
    def update_tab_groups_menu(self):
        tab_group_menu = self.findChild(QMenu, "タブグループ")
        if not tab_group_menu: return
        actions_to_remove = [action for action in tab_group_menu.actions() if action.text() not in ["新しいグループを作成", "現在のタブをグループに追加"]]
        for action in actions_to_remove: tab_group_menu.removeAction(action)
        if self.tab_groups:
            tab_group_menu.addSeparator()
            for group_id, group_info in self.tab_groups.items():
                group_name = group_info['name']
                group_action = QAction(f"グループを開く: {group_name}", self)
                group_action.triggered.connect(lambda checked, gid=group_id: self.open_tab_group(gid))
                tab_group_menu.addAction(group_action)
    def open_tab_group(self, group_id):
        if group_id in self.tab_groups:
            for url in self.tab_groups[group_id]['tabs']:
                self.add_new_tab(QUrl(url))
            self.statusBar().showMessage(f"タブグループ '{self.tab_groups[group_id]['name']}' が開かれました。", 3000)

    def show_notes_dialog(self):
        current_tab_index = self.tabs.currentIndex()
        if current_tab_index not in self.notes:
            self.notes[current_tab_index] = ""
        notes_dialog = QDialog(self)
        notes_dialog.setWindowTitle("シンプルメモ帳"); notes_dialog.setFixedSize(400, 300)
        layout = QVBoxLayout(notes_dialog); text_edit = QPlainTextEdit()
        text_edit.setPlaceholderText("ここにメモを入力してください..."); text_edit.setPlainText(self.notes[current_tab_index])
        layout.addWidget(text_edit); button_layout = QHBoxLayout()
        ok_button = QPushButton("OK"); cancel_button = QPushButton("キャンセル")
        button_layout.addStretch(1); button_layout.addWidget(ok_button); button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout); ok_button.clicked.connect(notes_dialog.accept); cancel_button.clicked.connect(notes_dialog.reject)
        if notes_dialog.exec(): self.notes[current_tab_index] = text_edit.toPlainText(); self.statusBar().showMessage("メモを保存しました。", 2000)

    def show_settings_dialog(self):
        """設定ダイアログを開き、設定を更新する。"""
        # 現在の設定とバージョン情報を渡す
        settings_dialog = SettingsDialog(self, self.settings_data, browser_version=self.browser_version) 
        if settings_dialog.exec():
            # OKが押された場合に設定を適用
            new_settings = settings_dialog.get_settings()
            
            # self.settings_data を更新
            self.settings_data.update(new_settings)
            
            # self.settings も self.settings_data から更新
            self.settings = self.settings_data.copy()

            # 検索エンジンを更新
            self.current_search_engine_url = self.settings_data['current_search_engine_url']
            self.search_engine_combo.setCurrentText(self.settings_data['search_engine_name']) # コンボボックスの表示も更新

            # お気に入りツールバーとブックマークメニューを更新
            self.bookmarks = self.settings['favorite_sites']
            self.update_bookmarks_menu()
            self.update_favorite_sites_toolbar()
            
            # 背景画像を更新
            self.update_background_image()
            
            self.save_settings() # 変更をファイルに保存
            self.statusBar().showMessage("設定が保存されました！", 3000)

    def update_bookmarks_menu(self):
        self.bookmarks_menu.clear()
        if self.is_private_window:
            return
        for name, url in self.bookmarks.items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, u=url, n=name: self.add_new_tab(QUrl(u), n))
            self.bookmarks_menu.addAction(action)
        self.bookmarks_menu.addSeparator()
        add_bookmark_action = QAction("現在のページをブックマーク", self)
        add_bookmark_action.triggered.connect(self.add_current_page_as_bookmark)
        self.bookmarks_menu.addAction(add_bookmark_action)
    def add_current_page_as_bookmark(self):
        if self.is_private_window:
            return
        current_browser = self.tabs.currentWidget()
        url = current_browser.url().toString()
        title = current_browser.title() if current_browser.title() else url
        new_title, ok = QInputDialog.getText(self, 'ブックマークを追加', 'ブックマーク名:', text=title)
        if ok and new_title:
            self.bookmarks[new_title] = url
            # settings_data にも反映
            self.settings_data['favorite_sites'][new_title] = url
            self.update_bookmarks_menu()
            self.update_favorite_sites_toolbar() # ツールバーも更新
            self.save_settings() # 保存
            print(f"ブックマークに追加: {new_title} ({url})")
            
    def set_favicon_on_action(self, url, icon):
        """ファビコン取得後にツールバーのアクションにアイコンを設定するスロット。"""
        if not icon.isNull():
            for action in self.favorites_toolbar.actions():
                if action.property("url") == url:
                    action.setIcon(icon)
                    break

    def update_favorite_sites_toolbar(self):
        self.favorites_toolbar.clear()
        for name, url in self.settings['favorite_sites'].items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, u=url, n=name: self.add_new_tab(QUrl(u), n))
            action.setProperty("url", url) # アクションにURLを紐付け

            # プレースホルダーとして空のアイコンを設定
            action.setIcon(QIcon())
            self.favorites_toolbar.addAction(action)

            # バックグラウンドでファビコンを取得
            fetcher = FaviconFetcher(url)
            fetcher.signals.favicon_ready.connect(self.set_favicon_on_action)
            self.threadpool.start(fetcher)

    def handle_download(self, download_request):
        self.download_manager.add_download(download_request)

    def add_to_history(self, qurl):
        if self.is_private_window:
            return
        try:
            url_str = qurl.toString()
            if self.history and self.history[-1][1] == url_str: return
            title = self.tabs.currentWidget().title() if self.tabs.currentWidget() else url_str
            self.history.append((title, url_str))
            if len(self.history) > 100: self.history.pop(0)
            self.update_history_menu()
        except RuntimeError:
            # self.tabs might be deleted during shutdown.
            pass

    def update_history_menu(self):
        if self.is_private_window:
            return
        self.history_menu.clear()
        for title, url in reversed(self.history):
            action = QAction(title, self)
            action.triggered.connect(lambda checked, u=url, t=title: self.add_new_tab(QUrl(u), t))
            self.history_menu.addAction(action)
        self.history_menu.addSeparator()
        clear_history_action = QAction("履歴をクリア", self)
        clear_history_action.triggered.connect(self.clear_history)
        self.history_menu.addAction(clear_history_action)
    def clear_history(self):
        if self.is_private_window:
            return
        self.history = []
        self.update_history_menu()
        print("履歴をクリアしました。")
    def toggle_preaching_mode(self, checked):
        self.is_preaching_mode_active = checked
        if checked:
            duration, ok = QInputDialog.getInt(self, "集中ポーション", "何分間集中しますか？", value=30, min=1, max=120)
            if ok:
                self.blocked_timer.start(duration * 60 * 1000)
                QMessageBox.information(self, "集中ポーション", f"{duration}分間、集中モードがONになりました。さぼっちゃダメですよ！")
            else: self.is_preaching_mode_active = False
        else:
            self.blocked_timer.stop()
            QMessageBox.information(self, "集中ポーション", "ポーションの効果が切れました。さぼっても大丈夫です...")
    def unblock_sites(self):
        self.is_preaching_mode_active = False
        self.statusBar().showMessage("集中ポーションの効果が切れました！", 5000)
    def activate_timemachine(self):
        current_url = self.tabs.currentWidget().url().toString()
        archive_url = f"https://web.archive.org/web/*/{current_url}"
        self.add_new_tab(QUrl(archive_url), "タイムマシン")
    def show_philosophy_on_new_tab(self):
        philosophies = [
            "インターネットの向こう側には何があるのだろうか？", "今見ている画面は誰かの夢なのだろうか？",
            "「検索」は私たちを賢くするのか、それとも依存させるだけなのか？",
            "クリックする前と後で、自分は本当に同じなのだろうか？",
            "もしAIに意識があったら、どんなウェブサイトを夢見るだろうか？",
            "エラーメッセージは宇宙からの手紙なのだろうか？",
        ]
        self.statusBar().showMessage(f"今日の哲学: '{random.choice(philosophies)}'", 7000)
    def toggle_time_travel_mode(self):
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        mode, ok = QInputDialog.getItem(self, "タイムトラベルモード", "どの時代にタイムトラベルしますか？", ["過去 (CSSなし)", "未来 (派手なCSS)", "現在 (リセット)"], 0, False)
        if ok and mode:
            if mode == "過去 (CSSなし)":
                current_browser.page().runJavaScript("document.querySelectorAll('link[rel=stylesheet],style').forEach(el => el.remove());")
                self.statusBar().showMessage("タイムトラベル成功！過去のウェブサイトに到着しました。", 5000)
            elif mode == "未来 (派手なCSS)":
                css = """
                    body { transition: background-color 2s ease-in-out; }
                    * { border: 2px solid neonpink !important; box-shadow: 0 0 10px 5px cyan !important; animation: flicker 0.5s infinite alternate; }
                    @keyframes flicker { from { opacity: 1; } to { opacity: 0.8; } }
                """
                current_browser.page().runJavaScript(f"var style = document.createElement('style'); style.id = 'cyberpunk-style'; style.innerHTML = `{css}`; document.head.appendChild(style);")
                self.statusBar().showMessage("タイムトラベル成功！未来のウェブサイトに到着しました。", 5000)
            else:
                current_browser.reload(); self.statusBar().showMessage("現在に戻りました。", 3000)
    
    def start_ai_chat(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            question, ok = QInputDialog.getText(self, "AIアシスタント", "質問を入力してください:")
            if ok and question:
                self.statusBar().showMessage("AIアシスタントが考えています...", 3000)
                # ここにAI API呼び出しのロジックを実装
                # 例: APIから応答を取得
                response_from_ai = self.get_ai_response(question)
                QMessageBox.information(self, "AIアシスタントからの返信", response_from_ai)

    def get_ai_response(self, question):
        # AI応答をシミュレート
        if "猫" in question or "ねこ" in question: return "ニャー。猫は液体のようですからね。"
        elif "天気" in question: return "今日の天気は散歩にぴったりです。お出かけしますか？"
        elif "人生の意味" in question: return "その質問は量子力学のようなものです。答えはあなたの中にあります。"
        else: return "その質問は私の知識を超えています。もっと哲学的なことを聞いてみてください。"
    
    def toggle_nostalgia_filter(self, checked):
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        if checked:
            filter_css = """
                body::before {content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:repeating-linear-gradient(0deg, transparent, rgba(0,0,0,0.1) 1px, transparent 2px);z-index:9999;pointer-events:none;opacity:0.5;}
                body::after {content:'';position:fixed;top:0;left:0;width:100%;height:100%;box-shadow:inset 0 0 100px 50px rgba(0,0,0,0.5);z-index:9999;pointer-events:none;}
            """
            current_browser.page().runJavaScript(f"var style = document.createElement('style'); style.id = 'nostalgia-filter'; style.innerHTML = `{filter_css}`; document.head.appendChild(style);")
            self.statusBar().showMessage("ノスタルジアフィルターON！古き良き思い出に浸りましょう。", 3000)
        else:
            current_browser.page().runJavaScript("var style = document.getElementById('nostalgia-filter'); if(style) style.remove();")
            self.statusBar().showMessage("ノスタルジアフィルターOFF。", 3000)
    def toggle_cyberpunk_mode(self, checked):
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        if checked:
            cyberpunk_css = """
                body { background-color: black !important; color: limegreen !important; filter: drop-shadow(0 0 1px limegreen); }
                a { color: cyan !important; }
                * { border-color: limegreen !important; }
                input, textarea, select, button { background-color: #1a1a1a !important; color: limegreen !important; border: 1px solid cyan !important; }
            """
            current_browser.page().runJavaScript(f"var style = document.createElement('style'); style.id = 'cyberpunk-style'; style.innerHTML = `{cyberpunk_css}`; document.head.appendChild(style);")
            self.statusBar().showMessage("サイバーパンクモードON！ネオンの光が輝く世界へようこそ。", 3000)
        else:
            current_browser.page().runJavaScript("var style = document.getElementById('cyberpunk-style'); if(style) style.remove();")
            self.statusBar().showMessage("サイバーパンクモードOFF。", 3000)
    def set_easter_eggs(self):
        mod_key = "Ctrl" if platform.system() != "Darwin" else "Cmd"
        theme_action = QAction("テーマを変更", self); theme_action.setShortcut(QKeySequence(f"{mod_key}+Alt+T")); theme_action.triggered.connect(self.change_theme); self.addAction(theme_action)
        proverb_action = QAction("隠された哲学", self); proverb_action.setShortcut(QKeySequence(f"{mod_key}+Shift+S")); proverb_action.triggered.connect(self.show_proverb); self.addAction(proverb_action)
    def change_theme(self):
        palette = self.palette(); random_color = QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        palette.setColor(QPalette.ColorRole.Window, random_color); palette.setColor(QPalette.ColorRole.Base, random_color.lighter(120)); palette.setColor(QPalette.ColorRole.AlternateBase, random_color.darker(120)); palette.setColor(QPalette.ColorRole.Text, random_color.lighter(200)); palette.setColor(QPalette.ColorRole.Button, random_color.darker(120)); palette.setColor(QPalette.ColorRole.ButtonText, random_color.lighter(200))
        self.setPalette(palette); QApplication.setPalette(palette)
        self.statusBar().showMessage(f"テーマの色がランダムに変更されました！", 3000)
    def show_proverb(self):
        proverbs = ["人生は短い、しかしタブは無限である。", "眠いなら眠れ。それも生産性の一部だ。", "完璧なコードなどない。動けばそれで十分だ。", "最大のバグは睡眠不足だ。", "デバッグは探偵の仕事だ。手がかりはエラーメッセージにある。",]
        QMessageBox.information(self, "隠された哲学", random.choice(proverbs))
    
    def start_auto_scroll(self):
        """自動スクロールを開始する。"""
        if not self.auto_scroll_timer.isActive():
            self.auto_scroll_timer.start()
            self.statusBar().showMessage(f"自動スクロールを開始しました。速度: {self.scroll_speed}px/tick", 3000)

    def stop_auto_scroll(self):
        """自動スクロールを停止する。"""
        if self.auto_scroll_timer.isActive():
            self.auto_scroll_timer.stop()
            self.statusBar().showMessage("自動スクロールを停止しました。", 3000)

    def set_scroll_speed(self):
        """スクロール速度を設定するダイアログを表示する。"""
        speed, ok = QInputDialog.getInt(self, "スクロール速度の設定", "スクロール速度を入力してください (1-50):",
                                        value=self.scroll_speed, min=1, max=50)
        if ok:
            self.scroll_speed = speed
            self.statusBar().showMessage(f"スクロール速度を {self.scroll_speed}px/tick に設定しました。", 3000)

    def perform_auto_scroll(self):
        """ウェブページを自動的にスクロールする。"""
        current_browser = self.tabs.currentWidget()
        if current_browser:
            # JavaScriptを使ってスクロールを実行
            current_browser.page().runJavaScript(f"window.scrollBy(0, {self.scroll_speed});")

    # --- 新機能の実装 ---
    def summarize_page(self):
        """AIページ要約機能"""
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        
        # JavaScriptを実行してページ内のテキストコンテンツを取得
        js_code = "document.body.innerText;"
        current_browser.page().runJavaScript(js_code, self.handle_summary_result)

    def handle_summary_result(self, text):
        if not text:
            QMessageBox.warning(self, "AIによる要約", "要約するテキストが見つかりませんでした。")
            return

        # AI要約ロジックをシミュレート
        sentences = re.split(r'[。.]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 最初の5文を要約として抽出 (単純な要約)
        summary = "。 ".join(sentences[:5]) + "。"
        
        QMessageBox.information(self, "AIによる要約", summary)
        self.statusBar().showMessage("ページの要約が完了しました！", 5000)

    def analyze_website_mood(self):
        """ウェブサイトのムード分析機能"""
        current_browser = self.tabs.currentWidget()
        if not current_browser: return

        # JavaScriptを実行してCSSとキーワードを抽出
        js_code = r"""
            var colors = {};
            var styleSheets = document.styleSheets;
            for(var i = 0; i < styleSheets.length; i++){
                try {
                    var rules = styleSheets[i].cssRules;
                    for(var j = 0; j < rules.length; j++){
                        if(rules[j].style){
                            var cssText = rules[j].style.cssText;
                            var matches = cssText.matchAll(/rgb\((\d+),\s*(\d+),\s*(\d+)\)|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}/g);
                            for(var match of matches) {
                                var color = match[0];
                                colors[color] = (colors[color] || 0) + 1;
                            }
                        }
                    }
                } catch(e) { /* クロスオリジンのスタイルシートエラーは無視 */ }
            }
            var text = document.body.innerText;
            var keywords = text.split(/\s+/);
            JSON.stringify({ colors: colors, keywords: keywords.slice(0, 500) });
        """
        current_browser.page().runJavaScript(js_code, self.handle_mood_analysis_result)

    def handle_mood_analysis_result(self, json_data):
        try:
            data = json.loads(json_data)
            colors = data.get('colors', {})
            keywords = data.get('keywords', [])

            # --- 単純なムード判定ロジック ---
            mood_scores = {
                'エネルギッシュ': 0,
                '穏やか': 0,
                'サイバーパンク': 0,
                '真面目': 0
            }

            # 1. 色分析
            for color_str, count in colors.items():
                if '#' in color_str:
                    r, g, b = int(color_str[1:3], 16), int(color_str[3:5], 16), int(color_str[5:7], 16)
                else: # rgb(r, g, b)形式
                    r, g, b = map(int, re.findall(r'\d+', color_str))

                if r > 150 and g < 100 and b < 100: mood_scores['エネルギッシュ'] += count # 赤っぽい色
                if g > 150 and b > 150: mood_scores['穏やか'] += count # 青緑色
                if g > 200 and b < 50 and r < 50: mood_scores['サイバーパンク'] += count # ネオングリーン
                if r < 100 and g < 100 and b < 100: mood_scores['真面目'] += count # 黒っぽい色

            # 2. キーワード分析 (非常に単純な例)
            for keyword in keywords:
                if keyword in ['fun', 'great', 'exciting', 'exciting']: mood_scores['エネルギッシュ'] += 1
                if keyword in ['calm', 'quiet', 'relaxing', 'peaceful']: mood_scores['穏やか'] += 1
                if keyword in ['technology', 'future', 'data', 'cyber']: mood_scores['サイバーパンク'] += 1
                if keyword in ['paper', 'research', 'analysis', 'information']: mood_scores['真面目'] += 1

            total_score = sum(mood_scores.values())
            if total_score == 0:
                result_mood = "判定不能なムード..."
            else:
                result_mood = max(mood_scores, key=mood_scores.get)

            QMessageBox.information(self, "ウェブサイトのムード分析", f"このサイトのムードは**'{result_mood}'**です！\n\n(分析結果は主観的なものです。)")
            self.statusBar().showMessage(f"サイトのムードを分析しました: {result_mood}", 5000)

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"ムード分析に失敗しました: {e}")

    def toggle_retro_pixel_mode(self, checked):
        """ウェブページ上の画像をピクセル化する。"""
        self.is_retro_mode_active = checked
        if checked:
            # JavaScriptで全ての画像をピクセル化
            js_code = """
                document.querySelectorAll('img').forEach(img => {
                    var canvas = document.createElement('canvas');
                    var context = canvas.getContext('2d');
                    var width = img.naturalWidth;
                    var height = img.naturalHeight;
                    canvas.width = width;
                    canvas.height = height;

                    context.webkitImageSmoothingEnabled = false;
                    context.mozImageSmoothingEnabled = false;
                    context.imageSmoothingEnabled = false;

                    // 低解像度で描画してから拡大
                    var pixelSize = 16;
                    context.drawImage(img, 0, 0, width / pixelSize, height / pixelSize);
                    context.drawImage(canvas, 0, 0, width / pixelSize, height / pixelSize, 0, 0, width, height);

                    img.src = canvas.toDataURL();
                });
            """
            current_browser = self.tabs.currentWidget()
            if current_browser:
                current_browser.page().runJavaScript(js_code)
                self.statusBar().showMessage("レトロピクセルモードON！ピクセルアートの世界へようこそ。", 3000)
        else:
            # タブをリロードして元に戻す
            self.tabs.currentWidget().reload()
            self.statusBar().showMessage("レトロピクセルモードOFF。", 3000)
    
    def activate_cleaning_robot(self):
        """画面にお掃除ロボットを表示する。"""
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        
        # JavaScriptでアニメーションと要素削除をシミュレート
        js_code = """
            // 小さなロボット要素を作成
            var robot = document.createElement('div');
            robot.style.position = 'fixed';
            robot.style.width = '50px';
            robot.style.height = '50px';
            robot.style.background = 'url("https://www.flaticon.com/svg/v2/search/p/13444/13444652.svg") no-repeat center center / contain';
            robot.style.bottom = '10px';
            robot.style.right = '10px';
            robot.style.zIndex = '99999';
            robot.style.transition = 'transform 1s ease-in-out';
            document.body.appendChild(robot);

            // ロボットをアニメーションさせる
            var positions = [
                {x: 100, y: -200}, {x: -300, y: -50}, {x: 50, y: 150},
                {x: -150, y: -150}, {x: 200, y: 10}, {x: -200, y: 200}
            ];
            var i = 0;
            var interval = setInterval(function() {
                if (i >= positions.length) {
                    clearInterval(interval);
                    robot.remove(); // アニメーション後にロボットを削除
                    return;
                }
                var pos = positions[i];
                robot.style.transform = `translate(${pos.x}px, ${pos.y}px) rotate(${i * 60}deg)`;
                i++;
            }, 1000);

            // クリーニングをシミュレート (ランダムなdivをいくつか削除)
            var all_divs = document.querySelectorAll('div');
            for(var i = 0; i < 5; i++){
                var random_div = all_divs[Math.floor(Math.random() * all_divs.length)];
                if(random_div && random_div.parentElement){
                    random_div.style.opacity = 0;
                    random_div.style.transition = 'opacity 0.5s ease-out';
                    setTimeout(() => random_div.remove(), 500);
                }
            }
        """
        current_browser.page().runJavaScript(js_code)
        self.statusBar().showMessage("お掃除ロボットが起動しました！ブラウザをきれいにしています。", 5000)

    def jump_to_random_site(self):
        """
        履歴からランダムなサイトにジャンプする。
        """
        if self.history:
            random_entry = random.choice(self.history)
            url = random_entry[1]
            title = random_entry[0]
            self.add_new_tab(QUrl(url), title)
            self.statusBar().showMessage(f"ランダムサイトジャンプ！'{title}'にアクセスします。", 5000)
        else:
            self.statusBar().showMessage("ジャンプできる履歴がありません。", 3000)

    def analyze_sentiment(self):
        """
        ページの感情を分析する (シンプル版)。
        """
        current_browser = self.tabs.currentWidget()
        if not current_browser: return
        
        js_code = "document.body.innerText;"
        current_browser.page().runJavaScript(js_code, self.handle_sentiment_result)

    def handle_sentiment_result(self, text):
        if not text:
            QMessageBox.warning(self, "感情分析", "分析するテキストが見つかりませんでした。")
            return

        # 感情キーワードの単純なリスト
        positive_words = ['great', 'best', 'fun', 'happy', 'success', 'beautiful', 'hope', '素晴らしい', '最高', '楽しい', '幸せ', '成功', '美しい', '希望']
        negative_words = ['terrible', 'worst', 'sad', 'painful', 'anger', 'failure', 'ugly', 'despair', 'ひどい', '最悪', '悲しい', 'つらい', '怒り', '失敗', '醜い', '絶望']

        positive_score = sum(1 for word in positive_words if word in text.lower())
        negative_score = sum(1 for word in negative_words if word in text.lower())
        
        total_score = positive_score + negative_score
        
        if total_score == 0:
            sentiment_result = "中立"
        elif positive_score > negative_score:
            sentiment_result = "ポジティブ"
        elif negative_score > positive_score:
            sentiment_result = "ネガティブ"
        else:
            sentiment_result = "中立" # 同点の場合

        sentiment_info = f"""
        **感情分析結果:**
        - **全体:** {sentiment_result}
        - **ポジティブスコア:** {positive_score}
        - **ネガティブスコア:** {negative_score}

        この結果は単純なキーワード分析に基づいています。
        """
        QMessageBox.information(self, "ページ内感情分析", sentiment_info)
        self.statusBar().showMessage(f"ページの感情を分析しました: {sentiment_result}", 5000)

    def toggle_rain_sound_mode(self, checked):
        """
        バーチャル雨音モードをON/OFFする。
        """
        if checked:
            self.is_rain_mode_active = True
            self.statusBar().showMessage("バーチャル雨音モードON。作業に集中してください。", 3000)
        else:
            self.is_rain_mode_active = False
            self.statusBar().showMessage("バーチャル雨音モードOFF。", 3000)
            
    def start_mission_mode(self):
        """
        ランダムなミッションを提示する。
        """
        missions = [
            "「猫」と検索して、一番かわいい猫を見つけよう！",
            "YouTubeにアクセスせずに30分間リサーチをしてみよう。",
            "今日の年月日を3つの異なるウェブサイトで見つけよう！",
            "URLバーに「about:blank」と入力して、心の空白と向き合ってみよう。",
            "開いているタブを全部閉じよう。そして、新しい世界に飛び出そう。",
            "Wikipediaのランダム記事に5回ジャンプして、知識の冒険を楽しもう。",
            "集中ポーションを飲んで、60分間SNSを開かないように頑張ろう！",
            "お気に入りのウェブサイトのファビコンのスクリーンショットを撮って保存しよう。",
        ]
        
        random_mission = random.choice(missions)
        QMessageBox.information(self, "ミッション開始！", f"あなたのミッションは…**'{random_mission}'**\n\nミッションの成功を祈ります！")
        self.statusBar().showMessage("新しいミッションが割り当てられました。", 5000)

def get_system_theme_mode():
    """
    システムのテーマ設定 (ダーク/ライト) を取得する (macOS, Windows, Linux)。
    """
    if platform.system() == "Darwin":
        try:
            import subprocess
            result = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'], capture_output=True, text=True)
            return 'dark' if result.returncode == 0 and 'Dark' in result.stdout else 'light'
        except Exception:
            return 'light'
    elif platform.system() == "Windows":
        try:
            import winreg
            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            value, _ = winreg.QueryValueEx(reg_key, 'AppsUseLightTheme')
            return 'light' if value == 1 else 'dark'
        except Exception:
            return 'light'
    elif platform.system() == "Linux":
        try:
            settings_path = os.path.expanduser('~/.config/gtk-3.0/settings.ini')
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    for line in f:
                        if line.strip().startswith('gtk-application-prefer-dark-theme'):
                            return 'dark' if 'true' in line.lower() else 'light'
        except Exception:
            pass
        return 'light'
    return 'light' # その他のOSまたは失敗

# --- アプリケーションの実行 ---
if __name__ == '__main__':
    # QApplicationインスタンスは一度だけ作成する必要がある。
    app = QApplication(sys.argv)

    # --- スプラッシュスクリーンの設定 ---
    pixmap = QPixmap('browser_logo.png')
    if pixmap.isNull():
        # ロゴ画像が見つからない場合のフォールバック
        pixmap = QPixmap(400, 250)
        pixmap.fill(QColor("#2d2d2d"))
        painter = QPainter(pixmap)
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Project-NOWB")
        painter.end()

    splash = QSplashScreen(pixmap)
    splash.showMessage("Project-NOWB を起動しています...",
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
                       Qt.GlobalColor.white)
    splash.show()
    app.processEvents() # スプラッシュスクリーンが確実に表示されるようにする

    # --- アプリケーションアイコンの設定 ---
    app_icon = QIcon('browser_logo.png')
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    else:
        print("警告: アプリケーションアイコン 'browser_logo.png' が見つかりませんでした。", file=sys.stderr)

    # --- テーマ設定 ---
    initial_theme = get_system_theme_mode()
    if initial_theme == 'dark':
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(50, 50, 50))
        palette.setColor(QPalette.ColorRole.Text, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.Button, QColor(60, 60, 60))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(240, 240, 240))
        app.setPalette(palette)
        app.setStyleSheet("""
            QMenu {{ background-color: #282828; color: #F0F0F0; border: 1px solid #3A3A3A; }}
            QMenu::item {{ padding: 5px 15px 5px 25px; }}
            QMenu::item:selected {{ background-color: #0078D7; color: #FFFFFF; }}
            QMenu::separator {{ height: 1px; background: #505050; margin: 5px 0px; }}
        """)

    # --- メインウィンドウの作成と表示 ---
    window = FullFeaturedBrowser() # 時間のかかる初期化処理
    window.show()
    splash.finish(window) # メインウィンドウが表示されたらスプラッシュスクリーンを閉じる

    sys.exit(app.exec())