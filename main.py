#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp Analyzer - Lokale Desktop-App zur Analyse von WhatsApp-Chatverläufen
Funktionen: Import, Transkription (Whisper), Filterung, Zusammenfassung, PDF-Export
"""

import sys
import os
import re
import json
from datetime import datetime, date
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QDateEdit, QTextEdit,
    QListWidget, QListWidgetItem, QGroupBox, QSplitter,
    QProgressBar, QMessageBox, QComboBox, QTabWidget, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QFont, QColor

from dateutil import parser as dateparser
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors


# ─────────────────────────────────────────────
# WhatsApp Parser
# ─────────────────────────────────────────────

WHATSAPP_MSG_RE = re.compile(
    r"^(\d{1,2}[./]\d{1,2}[./]\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap][Mm])?)\s*[-–]\s*([^:]+):\s*(.*)$"
)
AUDIO_RE = re.compile(r"<?(\S+\.(?:opus|ogg|mp3|m4a|aac|wav))>?", re.IGNORECASE)


def parse_whatsapp_export(filepath: str) -> list[dict]:
    """Parst eine WhatsApp-Exportdatei und gibt eine Liste von Nachrichten zurück."""
    messages = []
    base_dir = Path(filepath).parent

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    current_msg = None
    for line in lines:
        line = line.rstrip("\n")
        m = WHATSAPP_MSG_RE.match(line)
        if m:
            if current_msg:
                messages.append(current_msg)
            date_str, time_str, sender, text = m.groups()
            try:
                dt = dateparser.parse(f"{date_str} {time_str}", dayfirst=True)
            except Exception:
                dt = None

            audio_match = AUDIO_RE.search(text)
            audio_file = None
            if audio_match:
                candidate = base_dir / audio_match.group(1)
                if candidate.exists():
                    audio_file = str(candidate)

            current_msg = {
                "datetime": dt,
                "sender": sender.strip(),
                "text": text.strip(),
                "audio_file": audio_file,
                "transcript": None,
            }
        else:
            if current_msg:
                current_msg["text"] += " " + line.strip()

    if current_msg:
        messages.append(current_msg)

    return messages


def filter_messages(messages: list[dict], start: date, end: date,
                    senders: list[str] | None = None) -> list[dict]:
    """Filtert Nachrichten nach Zeitraum und optionalen Absendern."""
    result = []
    for msg in messages:
        if msg["datetime"] is None:
            continue
        msg_date = msg["datetime"].date()
        if not (start <= msg_date <= end):
            continue
        if senders and msg["sender"] not in senders:
            continue
        result.append(msg)
    return result


# ─────────────────────────────────────────────
# Transkriptions-Thread (Whisper)
# ─────────────────────────────────────────────

class TranscriptionWorker(QThread):
    progress = pyqtSignal(int, int)        # current, total
    message_done = pyqtSignal(int, str)    # index, transcript
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, messages: list[dict]):
        super().__init__()
        self.messages = messages

    def run(self):
        try:
            import whisper
            model = whisper.load_model("base")
        except Exception as e:
            self.error.emit(f"Whisper konnte nicht geladen werden: {e}")
            return

        audio_msgs = [(i, m) for i, m in enumerate(self.messages) if m["audio_file"]]
        total = len(audio_msgs)

        for idx, (i, msg) in enumerate(audio_msgs):
            self.progress.emit(idx + 1, total)
            try:
                result = model.transcribe(msg["audio_file"])
                self.message_done.emit(i, result["text"].strip())
            except Exception as e:
                self.message_done.emit(i, f"[Transkriptionsfehler: {e}]")

        self.finished.emit()


# ─────────────────────────────────────────────
# Zusammenfassungs-Funktion (lokal, regelbasiert)
# ─────────────────────────────────────────────

def generate_summary(messages: list[dict]) -> str:
    """Erstellt eine einfache regelbasierte Zusammenfassung der Nachrichten."""
    if not messages:
        return "Keine Nachrichten im gewählten Zeitraum."

    senders = {}
    for msg in messages:
        s = msg["sender"]
        senders[s] = senders.get(s, 0) + 1

    total = len(messages)
    audio_count = sum(1 for m in messages if m["audio_file"])
    start_dt = messages[0]["datetime"]
    end_dt = messages[-1]["datetime"]

    lines = [
        f"=== Zusammenfassung ===",
        f"Zeitraum: {start_dt.strftime('%d.%m.%Y %H:%M')} – {end_dt.strftime('%d.%m.%Y %H:%M')}",
        f"Nachrichten gesamt: {total}",
        f"Sprachnachrichten: {audio_count}",
        "",
        "Aktivität nach Teilnehmer:",
    ]
    for sender, count in sorted(senders.items(), key=lambda x: -x[1]):
        lines.append(f"  • {sender}: {count} Nachrichten")

    lines += ["", "Hinweis: Für eine detaillierte KI-Zusammenfassung kann ein lokales"]
    lines += ["         LLM (z. B. Ollama + LLaMA) in zukünftigen Versionen eingebunden werden."]

    return "\n".join(lines)


# ─────────────────────────────────────────────
# PDF-Export
# ─────────────────────────────────────────────

def export_pdf(filepath: str, messages: list[dict], summary: str | None = None):
    """Exportiert die Nachrichten (und optionale Zusammenfassung) als PDF."""
    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                 fontSize=16, spaceAfter=12)
    meta_style = ParagraphStyle("meta", parent=styles["Normal"],
                                fontSize=9, textColor=colors.grey)
    msg_style = ParagraphStyle("msg", parent=styles["Normal"],
                               fontSize=10, spaceAfter=4, leading=14)
    transcript_style = ParagraphStyle("transcript", parent=styles["Normal"],
                                      fontSize=10, spaceAfter=4,
                                      textColor=colors.darkblue, leading=14)
    summary_style = ParagraphStyle("summary", parent=styles["Normal"],
                                   fontSize=10, leading=14, spaceAfter=6)

    story.append(Paragraph("WhatsApp Analyse", title_style))
    if messages:
        start = messages[0]["datetime"].strftime("%d.%m.%Y")
        end = messages[-1]["datetime"].strftime("%d.%m.%Y")
        story.append(Paragraph(f"Zeitraum: {start} – {end} | {len(messages)} Nachrichten", meta_style))
    story.append(Spacer(1, 0.5*cm))

    for msg in messages:
        dt_str = msg["datetime"].strftime("%d.%m.%Y %H:%M") if msg["datetime"] else ""
        header = f"<b>{msg['sender']}</b> <font size='8' color='grey'>{dt_str}</font>"
        story.append(Paragraph(header, msg_style))

        if msg["audio_file"]:
            if msg["transcript"]:
                story.append(Paragraph(f"🎤 <i>{msg['transcript']}</i>", transcript_style))
            else:
                story.append(Paragraph("🎤 [Sprachnachricht – nicht transkribiert]", transcript_style))
        else:
            safe_text = msg["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_text, msg_style))

        story.append(Spacer(1, 0.2*cm))

    if summary:
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph("Zusammenfassung", title_style))
        for line in summary.split("\n"):
            safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_line or "&nbsp;", summary_style))

    doc.build(story)


# ─────────────────────────────────────────────
# Haupt-GUI
# ─────────────────────────────────────────────

class WhatsAppAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhatsApp Analyzer")
        self.setMinimumSize(1100, 750)
        self.messages: list[dict] = []
        self.filtered_messages: list[dict] = []
        self.summary_text: str | None = None
        self.worker: TranscriptionWorker | None = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # ── Schritt 1: Datei laden ──
        grp_import = QGroupBox("Schritt 1 – WhatsApp-Export laden")
        lay_import = QHBoxLayout(grp_import)
        self.lbl_file = QLabel("Keine Datei geladen")
        btn_open = QPushButton("📂 Datei öffnen …")
        btn_open.clicked.connect(self._load_file)
        lay_import.addWidget(self.lbl_file, 1)
        lay_import.addWidget(btn_open)
        root_layout.addWidget(grp_import)

        # ── Schritt 2: Filter ──
        grp_filter = QGroupBox("Schritt 2 – Filtern")
        lay_filter = QHBoxLayout(grp_filter)

        lay_filter.addWidget(QLabel("Von:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        lay_filter.addWidget(self.date_from)

        lay_filter.addWidget(QLabel("Bis:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        lay_filter.addWidget(self.date_to)

        lay_filter.addWidget(QLabel("Teilnehmer:"))
        self.combo_sender = QComboBox()
        self.combo_sender.addItem("Alle")
        lay_filter.addWidget(self.combo_sender)

        btn_filter = QPushButton("🔍 Filtern")
        btn_filter.clicked.connect(self._apply_filter)
        lay_filter.addWidget(btn_filter)
        root_layout.addWidget(grp_filter)

        # ── Schritt 3: Transkription ──
        grp_trans = QGroupBox("Schritt 3 – Sprachnachrichten transkribieren (Whisper, lokal)")
        lay_trans = QVBoxLayout(grp_trans)
        self.btn_transcribe = QPushButton("🎤 Transkription starten")
        self.btn_transcribe.clicked.connect(self._start_transcription)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        lay_trans.addWidget(self.btn_transcribe)
        lay_trans.addWidget(self.progress_bar)
        root_layout.addWidget(grp_trans)

        # ── Tabs: Original / Zusammenfassung ──
        self.tabs = QTabWidget()

        self.txt_original = QTextEdit()
        self.txt_original.setReadOnly(True)
        self.txt_original.setFont(QFont("Courier", 10))
        self.tabs.addTab(self.txt_original, "📋 Originalverlauf")

        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self.tabs.addTab(self.txt_summary, "📝 Zusammenfassung")

        root_layout.addWidget(self.tabs, 1)

        # ── Schritt 5 & 6: Aktionen ──
        grp_actions = QGroupBox("Auswertung & Export")
        lay_actions = QHBoxLayout(grp_actions)
        btn_summarize = QPushButton("📝 Zusammenfassung erstellen")
        btn_summarize.clicked.connect(self._create_summary)
        btn_pdf = QPushButton("📄 PDF exportieren")
        btn_pdf.clicked.connect(self._export_pdf)
        self.lbl_status = QLabel("")
        lay_actions.addWidget(btn_summarize)
        lay_actions.addWidget(btn_pdf)
        lay_actions.addStretch()
        lay_actions.addWidget(self.lbl_status)
        root_layout.addWidget(grp_actions)

    # ── Slots ──

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "WhatsApp-Export öffnen", "", "Textdateien (*.txt);;Alle Dateien (*)"
        )
        if not path:
            return
        self.messages = parse_whatsapp_export(path)
        self.lbl_file.setText(f"{path}  ({len(self.messages)} Nachrichten erkannt)")

        senders = sorted({m["sender"] for m in self.messages})
        self.combo_sender.clear()
        self.combo_sender.addItem("Alle")
        for s in senders:
            self.combo_sender.addItem(s)

        self._apply_filter()

    def _apply_filter(self):
        start = self.date_from.date().toPyDate()
        end = self.date_to.date().toPyDate()
        sender_sel = self.combo_sender.currentText()
        senders = None if sender_sel == "Alle" else [sender_sel]
        self.filtered_messages = filter_messages(self.messages, start, end, senders)
        self._render_original()
        self.lbl_status.setText(f"{len(self.filtered_messages)} Nachrichten im Zeitraum")

    def _render_original(self):
        lines = []
        for msg in self.filtered_messages:
            dt_str = msg["datetime"].strftime("%d.%m.%Y %H:%M") if msg["datetime"] else ""
            prefix = f"[{dt_str}] {msg['sender']}: "
            if msg["audio_file"]:
                content = f"🎤 {msg['transcript']}" if msg["transcript"] else "🎤 [Sprachnachricht]"
            else:
                content = msg["text"]
            lines.append(prefix + content)
        self.txt_original.setPlainText("\n".join(lines))

    def _start_transcription(self):
        if not self.filtered_messages:
            QMessageBox.warning(self, "Hinweis", "Bitte zuerst Nachrichten filtern.")
            return
        audio_msgs = [m for m in self.filtered_messages if m["audio_file"]]
        if not audio_msgs:
            QMessageBox.information(self, "Hinweis", "Keine Sprachnachrichten im Zeitraum gefunden.")
            return

        self.btn_transcribe.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(audio_msgs))
        self.progress_bar.setValue(0)

        self.worker = TranscriptionWorker(self.filtered_messages)
        self.worker.progress.connect(lambda cur, _: self.progress_bar.setValue(cur))
        self.worker.message_done.connect(self._on_transcript)
        self.worker.finished.connect(self._on_transcription_done)
        self.worker.error.connect(lambda e: QMessageBox.critical(self, "Fehler", e))
        self.worker.start()

    def _on_transcript(self, index: int, text: str):
        self.filtered_messages[index]["transcript"] = text
        # Auch im Original-Datensatz speichern
        orig = self.filtered_messages[index]
        for m in self.messages:
            if m is orig:
                m["transcript"] = text

    def _on_transcription_done(self):
        self.btn_transcribe.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._render_original()
        QMessageBox.information(self, "Fertig", "Transkription abgeschlossen.")

    def _create_summary(self):
        if not self.filtered_messages:
            QMessageBox.warning(self, "Hinweis", "Keine Nachrichten zum Zusammenfassen.")
            return
        self.summary_text = generate_summary(self.filtered_messages)
        self.txt_summary.setPlainText(self.summary_text)
        self.tabs.setCurrentIndex(1)

    def _export_pdf(self):
        if not self.filtered_messages:
            QMessageBox.warning(self, "Hinweis", "Keine Nachrichten zum Exportieren.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "PDF speichern", "whatsapp_analyse.pdf", "PDF-Dateien (*.pdf)"
        )
        if not path:
            return
        try:
            export_pdf(path, self.filtered_messages, self.summary_text)
            QMessageBox.information(self, "Erfolg", f"PDF gespeichert:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"PDF-Export fehlgeschlagen:\n{e}")


# ─────────────────────────────────────────────
# Einstiegspunkt
# ─────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("WhatsApp Analyzer")
    window = WhatsAppAnalyzer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
