from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
)
from PyQt5.QtCore import pyqtSignal


class PrivateChatWindow(QWidget):
    send_message = pyqtSignal(str, str, str)

    def __init__(self, local_user: str, target_user: str) -> None:
        super().__init__()
        self.local_user = local_user
        self.target_user = target_user
        self.setWindowTitle(f"Private Chat: {local_user} ↔ {target_user}")
        self.setGeometry(200, 200, 400, 500)

        layout = QVBoxLayout()

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(QLabel(f"Chat with {target_user}"))
        layout.addWidget(self.chat_display)

        self.input_box = QLineEdit()
        layout.addWidget(self.input_box)

        send_button = QPushButton("Send")
        send_button.clicked.connect(self.on_send)
        layout.addWidget(send_button)

        self.setLayout(layout)

    def on_send(self) -> None:
        msg = self.input_box.text().strip()
        if msg:
            self.send_message.emit(self.local_user, self.target_user, msg)
            self.display_message(f"You: {msg}")
            self.input_box.clear()

    def receive_message(self, sender: str, message: str) -> None:
        self.display_message(f"{sender}: {message}")

    def display_message(self, text: str) -> None:
        self.chat_display.append(text)
