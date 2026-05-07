"""
parser.py — RTF Parser for Neurosoft NCS/EMG/VEP output files.

Key insight about Neurosoft RTF structure:
- Each table row: column-definition block + \pard\intbl <cell1>\cell <cell2>\cell ... \row
- Column definitions (\cellx500, etc.) appear BEFORE \pard\intbl — we skip these
- Only content after \pard\intbl in each \row block contains actual data
- Patient demographics are in a 2-column table near the report header
- NCS tables follow: Motor CV, Sensory CV, F-Wave Findings, VEP

EMG machine table in RTF is intentionally IGNORED — EMG data comes from web form.
"""

import re


# ── RTF cleaning ──────────────────────────────────────────────────────────────

# RTF control word pattern: \word optionally followed by digits
_RTF_CTRL = re.compile(r'\\[a-zA-Z]+\-?\d*\s?')
# RTF hex escape pattern: \'xx (Windows-1252 encoded character)
_RTF_HEX = re.compile(r"\\'([0-9a-fA-F]{2})")
# RTF picture block pattern: {\pict ...hex...} or {\*\shppict{\pict ...}}
_PICT_BLOCK = re.compile(r'\{\\(?:\*\\shppict\s*\{)?\\pict[^}]*\}+', re.DOTALL)


def _strip_pict_blocks(rtf_text):
    """Remove embedded image \\pict blocks to prevent binary data leaking into table rows."""
    # Remove \pict blocks (may be nested)
    cleaned = _PICT_BLOCK.sub('', rtf_text)
    # Also strip long runs of hex chars that are raw binary image data
    cleaned = re.sub(r'(?:[0-9a-fA-F]{2}){50,}', '', cleaned)
    return cleaned

def _decode_rtf_hex(s):
    """Convert RTF \'xx hex escapes to proper Unicode using Windows-1252."""
    def replace(m):
        byte_val = int(m.group(1), 16)
        return bytes([byte_val]).decode('cp1252', errors='replace')
    return _RTF_HEX.sub(replace, s)

def _clean(s):
    """Strip all RTF control sequences and return plain text."""
    s = _decode_rtf_hex(s)  # decode \'xx escapes BEFORE stripping control words
    s = _RTF_CTRL.sub('', s)
    s = s.replace('{', '').replace('}', '').replace('\r', '').replace('\n', '').replace('\t', '')
    s = re.sub(r'\s+', ' ', s).strip()
    # Reject binary image data — long runs of hex characters are \pict block content
    if len(s) > 40 and re.match(r'^[0-9a-fA-F\s\\*]+$', s):
        return None
    # Normalise non-recordable
    if s in ('NR', 'nr', 'N/R', 'Absent', 'absent'):
        return 'NR'
    # Normalise em/en dash = empty cell
    if re.match(r'^[\u2013\u2014\-\s]*$', s):
        return None
    return s or None


# ── Row extraction ────────────────────────────────────────────────────────────

def _extract_rows(chunk):
    """
    Split a chunk of RTF into a list of rows, each row being a list of cell strings.

    Strategy:
    - Split the chunk on \\row to get individual row blocks
    - Within each block, find \\pard\\intbl to locate actual cell data
    - Split the post-\\pard\\intbl section on \\cell to get cells
    - Skip rows that don't contain \\pard\\intbl (they're column definition rows)
    """
    rows = []
    # Split on \row (careful: raw string r'\row' = literal \row)
    raw_rows = chunk.split('\\row')

    for raw in raw_rows:
        # Find the \pard\intbl marker
        intbl_idx = raw.find('\\pard\\intbl')
        if intbl_idx == -1:
            # Also try \pard\intbl with different spacing
            intbl_idx = raw.find('\\intbl')
            if intbl_idx == -1:
                continue

        # Get content after the intbl marker
        content = raw[intbl_idx:]

        # Split on \cell (cell terminator) but NOT \cellx\d+ (column width definitions)
        parts = re.split(r'\\cell(?![x\d])', content)

        cells = []
        for part in parts:
            cleaned = _clean(part)
            # Skip 'pard' and 'intbl' artifacts from the initial marker
            if cleaned in ('pardintbl', 'intbl', 'pard', None):
                cells.append(None)
            else:
                cells.append(cleaned)

        # Remove trailing Nones
        while cells and cells[-1] is None:
            cells.pop()

        if cells:
            rows.append(cells)

    return rows


