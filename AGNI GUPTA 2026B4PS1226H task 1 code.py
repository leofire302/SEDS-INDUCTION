import csv
from datetime import datetime
import math
import os
import sys

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.dates as mdates
from matplotlib.figure import Figure
import pandas as pd
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

INPUT_RAW_CSV = "deep.csv"
OUTPUT_CLEANED_CSV = "cleaned_deep.csv"


#modern dark theme

DARK_THEME_QSS = """
    QMainWindow { background-color: #121212; }
    QWidget { color: #E0E0E0; font-family: 'Segoe UI', sans-serif; }
    QFrame#statCard {
        background-color: #1E1E1E;
        border: 1px solid #2D2D2D;
        border-radius: 8px;
    }
    QTableWidget {
        background-color: #1E1E1E;
        gridline-color: #2D2D2D;
        border: 1px solid #2D2D2D;
        border-radius: 6px;
    }
    QHeaderView::section {
        background-color: #252526;
        color: #00ADB5;
        padding: 4px;
        font-weight: bold;
        border: none;
    }
    QPushButton {
        background-color: #00ADB5;
        color: #FFFFFF;
        font-weight: bold;
        border-radius: 5px;
        padding: 8px 16px;
    }
    QPushButton:hover { background-color: #00FFF5; color: #121212; }
"""


