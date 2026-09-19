"""Non-executing legacy preview with explicit selection before import."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from modem_controller.transport.privacy import contains_secret_input


class LegacyImportDialog(QDialog):
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.setWindowTitle("Legacy import preview")
        self.resize(950, 600)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Choose entries to import. Every imported command stays disabled "
            "until its applicability, syntax and risk are reviewed. "
            "Source files remain unchanged.",
            self,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.table = QTableWidget(len(entries), 3, self)
        self.table.setHorizontalHeaderLabels(
            ["Select / label", "Original command", "Review warnings"]
        )
        for row, entry in enumerate(entries):
            secret = contains_secret_input(entry.payload.encode("utf-8"))
            item = QTableWidgetItem(entry.label)
            item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
                if not secret
                else Qt.NoItemFlags
            )
            item.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, item)
            for column, value in (
                (1, "<credential literal excluded>" if secret else entry.payload),
                (2, " ".join(entry.warnings) or "Review before enabling"),
            ):
                cell = QTableWidgetItem(value)
                cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, column, cell)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_entries(self):
        return tuple(
            entry
            for row, entry in enumerate(self.entries)
            if self.table.item(row, 0).checkState() == Qt.Checked
        )
