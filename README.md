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

## EMG Photo Feature (Read from Photo)

The **📷 Read from photo** button on the data entry form lets you photograph a handwritten EMG sheet and have the data extracted automatically.

### Requirements

- [LM Studio](https://lmstudio.ai) — free desktop app (Mac/Windows/Linux)
- A vision-capable model loaded in LM Studio (tested with **Gemma 4 e4b**)

### Setup

1. Download and install LM Studio
2. Open LM Studio → search for and download **google/gemma-4-e4b** (or any vision model)
3. Load the model → click the **`</>`** icon in the left sidebar → toggle **Start Server**
4. The server runs on `http://localhost:1234` by default — no configuration needed

### Custom port

If LM Studio runs on a different port, set this in your `.env` file:

```
LM_STUDIO_URL=http://localhost:YOUR_PORT
```

### Photo tips

- Good lighting, flat surface, no glare
- All columns must be visible in frame
- HEIC photos (iPhone) are supported — converted automatically
- The model may take 30–60 seconds on complex sheets (reasoning model)

### What it reads

| Column | Expected values |
|---|---|
| Side | L / R / B |
| Muscle | Abbreviation (APB, BB, TA, VM…) |
| Insertion EMG | Brief Normal / Prolonged / Reduced |
| Resting EMG | Silent / Fibrillations / PSWs / Fasciculations / Giant potentials |
| Amplitude | Normal / ↑ / ↓ / Not recordable |
| Duration | Normal / ↑ / ↓ |
| Polyphasic | No / Yes |
| Recruitment | Normal / ↓ / ↑ / Patient couldn't recruit |
| Interference | Normal full / Incomplete / Low amplitude incomplete unitary… |

Always review extracted data before generating the report.

---

## Dependencies

| Package | Purpose |
|---|---|
| Flask | Web framework |
| python-docx | Word document generation |
| striprtf | RTF parsing |
| Pillow | Waveform image processing and autocrop |
| httpx | HTTP client for LM Studio API calls |
| anthropic | Claude AI integration (optional, for report enhancement) |
| python-dotenv | Environment variable management |
