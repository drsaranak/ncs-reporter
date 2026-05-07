"""
app.py — Flask web application for NCS-EMG Report Generator.
NCS-EMG Lab, Department of Physiology, AIIMS Patna.

Run:  python3 app.py
Access via browser: http://localhost:5000
On hospital LAN: http://<host-IP>:5000
"""

import os
import uuid
import json
import datetime
from pathlib import Path

from flask import (Flask, render_template, request, redirect, url_for,
                   send_file, session, flash, jsonify)
from dotenv import load_dotenv
import io

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

BASE_DIR = Path(__file__).parent
SESSIONS_DIR = BASE_DIR / 'sessions'
DATA_DIR = BASE_DIR / 'data'
CORRECTIONS_FILE = DATA_DIR / 'corrections.json'
CONFIG_FILE = DATA_DIR / 'config.json'

SESSIONS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {
        'lab_name': 'NCS-EMG LAB, DEPARTMENT OF PHYSIOLOGY, AIIMS PATNA',
        'default_doctor': 'Dr. Yogesh Kumar',
        'default_performed_by': 'Mr. Manish Kumar',
    }


def save_config(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


# ── Session helpers ───────────────────────────────────────────────────────────

def save_session_data(session_id, data):
    path = SESSIONS_DIR / f'{session_id}.json'
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def load_session_data(session_id):
    path = SESSIONS_DIR / f'{session_id}.json'
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def clean_old_sessions():
    """Remove session files older than 24 hours."""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
    for f in SESSIONS_DIR.glob('*.json'):
        if datetime.datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink(missing_ok=True)


# ── Corrections helpers ───────────────────────────────────────────────────────

def load_corrections():
    if CORRECTIONS_FILE.exists():
        with open(CORRECTIONS_FILE) as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []


def save_correction(entry):
    data = load_corrections()
    data.append(entry)
    with open(CORRECTIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)


# ── Image helpers ─────────────────────────────────────────────────────────────

def _autocrop_png_file(png_path, pad=20):
    """
    Crop white/near-white borders from a PNG file in-place.
    WMF→PNG from LibreOffice always leaves large white margins around the trace.
    """
    try:
        from PIL import Image, ImageChops
        img = Image.open(png_path).convert('RGB')
        bg = Image.new('RGB', img.size, (255, 255, 255))
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox:
            w, h = img.size
            x0 = max(0, bbox[0] - pad)
            y0 = max(0, bbox[1] - pad)
            x1 = min(w, bbox[2] + pad)
            y1 = min(h, bbox[3] + pad)
            img.crop((x0, y0, x1, y1)).save(png_path)
    except Exception:
        pass


# ── Image conversion helper ───────────────────────────────────────────────────

def _convert_images_to_png_b64(raw_images):
    """
    Convert a list of {'label': str, 'wmf_bytes': bytes} to
    {'label': str, 'png_b64': str} using a single LibreOffice batch call.
    Falls back to storing wmf_b64 if LibreOffice is unavailable.
    """
    import base64, tempfile, subprocess, shutil
    try:
        from docx_generator import LIBREOFFICE
    except Exception:
        LIBREOFFICE = None

    if not raw_images:
        return []

    if not LIBREOFFICE:
        return [{'label': img['label'],
                 'png_b64': None,
                 'wmf_b64': base64.b64encode(img['wmf_bytes']).decode('ascii')}
                for img in raw_images]

    tmp_dir = tempfile.mkdtemp(prefix='ncs_conv_')
    try:
        wmf_paths = []
        for i, img in enumerate(raw_images):
            p = os.path.join(tmp_dir, f'img_{i:02d}.wmf')
            with open(p, 'wb') as f:
                f.write(img['wmf_bytes'])
            wmf_paths.append(p)

        subprocess.run(
            [LIBREOFFICE, '--headless', '--convert-to', 'png'] + wmf_paths + ['--outdir', tmp_dir],
            capture_output=True, timeout=120
        )

        result = []
        for i, img in enumerate(raw_images):
            png_path = wmf_paths[i].replace('.wmf', '.png')
            if os.path.exists(png_path):
                _autocrop_png_file(png_path)
                with open(png_path, 'rb') as f:
                    png_b64 = base64.b64encode(f.read()).decode('ascii')
                result.append({'label': img['label'], 'png_b64': png_b64, 'wmf_b64': None})
            else:
                result.append({'label': img['label'], 'png_b64': None,
                               'wmf_b64': base64.b64encode(img['wmf_bytes']).decode('ascii')})
        return result
    except Exception:
        return [{'label': img['label'], 'png_b64': None,
                 'wmf_b64': base64.b64encode(img['wmf_bytes']).decode('ascii')}
                for img in raw_images]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    clean_old_sessions()
    config = load_config()
    return render_template('index.html', config=config)


@app.route('/parse', methods=['POST'])
def parse():
    """Parse uploaded RTF and redirect to form."""
    from parser import parse_rtf

    session_id = str(uuid.uuid4())
    parsed_data = {}
    report_types = []

    rtf_file = request.files.get('rtf_file')
    if rtf_file and rtf_file.filename:
        import base64
        from parser import extract_emg_images, extract_ncs_images
        # Save temporarily
        tmp_path = SESSIONS_DIR / f'{session_id}_input.rtf'
        rtf_file.save(str(tmp_path))
        try:
            parsed_data = parse_rtf(str(tmp_path))
            report_types = parsed_data.get('report_type', ['NCS'])
            # Extract waveform images while RTF is still on disk
            raw_images = extract_emg_images(str(tmp_path))
            emg_images_b64 = _convert_images_to_png_b64(raw_images)
            raw_ncs_images = extract_ncs_images(str(tmp_path), parsed_data=parsed_data)
            ncs_images_b64 = _convert_images_to_png_b64(raw_ncs_images)
        except Exception as e:
            flash(f'Could not parse RTF file: {e}', 'error')
            return redirect(url_for('index'))
        finally:
            tmp_path.unlink(missing_ok=True)

    # Apply config defaults to patient demographics
    config = load_config()
    if parsed_data.get('patient'):
        pt = parsed_data['patient']
        # Always use config defaults — RTF values for these fields are unreliable
        pt['doctor'] = config.get('default_doctor', 'Dr. Yogesh Kumar')
        pt['performed_by'] = config.get('default_performed_by', 'Mr. Manish Kumar')

    # Override with user-selected checkboxes if provided
    selected_types = request.form.getlist('report_types')
    if selected_types:
        report_types = selected_types

    # For EMG-only with manual demographics (no RTF uploaded)
    if not rtf_file or not rtf_file.filename:
        emg_images_b64 = []
        ncs_images_b64 = []
        parsed_data['patient'] = {
            'name': request.form.get('pt_name', ''),
            'age': request.form.get('pt_age', ''),
            'sex': request.form.get('pt_sex', ''),
            'age_sex': f"{request.form.get('pt_age', '')} years / {request.form.get('pt_sex', '')}",
            'id': request.form.get('pt_id', ''),
            'date': request.form.get('pt_date', ''),
            'referring_dept': request.form.get('pt_dept', ''),
            'doctor': request.form.get('pt_doctor', '') or config.get('default_doctor', 'Dr. Yogesh Kumar'),
            'diagnosis': request.form.get('pt_diagnosis', ''),
            'performed_by': request.form.get('pt_performed_by', '') or config.get('default_performed_by', 'Mr. Manish Kumar'),
        }
        parsed_data['motor_ncs'] = []
        parsed_data['sensory_ncs'] = []
        parsed_data['f_waves'] = []
        parsed_data['vep'] = []

    parsed_data['report_type'] = report_types
    save_session_data(session_id, {
        'parsed': parsed_data,
        'report_types': report_types,
        'emg_images': emg_images_b64,
        'ncs_images': ncs_images_b64,
    })
    return redirect(url_for('form_page', sid=session_id))


@app.route('/form')
def form_page():
    sid = request.args.get('sid')
    data = load_session_data(sid)
    if not data:
        flash('Session expired. Please upload again.', 'error')
        return redirect(url_for('index'))
    config = load_config()
    return render_template('form.html',
                           parsed=data['parsed'],
                           report_types=data['report_types'],
                           sid=sid,
                           config=config)


def _combine_interference(amp, complete, unitary):
    """
    Combine 3 interference sub-fields into a single descriptive phrase.
      amp:      Normal | ↑ Large | ↓ Small | Patient couldn't recruit
      complete: Complete | Incomplete | Patient couldn't recruit
      unitary:  No | Yes | Single unit | Patient couldn't recruit
    """
    if "couldn't recruit" in (amp + complete + unitary):
        return "Patient couldn't recruit"
    if unitary == 'Single unit':
        return 'Single unit discharge'

    amp_map  = {'Normal': '', '↑ Large': 'Large amplitude', '↓ Small': 'Small amplitude'}
    amp_str  = amp_map.get(amp, '')
    comp_str = complete   # 'Complete' or 'Incomplete'
    unit_str = ' unitary pattern' if unitary == 'Yes' else ''

    if not amp_str and comp_str == 'Complete' and not unit_str:
        return 'Normal full'

    parts = ' '.join(filter(None, [amp_str, comp_str.lower()])) + unit_str
    return parts.strip().capitalize()


@app.route('/generate', methods=['POST'])
def generate():
    """Run full pipeline: classify → generate → optional enhance → save session."""
    from classifier import run_classification
    from report_generator import generate_report
    from enhancer import enhance_report

    sid = request.form.get('sid')
    data = load_session_data(sid)
    if not data:
        flash('Session expired.', 'error')
        return redirect(url_for('index'))

    parsed_data = data['parsed']
    report_types = data.get('report_types', ['NCS'])

    # Apply any manually edited demographics from the form
    if request.form.get('pt_name'):
        parsed_data['patient']['name'] = request.form.get('pt_name', '')
    if request.form.get('pt_id'):
        parsed_data['patient']['id'] = request.form.get('pt_id', '')
    if request.form.get('pt_date'):
        parsed_data['patient']['date'] = request.form.get('pt_date', '')
    if request.form.get('pt_dept'):
        parsed_data['patient']['referring_dept'] = request.form.get('pt_dept', '')
    if request.form.get('pt_doctor'):
        parsed_data['patient']['doctor'] = request.form.get('pt_doctor', '')
    if request.form.get('pt_performed_by'):
        parsed_data['patient']['performed_by'] = request.form.get('pt_performed_by', '')
    if request.form.get('pt_diagnosis'):
        parsed_data['patient']['diagnosis'] = request.form.get('pt_diagnosis', '')

    # Collect EMG form data
    emg_form_data = []
    emg_muscles = request.form.getlist('emg_muscle[]')
    emg_sides = request.form.getlist('emg_side[]')
    emg_insertions = request.form.getlist('emg_insertion[]')
    emg_restings = request.form.getlist('emg_resting[]')
    emg_amplitudes = request.form.getlist('emg_amplitude[]')
    emg_durations = request.form.getlist('emg_duration[]')
    emg_polyphasics = request.form.getlist('emg_polyphasic[]')
    emg_recruitments = request.form.getlist('emg_recruitment[]')
    emg_interf_amps      = request.form.getlist('emg_interf_amp[]')
    emg_interf_completes = request.form.getlist('emg_interf_complete[]')
    emg_interf_unitaries = request.form.getlist('emg_interf_unitary[]')
    emg_notes = request.form.getlist('emg_notes[]')

    for i, muscle in enumerate(emg_muscles):
        if muscle.strip():
            emg_form_data.append({
                'muscle': muscle,
                'side': emg_sides[i] if i < len(emg_sides) else '',
                'insertion': emg_insertions[i] if i < len(emg_insertions) else 'Brief Normal',
                'resting': emg_restings[i] if i < len(emg_restings) else 'Silent',
                'amplitude': emg_amplitudes[i] if i < len(emg_amplitudes) else 'Normal',
                'duration': emg_durations[i] if i < len(emg_durations) else 'Normal',
                'polyphasic': emg_polyphasics[i] if i < len(emg_polyphasics) else 'No',
                'recruitment': emg_recruitments[i] if i < len(emg_recruitments) else 'Normal',
                'interference': _combine_interference(
                    emg_interf_amps[i]      if i < len(emg_interf_amps)      else 'Normal',
                    emg_interf_completes[i] if i < len(emg_interf_completes) else 'Complete',
                    emg_interf_unitaries[i] if i < len(emg_interf_unitaries) else 'No',
                ),
                'notes': emg_notes[i] if i < len(emg_notes) else '',
            })

    # Patient age for paediatric gating
    age_str = parsed_data.get('patient', {}).get('age', '')
    try:
        age_years = float(age_str)
    except (ValueError, TypeError):
        age_years = None

    sex = parsed_data.get('patient', {}).get('sex', '')

    # Classification
    classification = run_classification(parsed_data, age_years, sex)

    # Rule-based report
    report_dict = generate_report(parsed_data, classification, emg_form_data, report_types)

    # Optional Claude enhancement
    enhanced_report, was_enhanced = enhance_report(
        report_dict, parsed_data, classification, str(CORRECTIONS_FILE)
    )

    # Save to session
    data['emg_form_data'] = emg_form_data
    data['classification'] = classification
    data['report_dict'] = enhanced_report
    data['was_enhanced'] = was_enhanced
    save_session_data(sid, data)

    return redirect(url_for('report_page', sid=sid))


@app.route('/report')
def report_page():
    sid = request.args.get('sid')
    data = load_session_data(sid)
    if not data:
        flash('Session expired.', 'error')
        return redirect(url_for('index'))
    config = load_config()
    return render_template('report.html',
                           report=data.get('report_dict', {}),
                           classification=data.get('classification', {}),
                           parsed=data.get('parsed', {}),
                           was_enhanced=data.get('was_enhanced', False),
                           report_types=data.get('report_types', []),
                           ncs_images_count=len(data.get('ncs_images', [])),
                           ncs_image_labels=[img['label'] for img in data.get('ncs_images', [])],
                           emg_images_count=len(data.get('emg_images', [])),
                           emg_image_labels=[img['label'] for img in data.get('emg_images', [])],
                           sid=sid,
                           config=config)


@app.route('/ncs_preview/<sid>/<int:idx>')
def ncs_preview(sid, idx):
    """Serve a pre-converted NCS waveform PNG from session cache."""
    import base64

    data = load_session_data(sid)
    if not data:
        return 'Session expired', 404

    ncs_images = data.get('ncs_images', [])
    if idx >= len(ncs_images):
        return 'Not found', 404

    img = ncs_images[idx]
    png_b64 = img.get('png_b64')
    if png_b64:
        return base64.b64decode(png_b64), 200, {'Content-Type': 'image/png'}
    return 'Image not available', 404


@app.route('/emg_preview/<sid>/<int:idx>')
def emg_preview(sid, idx):
    """Serve a pre-converted EMG waveform PNG from session cache."""
    import base64

    data = load_session_data(sid)
    if not data:
        return 'Session expired', 404

    emg_images = data.get('emg_images', [])
    if idx >= len(emg_images):
        return 'Not found', 404

    img = emg_images[idx]
    png_b64 = img.get('png_b64')
    if png_b64:
        return base64.b64decode(png_b64), 200, {'Content-Type': 'image/png'}
    return 'Image not available', 404


@app.route('/download', methods=['POST'])
def download():
    """Save correction if edited, then serve DOCX."""
    from docx_generator import generate_docx

    sid = request.form.get('sid')
    data = load_session_data(sid)
    if not data:
        return 'Session expired', 404

    config = load_config()
    parsed_data = data.get('parsed', {})
    report_types = data.get('report_types', ['NCS'])
    emg_form_data = data.get('emg_form_data', [])
    original_report = data.get('report_dict', {})

    # Get (possibly edited) report text from form
    edited_report = {
        'intro': request.form.get('intro', original_report.get('intro', '')),
        'motor_summary': request.form.get('motor_summary', original_report.get('motor_summary', '')),
        'sensory_summary': request.form.get('sensory_summary', original_report.get('sensory_summary', '')),
        'fwave_summary': request.form.get('fwave_summary', original_report.get('fwave_summary', '')),
        'emg_summary': request.form.get('emg_summary', original_report.get('emg_summary', '')),
        'vep_summary': request.form.get('vep_summary', original_report.get('vep_summary', '')),
        'impression': request.form.get('impression', original_report.get('impression', '')),
    }

    was_edited = any(
        edited_report.get(k, '').strip() != original_report.get(k, '').strip()
        for k in edited_report
    )

    if was_edited:
        patient = parsed_data.get('patient', {})
        save_correction({
            'timestamp': datetime.datetime.now().isoformat(),
            'patient_id': patient.get('id', ''),
            'report_type': report_types,
            'input_summary': f"Motor: {len(parsed_data.get('motor_ncs', []))} rows, Sensory: {len(parsed_data.get('sensory_ncs', []))} rows",
            'rule_draft': json.dumps(original_report),
            'claude_enhanced': data.get('was_enhanced', False),
            'final_report': json.dumps(edited_report),
            'was_edited': True,
            'edit_summary': 'User edited report before download',
        })

    # Report customisation options
    include_graphs     = request.form.get('include_graphs')     == '1'
    include_ncs_tables = request.form.get('include_ncs_tables') == '1'
    include_emg_table  = request.form.get('include_emg_table')  == '1'
    include_vep_table  = request.form.get('include_vep_table')  == '1'

    import base64
    emg_images_b64 = data.get('emg_images', [])
    emg_images = [
        {'label': img['label'],
         'png_bytes': base64.b64decode(img['png_b64']) if img.get('png_b64') else None}
        for img in emg_images_b64
        if img.get('png_b64')
    ] if include_graphs else []

    ncs_images_b64 = data.get('ncs_images', [])
    ncs_images = [
        {'label': img['label'],
         'png_bytes': base64.b64decode(img['png_b64']) if img.get('png_b64') else None}
        for img in ncs_images_b64
        if img.get('png_b64')
    ] if include_graphs else []

    docx_bytes = generate_docx(
        parsed_data, edited_report,
        emg_form_data if include_emg_table else [],
        report_types,
        lab_name=config.get('lab_name', 'NCS-EMG LAB, DEPARTMENT OF PHYSIOLOGY, AIIMS PATNA'),
        emg_images=emg_images,
        ncs_images=ncs_images,
        include_ncs_tables=include_ncs_tables,
        include_vep_table=include_vep_table,
    )

    patient_name = parsed_data.get('patient', {}).get('name', 'report').replace(' ', '_')
    filename = f"NCS_{patient_name}_{datetime.date.today()}.docx"

    return send_file(
        io.BytesIO(docx_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@app.route('/parse_emg_photo', methods=['POST'])
def parse_emg_photo():
    """
    Accept a photo of the handwritten EMG sheet.
    Send to Claude vision → return extracted EMG rows as JSON.
    """
    import base64
    import anthropic

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo uploaded'}), 400

    photo = request.files['photo']
    image_bytes = photo.read()
    image_b64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    mime = photo.content_type or 'image/jpeg'

    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'API key not configured'}), 500

    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = """This is a photo of a handwritten EMG reporting sheet from a neurophysiology lab.

Extract the EMG table data. Each filled row has these columns:
- Muscle (abbreviation, e.g. TR, BB, APB, VM, TA)
- Side: Left (L), Right (R), or Bilateral (B) — infer from context or column grouping if present
- Insertion EMG: Brief Normal / Prolonged / Reduced / Normal
- Resting EMG: Silent / Fibrillations / PSWs / Fasciculations / Giant potentials / Fibrillations + PSWs
- Amplitude: Normal / ↑ / ↓ / Not recordable
- Duration: Normal / ↑ / ↓
- Polyphasic: No / Yes
- Recruitment: Normal / ↓ / ↑ / Patient couldn't recruit
- Interference: Normal full / Incomplete / Low amplitude incomplete unitary / Low amplitude unitary / Single unit discharge
- Notes: any free text, or empty

Return ONLY a JSON array of row objects. Use exactly these keys:
side, muscle, insertion, resting, amplitude, duration, polyphasic, recruitment, interference, notes

Only include rows that have data written. Skip blank rows.
If a value is illegible or absent, use the most common default:
  insertion=Brief Normal, resting=Silent, amplitude=Normal, duration=Normal,
  polyphasic=No, recruitment=Normal, interference=Normal full, notes=""

Example output:
[
  {"side":"L","muscle":"TR","insertion":"Brief Normal","resting":"Silent","amplitude":"Normal","duration":"Normal","polyphasic":"No","recruitment":"Normal","interference":"Normal full","notes":""},
  {"side":"R","muscle":"APB","insertion":"Brief Normal","resting":"Fibrillations","amplitude":"↓","duration":"Normal","polyphasic":"No","recruitment":"↓","interference":"Incomplete","notes":""}
]"""

        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1500,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image', 'source': {
                        'type': 'base64', 'media_type': mime, 'data': image_b64
                    }},
                    {'type': 'text', 'text': prompt}
                ]
            }]
        )

        text = response.content[0].text.strip()
        # Strip markdown code block if present
        import re
        m = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()

        rows = json.loads(text)
        return jsonify({'rows': rows})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    config = load_config()
    if request.method == 'POST':
        config['lab_name'] = request.form.get('lab_name', config['lab_name'])
        config['default_doctor'] = request.form.get('default_doctor', '')
        config['default_performed_by'] = request.form.get('default_performed_by', 'Mr. Manish Kumar')
        api_key = request.form.get('api_key', '').strip()
        if api_key:
            # Write to .env file
            env_path = BASE_DIR / '.env'
            lines = []
            if env_path.exists():
                with open(env_path) as f:
                    lines = [l for l in f.readlines() if not l.startswith('ANTHROPIC_API_KEY')]
            lines.append(f'ANTHROPIC_API_KEY={api_key}\n')
            with open(env_path, 'w') as f:
                f.writelines(lines)
            os.environ['ANTHROPIC_API_KEY'] = api_key
        save_config(config)
        flash('Settings saved.', 'success')
        return redirect(url_for('settings'))
    has_api_key = bool(os.getenv('ANTHROPIC_API_KEY', ''))
    return render_template('settings.html', config=config, has_api_key=has_api_key)


if __name__ == '__main__':
    print("NCS-EMG Report Generator")
    print(f"Open in browser: http://localhost:8000")
    print(f"On hospital LAN: http://<your-IP>:8000")
    app.run(host='0.0.0.0', port=8000, debug=False)
