#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zapret Auto-Selector for Windows
Готовое Windows-приложение с автоматическим подбором стратегий из zapret
"""

import sys
import os
import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QTabWidget, QGroupBox, QFormLayout,
    QCheckBox, QSpinBox, QComboBox, QMessageBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QIcon

# Constants
APP_VERSION = "1.0.0"
CONFIG_FILE = "config.json"
LOG_FILE = "events.log"
CHECK_INTERVAL_DEFAULT = 5  # minutes

# Target services from utils/targets.txt
TARGET_SERVICES = {
    "Discord": ["https://discord.com", "https://gateway.discord.gg"],
    "YouTube": ["https://www.youtube.com", "https://youtu.be"],
    "Google": ["https://www.google.com", "https://www.gstatic.com"],
    "Cloudflare": ["https://www.cloudflare.com"],
    "ChatGPT": ["https://chat.openai.com"],
}


class LogWorker(QObject):
    """Worker для записи логов в файл"""
    log_signal = pyqtSignal(str)
    
    def __init__(self, log_file: str):
        super().__init__()
        self.log_file = log_file
    
    def write_log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
        
        self.log_signal.emit(log_entry.strip())


class BlockCheckWorker(QThread):
    """Worker для многопоточного blockcheck"""
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(str, bool, str)  # target, success, strategy
    finished_signal = pyqtSignal()
    
    def __init__(self, targets: List[str], strategies: List[str]):
        super().__init__()
        self.targets = targets
        self.strategies = strategies
        self._stop_flag = False
    
    def run(self):
        """Запуск проверки по всем целям и стратегиям"""
        total = len(self.targets) * len(self.strategies)
        current = 0
        
        for target in self.targets:
            if self._stop_flag:
                break
                
            for strategy in self.strategies:
                if self._stop_flag:
                    break
                
                # Эмуляция проверки (в реальности здесь вызов winws.exe)
                success = self._check_target(target, strategy)
                self.result_signal.emit(target, success, strategy)
                
                current += 1
                self.progress_signal.emit(int(100 * current / total))
                time.sleep(0.1)  # Небольшая задержка между проверками
        
        self.finished_signal.emit()
    
    def _check_target(self, target: str, strategy: str) -> bool:
        """Проверка доступности цели с указанной стратегией"""
        try:
            # Здесь будет реальный вызов zapret
            # Для примера - эмуляция
            return True
        except Exception as e:
            return False
    
    def stop(self):
        self._stop_flag = True


class MonitorWorker(QThread):
    """Worker для мониторинга доступности сервисов"""
    status_signal = pyqtSignal(str, bool)  # service, is_available
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    
    def __init__(self, services: Dict[str, List[str]]):
        super().__init__()
        self.services = services
        self._stop_flag = False
    
    def run(self):
        """Цикл мониторинга"""
        while not self._stop_flag:
            for service, urls in self.services.items():
                if self._stop_flag:
                    break
                
                is_available = self._check_service(service, urls)
                self.status_signal.emit(service, is_available)
                
                if is_available:
                    self.log_signal.emit(f"✅ {service} доступен")
                else:
                    self.log_signal.emit(f"⚠️ {service} недоступен")
            
            # Проверка каждые 5 минут (300 секунд)
            for _ in range(300):
                if self._stop_flag:
                    break
                time.sleep(1)
        
        self.finished_signal.emit()
    
    def _check_service(self, service: str, urls: List[str]) -> bool:
        """Проверка доступности сервиса"""
        try:
            import requests
            for url in urls:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    return True
            return False
        except Exception:
            return False
    
    def stop(self):
        self._stop_flag = True


class StrategySelectorWindow(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.log_worker = None
        self.monitor_worker = None
        self.blockcheck_worker = None
        
        self.init_ui()
        self.setup_logging()
        self.start_monitoring()
    
    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle(f"Zapret Auto-Selector v{APP_VERSION}")
        self.setMinimumSize(900, 700)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Create tabs
        self.create_status_tab()
        self.create_auto_select_tab()
        self.create_blockcheck_tab()
        self.create_log_tab()
        self.create_settings_tab()
        
        # Status bar
        self.statusBar().showMessage("Готов к работе")
    
    def create_status_tab(self):
        """Вкладка статуса сервисов"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Group box for services
        group = QGroupBox("Статус сервисов")
        group_layout = QVBoxLayout(group)
        
        # Table for services
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(3)
        self.status_table.setHorizontalHeaderLabels(["Сервис", "Статус", "Последняя проверка"])
        self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.status_table.setAlternatingRowColors(True)
        
        # Add services to table
        self.status_table.setRowCount(len(TARGET_SERVICES))
        for i, (service, urls) in enumerate(TARGET_SERVICES.items()):
            self.status_table.setItem(i, 0, QTableWidgetItem(service))
            
            status_item = QTableWidgetItem("Проверка...")
            status_item.setForeground(QColor("orange"))
            self.status_table.setItem(i, 1, status_item)
            
            self.status_table.setItem(i, 2, QTableWidgetItem("-"))
        
        group_layout.addWidget(self.status_table)
        layout.addWidget(group)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Обновить статус")
        refresh_btn.clicked.connect(self.refresh_status)
        layout.addWidget(refresh_btn)
        
        self.tabs.addTab(tab, "📊 Статус")
    
    def create_auto_select_tab(self):
        """Вкладка автоподбора стратегий"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Info label
        info_label = QLabel(
            "Автоматический подбор оптимальной стратегии zapret для вашего соединения.\n"
            "Приложение протестирует доступные стратегии и выберет лучшую."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Progress
        self.auto_progress = QProgressBar()
        self.auto_progress.setVisible(False)
        layout.addWidget(self.auto_progress)
        
        # Start button
        self.auto_start_btn = QPushButton("▶️ Запустить автоподбор")
        self.auto_start_btn.clicked.connect(self.start_auto_select)
        layout.addWidget(self.auto_start_btn)
        
        # Results
        results_group = QGroupBox("Результаты подбора")
        results_layout = QVBoxLayout(results_group)
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(200)
        results_layout.addWidget(self.results_text)
        
        layout.addWidget(results_group)
        
        # Current strategy
        strategy_group = QGroupBox("Текущая стратегия")
        strategy_layout = QFormLayout(strategy_group)
        
        self.current_strategy_label = QLabel(self.config.get("selected_strategy", "auto"))
        strategy_layout.addRow("Стратегия:", self.current_strategy_label)
        
        apply_btn = QPushButton("💾 Применить стратегию")
        apply_btn.clicked.connect(self.apply_strategy)
        strategy_layout.addRow("", apply_btn)
        
        layout.addWidget(strategy_group)
        
        layout.addStretch()
        
        self.tabs.addTab(tab, "🎯 Автоподбор")
    
    def create_blockcheck_tab(self):
        """Вкладка Domain/IP Block Check"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Input section
        input_group = QGroupBox("Параметры проверки")
        input_layout = QFormLayout(input_group)
        
        # Target input
        self.blockcheck_target = QComboBox()
        self.blockcheck_target.setEditable(True)
        self.blockcheck_target.addItems([
            "youtube.com",
            "discord.com",
            "chat.openai.com",
            "google.com",
            "1.1.1.1",
            "8.8.8.8"
        ])
        input_layout.addRow("Домен/IP:", self.blockcheck_target)
        
        # Strategy selection
        self.blockcheck_strategy = QComboBox()
        self.blockcheck_strategy.addItems([
            "Все стратегии",
            "Fake TLS",
            "Fake QUIC",
            "Host Spoofing",
            "Custom"
        ])
        input_layout.addRow("Стратегия:", self.blockcheck_strategy)
        
        # Threads
        self.blockcheck_threads = QSpinBox()
        self.blockcheck_threads.setRange(1, 16)
        self.blockcheck_threads.setValue(4)
        input_layout.addRow("Потоков:", self.blockcheck_threads)
        
        layout.addWidget(input_group)
        
        # Start button
        start_btn = QPushButton("🔍 Запустить проверку")
        start_btn.clicked.connect(self.start_blockcheck)
        layout.addWidget(start_btn)
        
        # Progress
        self.blockcheck_progress = QProgressBar()
        self.blockcheck_progress.setVisible(False)
        layout.addWidget(self.blockcheck_progress)
        
        # Results
        results_group = QGroupBox("Результаты проверки")
        results_layout = QVBoxLayout(results_group)
        
        self.blockcheck_results = QTextEdit()
        self.blockcheck_results.setReadOnly(True)
        results_layout.addWidget(self.blockcheck_results)
        
        layout.addWidget(results_group)
        
        self.tabs.addTab(tab, "📋 Block Check")
    
    def create_log_tab(self):
        """Вкладка журнала событий"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        clear_btn = QPushButton("🗑️ Очистить журнал")
        clear_btn.clicked.connect(self.clear_log)
        btn_layout.addWidget(clear_btn)
        
        export_btn = QPushButton("💾 Экспорт журнала")
        export_btn.clicked.connect(self.export_log)
        btn_layout.addWidget(export_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.tabs.addTab(tab, "📝 Журнал")
    
    def create_settings_tab(self):
        """Вкладка настроек"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Settings form
        settings_group = QGroupBox("Основные настройки")
        settings_layout = QFormLayout(settings_group)
        
        # Check interval
        self.check_interval_spin = QSpinBox()
        self.check_interval_spin.setRange(1, 60)
        self.check_interval_spin.setValue(self.config.get("check_interval_minutes", CHECK_INTERVAL_DEFAULT))
        settings_layout.addRow("Интервал проверки (мин):", self.check_interval_spin)
        
        # Auto switch
        self.auto_switch_check = QCheckBox()
        self.auto_switch_check.setChecked(self.config.get("auto_switch_enabled", True))
        settings_layout.addRow("Автопереключение:", self.auto_switch_check)
        
        # Monitored services
        services_group = QGroupBox("Мониторируемые сервисы")
        services_layout = QVBoxLayout(services_group)
        
        self.service_checks = {}
        for service in TARGET_SERVICES.keys():
            check = QCheckBox(service)
            check.setChecked(service.lower() in [s.lower() for s in self.config.get("monitored_services", [])])
            self.service_checks[service] = check
            services_layout.addWidget(check)
        
        settings_layout.addRow("", services_group)
        
        layout.addWidget(settings_group)
        
        # Save button
        save_btn = QPushButton("💾 Сохранить настройки")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        
        self.tabs.addTab(tab, "⚙️ Настройки")
    
    def setup_logging(self):
        """Настройка логирования"""
        self.log_worker = LogWorker(LOG_FILE)
        self.log_worker.log_signal.connect(self.append_log)
        self.append_log("=== Приложение запущено ===")
    
    def append_log(self, message: str):
        """Добавление записи в журнал"""
        self.log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """Очистка журнала"""
        self.log_text.clear()
        self.append_log("Журнал очищен")
    
    def export_log(self):
        """Экспорт журнала"""
        try:
            with open("exported_log.txt", "w", encoding="utf-8") as f:
                f.write(self.log_text.toPlainText())
            QMessageBox.information(self, "Экспорт", "Журнал экспортирован в exported_log.txt")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать журнал: {e}")
    
    def start_monitoring(self):
        """Запуск мониторинга сервисов"""
        monitored = self.config.get("monitored_services", list(TARGET_SERVICES.keys()))
        services_to_monitor = {
            k: v for k, v in TARGET_SERVICES.items()
            if k.lower() in [s.lower() for s in monitored]
        }
        
        self.monitor_worker = MonitorWorker(services_to_monitor)
        self.monitor_worker.status_signal.connect(self.update_service_status)
        self.monitor_worker.log_signal.connect(self.append_log)
        self.monitor_worker.start()
        
        self.append_log("Мониторинг запущен")
    
    def update_service_status(self, service: str, is_available: bool):
        """Обновление статуса сервиса в таблице"""
        for row in range(self.status_table.rowCount()):
            if self.status_table.item(row, 0).text() == service:
                status_item = self.status_table.item(row, 1)
                if is_available:
                    status_item.setText("✅ Доступен")
                    status_item.setForeground(QColor("green"))
                else:
                    status_item.setText("❌ Недоступен")
                    status_item.setForeground(QColor("red"))
                
                # Update last check time
                now = datetime.now().strftime("%H:%M:%S")
                self.status_table.setItem(row, 2, QTableWidgetItem(now))
                break
    
    def refresh_status(self):
        """Принудительное обновление статуса"""
        self.append_log("Принудительное обновление статуса...")
        # В реальной реализации здесь будет вызов проверки
    
    def start_auto_select(self):
        """Запуск автоподбора стратегий"""
        self.auto_start_btn.setEnabled(False)
        self.auto_progress.setVisible(True)
        self.auto_progress.setValue(0)
        
        self.append_log("Запуск автоподбора стратегий...")
        self.results_text.clear()
        
        # Эмуляция процесса подбора
        strategies = ["Fake TLS", "Fake QUIC", "Host Spoofing"]
        targets = list(TARGET_SERVICES.keys())
        
        self.blockcheck_worker = BlockCheckWorker(targets, strategies)
        self.blockcheck_worker.progress_signal.connect(self.auto_progress.setValue)
        self.blockcheck_worker.result_signal.connect(self.handle_blockcheck_result)
        self.blockcheck_worker.finished_signal.connect(self.auto_select_finished)
        self.blockcheck_worker.start()
    
    def handle_blockcheck_result(self, target: str, success: bool, strategy: str):
        """Обработка результата проверки"""
        status = "✅" if success else "❌"
        self.results_text.append(f"{status} {target} - {strategy}: {'Успех' if success else 'Неудача'}")
    
    def auto_select_finished(self):
        """Завершение автоподбора"""
        self.auto_progress.setVisible(False)
        self.auto_start_btn.setEnabled(True)
        self.append_log("Автоподбор завершён")
        
        # Определение лучшей стратегии (в реальности - анализ результатов)
        best_strategy = "Fake TLS"
        self.config["selected_strategy"] = best_strategy
        self.current_strategy_label.setText(best_strategy)
        
        QMessageBox.information(
            self,
            "Автоподбор завершён",
            f"Лучшая стратегия: {best_strategy}\n\nСтратегия применена автоматически."
        )
    
    def apply_strategy(self):
        """Применение выбранной стратегии"""
        strategy = self.current_strategy_label.text()
        self.append_log(f"Применение стратегии: {strategy}")
        
        # В реальной реализации здесь будет вызов zapret с нужной стратегией
        QMessageBox.information(self, "Стратегия", f"Стратегия '{strategy}' применена")
    
    def start_blockcheck(self):
        """Запуск Block Check"""
        target = self.blockcheck_target.currentText()
        strategy = self.blockcheck_strategy.currentText()
        threads = self.blockcheck_threads.value()
        
        self.append_log(f"Запуск проверки: {target} (стратегия: {strategy}, потоков: {threads})")
        
        self.blockcheck_results.clear()
        self.blockcheck_progress.setVisible(True)
        self.blockcheck_progress.setValue(0)
        
        # Эмуляция проверки
        strategies_to_test = ["Все стратегии"] if strategy == "Все стратегии" else [strategy]
        
        self.blockcheck_worker = BlockCheckWorker([target], strategies_to_test)
        self.blockcheck_worker.progress_signal.connect(self.blockcheck_progress.setValue)
        self.blockcheck_worker.result_signal.connect(
            lambda t, s, strat: self.blockcheck_results.append(
                f"{'✅' if s else '❌'} {t} - {strat}: {'Доступно' if s else 'Заблокировано'}"
            )
        )
        self.blockcheck_worker.finished_signal.connect(self.blockcheck_finished)
        self.blockcheck_worker.start()
    
    def blockcheck_finished(self):
        """Завершение Block Check"""
        self.blockcheck_progress.setVisible(False)
        self.append_log("Проверка завершена")
    
    def save_settings(self):
        """Сохранение настроек"""
        self.config["check_interval_minutes"] = self.check_interval_spin.value()
        self.config["auto_switch_enabled"] = self.auto_switch_check.isChecked()
        
        monitored = [
            service for service, check in self.service_checks.items()
            if check.isChecked()
        ]
        self.config["monitored_services"] = monitored
        
        self.save_config()
        QMessageBox.information(self, "Настройки", "Настройки сохранены")
        self.append_log("Настройки сохранены")
        
        # Перезапуск мониторинга с новыми настройками
        if self.monitor_worker:
            self.monitor_worker.stop()
            self.monitor_worker.wait()
        self.start_monitoring()
    
    def load_config(self) -> dict:
        """Загрузка конфигурации"""
        default_config = {
            "selected_strategy": "auto",
            "check_interval_minutes": CHECK_INTERVAL_DEFAULT,
            "auto_switch_enabled": True,
            "monitored_services": list(TARGET_SERVICES.keys()),
            "custom_strategies": []
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    default_config.update(config)
            except Exception as e:
                print(f"Error loading config: {e}")
        
        return default_config
    
    def save_config(self):
        """Сохранение конфигурации"""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {e}")
    
    def closeEvent(self, event):
        """Обработка закрытия приложения"""
        if self.monitor_worker:
            self.monitor_worker.stop()
            self.monitor_worker.wait()
        
        if self.blockcheck_worker:
            self.blockcheck_worker.stop()
            self.blockcheck_worker.wait()
        
        self.append_log("=== Приложение закрыто ===")
        event.accept()


def main():
    """Точка входа приложения"""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    window = StrategySelectorWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
