import json
import sys
from typing import Any
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QListWidget,
    QLabel,
    QInputDialog,
    QMessageBox,
)
from PyQt5.QtCore import QThread, pyqtSignal
import zmq

from private_chat import PrivateChatWindow


class ZMQReceiverThread(QThread):
    message_received = pyqtSignal(dict)

    def __init__(self, sub_addr: str):
        super().__init__()
        self.sub_addr = sub_addr
        self.context = zmq.Context()
        self.sub = self.context.socket(zmq.SUB)
        self.sub.connect(self.sub_addr)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "")
    
    def run(self):
        while True:
            try:
                raw = self.sub.recv_string()
                msg = json.loads(raw)
                self.message_received.emit(msg)
            except Exception as e:
                print(str(e))
                pass

    def stop(self):
        self.sub.close()
        self.context.term()


class ChatClient(QMainWindow):
    def __init__(self, username: str, is_admin: bool = False) -> None:
        super().__init__()
        self.username = username
        self.is_admin = is_admin
        self.groups: dict[str, set[str]] = {}
        self.joined_groups: set[str] = set()
        self.private_windows: dict[str, PrivateChatWindow] = {}

        # ZMQ setup
        self.context = zmq.Context()
        self.pub = self.context.socket(zmq.PUB)
        self.pub.connect("tcp://localhost:6001")  # to provider SUB (for sending)

        # Start listening thread
        self.receiver = ZMQReceiverThread(
            "tcp://localhost:6000"
        )  # to provider PUB (for receiving)
        self.receiver.message_received.connect(self.handle_incoming_message)
        self.receiver.start()

        self.init_ui()
        self.refresh_groups()

    def init_ui(self) -> None:
        self.setWindowTitle(
            f"Chat Client - {self.username} ({'Admin' if self.is_admin else 'User'})"
        )
        self.setGeometry(100, 100, 800, 600)

        # Add a placeholder for group names
        self.group_placeholder = QTextEdit()
        self.group_placeholder.setPlainText(
            "No groups available. As an admin, you can create groups."
            if self.is_admin
            else "No groups available. Please wait for an admin to create groups."
        )
        self.group_placeholder.setReadOnly(True)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Top: User info + Admin buttons
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel(f"Logged in as: {self.username}"))
        if self.is_admin:
            self.create_group_btn = QPushButton("Create Group")
            self.create_group_btn.clicked.connect(self.create_group)
            top_layout.addWidget(self.create_group_btn)

            self.remove_group_btn = QPushButton("Remove Group")
            self.remove_group_btn.clicked.connect(self.remove_group)
            top_layout.addWidget(self.remove_group_btn)

            self.refresh_btn = QPushButton("Refresh Groups")
            self.refresh_btn.clicked.connect(self.refresh_groups)
            top_layout.addWidget(self.refresh_btn)

        main_layout.addLayout(top_layout)

        # Middle: Group Tabs + Member List
        mid_layout = QHBoxLayout()

        self.group_tabs = QTabWidget()
        self.group_tabs.addTab(self.group_placeholder, "No Groups")
        self.group_tabs.currentChanged.connect(self.on_group_tab_changed)
        mid_layout.addWidget(self.group_tabs, 3)

        main_layout.addLayout(mid_layout)

        # Bottom: Message input + Send
        bottom_layout = QHBoxLayout()
        self.message_input = QLineEdit()
        bottom_layout.addWidget(self.message_input)

        self.send_btn = QPushButton("Send to Group")
        self.send_btn.clicked.connect(self.send_group_message)
        bottom_layout.addWidget(self.send_btn)

        main_layout.addLayout(bottom_layout)

        # Initial group list refresh
        self.refresh_groups()
