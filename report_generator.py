"""
report_generator.py — Rule-based report writer.

Generates summary paragraphs and impression from classification output.
Templates derived from analysis of 94 actual AIIMS Patna NCS reports.
"""


def _nerve_phrase(results, classification_filter):
    """Build a comma-separated list of 'side nerve' phrases for matching results."""
    phrases = []
    for r in results:
        if r['classification'] in classification_filter:
            side = r['side']
            nerve = r['nerve'].lower()
            if side:
                phrases.append(f"{side} {nerve}")
            else:
                phrases.append(nerve)
    return phrases


def _join_nerves(nerve_list):
    """Join nerve list with commas and 'and'."""
    if not nerve_list:
        return ''
    if len(nerve_list) == 1:
        return nerve_list[0]
    return ', '.join(nerve_list[:-1]) + ' and ' + nerve_list[-1]


# ── Motor NCS Paragraph ───────────────────────────────────────────────────────

def generate_motor_paragraph(motor_results):
    """Generate motor NCS summary paragraph."""
    if not motor_results:
        return ''

    nr_nerves = [r for r in motor_results if r['classification'] == 'non-recordable']
    axonal_nerves = [r for r in motor_results if r['classification'] == 'axonal'
                     and r.get('amplitude_status') != 'asymmetric']
    asymmetric_nerves = [r for r in motor_results if r.get('amplitude_status') == 'asymmetric']
    demy_nerves = [r for r in motor_results if r['classification'] == 'demyelinating']
    mixed_nerves = [r for r in motor_results if r['classification'] == 'mixed']
    normal_nerves = [r for r in motor_results if r['classification'] == 'normal']

    sentences = []

    # Non-recordable
    for r in nr_nerves:
        side = r['side']
        nerve = r['nerve'].lower()
        sentences.append(
            f"Compound muscle action potentials (CMAPs) were non-recordable in "
            f"{side + ' ' if side else ''}{nerve} nerve."
        )

    # Axonal loss
    if axonal_nerves:
        nerve_list = _nerve_phrase(axonal_nerves, ['axonal'])
        joined = _join_nerves(nerve_list)
        if len(axonal_nerves) == 1:
            sentences.append(
                f"Reduced amplitude of compound muscle action potentials (CMAPs), "
                f"normal distal motor latency and conduction velocity in the {joined} nerve."
            )
        else:
            sentences.append(
                f"Reduced amplitude of compound muscle action potentials (CMAPs), "
                f"normal distal motor latency and conduction velocity in the {joined} nerves."
            )

    # Demyelinating — only mention what is actually abnormal
    for r in demy_nerves:
        side = r['side']
        nerve = r['nerve'].lower()
        cv_slow = r.get('cv_status') == 'slow'
        dl_long = r.get('dl_status') == 'prolonged'
        prefix = f"{side + ' ' if side else ''}{nerve}"
        if cv_slow and dl_long:
            sentences.append(
                f"Reduced conduction velocity and prolonged distal motor latency "
                f"in the {prefix} nerve."
            )
        elif cv_slow:
            sentences.append(
                f"Reduced conduction velocity in the {prefix} nerve."
            )
        elif dl_long:
            sentences.append(
                f"Prolonged distal motor latency in the {prefix} nerve."
            )

    # Mixed
    for r in mixed_nerves:
        side = r['side']
        nerve = r['nerve'].lower()
        prefix = f"{side + ' ' if side else ''}{nerve}"
        cv_slow = r.get('cv_status') == 'slow'
        dl_long = r.get('dl_status') == 'prolonged'
        cond_parts = []
        if dl_long:
            cond_parts.append('prolonged distal motor latency')
        if cv_slow:
            cond_parts.append('decreased conduction velocity')
        cond_str = ' and '.join(cond_parts) + ' ' if cond_parts else ''
        sentences.append(
            f"Reduced amplitude of compound muscle action potentials (CMAPs)"
            f"{', ' + cond_str.rstrip() if cond_str else ''} in the {prefix} nerve."
        )

    # Amplitude asymmetry (side-to-side comparison for proximal nerves)
    for r in asymmetric_nerves:
        side = r['side']
        nerve = r['nerve'].lower()
        note = next((n for n in r.get('notes', []) if 'amplitude asymmetry' in n), '')
        sentences.append(
            f"Reduced CMAP amplitude in {side + ' ' if side else ''}{nerve} nerve "
            f"with significant side-to-side asymmetry ({note.split('(')[-1].rstrip(')') if note else 'see data'})."
        )

    # Conduction block notes
    for r in motor_results:
        for note in r.get('notes', []):
            if 'conduction block' in note:
                import re
                pct_match = re.search(r'(\d+)%', note)
                pct = pct_match.group(1) if pct_match else '?'
                sentences.append(
                    f"Reduced CMAP amplitude on proximal stimulation compared to distal "
                    f"in {r['side'] + ' ' if r['side'] else ''}{r['nerve'].lower()} nerve, "
                    f"with a drop of {pct}%, suggestive of conduction block."
                )

    # Normal nerves (if any abnormal ones also present)
    all_abnormal = axonal_nerves or demy_nerves or mixed_nerves or nr_nerves or asymmetric_nerves
    if normal_nerves and all_abnormal:
        if len(normal_nerves) == 1:
            r = normal_nerves[0]
            side = r['side']
            nerve = r['nerve'].lower()
            sentences.append(
                f"{(side + ' ').capitalize() if side else ''}{nerve.capitalize()} nerve shows "
                f"normal CMAP amplitude, distal motor latency and conduction velocity."
            )
        else:
            sentences.append(
                "All other tested nerves show normal CMAP amplitude, distal motor latency "
                "and conduction velocity."
            )
    elif not axonal_nerves and not demy_nerves and not mixed_nerves and not nr_nerves and not asymmetric_nerves:
        sentences.append(
            "Normal CMAP amplitude, distal motor latency and conduction velocity in all the tested nerves."
        )

    return ' '.join(sentences)


