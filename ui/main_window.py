from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.media import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    collect_media,
    find_ffmpeg,
    process_image,
    process_video,
    unique_output_path,
    watermark_position_for,
)
from core.settings import APP_NAME, load_settings, save_settings
from core.resources import resource_path


BG = "#0b111b"
PANEL = "#111a28"
PANEL_2 = "#162235"
BORDER = "#263852"
TEXT = "#f2f6fc"
MUTED = "#8fa2bb"
ACCENT = "#2f8cff"
SUCCESS = "#36d399"
ERROR = "#fb7185"
WARNING = "#fbbf24"


STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QFrame#panel, QListWidget {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#dropZone {{
    background: {PANEL_2};
    border: 1px dashed #3b5578;
    border-radius: 10px;
}}
QFrame#dropZone[dragActive="true"] {{
    border: 2px solid {ACCENT};
    background: #172a44;
}}
QPushButton {{
    background: {ACCENT};
    border: none;
    border-radius: 6px;
    color: white;
    font-weight: 600;
    padding: 10px 14px;
}}
QPushButton:hover {{ background: #55a2ff; }}
QPushButton:disabled {{ background: {BORDER}; color: {MUTED}; }}
QPushButton[secondary="true"] {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    padding: 7px 10px;
}}
QPushButton[secondary="true"]:hover {{ background: {BORDER}; }}
QLineEdit, QComboBox {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 8px;
    selection-background-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 5px;
    background: {PANEL_2};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: white;
    width: 15px;
    margin: -5px 0;
    border-radius: 7px;
}}
QProgressBar {{
    background: {PANEL_2};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QListWidget {{
    padding: 6px;
    outline: none;
}}
QListWidget::item {{
    border-bottom: 1px solid #1c2a3e;
    padding: 10px 8px;
}}
QListWidget::item:selected {{ background: #1e4f85; border-radius: 4px; }}
"""


def secondary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("secondary", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class DropZone(QFrame):
    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(160)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus = QLabel("＋")
        plus.setStyleSheet(f"font-size: 30px; font-weight: 700; color: {ACCENT}; background: transparent;")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Drop photos, videos, or folders here")
        title.setStyleSheet("font-size: 14px; font-weight: 600; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("or click to browse  •  JPG, PNG, WEBP, MP4, MOV, AVI, MKV")
        subtitle.setStyleSheet(f"font-size: 9pt; color: {MUTED}; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(plus)
        layout.addWidget(title)
        layout.addWidget(subtitle)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()


class ExportWorker(QThread):
    progress = Signal(int, str)
    status = Signal(str, str)
    completed = Signal(list, list)

    def __init__(self, files: list[Path], settings: dict):
        super().__init__()
        self.files = files
        self.settings = settings

    def run(self):
        output = Path(self.settings["output_folder"])
        logo = Path(self.settings["logo_path"])
        completed: list[str] = []
        errors: list[tuple[str, str]] = []
        total = len(self.files)
        for index, source in enumerate(self.files):
            self.progress.emit(round(index / total * 100), f"{index + 1} of {total}")
            self.status.emit(f"Exporting {source.name}…", ACCENT)
            # All videos are exported as H.264/AAC MP4. Keeping an AVI, MKV,
            # or MOV extension after re-encoding can create files that common
            # Windows players refuse to open.
            destination = unique_output_path(
                output,
                source,
                ".mp4" if source.suffix.lower() in VIDEO_EXTENSIONS else None,
            )
            try:
                position = watermark_position_for(source)
                common = (
                    source,
                    logo,
                    destination,
                    position,
                    self.settings["size"],
                    self.settings["opacity"],
                    self.settings["margin"],
                )
                if source.suffix.lower() in IMAGE_EXTENSIONS:
                    process_image(*common)
                else:
                    process_video(*common)
                completed.append(str(destination))
            except Exception as exc:
                destination.unlink(missing_ok=True)
                errors.append((str(source), str(exc)))
        self.completed.emit(completed, errors)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.files: list[Path] = []
        self.worker: ExportWorker | None = None
        self.setWindowTitle(f"{APP_NAME} — Version 1.2.1")
        self.setWindowIcon(QIcon(str(resource_path("assets/rgv_logo.png"))))
        self.resize(1100, 740)
        self.setMinimumSize(930, 650)
        self._build()

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(30, 24, 30, 24)
        outer.setSpacing(18)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("RGV OPERATIONS SUITE")
        title.setStyleSheet("font-size: 20px; font-weight: 700; letter-spacing: 1px;")
        subtitle = QLabel("Media watermarking workspace")
        subtitle.setStyleSheet(f"color: {MUTED};")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        logo = QLabel()
        logo_pixmap = QPixmap(str(resource_path("assets/rgv_logo.png")))
        logo.setPixmap(
            logo_pixmap.scaled(
                54,
                54,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setFixedSize(62, 58)
        badge = QLabel("VERSION 1.2.1")
        badge.setStyleSheet(
            f"color: {ACCENT}; background: {PANEL_2}; padding: 8px 12px; "
            "border-radius: 5px; font-size: 9pt; font-weight: 600;"
        )
        header.addWidget(logo)
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(badge)
        outer.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(14)
        self.drop_zone = DropZone()
        self.drop_zone.browse_requested.connect(self._browse_media)
        self.drop_zone.files_dropped.connect(self._add_files)
        left.addWidget(self.drop_zone)

        queue_header = QHBoxLayout()
        queue_label = QLabel("EXPORT QUEUE")
        queue_label.setStyleSheet("font-weight: 600;")
        self.count_label = QLabel("0 files")
        self.count_label.setStyleSheet(f"color: {MUTED};")
        remove = secondary_button("Remove selected")
        remove.clicked.connect(self._remove_selected)
        clear = secondary_button("Clear")
        clear.clicked.connect(self._clear_files)
        queue_header.addWidget(queue_label)
        queue_header.addWidget(self.count_label)
        queue_header.addStretch()
        queue_header.addWidget(remove)
        queue_header.addWidget(clear)
        left.addLayout(queue_header)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        left.addWidget(self.file_list, 1)
        body.addLayout(left, 1)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(345)
        controls = QVBoxLayout(panel)
        controls.setContentsMargins(22, 20, 22, 20)
        controls.setSpacing(10)
        controls.addWidget(self._section_label("WATERMARK SETTINGS"))

        controls.addWidget(self._field_label("Logo preset"))
        self.logo_combo = QComboBox()
        self.logo_combo.addItems(["RGV", "Custom…"])
        self.logo_combo.setCurrentText(self.settings["watermark_preset"])
        self.logo_combo.currentTextChanged.connect(self._logo_preset_changed)
        controls.addWidget(self.logo_combo)

        self.custom_logo_row = QWidget()
        logo_row = QHBoxLayout(self.custom_logo_row)
        logo_row.setContentsMargins(0, 0, 0, 0)
        self.logo_edit = QLineEdit(self.settings["custom_logo_path"])
        self.logo_edit.setPlaceholderText("Choose a custom logo…")
        logo_button = secondary_button("Browse")
        logo_button.clicked.connect(self._browse_logo)
        logo_row.addWidget(self.logo_edit, 1)
        logo_row.addWidget(logo_button)
        controls.addWidget(self.custom_logo_row)
        self._logo_preset_changed(self.logo_combo.currentText())

        placement = QLabel("Photos: bottom-left  •  Videos: top-right")
        placement.setWordWrap(True)
        placement.setStyleSheet(f"color: {MUTED}; font-size: 9pt;")
        controls.addWidget(placement)

        self.opacity_slider, self.opacity_value = self._add_slider(
            controls, "Opacity", 10, 100, int(self.settings["opacity"]), "%"
        )
        self.size_slider, self.size_value = self._add_slider(
            controls, "Size", 5, 40, int(self.settings["size"]), "%"
        )
        self.margin_slider, self.margin_value = self._add_slider(
            controls, "Margin", 0, 100, int(self.settings["margin"]), " px"
        )

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {BORDER};")
        controls.addWidget(divider)
        controls.addWidget(self._field_label("Output folder"))
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit(self.settings["output_folder"])
        output_button = secondary_button("Browse")
        output_button.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(output_button)
        controls.addLayout(output_row)

        self.ffmpeg_label = QLabel()
        self._refresh_video_engine()
        controls.addWidget(self.ffmpeg_label)
        controls.addStretch()
        self.export_button = QPushButton("Export Watermarked Media")
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.clicked.connect(self._start_export)
        controls.addWidget(self.export_button)
        body.addWidget(panel)
        outer.addLayout(body, 1)

        footer = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {SUCCESS};")
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {MUTED};")
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {MUTED};")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setRange(0, 100)
        footer.addWidget(self.status_dot)
        footer.addWidget(self.status_label)
        footer.addStretch()
        footer.addWidget(self.progress_label)
        footer.addWidget(self.progress)
        outer.addLayout(footer)

    def _section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-size: 11pt; font-weight: 650; margin-bottom: 6px;")
        return label

    def _field_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(f"color: {MUTED}; font-size: 9pt; font-weight: 600; margin-top: 5px;")
        return label

    def _add_slider(self, layout, name, minimum, maximum, value, suffix):
        row = QHBoxLayout()
        label = self._field_label(name)
        value_label = QLabel(f"{value}{suffix}")
        value_label.setStyleSheet("font-size: 9pt;")
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value_label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(lambda current: value_label.setText(f"{current}{suffix}"))
        layout.addLayout(row)
        layout.addWidget(slider)
        return slider, value_label

    def _refresh_video_engine(self):
        ready = find_ffmpeg() is not None
        self.ffmpeg_label.setText("● Video engine ready" if ready else "● Video engine unavailable")
        self.ffmpeg_label.setStyleSheet(f"color: {SUCCESS if ready else WARNING}; font-size: 9pt;")

    def _browse_media(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose photos or videos",
            "",
            "Supported media (*.jpg *.jpeg *.png *.webp *.mp4 *.mov *.avi *.mkv);;All files (*.*)",
        )
        self._add_files(paths)

    def _add_files(self, paths):
        existing = {os.path.normcase(str(path)) for path in self.files}
        additions = [path for path in collect_media(paths) if os.path.normcase(str(path)) not in existing]
        self.files.extend(additions)
        self._refresh_list()
        if additions:
            self._set_status(f"Added {len(additions)} file{'s' if len(additions) != 1 else ''}", SUCCESS)

    def _refresh_list(self):
        self.file_list.clear()
        for path in self.files:
            kind = "PHOTO" if path.suffix.lower() in IMAGE_EXTENSIONS else "VIDEO"
            size = path.stat().st_size / (1024 * 1024)
            item = QListWidgetItem(f"{kind:<6}   {path.name}     {size:.1f} MB")
            item.setToolTip(str(path))
            self.file_list.addItem(item)
        count = len(self.files)
        self.count_label.setText(f"{count} file{'s' if count != 1 else ''}")

    def _remove_selected(self):
        selected_rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()}, reverse=True)
        for row in selected_rows:
            del self.files[row]
        self._refresh_list()

    def _clear_files(self):
        if not self.worker or not self.worker.isRunning():
            self.files.clear()
            self._refresh_list()

    def _browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a transparent watermark logo", "", "Images (*.png *.webp *.jpg *.jpeg)"
        )
        if path:
            self.logo_edit.setText(path)

    def _logo_preset_changed(self, preset):
        self.custom_logo_row.setVisible(preset == "Custom…")

    def _selected_logo_path(self):
        if self.logo_combo.currentText() == "RGV":
            return str(resource_path("assets/rgv_logo.png"))
        return self.logo_edit.text().strip()

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Choose export folder", self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def _settings_values(self):
        return {
            "logo_path": self._selected_logo_path(),
            "watermark_preset": self.logo_combo.currentText(),
            "custom_logo_path": self.logo_edit.text().strip(),
            "output_folder": self.output_edit.text().strip(),
            "opacity": self.opacity_slider.value(),
            "size": self.size_slider.value(),
            "margin": self.margin_slider.value(),
        }

    def _start_export(self):
        if self.worker and self.worker.isRunning():
            return
        logo = Path(self._selected_logo_path())
        output_text = self.output_edit.text().strip()
        if not self.files:
            QMessageBox.information(self, APP_NAME, "Add at least one photo or video to the export queue.")
            return
        if not logo.is_file() or logo.suffix.lower() not in IMAGE_EXTENSIONS:
            QMessageBox.critical(self, APP_NAME, "Choose a valid PNG, JPG, or WEBP watermark logo.")
            return
        if not output_text:
            QMessageBox.critical(self, APP_NAME, "Choose an output folder.")
            return
        if any(path.suffix.lower() in VIDEO_EXTENSIONS for path in self.files) and not find_ffmpeg():
            QMessageBox.critical(self, APP_NAME, "The bundled video engine could not be found.")
            return
        already_exported = [
            path for path in self.files
            if path.stem.lower().endswith("_rgv")
            or any(path.stem.lower().endswith(f"_rgv_{number}") for number in range(2, 100))
        ]
        if already_exported:
            examples = "\n".join(f"• {path.name}" for path in already_exported[:3])
            answer = QMessageBox.warning(
                self,
                APP_NAME,
                "These files appear to be previous watermarked exports:\n\n"
                f"{examples}\n\n"
                "Exporting them again will place a second watermark over the "
                "one already baked into the media. Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        output = Path(output_text)
        try:
            output.mkdir(parents=True, exist_ok=True)
            probe = output / ".rgv_write_test"
            probe.touch()
            probe.unlink()
            save_settings(self._settings_values())
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"The output folder cannot be used:\n{exc}")
            return
        self.export_button.setEnabled(False)
        self.export_button.setText("Exporting…")
        self.progress.setValue(0)
        self._set_status("Preparing export…", ACCENT)
        self.worker = ExportWorker(list(self.files), self._settings_values())
        self.worker.progress.connect(self._update_progress)
        self.worker.status.connect(self._set_status)
        self.worker.completed.connect(self._finish_export)
        self.worker.start()

    def _update_progress(self, value, text):
        self.progress.setValue(value)
        self.progress_label.setText(text)

    def _finish_export(self, completed, errors):
        self.export_button.setEnabled(True)
        self.export_button.setText("Export Watermarked Media")
        self.progress.setValue(100)
        self.progress_label.setText(f"{len(completed)} exported")
        if errors:
            self._set_status(f"Finished with {len(errors)} error(s)", ERROR)
            details = "\n".join(f"• {Path(path).name}: {error}" for path, error in errors[:5])
            QMessageBox.warning(
                self, APP_NAME, f"Exported {len(completed)} file(s). {len(errors)} failed:\n\n{details}"
            )
        else:
            self._set_status(f"Export complete — {len(completed)} file(s)", SUCCESS)
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"Successfully exported {len(completed)} file(s).\n\nOpen the export folder?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                os.startfile(Path(self.output_edit.text()))

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_dot.setStyleSheet(f"color: {color};")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(self, APP_NAME, "An export is running. Close the app anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        try:
            save_settings(self._settings_values())
        except OSError:
            pass
        event.accept()


def run():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(resource_path("assets/rgv_logo.png"))))
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(PANEL))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL_2))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
