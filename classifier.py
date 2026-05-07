"""
classifier.py — Pattern classification engine.

Takes flagged NCS rows and produces per-nerve and overall classifications.
"""

import re
from normatives import flag_motor_row, flag_sensory_row, flag_fwave_row, flag_vep_row


def _side_from_group(group):
    """Extract side (Left/Right/Bilateral) from group label like 'L, Ulnar'."""
    if not group:
        return ''
    g = group.strip()
    if g.startswith('L,') or g.startswith('L '):
        return 'left'
    if g.startswith('R,') or g.startswith('R '):
        return 'right'
    if g.startswith('B,') or g.startswith('Bilateral'):
        return 'bilateral'
    return ''


def _nerve_from_group(group):
    """Extract nerve name from group label like 'L, Ulnar'."""
    import re
    if not group:
        return ''
    return re.sub(r'^[LRB][,\s]+', '', group).strip()


# ── Known stimulation sites per nerve type ────────────────────────────────────
# NOTE: Neurosoft RTF sometimes has site name errors or unusual spellings.
# Rules:
# - Proximal nerves (axillary, suprascapular, musculocutaneous): single site → always Erb's point
# - Median / Ulnar: 2 rows → row[0] = wrist (distal), row[1] = elbow (proximal)
# - Peroneal: 2 rows → row[0] = ankle (distal), row[1] = head of fibula (proximal)
# - Tibial: 2 rows → row[0] = medial malleolus (distal), row[1] = popliteal fossa (proximal)
# When site name is unclear or missing, infer from nerve type and row position.
_PROXIMAL_NERVES = ('axillary', 'suprascapular', 'musculocutaneous',
                    'axillaris', 'suprascapularis', 'musculocutaneus')

def _is_proximal_nerve(nerve_lower):
    return any(p in nerve_lower for p in _PROXIMAL_NERVES)

def _get_distal_row(rows, nerve_lower):
    """
    Return the distal stimulation row for a nerve group.
    For proximal nerves (Erb's point), any single row is the distal row.
    For others, prefer rows with a recognised distal site name;
    if none found, fall back to first row (position-based inference).
    """
    DISTAL_SITES = ('wrist', 'ankle', 'dist', 'distal', 'dist.',
                    'medial malleolus', 'sole', 'erb')

    # Proximal nerve: only one stimulation point, always treat as distal
    if _is_proximal_nerve(nerve_lower):
        return rows[0] if rows else None

    # Try to find a recognised distal site
    for row in rows:
        site = (row.get('site') or '').lower()
        if any(ds in site for ds in DISTAL_SITES):
            return row

    # NOTE: site name not recognised — infer: first row = distal (wrist/ankle)
    return rows[0] if rows else None