# ── Sensory NCS Paragraph ─────────────────────────────────────────────────────

def generate_sensory_paragraph(sensory_results):
    """Generate sensory NCS summary paragraph."""
    if not sensory_results:
        return ''

    absent_nerves = [r for r in sensory_results if r['classification'] == 'absent']
    axonal_nerves = [r for r in sensory_results if r['classification'] == 'axonal']
    demy_nerves = [r for r in sensory_results if r['classification'] == 'demyelinating']
    normal_nerves = [r for r in sensory_results if r['classification'] == 'normal']

    sentences = []

    # Absent conduction
    for r in absent_nerves:
        side = r['side']
        nerve = r['nerve'].lower()
        sentences.append(
            f"Absence of {side + ' ' if side else ''}{nerve} sensory conduction."
        )

    # Axonal (reduced amplitude)
    for r in axonal_nerves:
        side = r['side']
        nerve = r['nerve'].lower()
        sentences.append(
            f"{(side + ' ').capitalize() if side else ''}{nerve.capitalize()} SNAP amplitude is reduced."
        )

    # Demyelinating (slow CV)
    for r in demy_nerves:
        side = r['side']
        nerve = r['nerve'].lower()
        sentences.append(
            f"Reduced conduction velocity of {side + ' ' if side else ''}{nerve} sensory nerve."
        )

    # Normal
    if normal_nerves and (absent_nerves or axonal_nerves or demy_nerves):
        if len(normal_nerves) == 1:
            r = normal_nerves[0]
            side = r['side']
            nerve = r['nerve'].lower()
            sentences.append(
                f"{(side + ' ').capitalize() if side else ''}{nerve.capitalize()} SNAP amplitude, "
                f"latency and conduction velocity were normal."
            )
        else:
            sentences.append(
                "SNAP amplitudes, latency and conduction velocity were normal in all other tested nerves."
            )
    elif not absent_nerves and not axonal_nerves and not demy_nerves:
        sentences.append(
            "SNAP amplitudes, latency and conduction velocity were normal in all the tested nerves."
        )

    return ' '.join(sentences)


# ── F-Wave Paragraph ──────────────────────────────────────────────────────────

