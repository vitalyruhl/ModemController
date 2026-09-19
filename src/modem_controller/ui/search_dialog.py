"""Explicit scope and bounded extended options for a serial settings search."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from modem_controller.transport.serial_port import FlowControl, Parity
from modem_controller.workflows.connection_search import ConnectionSearchRunner


class SearchOptionsDialog(QDialog):
    def __init__(self, base, preferred=(), parent=None):
        super().__init__(parent)
        self._base = base
        self._preferred = preferred
        self.candidates = ()
        self.setWindowTitle("Find working connection settings")
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Search this COM port only, using AT and the selected terminator. "
            "Opening a port can affect DTR/RTS. Avoid active data calls. "
            "Quick search tries preferred settings first, then five common rates. "
            "Autobaud may accept several rates; saved modem settings remain unknown.",
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.extended = QCheckBox(
            "Also try selected extended combinations (maximum 60)", self
        )
        layout.addWidget(self.extended)
        self.options = {}
        form = QFormLayout()
        for name, choices in (
            ("Data bits", (8, 7)),
            ("Parity", tuple(Parity)[:3]),
            ("Stop bits", (1, 2)),
            ("Flow control", tuple(FlowControl)),
        ):
            widget = QListWidget(self)
            widget.setMaximumHeight(85)
            for index, value in enumerate(choices):
                item = QListWidgetItem(str(getattr(value, "value", value)), widget)
                item.setData(Qt.UserRole, value)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if index == 0 else Qt.Unchecked)
            widget.setEnabled(False)
            self.extended.toggled.connect(widget.setEnabled)
            self.options[name] = widget
            form.addRow(name, widget)
        layout.addLayout(form)
        self.message = QLabel(self)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._accept_scope)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _selected(self, name):
        widget = self.options[name]
        return tuple(
            widget.item(index).data(Qt.UserRole)
            for index in range(widget.count())
            if widget.item(index).checkState() == Qt.Checked
        )

    def _accept_scope(self):
        try:
            quick = ConnectionSearchRunner.quick_candidates(
                self._base.port, preferred=self._preferred, base=self._base
            )
            extra = (
                ConnectionSearchRunner.extended_candidates(
                    self._base,
                    data_bits=self._selected("Data bits"),
                    parities=self._selected("Parity"),
                    stop_bits=self._selected("Stop bits"),
                    flow_controls=self._selected("Flow control"),
                )
                if self.extended.isChecked()
                else ()
            )
            unique = {candidate.settings: candidate for candidate in (*quick, *extra)}
            self.candidates = tuple(unique.values())
        except ValueError as error:
            self.message.setText(str(error))
            return
        self.accept()
