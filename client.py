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
        self.member_list=[]

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

    def refresh_groups(self):
        self.send_command("refresh")

    def send_command(self, action: str, group: str = ""):
        msg = {
            "type": "command",
            "from": self.username,
            "action": action,
            "group": group,
        }
        self.pub.send_string(json.dumps(msg))

    def create_group(self) -> None:
        group, ok = QInputDialog.getText(self, "Create Group", "Group name:")
        if ok and group.strip():
            self.send_command("create", group.strip())

    def remove_group(self) -> None:
        group, ok = QInputDialog.getText(self, "Remove Group", "Group name:")
        if ok and group.strip():
            if group.strip() in self.groups:
                self.send_command("remove", group.strip())
            else:
                QMessageBox.warning(self, "Error", "Group does not exist.")

    def on_group_tab_changed(self, index: int):
        if index >= 0:
            group_name = self.group_tabs.tabText(index)
            print(f"group name ============> {group_name}")
            if group_name != "No Groups":
                self.member_list.clear()
                self.member_list.addItem("Join group to see members")
            else:
                self.update_member_list(group_name)

    def update_member_list(self, group_name: str):
        self.member_list.clear()
        if group_name in self.groups:
            for member in sorted(self.groups[group_name]):
                self.member_list.addItem(member)

    def join_current_group(self):
        current_index = self.group_tabs.currentIndex()
        if current_index >= 0:
            current = self.group_tabs.tabText(current_index)
            if current and current != "No Groups":
                if current not in self.joined_groups:
                    self.send_command("join", current)
                    # Update member list immediately after joining
                    self.update_member_list(current)
                else:
                    QMessageBox.information(self, "Info", "Already joined this group.")

    def leave_current_group(self):
        current_index = self.group_tabs.currentIndex()
        if current_index >= 0:
            current = self.group_tabs.tabText(current_index)
            if current in self.joined_groups:
                self.send_command("leave", current)
            else:
                QMessageBox.information(self, "Info", "You haven't joined this group.")

    def send_group_message(self):
        current_index = self.group_tabs.currentIndex()
        if current_index < 0:
            QMessageBox.warning(self, "Error", "Select a group first.")
            return

        current = self.group_tabs.tabText(current_index)
        if not current or current == "No Groups":
            QMessageBox.warning(
                self,
                "Error",
                "Select a group first.",
            )
            return

        if current not in self.joined_groups:
            QMessageBox.warning(
                self,
                "Error",
                "You must join the group to send messages.",
            )
            return

        msg_text = self.message_input.text().strip()
        if msg_text:
            msg = {
                "type": "message",
                "from": self.username,
                "group": current,
                "data": msg_text,
            }
            self.pub.send_string(json.dumps(msg))
            # Echo locally
            tab = self.group_tabs.currentWidget()
            if tab:
                tab.append(f"You: {msg_text}")
            self.message_input.clear()

    def start_private_chat(self, item: Any):
        target = item.text()
        if target == self.username:
            # QMessageBox.warning(self, "Error", "Cannot chat with yourself.")
            return

        if target not in self.private_windows:
            win = PrivateChatWindow(self.username, target)
            win.send_message.connect(self.send_private_message)
            win.show()
            self.private_windows[target] = win
        else:
            self.private_windows[target].activateWindow()

    def send_private_message(self, from_user: str, to_user: str, message: str):
        msg = {
            "type": "message",
            "from": from_user,
            "to": to_user,
            "data": message,
        }
        self.pub.send_string(json.dumps(msg))

    def handle_incoming_message(self, msg: dict):
        mtype = msg.get("type")

        if mtype == "event":
            if "to" in msg and msg["to"] != self.username:
                return  # Not for us

            # Handle group list refresh
            if "groups" in msg:
                groups_data = msg.get("groups", {})
                if isinstance(groups_data, dict):
                    self.groups = {
                        g: set(members) for g, members in groups_data.items()
                    }
                    group_names = list(self.groups.keys())
                    self.update_group_list(group_names)
                return  # No need to process further

            # Handle text events (created, joined, left, etc.)
            data = msg.get("data", "")
            if not data:
                return

            if "created" in data or "removed" in data:
                self.refresh_groups()  # Re-fetch updated list
                QMessageBox.information(self, "Event", data)
            elif "joined" in data or "left" in data:
                parts = data.split()
                if len(parts) >= 3:
                    user = parts[0]
                    group = parts[2].rstrip(".")
                    if group in self.groups:
                        if "joined" in data:
                            self.groups[group].add(user)
                            if user == self.username:
                                self.joined_groups.add(group)
                        elif "left" in data:
                            self.groups[group].discard(user)
                            if user == self.username:
                                self.joined_groups.discard(group)
                        # Update member list if this is the current group
                        current_index = self.group_tabs.currentIndex()
                        if current_index >= 0:
                            current = self.group_tabs.tabText(current_index)
                            if current == group:
                                self.update_member_list(group)
                QMessageBox.information(self, "Event", data)

        elif mtype == "message":
            if "to" in msg:  # Private message
                sender = msg["from"]
                content = msg["data"]

                # Check if we already have a window for this sender
                if sender not in self.private_windows:
                    # Create new window if it doesn't exist
                    win = PrivateChatWindow(self.username, sender)
                    win.send_message.connect(self.send_private_message)
                    win.show()
                    self.private_windows[sender] = win

                # Deliver message to existing window
                self.private_windows[sender].receive_message(sender, content)
            else:  # Group message
                group = msg.get("group", "")
                sender = msg.get("from", "")
                content = msg.get("data", "")
                if group in self.get_all_group_names():
                    tab = self.find_tab_by_name(group)
                    if tab:
                        tab.append(f"{sender}: {content}")

    def update_group_list(self, group_names: list):
        current_index = self.group_tabs.currentIndex()

        # Rebuild tabs
        self.group_tabs.clear()

        if group_names:
            for name in sorted(group_names):
                chat_display = QTextEdit()
                chat_display.setReadOnly(True)
                self.group_tabs.addTab(chat_display, name)
        else:
            # Add placeholder if no groups
            self.group_tabs.addTab(self.group_placeholder, "No Groups")

        # Restore previous tab selection if possible
        if current_index >= 0 and current_index < self.group_tabs.count():
            self.group_tabs.setCurrentIndex(current_index)

        # Trigger UI update
        self.group_tabs.update()

        # Trigger member list update
        if self.group_tabs.count() > 0:
            current_index = self.group_tabs.currentIndex()
            if current_index >= 0:
                current = self.group_tabs.tabText(current_index)
                if current != "No Groups":
                    self.update_member_list(current)
                else:
                    self.member_list.clear()

    def get_all_group_names(self):
        pass

    def find_tab_by_name(self, name: str):
        pass

    def closeEvent(self, event):
        for group in list(self.joined_groups):
            self.send_command("leave", group)
        self.receiver.stop()
        self.pub.close()
        self.context.term()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Simple login dialog
    username, ok = QInputDialog.getText(None, "Login", "Enter your username:")
    if not ok or not username.strip():
        sys.exit()

    is_admin = (
        username.strip().lower() == "admin"
    )  # Simple check — you can improve this

    client = ChatClient(username.strip(), is_admin)
    client.show()

    sys.exit(app.exec_())
