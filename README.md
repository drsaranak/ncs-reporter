# NCS-EMG Report Generator

A web-based report generation tool for nerve conduction studies (NCS) and electromyography (EMG), built for neurophysiology labs. Upload a Neurosoft RTF export, review the auto-generated structured report, and download a formatted Word document — in under a minute.

---

## What it does

- Parses RTF files exported from Neurosoft NCS machines
- Extracts motor NCS, sensory NCS, F-waves, VEP, and EMG data automatically
- Classifies findings (axonal vs demyelinating, sensorimotor vs pure, etc.)
- Generates a structured clinical report with impression
- Optionally enhances the report using Claude AI for natural language quality
- Includes waveform images (NCS + EMG) in the final Word document
- Supports manual EMG data entry via form or photo upload (AI-parsed)
- Exports a ready-to-sign `.docx` report

---

## Supported report types

- NCS only
- EMG only
- NCS + EMG combined
- VEP (Visual Evoked Potentials)

---

## Setup

### Requirements

- Python 3.9+
- LibreOffice (for waveform image conversion)

Install LibreOffice on Mac:
```bash
brew install --cask libreoffice
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run

```bash
python3 app.py
```

Open in browser: [http://localhost:8000](http://localhost:8000)

On hospital LAN: `http://<your-machine-IP>:8000`

---

## Configuration

On first run, go to **Settings** (top-right) to configure:

| Setting | Description |
|---|---|
| Lab name | Appears on all reports |
| Default doctor | Pre-filled on every report |
| Default performed by | Pre-filled on every report |
| Anthropic API key | Optional — enables Claude AI report enhancement |

Settings are saved locally in `data/config.json` and persist across restarts.

### API key (optional)

To enable AI-enhanced report text, add your Anthropic API key via the Settings page, or create a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-...
```

See `.env.example` for reference. The app works fully without an API key — the rule-based report generator runs independently.

---

## Project structure

```
ncs_reporter/
├── app.py               # Flask web app — routes and session management
├── parser.py            # RTF parsing — extracts NCS/EMG data and waveform images
├── classifier.py        # Clinical classification logic
├── report_generator.py  # Rule-based report text generation
├── enhancer.py          # Claude AI report enhancement (optional)
├── docx_generator.py    # Word document generation with tables and images
├── normatives.py        # Reference normative values for NCS parameters
├── templates/           # HTML templates (Jinja2)
├── static/              # CSS and logo
├── data/                # Config and corrections (local, gitignored)
├── sessions/            # Temporary session files (local, gitignored)
└── requirements.txt
```

---

## Privacy

Patient data never leaves your machine. Sessions, outputs, and RTF files are stored locally only and are excluded from this repository via `.gitignore`. The tool is designed to run entirely on a local network — no cloud uploads except optional Claude AI API calls for report enhancement (text only, no patient identifiers).

---

## Dependencies

| Package | Purpose |
|---|---|
| Flask | Web framework |
| python-docx | Word document generation |
| striprtf | RTF parsing |
| Pillow | Waveform image processing and autocrop |
| anthropic | Claude AI integration (optional) |
| python-dotenv | Environment variable management |
