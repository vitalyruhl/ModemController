"""Explicit host-evidence scope and consent, with no collection on selection."""

from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class RasOptionsDialog(QDialog):
    def __init__(self, directory: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RAS collection scope")
        layout = QVBoxLayout(self)
        warning = QLabel(
            "Select only the host evidence you want collected. Reports may identify "
            "devices. Review redacted files before sharing. No modem commands, "
            "dialing or system changes are performed.",
            self,
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.collectors = {}
        for key, label in (
            ("modems", "Installed modem summary"),
            ("ports", "Serial port summary"),
            ("network", "Adapter status (without addresses)"),
            ("ras", "RAS status command availability (names omitted)"),
            ("phonebook", "Current-user phonebook device fields"),
            ("events", "RasClient event IDs, levels and times"),
        ):
            checkbox = QCheckBox(label, self)
            self.collectors[key] = checkbox
            layout.addWidget(checkbox)
        self.destination = QLineEdit(
            str(
                directory
                / ("ras-report-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
            ),
            self,
        )
        self.hours = QSpinBox(self)
        self.hours.setRange(1, 168)
        self.hours.setValue(24)
        form = QFormLayout()
        form.addRow("Event window (hours)", self.hours)
        row = QHBoxLayout()
        row.addWidget(self.destination)
        browse = QPushButton("Choose parent...", self)
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        form.addRow("New output directory", row)
        layout.addLayout(form)
        self.consent = QCheckBox(
            "I consent to this selected local collection and report creation", self
        )
        layout.addWidget(self.consent)
        self.message = QLabel(self)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        parent = QFileDialog.getExistingDirectory(
            self, "Choose report parent directory"
        )
        if parent:
            self.destination.setText(
                str(
                    Path(parent)
                    / ("ras-report-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
                )
            )

    def arguments(self):
        selected = [
            key for key, widget in self.collectors.items() if widget.isChecked()
        ]
        path = Path(self.destination.text())
        if not self.consent.isChecked() or not selected:
            raise ValueError("Select collectors and explicitly consent first")
        if not path.is_absolute() or path.exists() or str(path).startswith("\\\\"):
            raise ValueError("Choose a new absolute local output directory")
        return (
            "-OutputDirectory",
            str(path),
            "-Collectors",
            ",".join(selected),
            "-Hours",
            str(self.hours.value()),
            "-Consent",
        )

    def accept(self):
        try:
            self.arguments()
        except ValueError as error:
            self.message.setText(str(error))
            return
        super().accept()
