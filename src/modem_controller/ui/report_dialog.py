"""Preview before explicit redacted or raw evidence export."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from modem_controller.catalog.storage import StorageError
from modem_controller.workflows.reporting import (
    export_raw_capture,
    report_text,
    save_report,
)


class ReportDialog(QDialog):
    directory_used = Signal(str, str)

    def __init__(self, report, capture, directory: Path, parent=None):
        super().__init__(parent)
        self._report = report
        self._capture = capture
        self._directory = directory
        self.setWindowTitle("Diagnostic report preview")
        self.resize(850, 650)
        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setPlainText(report_text(report))
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        actions = QHBoxLayout()
        for title, callback in (
            ("Export text", lambda: self._export(True)),
            ("Export JSON", lambda: self._export(False)),
            ("Export sensitive raw bytes...", self._raw),
        ):
            button = QPushButton(title, self)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.preview)
        layout.addLayout(actions)
        layout.addWidget(self.message)

    def _choose(self, extension: str) -> Path | None:
        name, _ = QFileDialog.getSaveFileName(
            self,
            "Export evidence",
            str(self._directory / f"modem-report.{extension}"),
            f"Evidence (*.{extension})",
        )
        return Path(name) if name else None

    def _export(self, text: bool) -> None:
        path = self._choose("txt" if text else "json")
        if path is None:
            return
        try:
            save_report(path, self._report, text=text)
            self._saved(path)
        except StorageError as error:
            self.message.setText(str(error))

    def _raw(self) -> None:
        if (
            QMessageBox.warning(
                self,
                "Sensitive raw capture",
                "Raw bytes can include identifiers, phone numbers and message text. "
                "The file concatenates retained TX/RX records in capture order; "
                "it has no direction delimiters. Gaps shown in the report remain gaps. "
                "Export this separate binary file?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        path = self._choose("bin")
        if path is None:
            return
        try:
            export_raw_capture(path, self._capture.records, confirmed=True)
            self._saved(path)
        except StorageError as error:
            self.message.setText(str(error))

    def _saved(self, path: Path) -> None:
        self._directory = path.parent
        self.directory_used.emit("reports", str(path.parent))
        self.message.setText(f"Saved: {path}")