def generate_fwave_paragraph(fwave_results):
    """Generate F-wave summary."""
    if not fwave_results:
        return ''

    nr = [r for r in fwave_results if r['status'] == 'nr']
    prolonged = [r for r in fwave_results if r['status'] == 'prolonged']
    normal = [r for r in fwave_results if r['status'] == 'normal']

    sentences = []

    # Group all NR nerves into one sentence
    if nr:
        if len(nr) == len(fwave_results):
            sentences.append("F-waves were non-recordable in all of the tested nerves.")
        else:
            nr_list = [f"{r['side'] + ' ' if r['side'] else ''}{r['nerve'].lower()}" for r in nr]
            joined = _join_nerves(nr_list)
            suffix = 'nerve' if len(nr_list) == 1 else 'nerves'
            sentences.append(f"F-waves were non-recordable in {joined} {suffix}.")

    for r in prolonged:
        side = r['side']
        nerve = r['nerve'].lower()
        sentences.append(
            f"F-wave latency was prolonged in {side + ' ' if side else ''}{nerve} nerve."
        )

    if normal and not nr and not prolonged:
        sentences.append("F-wave min latency was normal in all of the tested nerves.")
    elif normal and (nr or prolonged):
        pass  # Don't mention normal ones if some are abnormal

    return ' '.join(sentences)


# ── Muscle name expansion ──────────────────────────────────────────────────────

MUSCLE_NAMES = {
    # Upper limb
    'DL':  'Deltoid',
    'SS':  'Supraspinatus',
    'IS':  'Infraspinatus',
    'BB':  'Biceps Brachii',
    'TR':  'Triceps',
    'BR':  'Brachioradialis',
    'FCR': 'Flexor Carpi Radialis',
    'FCU': 'Flexor Carpi Ulnaris',
    'APB': 'Abductor Pollicis Brevis',
    'ADM': 'Abductor Digiti Minimi',
    'IO':  'First Dorsal Interosseous',
    'LB':  'Lumbrical Brevis',
    'ED':  'Extensor Digitorum',
    # Lower limb
    'VM':  'Vastus Medialis',
    'VL':  'Vastus Lateralis',
    'GN':  'Gastrocnemius',
    'FDL': 'Flexor Digitorum Longus',
    'FHL': 'Flexor Hallucis Longus',
    'TA':  'Tibialis Anterior',
    'EDL': 'Extensor Digitorum Longus',
    'EDB': 'Extensor Digitorum Brevis',
    'AHL': 'Abductor Hallucis',
    'HS':  'Hamstrings',
}

SIDE_NAMES = {'L': 'Left', 'R': 'Right', 'B': 'Bilateral'}

def _expand_muscle_label(side, muscle):
    """Return expanded label e.g. 'Left Triceps'. Falls back to raw if not in map."""
    side_word = SIDE_NAMES.get(side.upper(), side) if side else ''
    muscle_word = MUSCLE_NAMES.get(muscle.upper(), muscle)
    return f"{side_word} {muscle_word}".strip() if side_word else muscle_word


# ── EMG Paragraph ─────────────────────────────────────────────────────────────

def _findings_key(row):
    """Tuple that uniquely identifies a set of EMG findings."""
    return (
        row.get('insertion', ''),
        row.get('resting', 'Silent'),
        row.get('amplitude', 'Normal'),
        row.get('duration', 'Normal'),
        row.get('polyphasic', 'No'),
        row.get('recruitment', 'Normal'),
        row.get('interference', 'Normal full'),
        row.get('notes', ''),
    )


def _emg_label(side, muscle_names):
    """
    Build a natural-language label for one or more muscles on the same side.
      1 muscle  → 'Left Triceps'
      2+ muscles → 'Left side Triceps and Biceps Brachii'
                   'Left side Triceps, Biceps Brachii and Deltoid'
    """
    side_word = SIDE_NAMES.get(side.upper(), side) if side else ''
    if len(muscle_names) == 1:
        return f"{side_word} {muscle_names[0]}".strip()
    joined = ', '.join(muscle_names[:-1]) + f" and {muscle_names[-1]}"
    return f"{side_word} side {joined}".strip() if side_word else joined


