import sys
import meshtastic
from meshtastic.serial_interface import SerialInterface
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QTextEdit, QVBoxLayout, QLabel, 
    QLineEdit, QComboBox, QMessageBox, QGroupBox, QStatusBar, QHBoxLayout,
    QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QScrollArea, QProgressBar
)
from PyQt6.QtCore import QTimer, Qt, pyqtSlot, QDateTime, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QTextCursor
import serial.tools.list_ports
from datetime import datetime
import logging
import threading
import queue

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MeshtasticGUI(QWidget):
    message_received = pyqtSignal(str)  # Signal for received messages

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Meshtastic Console")
        self.setGeometry(100, 100, 900, 700)  # Smaller window size
        
        # Dark theme with teal (#26A69A) and square edges
        self.setStyleSheet("""
            QWidget {
                background-color: #1E1E1E;
                color: #26A69A;
                font-family: 'Courier New', monospace;
                font-size: 12pt;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #26A69A;
                margin-top: 15px;
                padding: 10px;
                color: #26A69A;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #26A69A;
            }
            QPushButton {
                background-color: #2D2D2D;
                border: 1px solid #26A69A;
                padding: 5px;
                min-width: 100px;
                color: #26A69A;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
            QLineEdit, QComboBox {
                background-color: #2D2D2D;
                border: 1px solid #26A69A;
                padding: 4px;
                color: #26A69A;
            }
            QTextEdit {
                background-color: #151515;
                border: 1px solid #26A69A;
                color: #26A69A;
            }
            QStatusBar {
                background-color: #2D2D2D;
                border-top: 1px solid #26A69A;
                color: #26A69A;
            }
            QLabel {
                color: #26A69A;
            }
            QTableWidget {
                background-color: #151515;
                border: 1px solid #26A69A;
                color: #26A69A;
                gridline-color: #26A69A;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #26A69A;
                padding: 5px;
                border: 1px solid #26A69A;
            }
            QScrollArea {
                border: none;
            }
        """)

        # Main Layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        # Create a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)  # Allow the widget to resize
        scroll_widget = QWidget()
        scroll_widget.setLayout(main_layout)
        scroll_area.setWidget(scroll_widget)

        # Status Bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Disconnected")
        main_layout.addWidget(self.status_bar)

        # Control Panel
        control_panel = QHBoxLayout()
        control_panel.setSpacing(15)

        # Left Column: Connection and Messaging
        left_column = QVBoxLayout()
        
        # Serial Port Section
        self.serial_group = QGroupBox("Serial Connection")
        serial_layout = QGridLayout()
        serial_layout.setSpacing(8)

        serial_layout.addWidget(QLabel("Port:"), 0, 0)
        self.port_selector = QComboBox(self)
        self.port_selector.setMinimumWidth(150)
        serial_layout.addWidget(self.port_selector, 0, 1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)
        serial_layout.addWidget(self.refresh_button, 0, 2)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_device)
        serial_layout.addWidget(self.connect_button, 1, 1, 1, 2)
        
        self.serial_group.setLayout(serial_layout)
        left_column.addWidget(self.serial_group)

        # Message Section
        self.message_group = QGroupBox("Messaging")
        message_layout = QVBoxLayout()
        message_layout.setSpacing(8)

        self.message_input = QLineEdit(self)
        self.message_input.setMinimumHeight(40)
        self.message_input.setPlaceholderText("Enter message...")
        self.message_input.returnPressed.connect(self.send_message)  # Enter key sends message
        message_layout.addWidget(self.message_input)

        send_layout = QHBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        send_layout.addStretch()
        send_layout.addWidget(self.send_button)
        message_layout.addLayout(send_layout)

        self.message_group.setLayout(message_layout)
        left_column.addWidget(self.message_group)
        
        control_panel.addLayout(left_column)

        # Right Column: Device Settings
        right_column = QVBoxLayout()
        
        # Device Settings
        self.name_group = QGroupBox("Device Settings")
        name_layout = QGridLayout()
        name_layout.setSpacing(8)

        name_layout.addWidget(QLabel("Long Name:"), 0, 0)
        self.device_name_input = QLineEdit(self)
        self.device_name_input.setPlaceholderText("Enter device name...")
        name_layout.addWidget(self.device_name_input, 0, 1)

        name_layout.addWidget(QLabel("Short Name:"), 1, 0)
        self.short_name_input = QLineEdit(self)
        self.short_name_input.setPlaceholderText("Enter 4-char ID...")
        name_layout.addWidget(self.short_name_input, 1, 1)

        self.set_name_button = QPushButton("Apply")
        self.set_name_button.clicked.connect(self.set_device_names)
        name_layout.addWidget(self.set_name_button, 2, 1)
        
        self.name_group.setLayout(name_layout)
        right_column.addWidget(self.name_group)

        control_panel.addLayout(right_column)
        main_layout.addLayout(control_panel)

        # Log Display
        log_group = QGroupBox("Console Log")
        log_layout = QVBoxLayout()
        self.log = QTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Courier New", 10))
        self.log.setPlaceholderText("Console output...")
        log_layout.addWidget(self.log)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, stretch=1)

        # Add loading bar
        self.loading_bar = QProgressBar(self)
        self.loading_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #26A69A;
                border-radius: 2px;
                text-align: center;
                background-color: #1E1E1E;
                color: #26A69A;
                height: 20px;
                margin: 5px;
            }
            QProgressBar::chunk {
                background-color: #26A69A;
                border-radius: 2px;
                width: 10px;
                margin: 1px;
            }
        """)
        self.loading_bar.setMaximum(0)  # Indeterminate progress
        self.loading_bar.hide()
        self.loading_bar.setFixedHeight(20)  # Set fixed height
        main_layout.addWidget(self.loading_bar)

        # Set the scroll area as the main widget
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(scroll_area)

        self.interface = None
        self.received_messages = []

        # Timer for checking messages every 100ms
        self.message_timer = QTimer(self)
        self.message_timer.setInterval(100)
        self.message_timer.timeout.connect(self.check_messages)
        self.message_timer.start()

        # Timer for loading bar delay
        self.loading_timer = QTimer(self)
        self.loading_timer.setSingleShot(True)
        self.loading_timer.timeout.connect(self.hide_loading_bar)

        # Initial port refresh
        self.refresh_ports()

    def hide_loading_bar(self):
        self.loading_bar.hide()
        self.loading_bar.repaint()
        QApplication.processEvents()

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        self.port_selector.clear()
        self.port_selector.addItem("Select port")
        for port in ports:
            self.port_selector.addItem(port.device)

    def connect_device(self):
        port = self.port_selector.currentText()
        if not port or port == "Select port":
            QMessageBox.warning(self, "Error", "No serial port selected")
            return
        
        # Show loading bar and disable controls
        self.loading_bar.show()
        self.loading_bar.setMaximum(0)  # Ensure it's in indeterminate mode
        self.loading_bar.repaint()  # Force immediate repaint
        QApplication.processEvents()  # Process any pending events
        self.port_selector.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.status_bar.showMessage("Connecting...")
        
        try:
            logger.debug(f"Attempting to connect to port: {port}")
            self.interface = SerialInterface(port)
            
            # Set up the receive callback
            def on_receive(packet, interface):
                try:
                    if packet.get("decoded", {}).get("portnum") == "TEXT_MESSAGE_APP":
                        sender = packet.get("from", "Unknown")
                        message = packet.get("decoded", {}).get("payload", {}).get("text", "")
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        
                        # Get sender info
                        sender_info = f"Node {sender}"
                        if hasattr(interface, 'nodes'):
                            node = interface.nodes.get(sender)
                            if node and hasattr(node, 'user'):
                                user = node.user
                                if hasattr(user, 'longName') and user.longName:
                                    sender_info = user.longName
                                elif hasattr(user, 'shortName') and user.shortName:
                                    sender_info = f"{user.shortName} (Node {sender})"
                        
                        formatted_message = f"[{timestamp}] < {sender_info}: {message}"
                        logger.debug(f"Formatted message: {formatted_message}")
                        
                        # Add to received messages list
                        self.received_messages.append(formatted_message)
                except Exception as e:
                    logger.error(f"Receive error: {e}")
                    error_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Receive error: {e}"
                    self.received_messages.append(error_msg)
            
            self.interface.onReceive = on_receive
            
            self.status_bar.showMessage(f"Connected to {port}")
            self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to {port}")
            
            # Clear any existing messages
            self.received_messages.clear()
            self.log.clear()
            
            # Test connection by getting node info
            if self.interface.localNode:
                node_info = self.interface.localNode
                logger.debug(f"Node info: {node_info}")
                # Get node ID from the interface
                node_id = str(self.interface.myInfo.my_node_num)
                self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Node ID: {node_id}")
        except Exception as e:
            logger.error(f"Connection error: {e}")
            QMessageBox.critical(self, "Connection Error", f"Failed to connect: {e}")
            self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Connection failed: {e}")
        finally:
            # Re-enable controls immediately
            self.port_selector.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.connect_button.setEnabled(True)
            
            # Start timer to hide loading bar after 500ms
            self.loading_timer.start(500)

    def check_messages(self):
        if not self.interface:
            return
            
        while self.received_messages:
            message = self.received_messages.pop(0)
            self.log.append(message)
            self.log.moveCursor(QTextCursor.End)
            QApplication.processEvents()

    def send_message(self):
        if not self.interface:
            QMessageBox.warning(self, "Error", "Not connected to device")
            return
        message = self.message_input.text().strip()
        if message:
            try:
                self.interface.sendText(message)
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.log.append(f"[{timestamp}] > You: {message}")
                self.message_input.clear()
            except Exception as e:
                self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to send message: {e}")
                QMessageBox.warning(self, "Error", f"Failed to send message: {e}")

    def set_device_names(self):
        if not self.interface:
            QMessageBox.warning(self, "Error", "Not connected to device")
            return
        long_name = self.device_name_input.text().strip()
        short_name = self.short_name_input.text().strip()
        if not long_name or not short_name:
            QMessageBox.warning(self, "Error", "Both names required")
            return
        if len(short_name) != 4:
            QMessageBox.warning(self, "Error", "Short name must be 4 characters")
            return
        try:
            local_node = self.interface.localNode
            local_node.setOwner(long_name=long_name, short_name=short_name)
            self.interface.sendPosition()
            self.log.append(f"[+]Name updated: {long_name} ({short_name})")
        except Exception as e:
            self.log.append(f"[-]Name update failed: {e}")

    def closeEvent(self, event):
        if self.interface:
            try:
                self.interface.close()
                self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Connection closed")
            except Exception as e:
                logger.error(f"Error closing interface: {e}")
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MeshtasticGUI()
    window.show()
    sys.exit(app.exec())