"""
normatives.py — Normative values and abnormality detection.

Sources:
  Adult:     Preston & Shapiro, EMG and Neuromuscular Disorders, 4th Ed. (2021)
  Paediatric: Parano et al., J Child Neurol 1993;8:336–338

Age gating: use paediatric if age < 14 years.
"""

import re

# ── Adult Normative Tables ────────────────────────────────────────────────────

# Motor: keyed by (nerve_name_fragment, recording_muscle)
# Values: (amp_min_mv, cv_min_ms, dl_max_ms)
# None = not applicable / not measured
ADULT_MOTOR = {
    # Upper extremity
    ('median', 'apb'):              (4.0, 50, 4.4),
    ('ulnar', 'adm'):               (6.0, 50, 3.3),
    ('ulnar', 'fdi'):               (7.0, 50, 4.5),
    ('radial', 'eip'):              (2.0, 50, 2.9),
    ('axillary', 'deltoid'):        (None, None, 4.9),
    ('musculocutaneous', 'biceps'): (None, None, 5.7),
    ('suprascapular', 'supraspinatus'): (None, None, 3.7),
    ('suprascapular', 'infraspinatus'): (None, None, 4.3),
    ('facial', 'nasalis'):          (1.0, None, 4.2),
    ('facial', 'orbicularis'):      (1.0, None, 3.1),
    # Lower extremity
    ('peroneal', 'edb'):            (2.0, 40, 6.5),
    ('peroneal', 'ta'):             (3.0, 40, 6.7),
    ('tibial', 'ahb'):              (4.0, 40, 5.8),
    ('tibial', 'adqp'):             (3.0, 40, 6.3),
}

# Sensory: keyed by nerve_name_fragment
# Values: (amp_min_uv, cv_min_ms, peak_dl_max_ms)
ADULT_SENSORY = {
    'median':           (20, 50, 3.5),
    'ulnar':            (17, 50, 3.1),
    'radial':           (15, 50, 2.9),
    'dorsal ulnar':     (8,  50, 2.5),
    'lateral antebrachial': (10, 55, 3.0),
    'medial antebrachial':  (5,  50, 3.2),
    'sural':            (6,  40, 4.4),
    'superficial peroneal': (6, 40, 4.4),
    'saphenous':        (4,  40, 4.4),
}

# F-Waves: upper limit of normal (ms)
ADULT_FWAVE = {
    'median':   31,
    'ulnar':    32,
    'peroneal': 56,
    'tibial':   56,
    'h-reflex': 34,
}

# ── Paediatric Normative Tables ───────────────────────────────────────────────
# Parano et al. — Mean (SD). Cutoffs = Mean ± 2SD.
# Format: {age_group_label: (dml_mean, dml_sd, cv_mean, cv_sd, f_mean, f_sd, amp_mean, amp_sd)}
# amp in mV for motor, µV for sensory

PAED_AGE_GROUPS = [
    # (min_days, max_days, label)
    (0,    30,   '0-1mo'),
    (31,   180,  '1-6mo'),
    (181,  365,  '6-12mo'),
    (366,  730,  '1-2yr'),
    (731,  1460, '2-4yr'),
    (1461, 2190, '4-6yr'),
    (2191, 5110, '6-14yr'),
]

PAED_MEDIAN_MOTOR = {
    '0-1mo':  (2.23, 0.29, 25.43, 3.84, 16.12, 1.50, 3.00, 0.31),
    '1-6mo':  (2.21, 0.34, 34.35, 6.61, 16.89, 1.65, 7.37, 3.24),
    '6-12mo': (2.13, 0.19, 43.57, 4.78, 17.31, 1.77, 7.67, 4.45),
    '1-2yr':  (2.04, 0.18, 48.23, 4.58, 17.44, 1.29, 8.90, 3.61),
    '2-4yr':  (2.18, 0.43, 53.59, 5.29, 17.91, 1.11, 9.55, 4.34),
    '4-6yr':  (2.27, 0.45, 56.26, 4.61, 19.44, 1.51, 10.37, 3.66),
    '6-14yr': (2.73, 0.44, 57.32, 3.35, 23.23, 2.57, 12.37, 4.79),
}

PAED_PERONEAL_MOTOR = {
    '0-1mo':  (2.43, 0.48, 22.43, 1.22, 22.07, 1.46, 3.06, 1.26),
    '1-6mo':  (2.25, 0.48, 35.18, 3.96, 23.11, 1.89, 5.23, 2.37),
    '6-12mo': (2.31, 0.62, 43.55, 3.77, 25.86, 1.35, 5.41, 2.01),
    '1-2yr':  (2.29, 0.43, 51.42, 3.02, 25.98, 1.95, 5.80, 2.48),
    '2-4yr':  (2.62, 0.75, 55.73, 4.45, 29.52, 2.15, 6.10, 2.99),
    '4-6yr':  (3.01, 0.43, 56.14, 4.96, 29.98, 2.68, 7.10, 4.50),
    '6-14yr': (3.25, 0.51, 57.05, 4.54, 34.27, 4.29, 8.15, 4.50),
}