def generate_emg_paragraph(emg_form_data):
    """
    Generate EMG summary, grouping muscles with identical findings on the same side
    into a single sentence.
    """
    if not emg_form_data:
        return ''

    # Step 1: expand B → L + R, collect flat list preserving input order
    entries = []
    for row in emg_form_data:
        muscle = row.get('muscle', '')
        if not muscle:
            continue
        side = row.get('side', '')
        for s in (['L', 'R'] if side == 'B' else [side]):
            entries.append(dict(row, side=s, muscle=muscle))

    if not entries:
        return ''

    # Step 2a: pull out all "can't recruit" entries first — group by side regardless of other findings
    from collections import OrderedDict
    cant_recruit_by_side = OrderedDict()
    normal_entries = []
    for e in entries:
        if e.get('recruitment') == "Patient couldn't recruit":
            s = e['side']
            if s not in cant_recruit_by_side:
                cant_recruit_by_side[s] = []
            muscle_expanded = MUSCLE_NAMES.get(e['muscle'].upper(), e['muscle'])
            if muscle_expanded not in cant_recruit_by_side[s]:
                cant_recruit_by_side[s].append(muscle_expanded)
        else:
            normal_entries.append(e)

    # Step 2b: group remaining entries by (side, findings_key)
    groups = OrderedDict()
    for e in normal_entries:
        key = (e['side'], _findings_key(e))
        if key not in groups:
            groups[key] = {'row': e, 'muscles': []}
        muscle_expanded = MUSCLE_NAMES.get(e['muscle'].upper(), e['muscle'])
        if muscle_expanded not in groups[key]['muscles']:
            groups[key]['muscles'].append(muscle_expanded)

    # Step 3: build sentences — can't-recruit first, then normal groups
    sentences = []

    # One sentence per side for can't-recruit muscles
    for side, muscles in cant_recruit_by_side.items():
        label = _emg_label(side, muscles)
        sentences.append(f"Patient could not recruit {label} during the study.")

    for (side, _), group in groups.items():
        row = group['row']
        muscles = group['muscles']
        label = _emg_label(side, muscles)

        if row.get('recruitment') == "Patient couldn't recruit":
            sentences.append(f"Patient could not recruit {label} during the study.")
            continue

        insertion   = row.get('insertion', '')
        resting     = row.get('resting', 'Silent')
        amplitude   = row.get('amplitude', 'Normal')
        duration    = row.get('duration', 'Normal')
        polyphasic  = row.get('polyphasic', 'No')
        recruitment = row.get('recruitment', 'Normal')
        interference = row.get('interference', 'Normal full')
        notes       = row.get('notes', '')

        amp_desc  = {'Normal': 'normal', '↑': 'increased', '↓': 'low',
                     'Not recordable': 'not recordable'}.get(amplitude, amplitude)
        dur_desc  = {'Normal': 'normal', '↑': 'increased', '↓': 'short'}.get(duration, duration)
        poly_desc = 'polyphasic potentials' if polyphasic == 'Yes' else 'no polyphasic potentials'
        rec_desc  = {'Normal': 'normal', '↓': 'reduced', '↑': 'increased'}.get(recruitment, recruitment)
        interf_desc = interference or 'Normal full'

        sentence = (
            f"{label} showed {insertion.lower() if insertion else 'brief normal'} "
            f"insertional activity, {resting.lower()} at rest, MUPs with {amp_desc} amplitude "
            f"and {dur_desc} duration, {poly_desc} and {rec_desc} recruitment. "
            f"{interf_desc.capitalize()} on interference."
        )
        if notes:
            sentence += f" {notes}"
        sentences.append(sentence)

    return ' '.join(sentences)

    if is_neuropathic:
        neuropathic_muscles.append(label)
    elif is_myopathic:
        myopathic_muscles.append(label)
    else:
        normal_muscles.append(label)


# ── VEP Paragraph ─────────────────────────────────────────────────────────────

def generate_vep_paragraph(vep_results):
    """Generate VEP summary paragraph."""
    if not vep_results:
        return ''

    all_normal = all(r.get('p100_status') == 'normal' for r in vep_results)
    all_prolonged = all(r.get('p100_status') == 'prolonged' for r in vep_results)
    any_absent = any(r.get('p100_status') == 'absent' for r in vep_results)

    if all_normal:
        return "Normal latencies of P100 bilaterally. Normal amplitude bilaterally."
    elif all_prolonged:
        return "Low amplitudes and prolonged latencies of N75, P100 and N145 of both eyes."
    elif any_absent:
        normal_sides = [r['side'] for r in vep_results if r.get('p100_status') == 'normal']
        absent_sides = [r['side'] for r in vep_results if r.get('p100_status') == 'absent']
        prolonged_sides = [r['side'] for r in vep_results if r.get('p100_status') == 'prolonged']
        parts = []
        if prolonged_sides or normal_sides:
            parts.append(
                f"Low amplitudes and prolonged latencies of N75, P100 and N145 of "
                f"{', '.join(prolonged_sides)} eye."
            )
        if absent_sides:
            parts.append(
                f"Absence of VEP from the {', '.join(absent_sides)} eye."
            )
        return ' '.join(parts)
    else:
        return "Normal latencies of P100 bilaterally. Decreased amplitude on one side."