def classify_motor(motor_rows, age_years=None):
    """
    Classify each motor nerve group.
    Returns list of dicts:
    {nerve, side, classification, amplitude_status, conduction_status, notes}
    """
    # Group rows by nerve group
    groups = {}
    for row in motor_rows:
        g = row.get('group', '')
        if g not in groups:
            groups[g] = []
        groups[g].append(row)

    results = []
    for group, rows in groups.items():
        if not group:
            continue
        side = _side_from_group(group)
        nerve = _nerve_from_group(group)
        nerve_lower = nerve.lower()

        distal_row = _get_distal_row(rows, nerve_lower)
        if distal_row is None:
            continue

        flags = flag_motor_row(distal_row, age_years)

        # For velocity: check ALL rows (motor CV is calculated from proximal sites)
        for row in rows:
            vel = row.get('vel_ms')
            if vel and vel != 'NR':
                try:
                    from normatives import get_motor_normatives
                    nerve_key = re.sub(r'^[LRB][,\s]+', '', group or '').strip().lower()
                    _, cv_min, _ = get_motor_normatives(nerve_key, age_years)
                    if cv_min and float(vel) < cv_min:
                        flags['cv'] = 'slow'
                        break
                except (ValueError, TypeError):
                    pass

        amp_status = flags.get('amp')
        cv_status = flags.get('cv')
        dl_status = flags.get('dl')

        # Conduction flag: slow CV or prolonged DL = demyelinating
        cond_flag = 'normal'
        if cv_status == 'slow' or dl_status == 'prolonged':
            cond_flag = 'demyelinating'

        # Classification
        if amp_status == 'nr':
            classification = 'non-recordable'
        elif amp_status == 'low' and cond_flag == 'demyelinating':
            classification = 'mixed'
        elif amp_status == 'low':
            classification = 'axonal'
        elif cond_flag == 'demyelinating':
            classification = 'demyelinating'
        else:
            classification = 'normal'

        # Check for unequivocal demyelination
        notes = []
        for row in rows:
            vel = row.get('vel_ms')
            if vel and vel != 'NR':
                try:
                    v = float(vel)
                    nerve_lower = nerve.lower()
                    # Upper limb: arms
                    is_upper = any(x in nerve_lower for x in ('median', 'ulnar', 'radial', 'axillary', 'musculo', 'suprasc'))
                    if is_upper and v < 35:
                        notes.append('unequivocal demyelination (CV < 35 m/s)')
                    elif not is_upper and v < 30:
                        notes.append('unequivocal demyelination (CV < 30 m/s)')
                except ValueError:
                    pass

        # Check conduction block (proximal vs distal amplitude)
        if len(rows) >= 2:
            try:
                dist_amp = float(rows[0].get('ampl_mv') or 0)
                prox_amp = float(rows[-1].get('ampl_mv') or 0)
                if dist_amp > 0:
                    drop_pct = (dist_amp - prox_amp) / dist_amp * 100
                    if drop_pct > 50:
                        notes.append(f'conduction block ({drop_pct:.0f}% amplitude drop)')
                    # Temporal dispersion flag (>20% proximal drop) — disabled for now
                    # elif drop_pct > 20:
                    #     notes.append('possible temporal dispersion')
            except (ValueError, TypeError):
                pass

        results.append({
            'nerve': nerve,
            'side': side,
            'group': group,
            'classification': classification,
            'amplitude_status': amp_status,
            'conduction_status': cond_flag,
            'cv_status': cv_status,
            'dl_status': dl_status,
            'notes': notes,
            'modality': 'motor',
            '_distal_amp': distal_row.get('ampl_mv'),  # kept for side-to-side comparison
        })

    # ── Side-to-side amplitude comparison ────────────────────────────────────
    # Used when no absolute amplitude normative exists (proximal nerves).
    # If one side is ≥70% less than the other, flag as axonal asymmetry.
    # NOTE: 70% threshold — less strict than 50% to avoid over-flagging
    #       minor physiological asymmetry in proximal nerve studies.
    from collections import defaultdict
    by_nerve = defaultdict(list)
    for r in results:
        by_nerve[r['nerve'].lower()].append(r)

    for nerve_key, pair in by_nerve.items():
        if len(pair) != 2:
            continue
        r_left  = next((r for r in pair if r['side'] == 'left'),  None)
        r_right = next((r for r in pair if r['side'] == 'right'), None)
        if not r_left or not r_right:
            continue
        # Only apply when no absolute normative was used (amp_status is None on both)
        if r_left['amplitude_status'] is not None or r_right['amplitude_status'] is not None:
            continue
        try:
            amp_l = float(r_left['_distal_amp'])  if r_left['_distal_amp']  not in (None, 'NR') else None
            amp_r = float(r_right['_distal_amp']) if r_right['_distal_amp'] not in (None, 'NR') else None
            if amp_l and amp_r:
                stronger = max(amp_l, amp_r)
                weaker_r = r_left if amp_l < amp_r else r_right
                weaker_amp = min(amp_l, amp_r)
                if weaker_amp / stronger < 0.80:  # weaker side is ≥20% less
                    weaker_r['amplitude_status'] = 'asymmetric'
                    if weaker_r['classification'] == 'normal':
                        weaker_r['classification'] = 'axonal'
                    weaker_r['notes'].append(
                        f'amplitude asymmetry: {weaker_amp:.1f} mV vs {stronger:.1f} mV '
                        f'({100 - weaker_amp/stronger*100:.0f}% reduction)'
                    )
        except (ValueError, TypeError):
            pass

    # Clean up internal key before returning
    for r in results:
        r.pop('_distal_amp', None)

    return results


