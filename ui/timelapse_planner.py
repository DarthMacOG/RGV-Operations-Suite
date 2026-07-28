from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from tzlocal import get_localzone

from core.settings import APP_NAME
from core.timelapse import build_schedule, format_duration, format_schedule_summary


BG = "#0b111b"
PANEL = "#111a28"
PANEL_2 = "#162235"
BORDER = "#263852"
TEXT = "#f2f6fc"
MUTED = "#8fa2bb"
ACCENT = "#2f8cff"
SUCCESS = "#36d399"


class ResultCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("plannerCard")
        self.setStyleSheet(
            f"QFrame#plannerCard {{ background: {PANEL}; border: 1px solid {BORDER}; "
            "border-radius: 8px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        self.title = QLabel(title)
        self.title.setStyleSheet(f"color: {MUTED}; font-size: 9pt; font-weight: 600; border: none;")
        self.value = QLabel("—")
        self.value.setWordWrap(True)
        self.value.setStyleSheet("font-size: 11pt; font-weight: 600; border: none;")
        layout.addWidget(self.title)
        layout.addWidget(self.value)


class TimelapsePlanner(QWidget):
    def __init__(self):
        super().__init__()
        self.local_timezone = get_localzone()
        self.current_schedule = None
        self._build()
        self._calculate()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)
        outer.setSpacing(14)

        intro = QFrame()
        intro.setObjectName("panel")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("STARBASE TIMELAPSE PLANNER")
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        detail = QLabel(
            "Plan in Starbase time. The app converts the schedule into the local time "
            "that the Reolink Client on this PC expects—without changing Windows."
        )
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color: {MUTED};")
        timezone_label = QLabel(
            f"Starbase: America/Chicago  •  This PC: {self.local_timezone.key}"
        )
        timezone_label.setStyleSheet(f"color: {ACCENT}; font-size: 9pt;")
        intro_layout.addWidget(title)
        intro_layout.addWidget(detail)
        intro_layout.addWidget(timezone_label)
        outer.addWidget(intro)

        content = QHBoxLayout()
        content.setSpacing(14)
        form_panel = QFrame()
        form_panel.setObjectName("panel")
        form = QGridLayout(form_panel)
        form.setContentsMargins(20, 18, 20, 18)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(11)

        now = datetime.now().replace(second=0, microsecond=0)
        next_hour = now + timedelta(hours=1)
        next_hour = next_hour.replace(minute=0)
        self.start_edit = QDateTimeEdit(QDateTime(next_hour))
        self.end_edit = QDateTimeEdit(QDateTime(next_hour + timedelta(hours=1)))
        for editor in (self.start_edit, self.end_edit):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("ddd, MMM d, yyyy  h:mm AP")

        form.addWidget(self._label("Start at Starbase"), 0, 0)
        form.addWidget(self.start_edit, 0, 1)
        form.addWidget(self._label("End at Starbase"), 1, 0)
        form.addWidget(self.end_edit, 1, 1)

        calculate = QPushButton("Calculate Reolink Schedule")
        calculate.clicked.connect(self._calculate)
        form.addWidget(calculate, 2, 0, 1, 2)
        content.addWidget(form_panel, 3)

        results = QVBoxLayout()
        self.starbase_card = ResultCard("STARBASE TIME")
        self.reolink_card = ResultCard("ENTER IN REOLINK ON THIS PC")
        self.details_card = ResultCard("DURATION")
        results.addWidget(self.starbase_card)
        results.addWidget(self.reolink_card)
        results.addWidget(self.details_card)
        self.copy_button = QPushButton("Copy Schedule")
        self.copy_button.clicked.connect(self._copy)
        results.addWidget(self.copy_button)
        results.addStretch()
        content.addLayout(results, 2)
        outer.addLayout(content, 1)

        note = QLabel(
            "Planner only: this does not connect to the LTE cameras or submit the schedule. "
            "Always confirm Reolink's displayed start time and duration before capture."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {MUTED}; font-size: 9pt;")
        outer.addWidget(note)

    def _label(self, text):
        label = QLabel(text)
        label.setStyleSheet(f"color: {MUTED}; font-size: 9pt; font-weight: 600;")
        return label

    def _naive_datetime(self, editor):
        value = editor.dateTime()
        return datetime(
            value.date().year(),
            value.date().month(),
            value.date().day(),
            value.time().hour(),
            value.time().minute(),
        )

    def _calculate(self):
        try:
            self.current_schedule = build_schedule(
                self._naive_datetime(self.start_edit),
                self._naive_datetime(self.end_edit),
                self.local_timezone,
            )
        except ValueError as exc:
            self.current_schedule = None
            QMessageBox.warning(self, APP_NAME, str(exc))
            return

        schedule = self.current_schedule
        self.starbase_card.value.setText(
            f"{schedule.starbase_start:%a, %b %d • %I:%M %p} → "
            f"{schedule.starbase_end:%a, %b %d • %I:%M %p}\n"
            f"{schedule.starbase_start.tzname()} / {schedule.starbase_end.tzname()}"
        )
        self.reolink_card.value.setText(
            f"{schedule.reolink_start:%a, %b %d • %I:%M %p} → "
            f"{schedule.reolink_end:%a, %b %d • %I:%M %p}\n"
            f"{schedule.reolink_start.tzname() or self.local_timezone.key}"
        )
        self.details_card.value.setText(format_duration(schedule.duration))

    def _copy(self):
        if not self.current_schedule:
            self._calculate()
        if not self.current_schedule:
            return
        text = format_schedule_summary(self.current_schedule)
        QGuiApplication.clipboard().setText(text)
        original = self.copy_button.text()
        self.copy_button.setText("Copied!")
        self.copy_button.setStyleSheet(f"background: {SUCCESS};")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1400, lambda: (self.copy_button.setText(original), self.copy_button.setStyleSheet("")))
