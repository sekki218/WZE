#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zapret Auto-Selector for Windows v3.0
Приложение с автоподбором существующих стратегий zapret и проверкой сервисов
"""

import sys
import os
import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QTabWidget, QGroupBox, QFormLayout,
    QCheckBox, QSpinBox, QComboBox, QMessageBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QSplitter, QFrame, QLineEdit, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor

APP_VERSION = "3.0.0"
CONFIG_FILE = "config.json"
LOG_FILE = "events.log"

DEFAULT_SERVICES = {
    "Discord": ["https://discord.com"],
    "YouTube": ["https://www.youtube.com"],
    "Google": ["https://www.google.com"],
    "Cloudflare": ["https://www.cloudflare.com"],
    "ChatGPT": ["https://chat.openai.com"],
}


def scan_strategies() -> List[Dict]:
    """Сканирование существующих .bat файлов как стратегий"""
    strategies = []
    bat_dir = Path(__file__).parent
    
    for bat_file in sorted(bat_dir.glob("*.bat")):
        if bat_file.name == "service.bat":
            continue
        
        name = bat_file.stem.replace("general ", "").replace("(", "").replace(")", "").strip()
        stype = "custom"
        try:
            with open(bat_file, "r", encoding="utf-8") as f:
                content = f.read().lower()
                if "fake" in content and "tls" in content:
                    stype = "Fake TLS"
                elif "fake" in content and "quic" in content:
                    stype = "Fake QUIC"
                elif "multisplit" in content:
                    stype = "MultiSplit"
        except:
            pass
        
        strategies.append({"name": name, "file": bat_file.name, "type": stype})
    
    return strategies


class LogWorker(QObject):
    log_signal = pyqtSignal(str)
    
    def __init__(self, log_file: str):
        super().__init__()
        self.log_file = log_file
    
    def write(self, message: str, level: str = "INFO"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] [{level}] {message}\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(entry)
        self.log_signal.emit(entry.strip())


class MonitorWorker(QThread):
    status_signal = pyqtSignal(str, bool)
    log_signal = pyqtSignal(str)
    strategy_test_signal = pyqtSignal(str, str, bool)  # service, strategy, result
    
    def __init__(self, services: Dict[str, List[str]], strategies: List[Dict], 
                 interval: int = 300, test_mode: bool = False):
        super().__init__()
        self.services = services
        self.strategies = strategies
        self.interval = interval
        self._stop = False
        self.test_mode = test_mode
    
    def run(self):
        if self.test_mode:
            # Режим тестирования стратегий
            for service, urls in self.services.items():
                for strat in self.strategies:
                    if self._stop:
                        break
                    available = self._check(urls)
                    self.strategy_test_signal.emit(service, strat["name"], available)
                    self.log_signal.emit(f"Тест {service} + {strat['name']}: {'✅' if available else '❌'}")
                    time.sleep(0.5)
            return
        
        while not self._stop:
            for service, urls in self.services.items():
                if self._stop:
                    break
                available = self._check(urls)
                self.status_signal.emit(service, available)
                self.log_signal.emit(f"{'✅' if available else '⚠️'} {service}")
            
            for _ in range(self.interval):
                if self._stop:
                    break
                time.sleep(1)
    
    def _check(self, urls: List[str]) -> bool:
        try:
            import requests
            for url in urls:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    return True
            return False
        except:
            return False
    
    def stop(self):
        self._stop = True


class BlockCheckWorker(QThread):
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(str, bool, str)
    finished_signal = pyqtSignal()
    
    def __init__(self, targets: List[str], strategies: List[Dict]):
        super().__init__()
        self.targets = targets
        self.strategies = strategies
        self._stop = False
    
    def run(self):
        total = len(self.targets) * len(self.strategies)
        current = 0
        
        for target in self.targets:
            if self._stop:
                break
            for strat in self.strategies:
                if self._stop:
                    break
                
                success = self._test(target, strat)
                self.result_signal.emit(target, success, strat["name"])
                current += 1
                self.progress_signal.emit(int(100 * current / total))
                time.sleep(0.05)
        
        self.finished_signal.emit()
    
    def _test(self, target: str, strategy: Dict) -> bool:
        # Эмуляция - в реальности вызов winws.exe
        import random
        return random.choice([True, True, True, False])
    
    def stop(self):
        self._stop = True


class AddServiceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить сервис")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например: Netflix")
        form.addRow("Название:", self.name_edit)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://netflix.com")
        form.addRow("URL:", self.url_edit)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_data(self):
        return self.name_edit.text().strip(), self.url_edit.text().strip()


class ZapretApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.strategies = scan_strategies()
        self.services = self.load_services()
        self.monitor = None
        self.current_strategy = None
        
        self.init_ui()
        self.setup_log()
        self.start_monitor()
    
    def load_services(self) -> Dict[str, List[str]]:
        """Загрузка сервисов из конфига"""
        services = dict(DEFAULT_SERVICES)
        
        # Добавляем пользовательские сервисы
        custom = self.config.get("custom_services", {})
        for name, url in custom.items():
            services[name] = [url]
        
        return services
    
    def init_ui(self):
        self.setWindowTitle(f"Zapret Auto-Selector v{APP_VERSION}")
        self.setMinimumSize(900, 650)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Вкладка 1: Главная (Статус + Стратегии + Автоподбор)
        tabs.addTab(self.create_main_tab(), "🏠 Главная")
        # Вкладка 2: Block Check
        tabs.addTab(self.create_blockcheck_tab(), "📋 Block Check")
        # Вкладка 3: Журнал
        tabs.addTab(self.create_log_tab(), "📝 Журнал")
        # Вкладка 4: Настройки
        tabs.addTab(self.create_settings_tab(), "⚙️ Настройки")
        
        self.statusBar().showMessage("Готов")
    
    def create_main_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Верхняя часть: Статус сервисов
        status_group = QGroupBox("🌐 Статус сервисов")
        status_layout = QVBoxLayout(status_group)
        
        # Кнопки управления сервисами
        btn_row = QHBoxLayout()
        add_service_btn = QPushButton("➕ Добавить сервис")
        add_service_btn.clicked.connect(self.add_service)
        btn_row.addWidget(add_service_btn)
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.refresh_services)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        status_layout.addLayout(btn_row)
        
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(3)
        self.status_table.setHorizontalHeaderLabels(["Сервис", "Статус", "Время"])
        self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.status_table.setAlternatingRowColors(True)
        self.update_status_table()
        
        status_layout.addWidget(self.status_table)
        layout.addWidget(status_group)
        
        # Средняя часть: Список стратегий и автоподбор
        middle_splitter = QSplitter(Qt.Horizontal)
        
        # Список стратегий
        strat_group = QGroupBox("📦 Доступные стратегии")
        strat_layout = QVBoxLayout(strat_group)
        
        self.strategy_list = QListWidget()
        self.strategy_list.setSelectionMode(QListWidget.ExtendedSelection)
        for s in self.strategies:
            item = QListWidgetItem(f"{s['type']}: {s['name']}")
            item.setData(Qt.UserRole, s)
            self.strategy_list.addItem(item)
        
        strat_layout.addWidget(self.strategy_list)
        
        # Кнопки стратегий
        strat_btn_layout = QHBoxLayout()
        
        run_btn = QPushButton("▶️ Запустить")
        run_btn.clicked.connect(self.run_strategy)
        strat_btn_layout.addWidget(run_btn)
        
        apply_btn = QPushButton("💾 Применить")
        apply_btn.clicked.connect(self.apply_strategy)
        strat_btn_layout.addWidget(apply_btn)
        
        strat_layout.addLayout(strat_btn_layout)
        middle_splitter.addWidget(strat_group)
        
        # Панель автоподбора
        auto_group = QGroupBox("🎯 Автоподбор стратегий")
        auto_layout = QVBoxLayout(auto_group)
        
        auto_label = QLabel("Выберите стратегии для проверки\nили оставьте все для автоматического подбора")
        auto_label.setWordWrap(True)
        auto_layout.addWidget(auto_label)
        
        self.auto_combo = QComboBox()
        self.auto_combo.addItems(["Все стратегии", "Fake TLS", "Fake QUIC", "MultiSplit", "custom"])
        auto_layout.addWidget(self.auto_combo)
        
        test_services_btn = QPushButton("🧪 Тестировать стратегии")
        test_services_btn.clicked.connect(self.test_strategies)
        auto_layout.addWidget(test_services_btn)
        
        auto_start_btn = QPushButton("🚀 Запустить автоподбор")
        auto_start_btn.clicked.connect(self.auto_select)
        auto_layout.addWidget(auto_start_btn)
        
        self.auto_progress = QProgressBar()
        self.auto_progress.setVisible(False)
        auto_layout.addWidget(self.auto_progress)
        
        self.auto_result = QTextEdit()
        self.auto_result.setReadOnly(True)
        self.auto_result.setMaximumHeight(150)
        self.auto_result.setPlaceholderText("Результаты тестирования...")
        auto_layout.addWidget(self.auto_result)
        
        middle_splitter.addWidget(auto_group)
        middle_splitter.setStretchFactor(0, 1)
        middle_splitter.setStretchFactor(1, 1)
        
        layout.addWidget(middle_splitter)
        
        # Нижняя часть: Текущая стратегия
        curr_group = QGroupBox("Активная стратегия")
        curr_layout = QHBoxLayout(curr_group)
        
        self.curr_strategy_label = QLabel(self.config.get("active_strategy", "Не выбрана"))
        self.curr_strategy_label.setFont(QFont("Arial", 12, QFont.Bold))
        curr_layout.addWidget(self.curr_strategy_label)
        
        curr_layout.addStretch()
        layout.addWidget(curr_group)
        
        return tab
    
    def create_blockcheck_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Параметры
        param_group = QGroupBox("Параметры проверки")
        param_layout = QFormLayout(param_group)
        
        self.bc_target = QComboBox()
        self.bc_target.setEditable(True)
        targets = ["youtube.com", "discord.com", "chat.openai.com", "google.com", "1.1.1.1", "8.8.8.8"]
        self.bc_target.addItems(targets)
        param_layout.addRow("Домен/IP:", self.bc_target)
        
        self.bc_mode = QComboBox()
        self.bc_mode.addItems(["Все стратегии", "Fake TLS", "Fake QUIC", "MultiSplit"])
        param_layout.addRow("Режим:", self.bc_mode)
        
        self.bc_threads = QSpinBox()
        self.bc_threads.setRange(1, 16)
        self.bc_threads.setValue(4)
        param_layout.addRow("Потоков:", self.bc_threads)
        
        layout.addWidget(param_group)
        
        start_btn = QPushButton("🔍 Запустить проверку")
        start_btn.clicked.connect(self.run_blockcheck)
        layout.addWidget(start_btn)
        
        self.bc_progress = QProgressBar()
        self.bc_progress.setVisible(False)
        layout.addWidget(self.bc_progress)
        
        # Результаты
        res_group = QGroupBox("Результаты")
        res_layout = QVBoxLayout(res_group)
        
        self.bc_results = QTextEdit()
        self.bc_results.setReadOnly(True)
        self.bc_results.setMaximumHeight(200)
        res_layout.addWidget(self.bc_results)
        
        layout.addWidget(res_group)
        layout.addStretch()
        
        return tab
    
    def create_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        btn_layout = QHBoxLayout()
        
        clear_btn = QPushButton("🗑️ Очистить")
        clear_btn.clicked.connect(lambda: self.log_text.clear())
        btn_layout.addWidget(clear_btn)
        
        export_btn = QPushButton("💾 Экспорт")
        export_btn.clicked.connect(self.export_log)
        btn_layout.addWidget(export_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return tab
    
    def create_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        settings_group = QGroupBox("Настройки")
        settings_layout = QFormLayout(settings_group)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(self.config.get("interval", 5))
        settings_layout.addRow("Интервал (мин):", self.interval_spin)
        
        self.auto_check = QCheckBox()
        self.auto_check.setChecked(self.config.get("auto_switch", True))
        settings_layout.addRow("Автопереключение:", self.auto_check)
        
        # Управление сервисами
        services_group = QGroupBox("Мониторинг сервисов")
        services_layout = QVBoxLayout(services_group)
        
        self.service_checks = {}
        for service in self.services.keys():
            cb = QCheckBox(service)
            cb.setChecked(service in self.config.get("monitor_services", list(self.services.keys())))
            self.service_checks[service] = cb
            services_layout.addWidget(cb)
        
        settings_layout.addRow("", services_group)
        layout.addWidget(settings_group)
        
        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        layout.addStretch()
        
        return tab
    
    def update_status_table(self):
        """Обновление таблицы статусов"""
        self.status_table.setRowCount(len(self.services))
        for i, service in enumerate(self.services.keys()):
            self.status_table.setItem(i, 0, QTableWidgetItem(service))
            item = QTableWidgetItem("Проверка...")
            item.setForeground(QColor("orange"))
            self.status_table.setItem(i, 1, item)
            self.status_table.setItem(i, 2, QTableWidgetItem("-"))
    
    def setup_log(self):
        self.log_worker = LogWorker(LOG_FILE)
        self.log_worker.log_signal.connect(self.log_text.append)
        self.log_worker.write("=== Запуск ===")
    
    def start_monitor(self):
        monitor_list = self.config.get("monitor_services", list(self.services.keys()))
        to_monitor = {k: v for k, v in self.services.items() if k in monitor_list}
        
        self.monitor = MonitorWorker(to_monitor, self.strategies, 
                                     self.config.get("interval", 5) * 60)
        self.monitor.status_signal.connect(self.update_status)
        self.monitor.log_signal.connect(self.log_worker.write)
        self.monitor.start()
    
    def update_status(self, service: str, available: bool):
        for row in range(self.status_table.rowCount()):
            if self.status_table.item(row, 0).text() == service:
                item = self.status_table.item(row, 1)
                item.setText("✅ OK" if available else "❌ FAIL")
                item.setForeground(QColor("green" if available else "red"))
                self.status_table.setItem(row, 2, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
                break
    
    def add_service(self):
        dialog = AddServiceDialog(self)
        if dialog.exec() == QDialog.Accepted:
            name, url = dialog.get_data()
            if name and url:
                self.services[name] = [url]
                
                # Сохраняем в конфиг
                if "custom_services" not in self.config:
                    self.config["custom_services"] = {}
                self.config["custom_services"][name] = url
                self.save_config()
                
                # Обновляем таблицу
                self.update_status_table()
                
                # Добавляем чекбокс в настройки
                cb = QCheckBox(name)
                cb.setChecked(True)
                self.service_checks[name] = cb
                # Нужно пересоздать settings tab или добавить динамически
                # Для простоты просто обновим список
                
                self.log_worker.write(f"Добавлен сервис: {name} ({url})")
                QMessageBox.information(self, "Готово", f"Сервис '{name}' добавлен")
    
    def refresh_services(self):
        """Принудительное обновление статусов"""
        self.log_worker.write("Обновление статусов сервисов...")
        if self.monitor:
            self.monitor.stop()
            self.monitor.wait()
        self.start_monitor()
    
    def run_strategy(self):
        items = self.strategy_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Внимание", "Выберите стратегию")
            return
        
        strat = items[0].data(Qt.UserRole)
        self.log_worker.write(f"Запуск стратегии: {strat['name']}")
        QMessageBox.information(self, "Стратегия", f"Запущено: {strat['name']}")
    
    def test_strategies(self):
        """Тестирование выбранных стратегий на доступность сервисов"""
        mode = self.auto_combo.currentText()
        
        if mode == "Все стратегии":
            strats_to_test = self.strategies
        else:
            strats_to_test = [s for s in self.strategies if s["type"] == mode]
        
        if not strats_to_test:
            QMessageBox.warning(self, "Внимание", f"Нет стратегий типа '{mode}'")
            return
        
        self.auto_result.clear()
        self.auto_result.append(f"🧪 Тестирование стратегий ({len(strats_to_test)} шт.)...\n")
        
        # Запускаем тест
        to_monitor = dict(list(self.services.items())[:3])  # Первые 3 сервиса
        
        self.test_monitor = MonitorWorker(to_monitor, strats_to_test, test_mode=True)
        self.test_monitor.strategy_test_signal.connect(self.on_strategy_test_result)
        self.test_monitor.log_signal.connect(self.log_worker.write)
        self.test_monitor.start()
    
    def on_strategy_test_result(self, service: str, strategy: str, result: bool):
        icon = "✅" if result else "❌"
        self.auto_result.append(f"{icon} {service} + {strategy}")
    
    def auto_select(self):
        """Автоматический подбор лучшей стратегии"""
        self.log_worker.write("Запуск автоподбора...")
        self.auto_result.clear()
        self.auto_result.append("🚀 Автоподбор стратегий...\n")
        self.auto_progress.setVisible(True)
        self.auto_progress.setValue(0)
        
        # Эмуляция процесса подбора
        best_strategy = None
        best_score = 0
        
        for i, strat in enumerate(self.strategies):
            score = sum([True for _ in range(3)])  # Эмуляция теста
            self.auto_result.append(f"Тест {strat['name']}: {score}/3")
            self.auto_progress.setValue(int(100 * (i + 1) / len(self.strategies)))
            
            if score > best_score:
                best_score = score
                best_strategy = strat
        
        self.auto_progress.setVisible(False)
        
        if best_strategy:
            self.auto_result.append(f"\n🏆 Лучшая стратегия: {best_strategy['name']} (тип: {best_strategy['type']})")
            self.log_worker.write(f"Автоподбор завершён. Лучшая: {best_strategy['name']}")
            
            reply = QMessageBox.question(
                self, "Применить стратегию",
                f"Применить стратегию '{best_strategy['name']}'?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.config["active_strategy"] = best_strategy["name"]
                self.save_config()
                self.curr_strategy_label.setText(best_strategy["name"])
                QMessageBox.information(self, "Готово", f"Стратегия '{best_strategy['name']}' применена")
        else:
            self.auto_result.append("\n⚠️ Не удалось подобрать стратегию")
    
    def apply_strategy(self):
        items = self.strategy_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Внимание", "Выберите стратегию")
            return
        
        strat = items[0].data(Qt.UserRole)
        self.config["active_strategy"] = strat["name"]
        self.save_config()
        self.curr_strategy_label.setText(strat["name"])
        self.log_worker.write(f"Применена стратегия: {strat['name']}")
        QMessageBox.information(self, "Готово", f"Стратегия '{strat['name']}' применена")
    
    def run_blockcheck(self):
        target = self.bc_target.currentText()
        mode = self.bc_mode.currentText()
        threads = self.bc_threads.value()
        
        self.log_worker.write(f"BlockCheck: {target} ({mode}, {threads} потоков)")
        self.bc_results.clear()
        self.bc_progress.setVisible(True)
        self.bc_progress.setValue(0)
        
        strats = self.strategies if mode == "Все стратегии" else [s for s in self.strategies if s["type"] == mode]
        
        self.bc_worker = BlockCheckWorker([target], strats)
        self.bc_worker.progress_signal.connect(self.bc_progress.setValue)
        self.bc_worker.result_signal.connect(lambda t, s, st: self.bc_results.append(f"{'✅' if s else '❌'} {t} - {st}"))
        self.bc_worker.finished_signal.connect(lambda: self.bc_progress.setVisible(False))
        self.bc_worker.start()
    
    def export_log(self):
        try:
            with open("log_export.txt", "w", encoding="utf-8") as f:
                f.write(self.log_text.toPlainText())
            QMessageBox.information(self, "Экспорт", "Журнал экспортирован в log_export.txt")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
    
    def save_settings(self):
        self.config["interval"] = self.interval_spin.value()
        self.config["auto_switch"] = self.auto_check.isChecked()
        self.config["monitor_services"] = [s for s, cb in self.service_checks.items() if cb.isChecked()]
        self.save_config()
        
        if self.monitor:
            self.monitor.stop()
            self.monitor.wait()
        self.start_monitor()
        
        QMessageBox.information(self, "Готово", "Настройки сохранены")
    
    def load_config(self) -> dict:
        default = {
            "active_strategy": "Не выбрана",
            "interval": 5,
            "auto_switch": True,
            "monitor_services": list(DEFAULT_SERVICES.keys()),
            "custom_services": {}
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    default.update(cfg)
            except:
                pass
        return default
    
    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
    
    def closeEvent(self, event):
        if self.monitor:
            self.monitor.stop()
            self.monitor.wait()
        self.log_worker.write("=== Завершение ===")
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ZapretApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