# ── EMG classification for impression ────────────────────────────────────────

def _classify_emg_row(row):
    """
    Classify a single EMG row as one of:
      'active_denervation'  — fibrillations / PSWs at rest (ongoing axonal damage)
      'chronic_denervation' — neuropathic MUPs without active denervation (old/stable)
      'myopathic'           — small amplitude, short duration, early recruitment
      'cannot_recruit'      — patient unable to cooperate
      'normal'
    Priority: active_denervation > myopathic > chronic_denervation > normal
    """
    resting     = row.get('resting', 'Silent')
    amplitude   = row.get('amplitude', 'Normal')
    duration    = row.get('duration', 'Normal')
    polyphasic  = row.get('polyphasic', 'No')
    recruitment = row.get('recruitment', 'Normal')
    interference = row.get('interference', 'Normal full')

    if recruitment == "Patient couldn't recruit":
        return 'cannot_recruit'

    active = resting in ('Fibrillations', 'PSWs', 'Fibrillations + PSWs', 'Giant potentials')
    neuropathic_mups = (
        amplitude == '↑' or duration == '↑' or
        recruitment == '↓' or
        interference in ('Incomplete', 'Low amplitude incomplete unitary',
                         'Low amplitude unitary', 'Single unit discharge')
    )
    myopathic = (
        amplitude == '↓' or duration == '↓' or
        recruitment == '↑' or polyphasic == 'Yes'
    )

    if active:
        return 'active_denervation'
    if myopathic and not neuropathic_mups:
        return 'myopathic'
    if neuropathic_mups:
        return 'chronic_denervation'
    return 'normal'


def _classify_emg_for_impression(emg_form):
    """
    Returns dict:
      active_denervation:  [(expanded_label), ...]
      chronic_denervation: [...]
      myopathic:           [...]
      normal_count:        int
      total:               int
    """
    result = {'active_denervation': [], 'chronic_denervation': [],
              'myopathic': [], 'normal_count': 0, 'total': 0}

    for row in emg_form:
        muscle = row.get('muscle', '')
        if not muscle:
            continue
        side = row.get('side', '')
        sides = ['L', 'R'] if side == 'B' else [side]
        for s in sides:
            result['total'] += 1
            label = _expand_muscle_label(s, muscle)
            cat = _classify_emg_row(row)
            if cat == 'normal' or cat == 'cannot_recruit':
                result['normal_count'] += 1
            else:
                result[cat].append(label)

    return result


def _fmt_muscle_list(labels):
    """Format list of muscle labels into natural language."""
    if not labels:
        return ''
    if len(labels) == 1:
        return labels[0]
    return ', '.join(labels[:-1]) + ' and ' + labels[-1]


def _ncs_path(results):
    """Determine predominant NCS pathology from a list of results: axonal / demyelinating / mixed."""
    classes = [r['classification'] for r in results]
    if all(c in ('axonal', 'absent', 'non-recordable') for c in classes):
        return 'axonal'
    if all(c == 'demyelinating' for c in classes):
        return 'demyelinating'
    return 'mixed'


def _path_phrase(path):
    return {
        'axonal':        'axonal loss',
        'demyelinating': 'demyelination',
        'mixed':         'axonal loss with features of demyelination',
    }.get(path, 'axonal loss')


