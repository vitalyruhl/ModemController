"""Non-modal product information for the desktop application."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton, QVBoxLayout

from modem_controller.versioning import build_info, build_time_label, product_version


class AboutDialog(QDialog):
    """Show stable product identity without exposing build hashes."""

    def __init__(self, parent=None, *, build_metadata: dict | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        self.setWindowTitle("About Modem Controller")
        self.setModal(False)

        metadata = build_info() if build_metadata is None else build_metadata
        self.version_label = QLabel(product_version(), self)
        self.build_label = QLabel(build_time_label(metadata), self)
        self.author_label = QLabel("Vitaly Ruhl", self)
        self.license_label = QLabel("GPL-3.0-only", self)
        for label in (
            self.version_label,
            self.build_label,
            self.author_label,
            self.license_label,
        ):
            label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Product version", self.version_label)
        form.addRow("Build time (UTC)", self.build_label)
        form.addRow("Author", self.author_label)
        form.addRow("License", self.license_label)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(close_button)
