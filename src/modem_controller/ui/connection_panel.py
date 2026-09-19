"""Connection controls that expose user intent without touching serial hardware."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from modem_controller.transport.serial_port import (
    ControlLinePolicy,
    FlowControl,
    Parity,
    SerialSettings,
)


class ConnectionPanel(QWidget):
    """Presents connection state and settings; an application controller owns I/O."""

    connect_requested = Signal()
    disconnect_requested = Signal()
    refresh_requested = Signal()
    find_settings_requested = Signal()
    diagnostics_requested = Signal()
    cancel_requested = Signal()
    lines_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.port_selector = QComboBox(self)
        self.port_selector.setObjectName("portSelector")
        self.port_selector.setEditable(False)
        self.port_selector.addItem("No port")

        self.status = QLabel("Disconnected", self)
        self.status.setObjectName("connectionStatus")
        self.effective_settings = QLabel("No connection", self)

        self.connect_button = QPushButton("Connect", self)
        self.disconnect_button = QPushButton("Disconnect", self)
        self.refresh_button = QPushButton("Refresh", self)
        self.find_button = QPushButton("Find settings", self)
        self.diagnostics_button = QPushButton("Run diagnostics", self)
        self.cancel_button = QPushButton("Stop", self)
        self.disconnect_button.setEnabled(False)
        self.diagnostics_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

        self.connect_button.clicked.connect(self.connect_requested)
        self.disconnect_button.clicked.connect(self.disconnect_requested)
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.find_button.clicked.connect(self.find_settings_requested)
        self.diagnostics_button.clicked.connect(self.diagnostics_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)

        self.advanced = QGroupBox("Advanced connection", self)
        self.advanced.setCheckable(True)
        self.advanced.setChecked(False)
        advanced_layout = QFormLayout(self.advanced)
        self.baud_rate = QComboBox(self.advanced)
        self.baud_rate.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baud_rate.setCurrentText("115200")
        self.data_bits = QComboBox(self.advanced)
        self.data_bits.addItems(["8", "7"])
        self.parity = QComboBox(self.advanced)
        self.parity.addItems(["N", "E", "O"])
        self.stop_bits = QComboBox(self.advanced)
        self.stop_bits.addItems(["1", "2"])
        self.flow_control = QComboBox(self.advanced)
        self.flow_control.addItems(["None", "RTS/CTS", "DSR/DTR"])
        self.deadline = QSpinBox(self.advanced)
        self.deadline.setRange(100, 60_000)
        self.deadline.setValue(2_000)
        self.deadline.setSuffix(" ms")
        advanced_layout.addRow("Baud rate", self.baud_rate)
        advanced_layout.addRow("Data bits", self.data_bits)
        advanced_layout.addRow("Parity", self.parity)
        advanced_layout.addRow("Stop bits", self.stop_bits)
        advanced_layout.addRow("Flow control", self.flow_control)
        advanced_layout.addRow("Response timeout", self.deadline)
        self.dtr = QComboBox(self)
        self.rts = QComboBox(self)
        for selector in (self.dtr, self.rts):
            selector.addItems(["Driver default", "On", "Off"])
        self.apply_lines = QPushButton("Apply DTR / RTS now", self)
        self.apply_lines.setEnabled(False)
        self.apply_lines.clicked.connect(
            lambda: self.lines_requested.emit(self.selected_lines())
        )
        self.line_status = QLabel("CTS / DSR / RI / CD: unavailable", self)
        self.pacing = QSpinBox(self)
        self.pacing.setRange(0, 100)
        self.pacing.setSuffix(" ms per byte")
        for name, widget in (
            ("DTR", self.dtr),
            ("RTS", self.rts),
            ("", self.apply_lines),
            ("Signals", self.line_status),
            ("Manual TX pacing", self.pacing),
        ):
            advanced_layout.addRow(name, widget)
        self.advanced.toggled.connect(self._set_advanced_visible)
        self._set_advanced_visible(False)

        buttons = QHBoxLayout()
        for button in (
            self.connect_button,
            self.disconnect_button,
            self.refresh_button,
            self.find_button,
            self.diagnostics_button,
            self.cancel_button,
        ):
            buttons.addWidget(button)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("COM port", self.port_selector)
        form.addRow("Status", self.status)
        form.addRow("Active", self.effective_settings)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.advanced)

    def set_ports(self, ports: list[str]) -> None:
        selected = self.port_selector.currentText()
        self.port_selector.clear()
        self.port_selector.addItems(ports or ["No port"])
        if selected in ports:
            self.port_selector.setCurrentText(selected)

    def set_connected(self, connected: bool, settings: str = "") -> None:
        self.status.setText("Connected" if connected else "Disconnected")
        self.effective_settings.setText(settings or "No connection")
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.diagnostics_button.setEnabled(connected)
        self.apply_lines.setEnabled(connected)
        if not connected:
            self.line_status.setText("CTS / DSR / RI / CD: unavailable")

    def selected_lines(self) -> ControlLinePolicy:
        states = {"Driver default": None, "On": True, "Off": False}
        flow = self.flow_control.currentText()
        return ControlLinePolicy(
            dtr=None if flow == "DSR/DTR" else states[self.dtr.currentText()],
            rts=None if flow == "RTS/CTS" else states[self.rts.currentText()],
        )

    def show_lines(self, values: dict[str, bool | None]) -> None:
        self.line_status.setText(
            " | ".join(
                f"{key.upper()}: "
                + ("unavailable" if value is None else "On" if value else "Off")
                for key, value in values.items()
            )
        )

    def selected_settings(self) -> SerialSettings:
        port = self.port_selector.currentText()
        if port == "No port":
            raise ValueError("Select a COM port first.")
        flow_control = {
            "None": FlowControl.NONE,
            "RTS/CTS": FlowControl.RTS_CTS,
            "DSR/DTR": FlowControl.DSR_DTR,
        }[self.flow_control.currentText()]
        return SerialSettings(
            port=port,
            baud_rate=int(self.baud_rate.currentText()),
            data_bits=int(self.data_bits.currentText()),
            parity=Parity(self.parity.currentText()),
            stop_bits=float(self.stop_bits.currentText()),
            flow_control=flow_control,
            response_timeout=self.deadline.value() / 1_000,
            inter_byte_delay=self.pacing.value() / 1_000,
            control_lines=self.selected_lines(),
        )

    def set_connecting(self) -> None:
        self.status.setText("Connecting...")
        self.connect_button.setEnabled(False)

    def preferences(self) -> dict[str, str]:
        return {
            "port": self.port_selector.currentText(),
            "baud_rate": self.baud_rate.currentText(),
            "data_bits": self.data_bits.currentText(),
            "parity": self.parity.currentText(),
            "stop_bits": self.stop_bits.currentText(),
            "flow_control": self.flow_control.currentText(),
            "deadline_ms": str(self.deadline.value()),
            "dtr": self.dtr.currentText(),
            "rts": self.rts.currentText(),
            "pacing_ms": str(self.pacing.value()),
        }

    def apply_preferences(self, preferences: dict[str, str]) -> None:
        port = preferences.get("port", "")
        if port and port != "No port":
            if self.port_selector.findText(port) < 0:
                self.port_selector.addItem(port)
            self.port_selector.setCurrentText(port)
        for selector, key in (
            (self.baud_rate, "baud_rate"),
            (self.data_bits, "data_bits"),
            (self.parity, "parity"),
            (self.stop_bits, "stop_bits"),
            (self.flow_control, "flow_control"),
            (self.dtr, "dtr"),
            (self.rts, "rts"),
        ):
            value = preferences.get(key)
            if value is not None and selector.findText(value) >= 0:
                selector.setCurrentText(value)
        deadline = preferences.get("deadline_ms")
        if deadline is not None and deadline.isdecimal():
            self.deadline.setValue(int(deadline))
        pacing = preferences.get("pacing_ms", "0")
        if pacing.isdecimal():
            self.pacing.setValue(int(pacing))

    def apply_settings(self, settings: SerialSettings) -> None:
        self.apply_preferences(
            {
                "port": settings.port,
                "baud_rate": str(settings.baud_rate),
                "data_bits": str(settings.data_bits),
                "parity": settings.parity.value,
                "stop_bits": f"{settings.stop_bits:g}",
                "deadline_ms": str(int(settings.response_timeout * 1000)),
                "pacing_ms": str(int(settings.inter_byte_delay * 1000)),
                "dtr": {None: "Driver default", True: "On", False: "Off"}[
                    settings.control_lines.dtr
                ],
                "rts": {None: "Driver default", True: "On", False: "Off"}[
                    settings.control_lines.rts
                ],
                "flow_control": {
                    FlowControl.NONE: "None",
                    FlowControl.RTS_CTS: "RTS/CTS",
                    FlowControl.DSR_DTR: "DSR/DTR",
                }[settings.flow_control],
            }
        )

    def set_workflow_active(self, active: bool) -> None:
        self.cancel_button.setEnabled(active)
        self.find_button.setEnabled(not active)
        self.apply_lines.setEnabled(not active and self.disconnect_button.isEnabled())
        self.diagnostics_button.setEnabled(
            not active and not self.connect_button.isEnabled()
        )

    def show_error(self, message: str) -> None:
        self.status.setText(f"Error: {message}")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

    def _set_advanced_visible(self, visible: bool) -> None:
        layout = self.advanced.layout()
        if not isinstance(layout, QFormLayout):
            return
        for row in range(layout.rowCount()):
            for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                item = layout.itemAt(row, role)
                if item is not None and item.widget() is not None:
                    item.widget().setVisible(visible)