def _build_ncs_clauses(motor_abnormal, sensory_abnormal):
    """
    Group abnormal nerves by modality and build impression clauses.

    Rules:
    - Nerve with BOTH motor and sensory abnormal → 'sensorimotor neuropathy of [nerve(s)]'
    - Nerve with ONLY motor abnormal → 'motor neuropathy of [nerve(s)]'
    - Nerve with ONLY sensory abnormal → 'sensory neuropathy of [nerve(s)]'
    - Nerves sharing the same category are grouped together.

    Returns list of clause strings (no leading article, no trailing period).
    e.g. ['motor neuropathy of the right peroneal nerve suggestive of demyelination',
          'sensory neuropathy of the right sural nerve suggestive of axonal loss']
    """
    # Build per-nerve map keyed by (side, nerve_lower)
    nerve_map = {}
    for r in motor_abnormal:
        key = (r['side'], r['nerve'].lower())
        if key not in nerve_map:
            nerve_map[key] = {'motor': [], 'sensory': [], 'side': r['side'], 'nerve': r['nerve']}
        nerve_map[key]['motor'].append(r)
    for r in sensory_abnormal:
        key = (r['side'], r['nerve'].lower())
        if key not in nerve_map:
            nerve_map[key] = {'motor': [], 'sensory': [], 'side': r['side'], 'nerve': r['nerve']}
        nerve_map[key]['sensory'].append(r)

    both_group   = []
    motor_group  = []
    sensory_group = []

    for data in nerve_map.values():
        if data['motor'] and data['sensory']:
            both_group.append(data)
        elif data['motor']:
            motor_group.append(data)
        else:
            sensory_group.append(data)

    def _nerve_label(d):
        side = d['side']
        nerve = d['nerve'].lower()
        return f"{side + ' ' if side else ''}{nerve}"

    def _clause(group, all_results, modality):
        labels = [_nerve_label(d) for d in group]
        joined = _join_nerves(labels)
        suffix = 'nerve' if len(labels) == 1 else 'nerves'
        path = _ncs_path(all_results)
        if path == 'demyelinating':
            return f"{modality} neuropathy with features of demyelination in {joined} {suffix}"
        else:
            return (f"{modality} neuropathy of the {joined} {suffix} "
                    f"suggestive of {_path_phrase(path)}")

    clauses = []
    if both_group:
        results = [r for d in both_group for r in d['motor'] + d['sensory']]
        clauses.append(_clause(both_group, results, 'sensorimotor'))
    if motor_group:
        results = [r for d in motor_group for r in d['motor']]
        clauses.append(_clause(motor_group, results, 'motor'))
    if sensory_group:
        results = [r for d in sensory_group for r in d['sensory']]
        clauses.append(_clause(sensory_group, results, 'sensory'))

    return clauses


# ── Impression ────────────────────────────────────────────────────────────────