PAED_MEDIAN_SENSORY = {
    '0-1mo':  (22.31, 2.16, 6.22, 1.30),
    '1-6mo':  (35.52, 6.59, 15.86, 5.18),
    '6-12mo': (40.31, 5.23, 16.00, 5.18),
    '1-2yr':  (46.93, 5.03, 24.00, 7.36),
    '2-4yr':  (49.51, 3.34, 24.28, 5.49),
    '4-6yr':  (51.71, 5.16, 25.12, 5.22),
    '6-14yr': (53.84, 3.26, 26.72, 9.43),
}

PAED_SURAL_SENSORY = {
    '0-1mo':  (20.26, 1.55, 9.12, 3.02),
    '1-6mo':  (34.63, 5.43, 11.66, 3.57),
    '6-12mo': (38.18, 5.00, 15.10, 8.22),
    '1-2yr':  (49.73, 5.53, 15.41, 9.98),
    '2-4yr':  (52.63, 2.96, 23.27, 6.84),
    '4-6yr':  (53.83, 4.34, 22.66, 5.42),
    '6-14yr': (53.85, 4.19, 26.75, 6.59),
}


def _age_group(age_years):
    """Return paediatric age group label for given age in years."""
    age_days = age_years * 365
    for min_d, max_d, label in PAED_AGE_GROUPS:
        if min_d <= age_days <= max_d:
            return label
    return None


def _nerve_key(nerve_name):
    """Normalise nerve name for dict lookup."""
    nk = nerve_name.lower().strip()
    # Handle common Neurosoft spelling variants
    nk = nk.replace('peronial', 'peroneal')
    nk = nk.replace('tibialis', 'tibial')
    nk = nk.replace('suralis', 'sural')
    nk = nk.replace('medianus', 'median')
    nk = nk.replace('ulnaris', 'ulnar')
    nk = nk.replace('axillaris', 'axillary')
    nk = nk.replace('musculocutaneus', 'musculocutaneous')
    nk = nk.replace('suprascapularis', 'suprascapular')
    return nk


def get_motor_normatives(nerve_name, age_years=None):
    """
    Return (amp_min_mv, cv_min_ms, dl_max_ms) for a motor nerve.
    Uses paediatric table if age < 14.
    Returns (None, None, None) if not found.
    """
    nk = _nerve_key(nerve_name)
    # Try paediatric first
    if age_years is not None and age_years < 14:
        ag = _age_group(age_years)
        if ag:
            if 'median' in nk:
                row = PAED_MEDIAN_MOTOR[ag]
                dml_uln = row[0] + 2 * row[1]
                cv_lln = row[2] - 2 * row[3]
                f_uln = row[4] + 2 * row[5]
                amp_lln = row[6] - 2 * row[7]
                return (max(0, amp_lln), max(0, cv_lln), dml_uln)
            if 'peroneal' in nk or 'peronial' in nk:
                row = PAED_PERONEAL_MOTOR[ag]
                dml_uln = row[0] + 2 * row[1]
                cv_lln = row[2] - 2 * row[3]
                amp_lln = row[6] - 2 * row[7]
                return (max(0, amp_lln), max(0, cv_lln), dml_uln)

    # Adult lookup — match nerve_frag first, then prefer muscle match
    best = None
    for (nerve_frag, muscle), vals in ADULT_MOTOR.items():
        if nerve_frag in nk:
            if muscle in nk:
                return vals   # exact nerve+muscle match — use immediately
            if best is None:
                best = vals   # nerve-only match — keep as fallback
    if best is not None:
        return best

    return (None, None, None)


def get_sensory_normatives(nerve_name, age_years=None):
    """
    Return (amp_min_uv, cv_min_ms, peak_dl_max_ms) for a sensory nerve.
    """
    nk = _nerve_key(nerve_name)
    if age_years is not None and age_years < 14:
        ag = _age_group(age_years)
        if ag:
            if 'median' in nk:
                row = PAED_MEDIAN_SENSORY[ag]
                cv_lln = row[0] - 2 * row[1]
                amp_lln = row[2] - 2 * row[3]
                return (max(0, amp_lln), max(0, cv_lln), None)
            if 'sural' in nk:
                row = PAED_SURAL_SENSORY[ag]
                cv_lln = row[0] - 2 * row[1]
                amp_lln = row[2] - 2 * row[3]
                return (max(0, amp_lln), max(0, cv_lln), None)

    for nerve_frag, vals in ADULT_SENSORY.items():
        if nerve_frag in nk:
            return vals

    return (None, None, None)


def get_fwave_uln(nerve_name):
    """Return F-wave upper limit of normal (ms)."""
    nk = _nerve_key(nerve_name)
    for nerve_frag, uln in ADULT_FWAVE.items():
        if nerve_frag in nk:
            return uln
    return None


