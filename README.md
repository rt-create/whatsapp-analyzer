# WhatsApp Analyzer

Lokale Desktop-App zur Analyse von WhatsApp-Chatverläufen – vollständig offline, datenschutzfreundlich.

## Funktionen

- **Import** exportierter WhatsApp-Textdateien (.txt)
- **Automatische Erkennung** von Sprachnachrichten (opus, ogg, mp3, m4a, aac, wav)
- **Filterung** nach Zeitraum und Teilnehmer
- **Lokale Transkription** via OpenAI Whisper (läuft vollständig offline)
- **Originalverlauf** mit eingebetteten Transkripten
- **Zusammenfassung** (regelbasiert, lokal)
- **PDF-Export** mit Verlauf und optionaler Zusammenfassung

## Voraussetzungen

- Python 3.10+
- FFmpeg installiert und im PATH
- pip

## Installation

```bash
git clone https://github.com/rt-create/whatsapp-analyzer.git
cd whatsapp-analyzer
pip install -r requirements.txt
```

### FFmpeg installieren

macOS: `brew install ffmpeg`

Windows: FFmpeg von https://ffmpeg.org/download.html herunterladen und zum PATH hinzufügen.

Linux (Ubuntu/Debian): `sudo apt install ffmpeg`

## Starten

```bash
python main.py
```

## WhatsApp-Export erstellen

1. WhatsApp öffnen → Chat auswählen
2. Drei Punkte → Mehr → Chat exportieren
3. "Ohne Medien" oder "Mit Medien" wählen
4. Die .txt-Datei (und ggf. Mediendateien) in einen Ordner entpacken
5. In der App auf "Datei öffnen" klicken und die .txt-Datei auswählen

## Projektstruktur

```
whatsapp-analyzer/
├── main.py           # Haupt-Anwendung (GUI + Logik)
├── requirements.txt  # Python-Abhängigkeiten
└── README.md         # Diese Datei
```

## Datenschutz

Alle Verarbeitungsschritte (Transkription, Analyse, PDF-Export) laufen ausschließlich lokal auf dem eigenen Rechner. Es werden keine Daten an externe Server gesendet.

## Technologien

| Komponente | Technologie |
|---|---|
| GUI | PyQt6 |
| Transkription | OpenAI Whisper (lokal) |
| PDF-Export | ReportLab |
| Datumsverarbeitung | python-dateutil |