def generate_impression(classification, patient, report_types):
    """Generate the impression paragraph with proper NCS-EMG correlation."""
    motor   = classification.get('motor', [])
    sensory = classification.get('sensory', [])
    vep     = classification.get('vep', [])
    emg_form = classification.get('emg_form', [])

    motor_abnormal   = [r for r in motor   if r['classification'] not in ('normal',)]
    sensory_abnormal = [r for r in sensory if r['classification'] not in ('normal', None)]
    vep_abnormal     = [r for r in vep     if r.get('p100_status') not in ('normal', None)]

    has_motor   = bool(motor_abnormal)
    has_sensory = bool(sensory_abnormal)
    is_ncs = 'NCS' in report_types
    is_emg = 'EMG' in report_types
    is_vep = 'VEP' in report_types

    # Classify EMG findings
    emg_cl = _classify_emg_for_impression(emg_form) if is_emg and emg_form else {}
    emg_active  = emg_cl.get('active_denervation', [])
    emg_chronic = emg_cl.get('chronic_denervation', [])
    emg_myop    = emg_cl.get('myopathic', [])
    emg_total   = emg_cl.get('total', 0)
    emg_n_normal = emg_cl.get('normal_count', 0)
    all_emg_normal    = emg_total > 0 and emg_n_normal == emg_total
    any_emg_neuropathic = bool(emg_active or emg_chronic)
    any_emg_myopathic   = bool(emg_myop)

    lines = []

    # ── VEP ──────────────────────────────────────────────────────────────────
    if is_vep:
        if not vep_abnormal:
            lines.append("Normal VEP study.")
        else:
            any_absent    = any(r.get('p100_status') == 'absent'    for r in vep_abnormal)
            all_prolonged = all(r.get('p100_status') == 'prolonged' for r in vep_abnormal)
            if any_absent or all_prolonged:
                lines.append("Abnormal bilateral VEP study.")
            else:
                sides = ', '.join(set(r['side'] for r in vep_abnormal if r.get('side')))
                lines.append(f"Abnormal VEP study in the {sides} side.")

    # ── NCS + EMG ─────────────────────────────────────────────────────────────
    # Internal decision framework (not reported):
    # Q1: Neurogenic vs myopathic vs normal?
    # Q2: Active vs chronic denervation?
    # Q3: Length-dependent (polyneuropathy) vs focal vs proximal (root/plexus/AHC)?
    # Q4: Do NCS and EMG fit the same pathology?

    ncs_normal = not motor_abnormal and not sensory_abnormal

    if is_ncs and ncs_normal and (not is_emg or all_emg_normal):
        # Q1: Normal. Q4: Concordant.
        study = "NCS-EMG" if is_emg else "nerve conduction"
        lines.append(f"Normal {study} study.")

    elif is_ncs and ncs_normal and is_emg and any_emg_neuropathic:
        # Q1: Neurogenic. Q3: Proximal (NCS normal → lesion proximal to DRG or anterior horn).
        # Q4: Discordant NCS/EMG — do not over-commit to a single diagnosis.
        abn_muscles = _fmt_muscle_list(emg_active + emg_chronic)
        activity = 'active' if emg_active else 'chronic'
        lines.append(
            f"Nerve conduction study is normal. EMG shows {activity} neuropathic changes "
            f"in {abn_muscles}. Normal NCS with neuropathic EMG suggests a process proximal "
            f"to the nerve — possibilities include radiculopathy, plexopathy, or motor neuron disease. "
            f"Please correlate clinically."
        )

    elif is_ncs and ncs_normal and is_emg and any_emg_myopathic:
        # Q1: Myopathic. Q4: Concordant (NCS expected normal in myopathy).
        abn_muscles = _fmt_muscle_list(emg_myop)
        lines.append(
            f"Nerve conduction study is normal. EMG shows myopathic changes in {abn_muscles}, "
            f"suggestive of a primary muscle disorder."
        )

    elif is_ncs and (has_motor or has_sensory):
        # NCS abnormal — build per-modality clauses
        clauses = _build_ncs_clauses(motor_abnormal, sensory_abnormal)
        ncs_str = ' and '.join(clauses)

        if not is_emg or emg_total == 0:
            # NCS only
            lines.append(f"The nerve conduction study shows {ncs_str}.")

        elif all_emg_normal:
            # Normal EMG
            overall_path = _ncs_path(motor_abnormal + sensory_abnormal)
            if overall_path == 'demyelinating':
                lines.append(
                    f"The nerve conduction study shows {ncs_str}. "
                    f"EMG does not show evidence of active denervation, consistent with "
                    f"demyelination without significant axonal loss in the tested muscles."
                )
            else:
                lines.append(
                    f"The nerve conduction study shows {ncs_str}. "
                    f"EMG does not show active denervation in the tested muscles — "
                    f"this may reflect sensory-predominant involvement, early axonal neuropathy, "
                    f"or chronic stable disease with complete reinnervation."
                )

        elif any_emg_myopathic and not any_emg_neuropathic:
            abn_muscles = _fmt_muscle_list(emg_myop)
            lines.append(
                f"The nerve conduction study shows {ncs_str}. "
                f"EMG shows myopathic features in {abn_muscles}. "
                f"The combination of neuropathic NCS and myopathic EMG is atypical — "
                f"this may represent an overlap syndrome or chronic neurogenic changes "
                f"presenting with small polyphasic units. Clinical and biochemical correlation is advised."
            )

        elif emg_active:
            abn_muscles = _fmt_muscle_list(emg_active)
            if emg_chronic:
                abn_muscles += ' and chronic denervation in ' + _fmt_muscle_list(emg_chronic)
            overall_path = _ncs_path(motor_abnormal + sensory_abnormal)
            if overall_path == 'demyelinating':
                lines.append(
                    f"The NCS-EMG study shows {ncs_str}. "
                    f"Active denervation in {abn_muscles} indicates secondary axonal loss "
                    f"in addition to demyelination."
                )
            else:
                lines.append(
                    f"The NCS-EMG study shows {ncs_str} with active denervation in "
                    f"{abn_muscles}, consistent with ongoing axonal loss."
                )

        elif emg_chronic:
            abn_muscles = _fmt_muscle_list(emg_chronic)
            lines.append(
                f"The NCS-EMG study shows {ncs_str} with chronic neurogenic changes in "
                f"{abn_muscles}. Absence of active denervation potentials suggests a stable "
                f"or resolving lesion with reinnervation."
            )

    elif is_emg and not is_ncs:
        # EMG only (no NCS requested)
        if all_emg_normal or emg_total == 0:
            lines.append("Normal EMG study.")
        elif emg_active:
            lines.append(
                f"EMG shows active denervation in {_fmt_muscle_list(emg_active)}."
            )
        elif emg_chronic:
            lines.append(
                f"EMG shows chronic denervation changes in {_fmt_muscle_list(emg_chronic)}."
            )
        elif any_emg_myopathic:
            lines.append(
                f"EMG shows myopathic changes in {_fmt_muscle_list(emg_myop)}."
            )

    # Diagnosis-based context additions
    import re as _re
    diagnosis = (patient.get('diagnosis') or '').upper()
    context = ''
    # Hansen's: match HANSEN, LEPROSY, PNL HANSEN, or leprosy subtypes BT/BL/TT
    # NOTE: LL removed — too ambiguous with "lower limb"
    if (_re.search(r'\bHANSEN\b', diagnosis) or
            _re.search(r'\bLEPROSY\b', diagnosis) or
            _re.search(r'\bPNL\b', diagnosis) or
            _re.search(r'\b(BT|BL|TT)\b', diagnosis)):
        context = ' possibly due to nerve damage in Hansen\'s disease'
    elif _re.search(r'\bGBS\b', diagnosis) or 'GUILLAIN' in diagnosis:
        context = ' consistent with Guillain-Barré syndrome'
    elif any(kw in diagnosis for kw in ('BPI', 'BRACHIAL PLEXUS')):
        context = ' suggestive of brachial plexus injury'
    elif 'DIABETIC' in diagnosis:
        context = ' consistent with diabetic neuropathy'
    elif 'WRIST DROP' in diagnosis:
        context = ' at the level of the radial nerve'
    elif 'FOOT DROP' in diagnosis:
        context = ' at the level of the peroneal nerve'
    elif 'RTA' in diagnosis:
        context = ' possibly following post-traumatic nerve injury'

    if context and lines:
        # Append context to last line (before period)
        last = lines[-1]
        if last.endswith('.'):
            lines[-1] = last[:-1] + context + '.'
        else:
            lines[-1] = last + context + '.'

    # Standard footer
    lines.append("Please Correlate Clinically")
    lines.append("Not for Medico Legal Purpose.")

    return '\n'.join(lines)