def classify_sensory(sensory_rows, age_years=None):
    """Classify each sensory nerve group."""
    groups = {}
    for row in sensory_rows:
        g = row.get('group', '')
        if g not in groups:
            groups[g] = []
        groups[g].append(row)

    results = []
    for group, rows in groups.items():
        if not group:
            continue
        side = _side_from_group(group)
        nerve = _nerve_from_group(group)

        # Use first (distal) row
        row = rows[0] if rows else {}
        flags = flag_sensory_row(row, age_years)

        amp_status = flags.get('amp')
        dl_status  = flags.get('dl')

        # Amplitude takes priority — low/NR = axonal regardless of latency
        if amp_status == 'nr':
            classification = 'absent'
        elif amp_status == 'low':
            classification = 'axonal'
        elif dl_status == 'prolonged':
            classification = 'demyelinating'
        else:
            classification = 'normal'

        results.append({
            'nerve': nerve,
            'side': side,
            'group': group,
            'classification': classification,
            'amplitude_status': amp_status,
            'conduction_status': dl_status,
            'notes': [],
            'modality': 'sensory',
        })

    return results


def classify_fwaves(fwave_rows):
    """Classify F-wave rows."""
    groups = {}
    for row in fwave_rows:
        g = row.get('group', '')
        if g not in groups:
            groups[g] = []
        groups[g].append(row)

    results = []
    for group, rows in groups.items():
        if not group:
            continue
        side = _side_from_group(group)
        nerve = _nerve_from_group(group)
        row = rows[0] if rows else {}
        flags = flag_fwave_row(row)
        results.append({
            'nerve': nerve,
            'side': side,
            'group': group,
            'status': flags.get('status', 'normal'),
            'modality': 'fwave',
        })
    return results


def classify_vep(vep_rows, sex=None):
    """Classify VEP rows."""
    results = []
    for row in vep_rows:
        flags = flag_vep_row(row, sex)
        results.append({
            'side': row.get('stim_side', ''),
            'p100_lat': row.get('p100_lat'),
            'p100_status': flags.get('p100_status'),
            'amp_status': flags.get('amp_status'),
            'modality': 'vep',
        })
    return results


def determine_overall_pattern(motor_results, sensory_results):
    """
    Determine overall neuropathy pattern:
    mononeuropathy | multiple mononeuropathies | polyneuropathy | normal
    """
    abnormal_motor = [r for r in motor_results if r['classification'] != 'normal']
    abnormal_sensory = [r for r in sensory_results if r['classification'] not in ('normal', None)]

    all_abnormal = abnormal_motor + abnormal_sensory

    if not all_abnormal:
        return 'normal'

    # Count unique nerves affected
    affected_nerves = set(r['nerve'].lower() for r in all_abnormal)

    if len(affected_nerves) == 1:
        return 'mononeuropathy'
    elif len(affected_nerves) >= 3:
        # Check if symmetric — same nerves on both sides
        sides = set(r['side'] for r in all_abnormal)
        if 'left' in sides and 'right' in sides:
            return 'polyneuropathy'
        return 'multiple mononeuropathies'
    else:
        return 'multiple mononeuropathies'


def run_classification(parsed_data, age_years=None, sex=None):
    """
    Full classification pipeline.
    Returns dict with all classification results.
    """
    motor = classify_motor(parsed_data.get('motor_ncs', []), age_years)
    sensory = classify_sensory(parsed_data.get('sensory_ncs', []), age_years)
    fwaves = classify_fwaves(parsed_data.get('f_waves', []))
    vep = classify_vep(parsed_data.get('vep', []), sex)
    pattern = determine_overall_pattern(motor, sensory)

    return {
        'motor': motor,
        'sensory': sensory,
        'fwaves': fwaves,
        'vep': vep,
        'overall_pattern': pattern,
    }