def _normalize_group(label):
    """
    Normalize a nerve group label from Neurosoft RTF to clean display form.
    Examples:
      'L, n. Suralis, S1-S2'  → 'L, Suralis'
      'R, n. Suralis'         → 'R, Suralis'
      'L, Median'             → 'L, Median'   (unchanged)
    """
    if not label:
        return label

    # Split side prefix (e.g. 'L, ') from nerve part
    m = re.match(r'^([LRB][,\s]+)(.*)', label)
    if m:
        side_prefix = m.group(1)
        nerve_part = m.group(2).strip()
    else:
        side_prefix = ''
        nerve_part = label.strip()

    # Remove leading 'n. ' or 'n.' (Latin abbreviation for nervus)
    nerve_part = re.sub(r'^n\.\s*', '', nerve_part, flags=re.IGNORECASE)

    # Remove trailing dermatome segment like ', S1-S2' or ', C6-C7' or ', L4-S1'
    nerve_part = re.sub(r',\s*[A-Z]\d+[^,]*$', '', nerve_part).strip()

    return side_prefix + nerve_part


def _is_group_header(cells):
    """
    A nerve group header row has exactly one non-None value
    and the value looks like a nerve name (e.g. 'L, Ulnar', 'R, Median').
    """
    non_none = [c for c in cells if c is not None]
    if len(non_none) == 1:
        v = non_none[0]
        # Group headers typically start with L, R, B followed by comma + nerve name
        # or are a section title
        if re.match(r'^[LRB][,\s]', v) or len(v) < 40:
            return True
    return False


# ── Demographics ─────────────────────────────────────────────────────────────

def _extract_demographics(rtf_text):
    """
    Extract patient header fields.
    Demographics are in 2-cell rows: label\cell value\cell\row
    Patterns: "Patient's Name : VALUE", "Age/Sex: VALUE", etc.
    """
    # Find the demographics table — it appears before the report title
    # and contains "Patient's Name"
    demo_start = -1
    for marker in ["Patient's Name", "Patient\\'92s Name", "Name :"]:
        idx = rtf_text.find(marker)
        if idx != -1:
            demo_start = max(0, idx - 200)
            break

    if demo_start == -1:
        return {}

    # Find where the report title starts (marks end of demographics)
    demo_end = len(rtf_text)
    for title in ['NCS REPORT', 'NCS-EMG REPORT', 'NCS EMG REPORT', 'VEP REPORT', 'EMG REPORT',
                  'Motor CV', 'Sensory CV']:
        idx = rtf_text.find(title, demo_start)
        if idx != -1 and idx < demo_end:
            demo_end = idx

    demo_chunk = rtf_text[demo_start:demo_end]
    rows = _extract_rows(demo_chunk)

    # Flatten all cells and parse label: value pairs
    demo = {
        'name': '', 'age_sex': '', 'id': '', 'date': '',
        'referring_dept': '', 'doctor': '', 'diagnosis': '',
        'referring_doctor': '', 'performed_by': 'Mr. Manish Kumar',
    }

    label_map = {
        "Patient's Name": 'name',
        "Patient\\'92s Name": 'name',
        "Name :": 'name',
        "Age/Sex": 'age_sex',
        "ID": 'id',
        "Date": 'date',
        "Referring Department": 'referring_dept',
        "Referring Dept": 'referring_dept',
        "Doctor": 'doctor',
        "Diagnosis": 'diagnosis',
        "Referring Doctor": 'referring_doctor',
        "Ref. Doctor": 'referring_doctor',
        "Performed by": 'performed_by',
        "Performed By": 'performed_by',
    }

    for row in rows:
        # Each row can have 2 cells: [label+value, label+value] or just label:value in one cell
        for cell in row:
            if not cell:
                continue
            for label, field in label_map.items():
                # Check if this cell contains this label
                if label.lower() in cell.lower():
                    # Extract value after the colon
                    colon_idx = cell.find(':')
                    if colon_idx != -1:
                        val = cell[colon_idx + 1:].strip(' :')
                        if val:
                            demo[field] = val
                    break

    # Parse age and sex from age_sex
    age_sex = demo.get('age_sex', '')
    age_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:year|yr|y\b)', age_sex, re.IGNORECASE)
    sex_m = re.search(r'\b(Male|Female|M|F)\b', age_sex, re.IGNORECASE)
    demo['age'] = age_m.group(1) if age_m else ''
    demo['sex'] = sex_m.group(1) if sex_m else ''

    return demo


# ── Report type detection ─────────────────────────────────────────────────────