# ── Master Report Builder ─────────────────────────────────────────────────────

def generate_report(parsed_data, classification, emg_form_data, report_types):
    """
    Build full report dict from all inputs.
    Returns dict:
    {
      'intro': str,
      'motor_summary': str,
      'sensory_summary': str,
      'fwave_summary': str,
      'emg_summary': str,
      'vep_summary': str,
      'impression': str,
    }
    """
    patient = parsed_data.get('patient', {})
    name = patient.get('name', 'the patient')
    age = patient.get('age', '')
    sex = patient.get('sex', '')

    # Intro line
    report_label = ' and '.join(report_types)
    intro = (
        f"This is an {report_label} report of "
        f"{'a ' if not age else ''}{age + ' years old ' if age else ''}"
        f"{sex.lower() + ', ' if sex else ''}{name}.\n"
        f"Following are the Observations during the study."
    )

    classification['emg_form'] = emg_form_data

    motor_p = generate_motor_paragraph(classification.get('motor', []))
    sensory_p = generate_sensory_paragraph(classification.get('sensory', []))
    fwave_p = generate_fwave_paragraph(classification.get('fwaves', []))
    emg_p = generate_emg_paragraph(emg_form_data)
    vep_p = generate_vep_paragraph(classification.get('vep', []))
    impression = generate_impression(classification, patient, report_types)

    return {
        'intro': intro,
        'motor_summary': motor_p,
        'sensory_summary': sensory_p,
        'fwave_summary': fwave_p,
        'emg_summary': emg_p,
        'vep_summary': vep_p,
        'impression': impression,
    }
