"""
enhancer.py — Optional Claude API enhancement layer.

Activates only if ANTHROPIC_API_KEY is present in .env.
Falls back silently to rule-based report on any error.
"""

import os
import json

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


def _load_recent_corrections(corrections_path, n=5):
    """Load n most recent edited corrections as few-shot examples."""
    try:
        with open(corrections_path, 'r') as f:
            data = json.load(f)
        edited = [c for c in data if c.get('was_edited')]
        return edited[-n:]
    except Exception:
        return []


def enhance_report(report_dict, parsed_data, classification, corrections_path):
    """
    Attempt to enhance report_dict using Claude API.
    Returns (enhanced_report_dict, was_enhanced: bool).
    """
    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key or not _ANTHROPIC_AVAILABLE:
        return report_dict, False

    try:
        client = anthropic.Anthropic(api_key=api_key)

        corrections = _load_recent_corrections(corrections_path)
        few_shot = ''
        if corrections:
            few_shot = '\n\nRecent corrections (use as style examples):\n'
            for c in corrections:
                few_shot += f"--- Example ---\nRule draft: {c.get('rule_draft', '')}\nFinal: {c.get('final_report', '')}\n"

        system_prompt = (
            "You are a clinical neurophysiology report generator for the NCS-EMG Lab, "
            "Department of Physiology, AIIMS Patna. "
            "Your task is to refine the draft report text.\n\n"
            "Rules:\n"
            "1. Preserve ALL clinical facts, nerve names, sides, and classifications exactly.\n"
            "2. Do NOT change clinical conclusions or the impression.\n"
            "3. Only improve phrasing, grammar, flow, and clinical writing style.\n"
            "4. Match the formal, concise style of AIIMS Patna neurophysiology reports.\n"
            "5. Return ONLY the refined report in the same JSON structure — no commentary."
        )

        patient = parsed_data.get('patient', {})
        user_prompt = (
            f"Patient: {patient.get('name')}, {patient.get('age')}y/{patient.get('sex')}\n"
            f"Diagnosis: {patient.get('diagnosis')}\n\n"
            f"Draft report sections:\n"
            f"{json.dumps(report_dict, indent=2)}\n\n"
            f"Classification summary:\n"
            f"Motor: {[r['classification'] + ' - ' + r['group'] for r in classification.get('motor', [])]}\n"
            f"Sensory: {[r['classification'] + ' - ' + r['group'] for r in classification.get('sensory', [])]}\n"
            f"{few_shot}\n\n"
            "Return the refined report as a JSON object with the same keys as the draft."
        )

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_prompt}],
        )

        text = response.content[0].text.strip()
        # Extract JSON if wrapped in code block
        if '```' in text:
            import re
            m = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
            if m:
                text = m.group(1).strip()

        enhanced = json.loads(text)
        # Merge — only update string fields that exist in both
        for key in report_dict:
            if key in enhanced and isinstance(enhanced[key], str):
                report_dict[key] = enhanced[key]

        return report_dict, True

    except Exception:
        return report_dict, False