def _detect_report_type(rtf_text):
    upper = rtf_text.upper()
    if 'NCS-EMG REPORT' in upper or 'NCS EMG REPORT' in upper:
        return ['NCS', 'EMG']
    elif 'VISUAL EVOKED' in upper or 'VEP REPORT' in upper:
        return ['VEP']
    elif 'NCS REPORT' in upper:
        return ['NCS']
    elif 'EMG REPORT' in upper:
        return ['EMG']
    # Fallback: detect by table presence
    types = []
    if 'MOTOR CV' in upper or 'SENSORY CV' in upper:
        types.append('NCS')
    if 'VISUAL EVOKED' in upper:
        types.append('VEP')
    return types or ['NCS']


# ── Table section extraction ──────────────────────────────────────────────────

def _get_section(rtf_text, start_markers, end_markers):
    """Extract RTF chunk between first start_marker hit and first end_marker hit."""
    start = -1
    for m in (start_markers if isinstance(start_markers, list) else [start_markers]):
        idx = rtf_text.find(m)
        if idx != -1:
            start = idx
            break
    if start == -1:
        return ''

    chunk = rtf_text[start:]
    for m in (end_markers if isinstance(end_markers, list) else [end_markers]):
        idx = chunk.find(m)
        if 0 < idx:
            chunk = chunk[:idx]
    return chunk


def _parse_ncs_table(rows, col_keys):
    """
    Convert extracted row lists into NCS table records.
    Skips the header row (contains column names like 'Test', 'Lat', etc.).
    Groups data rows under their nerve group headers.

    col_keys: list of field names matching the column order.
    """
    result = []
    current_group = ''
    header_found = False

    for cells in rows:
        non_none = [c for c in cells if c is not None]
        if not non_none:
            continue

        # Skip the column header row
        if not header_found:
            if non_none[0] in ('Test', 'test', 'Motor CV', 'Sensory CV', 'F-Wave Findings'):
                header_found = True
                continue

        # Group header: single cell that looks like a nerve name
        if _is_group_header(cells):
            current_group = _normalize_group(non_none[0])
            continue

        # Data row: map cells to keys
        record = {'group': current_group}
        for i, key in enumerate(col_keys):
            val = cells[i] if i < len(cells) else None
            # Amplitude of 0 means non-recordable (machine outputs 0 instead of NR)
            if 'ampl' in key and val in ('0', '0.0', '0.00'):
                val = 'NR'
            record[key] = val
        result.append(record)

    return result


# ── Public API ────────────────────────────────────────────────────────────────

MOTOR_KEYS = ['test_no', 'site', 'lat_ms', 'ampl_mv', 'dur_ms', 'area',
              'stim_ma', 'stim_ms', 'dist_mm', 'time_ms', 'vel_ms']

SENSORY_KEYS = ['test_no', 'site', 'lat_ms', 'ampl_uv', 'dur_ms', 'area',
                'stim_ma', 'stim_ms', 'dist_mm', 'time_ms', 'vel_ms',
                'vel_norm', 'vel_dev_pct']

FWAVE_KEYS = ['test_no', 'fmin_lat_ms', 'm_lat_ms', 'fmin_m_lat_ms', 'max_vprox']

VEP_KEYS = ['n', 'rec_sites', 'n75_lat', 'p100_lat', 'n145_lat',
            'p100_n145_ampl', 'stim_side', 'stimulus', 'stim_dur']