class RealTimeDepthCleaner:

    def __init__(
        self,
        output_csv_path: str,
        max_delta: float = 50.0,
        default_initial: float = 0.0,
    ):
        self.output_csv_path = output_csv_path
        self.max_delta = max_delta
        self.last_valid_val = None
        self.default_initial = default_initial

        with open(self.output_csv_path, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "depth"])

    def process_and_append_point(self, timestamp: str, raw_value) -> str:
        try:
            val = float(raw_value)
            is_valid = not math.isnan(val)
        except (ValueError, TypeError):
            is_valid = False
            val = None

        if self.last_valid_val is None:
            if not is_valid:
                self.last_valid_val = self.default_initial
                cleaned_val_str = f"{self.last_valid_val}!"
            else:
                self.last_valid_val = val
                cleaned_val_str = str(val)
        else:
            if not is_valid or abs(val - self.last_valid_val) > self.max_delta:
                cleaned_val_str = f"{self.last_valid_val}!"
            else:
                self.last_valid_val = val
                cleaned_val_str = str(val)

        with open(self.output_csv_path, mode="a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, cleaned_val_str])

        return cleaned_val_str


class DashboardApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Depth Sensor Telemetry Dashboard")
        self.resize(1100, 700)
        self.setStyleSheet(DARK_THEME_QSS)

        if os.path.exists(OUTPUT_CLEANED_CSV):
            os.remove(OUTPUT_CLEANED_CSV)

        self.cleaner = RealTimeDepthCleaner(OUTPUT_CLEANED_CSV)

        # File parsing setup
        self.raw_df = pd.read_csv(INPUT_RAW_CSV)
        self.raw_df.columns = self.raw_df.columns.str.strip()
        depth_cols = [
            c
            for c in self.raw_df.columns
            if "depth" in c.lower() or "val" in c.lower()
        ]
        self.DEPTH_COL = depth_cols[0] if depth_cols else self.raw_df.columns[-1]
        time_cols = [
            c
            for c in self.raw_df.columns
            if "time" in c.lower() or "date" in c.lower()
        ]
        self.TIME_COL = time_cols[0] if time_cols else None
        self.raw_records = self.raw_df.to_dict(orient="records")

        # UI Layout Construction
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)

        # 1. Top Stat Cards Row
        stats_layout = QHBoxLayout()
        self.card_val = self.create_stat_card("CURRENT DEPTH", "--")
        self.card_flags = self.create_stat_card("ANOMALIES (!)", "0")
        self.card_status = self.create_stat_card("SYSTEM STATUS", "Active")
        stats_layout.addWidget(self.card_val)
        stats_layout.addWidget(self.card_flags)
        stats_layout.addWidget(self.card_status)
        root_layout.addLayout(stats_layout)

        # 2. Main Resizable Splitter (Plot on Left, Data Grid on Right)
        splitter = QSplitter(Qt.Horizontal)

        # Matplotlib Dark Canvas Setup
        self.figure = Figure(figsize=(6, 4), facecolor="#1E1E1E")
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor("#1E1E1E")
        splitter.addWidget(self.canvas)

        # Real-time Table Widget
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Cleaned Depth"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        splitter.addWidget(self.table)
        splitter.setSizes([700, 400])

        root_layout.addWidget(splitter)

        # 3. Bottom Control Toolbar
        controls_layout = QHBoxLayout()
        self.toggle_btn = QPushButton("Pause Monitoring")
        self.toggle_btn.clicked.connect(self.toggle_stream)
        controls_layout.addStretch()
        controls_layout.addWidget(self.toggle_btn)
        root_layout.addLayout(controls_layout)

        # Timer setup
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_pipeline)
        self.timer.start()

    def create_stat_card(self, title: str, default_val: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        layout = QVBoxLayout(card)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #888888; font-size: 11px;")

        lbl_val = QLabel(default_val)
        lbl_val.setStyleSheet(
            "color: #00ADB5; font-size: 20px; font-weight: bold;"
        )
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        card.lbl_val = lbl_val  # Store reference for live updates
        return card

    def update_pipeline(self):
        if self.raw_records:
            row = self.raw_records.pop(0)
            t_stamp = (
                str(row[self.TIME_COL])
                if self.TIME_COL and pd.notna(row.get(self.TIME_COL))
                else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            raw_val = row.get(self.DEPTH_COL)
            cleaned_str = self.cleaner.process_and_append_point(t_stamp, raw_val)

            # Update Stat Cards & Table Row
            self.card_val.lbl_val.setText(cleaned_str)

            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(t_stamp))

            item_val = QTableWidgetItem(cleaned_str)
            if "!" in cleaned_str:
                item_val.setForeground(QColor("#FF4C4C"))  # Highlight red flag
            self.table.setItem(row_idx, 1, item_val)
            self.table.scrollToBottom()

        # Update Chart Canvas
        try:
            df = pd.read_csv(OUTPUT_CLEANED_CSV)
            if df.empty:
                return

            df["is_flagged"] = df["depth"].astype(str).str.contains("!")
            df["numeric_depth"] = (
                df["depth"].astype(str).str.rstrip("!").astype(float)
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Update Anomaly Count Card
            self.card_flags.lbl_val.setText(str(df["is_flagged"].sum()))

            self.ax.clear()
            self.ax.set_facecolor("#1E1E1E")
            self.ax.tick_params(colors="#888888")
            for spine in self.ax.spines.values():
                spine.set_color("#2D2D2D")

            # Dynamic line and anomaly markers
            self.ax.plot(
                df["timestamp"],
                df["numeric_depth"],
                color="#00ADB5",
                linewidth=2,
                label="Depth Trend",
            )
            flagged = df[df["is_flagged"]]
            if not flagged.empty:
                self.ax.scatter(
                    flagged["timestamp"],
                    flagged["numeric_depth"],
                    color="#FF4C4C",
                    s=60,
                    zorder=5,
                    label="Corrected (!)",
                )

            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            self.figure.autofmt_xdate()
            self.ax.grid(True, linestyle="--", alpha=0.2, color="#FFFFFF")
            self.ax.legend(
                loc="upper left", facecolor="#1E1E1E", edgecolor="none"
            )
            self.canvas.draw()
        except Exception:
            pass

    def toggle_stream(self):
        if self.timer.isActive():
            self.timer.stop()
            self.toggle_btn.setText("Resume Monitoring")
            self.card_status.lbl_val.setText("Paused")
            self.card_status.lbl_val.setStyleSheet(
                "color: #FFB300; font-size: 20px; font-weight: bold;"
            )
        else:
            self.timer.start()
            self.toggle_btn.setText("Pause Monitoring")
            self.card_status.lbl_val.setText("Active")
            self.card_status.lbl_val.setStyleSheet(
                "color: #00ADB5; font-size: 20px; font-weight: bold;"
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DashboardApp()
    window.show()
    sys.exit(app.exec_())