# ── Abnormality Flagging ──────────────────────────────────────────────────────

def flag_motor_row(row, age_years=None):
    """
    Given a motor NCS row dict, return abnormality flags dict.
    flags: {amp: 'low'|'nr'|'normal'|None, cv: 'slow'|'normal'|None, dl: 'prolonged'|'normal'|None}
    """
    group = row.get('group', '')
    # Extract nerve name from group (e.g. "L, Ulnar" → "ulnar")
    nerve = re.sub(r'^[LR][,\s]+', '', group or '').strip().lower()

    amp_min, cv_min, dl_max = get_motor_normatives(nerve, age_years)

    flags = {'amp': None, 'cv': None, 'dl': None, 'nerve': nerve, 'group': group}

    ampl = row.get('ampl_mv')
    vel = row.get('vel_ms')
    lat = row.get('lat_ms')

    if ampl == 'NR':
        flags['amp'] = 'nr'
    elif ampl is not None and amp_min is not None:
        try:
            if float(ampl) < amp_min:
                flags['amp'] = 'low'
            else:
                flags['amp'] = 'normal'
        except ValueError:
            pass

    if vel is not None and cv_min is not None:
        try:
            pct = float(vel) / cv_min * 100
            if pct < 75:
                flags['cv'] = 'slow'
            else:
                flags['cv'] = 'normal'
        except ValueError:
            pass

    if lat is not None and dl_max is not None:
        # Only applies to distal (wrist/ankle) stimulation
        site = (row.get('site') or '').lower()
        if site in ('wrist', 'ankle', 'dist.', 'distal') or 'erb' in site:
            try:
                lat_f = float(lat)
                # Report as prolonged if DL exceeds the ULN (used in summary text)
                flags['dl'] = 'prolonged' if lat_f > dl_max else 'normal'
                # Demyelination criterion: >130% of ULN (used for classification only)
                flags['dl_demy'] = 'prolonged' if lat_f / dl_max * 100 > 130 else 'normal'
            except ValueError:
                pass

    return flags


def flag_sensory_row(row, age_years=None):
    """
    Return abnormality flags for a sensory NCS row.

    Sensory classification rules:
    - Amplitude NR or low → axonal loss
    - Distal latency > ULN → demyelinating
    - CV is NOT used — latency already captures conduction slowing and is more reliable
    """
    group = row.get('group', '')
    nerve = re.sub(r'^[LR][,\s]+', '', group or '').strip().lower()

    amp_min, _cv_min, dl_max = get_sensory_normatives(nerve, age_years)
    flags = {'amp': None, 'dl': None, 'nerve': nerve, 'group': group}

    ampl = row.get('ampl_uv')
    lat  = row.get('lat_ms')

    if ampl == 'NR':
        flags['amp'] = 'nr'
    elif ampl is not None and amp_min is not None:
        try:
            flags['amp'] = 'low' if float(ampl) < amp_min else 'normal'
        except ValueError:
            pass

    # Latency check — only at distal stimulation site
    if lat is not None and dl_max is not None:
        try:
            lat_f = float(lat)
            # Report as prolonged if DL exceeds ULN
            flags['dl'] = 'prolonged' if lat_f > dl_max else 'normal'
            # Demyelination criterion: >130% of ULN (for mixed classification)
            flags['dl_demy'] = 'prolonged' if lat_f / dl_max * 100 > 130 else 'normal'
        except ValueError:
            pass

    return flags


def flag_fwave_row(row):
    """Return abnormality flags for an F-wave row."""
    group = row.get('group', '')
    nerve = re.sub(r'^[LR][,\s]+', '', group or '').strip().lower()
    uln = get_fwave_uln(nerve)
    flags = {'status': None, 'nerve': nerve, 'group': group}

    fmin = row.get('fmin_lat_ms')
    if fmin == 'NR':
        flags['status'] = 'nr'
    elif fmin is not None and uln is not None:
        try:
            if float(fmin) > uln:
                flags['status'] = 'prolonged'
            else:
                flags['status'] = 'normal'
        except ValueError:
            pass

    return flags


def flag_vep_row(row, sex=None):
    """Return VEP abnormality flags."""
    p100 = row.get('p100_lat')
    ampl = row.get('p100_n145_ampl')
    stim_side = row.get('stim_side', '')
    flags = {'p100_status': None, 'amp_status': None, 'side': stim_side}

    # P100 cutoffs: ≤115ms females, ≤110ms males
    p100_uln = 115 if (sex or '').lower() in ('female', 'f') else 110
    if p100 == 'NR':
        flags['p100_status'] = 'absent'
    elif p100 is not None:
        try:
            if float(p100) > p100_uln:
                flags['p100_status'] = 'prolonged'
            else:
                flags['p100_status'] = 'normal'
        except ValueError:
            pass

    return flags