def parse_rtf(file_path):
    """
    Parse a Neurosoft RTF file.

    Returns:
    {
        'patient': {name, age, sex, id, date, referring_dept, doctor, diagnosis, ...},
        'report_type': ['NCS'] | ['NCS', 'EMG'] | ['VEP'],
        'motor_ncs': [...],
        'sensory_ncs': [...],
        'f_waves': [...],
        'vep': [...],
    }
    """
    with open(file_path, 'rb') as f:
        raw = f.read().decode('latin-1')

    # Skip the large binary logo block — find the first patient data marker
    text_start = len(raw)
    for marker in ["Patient's Name", "Age/Sex", "NCS REPORT", "NCS-EMG", "Motor CV"]:
        idx = raw.find(marker)
        if idx != -1 and idx < text_start:
            text_start = max(0, idx - 500)

    if text_start == len(raw):
        text_start = 0

    rtf = raw[text_start:]

    # ── Parse sections ────────────────────────────────────────────────────────

    patient = _extract_demographics(rtf)
    report_type = _detect_report_type(rtf)

    # Motor CV
    motor_chunk = _get_section(rtf, 'Motor CV',
                               ['Sensory CV', 'F-Wave Findings', 'Visual Evoked', 'Summary:',
                                'Insertion EMG', 'Spont. Activity'])
    motor_rows = _extract_rows(_strip_pict_blocks(motor_chunk))
    motor_ncs = _parse_ncs_table(motor_rows, MOTOR_KEYS)

    # Sensory CV
    sensory_chunk = _get_section(rtf, 'Sensory CV',
                                 ['F-Wave Findings', 'Visual Evoked', 'Summary:', '\\ul\\b'])
    sensory_rows = _extract_rows(_strip_pict_blocks(sensory_chunk))
    sensory_ncs = _parse_ncs_table(sensory_rows, SENSORY_KEYS)

    # F-Wave
    fwave_chunk = _get_section(rtf, 'F-Wave Findings',
                               ['Sensory CV', 'Motor CV', 'Visual Evoked', 'Summary:', '\\ul\\b'])
    fwave_rows = _extract_rows(_strip_pict_blocks(fwave_chunk))
    f_waves = _parse_ncs_table(fwave_rows, FWAVE_KEYS)

    # VEP
    vep_chunk = _get_section(rtf, ['Visual Evoked Potential', 'VEP'],
                              ['Motor CV', 'Sensory CV', 'Summary:', '\\ul\\b'])
    vep_rows = _extract_rows(_strip_pict_blocks(vep_chunk))
    vep = _parse_ncs_table(vep_rows, VEP_KEYS)

    return {
        'patient': patient,
        'report_type': report_type,
        'motor_ncs': motor_ncs,
        'sensory_ncs': sensory_ncs,
        'f_waves': f_waves,
        'vep': vep,
    }


def extract_emg_images(rtf_path):
    """
    Extract embedded EMG waveform images from a Neurosoft RTF file.

    Each image in the RTF is a WMF (Windows Metafile) stored as hex.
    The label immediately before each image follows Neurosoft's format:
      'Spont. Activity : R, Tibialis anterior, Peroneus, L4 L5 s1'
      'Interf. Pattern : L, Deltoideus, Axillaris, C5 C6'
      'Motor Unit Potential : R, Vastus lateralis, Femoralis, L2-L4'

    Returns list of {'label': str, 'wmf_bytes': bytes}.
    The AIIMS logo (first WMF, no EMG label) is skipped automatically.
    Returns [] if no images found or on any error.
    """
    import binascii

    try:
        with open(rtf_path, 'rb') as f:
            raw = f.read().decode('latin-1')
    except Exception:
        return []

    # ── Step 1: Find all EMG label positions in document order ──────────────────
    _LABEL_RE = re.compile(
        r'(Spont\.\s+Activity|Interf\.\s+Pattern|Motor\s+Unit\s+Potential)'
        r'\s*:\s*([LR],\s*.+?)(?=\s*\\|\s*\*|\s{3,}|$)',
        re.IGNORECASE
    )

    labeled_positions = []  # (doc_position, label_string)
    for m in _LABEL_RE.finditer(raw):
        display_type = m.group(1).strip()
        muscle_info  = m.group(2).strip().rstrip('\\* ')
        label = f"{display_type} : {muscle_info}"
        labeled_positions.append((m.start(), label))

    if not labeled_positions:
        return []

    # ── Step 2: Find all WMF hex blocks with their positions ────────────────────
    _WMF_RE = re.compile(
        r'\\wmetafile\d+'
        r'(?:\\[a-zA-Z]+[-]?\d*\s?)*'   # skip any RTF control words (picw, pich, bliptag, etc.)
        r'\s*([\da-fA-F\s]{40,})',
        re.DOTALL
    )

    wmf_list = []  # (doc_position, wmf_bytes)
    for wm in _WMF_RE.finditer(raw):
        hex_data = re.sub(r'\s+', '', wm.group(1))
        hex_data = re.match(r'[0-9a-fA-F]*', hex_data).group()
        if len(hex_data) < 40:
            continue
        try:
            wmf_list.append((wm.start(), binascii.unhexlify(hex_data)))
        except Exception:
            continue

    if not wmf_list:
        return []

    # ── Step 3: Match each label to the next WMF block after it ─────────────────
    # This works regardless of whether \shplid tags are present or not.
    # Each label appears just before its image in the RTF stream.
    results = []
    wmf_positions = [pos for pos, _ in wmf_list]

    for label_pos, label in labeled_positions:
        # Find the first WMF that starts after this label
        next_wmf_idx = None
        for i, wpos in enumerate(wmf_positions):
            if wpos > label_pos:
                next_wmf_idx = i
                break
        if next_wmf_idx is not None:
            results.append({'label': label, 'wmf_bytes': wmf_list[next_wmf_idx][1]})

    return results


