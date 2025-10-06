"""Connection settings pane."""

from __future__ import annotations

from typing import Optional

from .common import (
    QColor,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)


class ConnectionPane(QWidget):  # type: ignore[misc]
    """Simple form for host/port selection."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "connection")
        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Connection Settings")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        host_row = QHBoxLayout()  # type: ignore[call-arg]
        host_label = QLabel("Host:")  # type: ignore[call-arg]
        self.host_edit = QLineEdit("127.0.0.1")  # type: ignore[call-arg]
        host_row.addWidget(host_label)
        host_row.addWidget(self.host_edit)

        port_row = QHBoxLayout()  # type: ignore[call-arg]
        port_label = QLabel("Port:")  # type: ignore[call-arg]
        self.port_edit = QLineEdit("9090")  # type: ignore[call-arg]
        port_row.addWidget(port_label)
        port_row.addWidget(self.port_edit)

        self.connect_button = QPushButton("Connect")  # type: ignore[call-arg]
        self.connect_button.setObjectName("connectButton")
        self.status_label = QLabel("Disconnected")  # type: ignore[call-arg]
        self.status_label.setObjectName("connectionStatus")
        self.status_label.setProperty("statusKind", "idle")
        if Qt is not None:
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)  # type: ignore[attr-defined]

        layout.addLayout(host_row)
        layout.addLayout(port_row)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.status_label)

        if Qt is not None and QGraphicsDropShadowEffect is not None:
            effect = QGraphicsDropShadowEffect(self)
            effect.setOffset(0, 0)
            effect.setBlurRadius(18)
            effect.setColor(QColor("#00B4FF"))
            self.connect_button.setGraphicsEffect(effect)

    def set_status(self, text: str, kind: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("statusKind", kind)
        self._repolish(self.status_label)

    def _repolish(self, widget: QWidget) -> None:
        if Qt is None:
            return
        style = widget.style()
        if style is None:  # pragma: no cover - headless fallback
            return
        style.unpolish(widget)  # type: ignore[attr-defined]
        style.polish(widget)  # type: ignore[attr-defined]