def extract_ncs_images(rtf_path, parsed_data=None):
    """
    Extract NCS waveform images (Motor CV, Sensory CV, F-Wave) from a Neurosoft RTF file.

    Neurosoft stores each NCS waveform as a \shppict (EMF) block preceded by a
    section label line like 'Motor CV\\b0\\par' or 'Sensory CV\\b0\\par'.
    Each \shppict also has a \nonshppict WMF fallback — we extract that for
    LibreOffice conversion (same pipeline as EMG images).

    Labels are assigned positionally from parsed_data nerve groups so that
    "Motor CV 1" → first motor nerve group, etc.

    Returns list of {'label': str, 'wmf_bytes': bytes}.
    Returns [] if no images found or on any error.
    """
    import binascii

    try:
        with open(rtf_path, 'rb') as f:
            raw = f.read().decode('latin-1')
    except Exception:
        return []

    # ── Step 1: Find NCS waveform section labels that are immediately followed
    #    by a \shppict image block (within ~600 chars).
    #    This distinguishes waveform labels from data table section headers.
    _NCS_LABEL_RE = re.compile(
        r'\\v0(?:\\fs\d+)?\s+(Motor CV|Sensory CV|F-Wave(?:\s+Findings)?|VEP)\\b0\\par',
        re.IGNORECASE
    )

    label_positions = []   # (doc_pos, label_text)
    for m in _NCS_LABEL_RE.finditer(raw):
        label_text = m.group(1).strip()
        after = raw[m.end():m.end() + 600]
        if r'\shppict' in after or r'\pict' in after:
            label_positions.append((m.start(), label_text))

    if not label_positions:
        return []

    # ── Step 2: Find all \nonshppict WMF hex blocks (the LibreOffice-compatible fallbacks)
    _WMF_RE = re.compile(
        r'\\nonshppict[^{]*\{[^\\]*\\pict'
        r'(?:\\[a-zA-Z]+[-]?\d*\s?)*'
        r'\\wmetafile\d+'
        r'(?:\\[a-zA-Z]+[-]?\d*\s?)*'
        r'\s*([\da-fA-F\s]{40,})',
        re.DOTALL
    )

    wmf_list = []   # (doc_pos, wmf_bytes)
    for wm in _WMF_RE.finditer(raw):
        hex_data = re.sub(r'\s+', '', wm.group(1))
        hex_data = re.match(r'[0-9a-fA-F]*', hex_data).group()
        if len(hex_data) < 40:
            continue
        try:
            wmf_list.append((wm.start(), binascii.unhexlify(hex_data)))
        except Exception:
            continue

    if not wmf_list:
        return []

    # ── Step 3: Build human-readable nerve labels from parsed_data ─────────────
    motor_groups  = []
    sensory_groups = []
    if parsed_data:
        seen = set()
        for row in parsed_data.get('motor_ncs', []):
            g = row.get('group', '')
            if g and g not in seen:
                motor_groups.append(g)
                seen.add(g)
        seen = set()
        for row in parsed_data.get('sensory_ncs', []):
            g = row.get('group', '')
            if g and g not in seen:
                sensory_groups.append(g)
                seen.add(g)

    motor_idx = sensory_idx = 0

    # ── Step 4: Match each label to the next WMF block after it ─────────────────
    wmf_positions = [pos for pos, _ in wmf_list]
    results = []

    for label_pos, label_text in label_positions:
        next_wmf_idx = None
        for i, wpos in enumerate(wmf_positions):
            if wpos > label_pos:
                next_wmf_idx = i
                break
        if next_wmf_idx is None:
            continue

        # Build a descriptive label using nerve group name if available
        lt_lower = label_text.lower()
        if 'motor' in lt_lower:
            nerve = motor_groups[motor_idx] if motor_idx < len(motor_groups) else f'Motor {motor_idx+1}'
            motor_idx += 1
            display = f"Motor CV : {nerve}"
        elif 'sensory' in lt_lower:
            nerve = sensory_groups[sensory_idx] if sensory_idx < len(sensory_groups) else f'Sensory {sensory_idx+1}'
            sensory_idx += 1
            display = f"Sensory CV : {nerve}"
        else:
            display = label_text

        results.append({'label': display, 'wmf_bytes': wmf_list[next_wmf_idx][1]})

    return results
