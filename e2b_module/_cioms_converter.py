"""
CIOMS I form HTML generator for E2B R3 ICSR data.

Based on the repository CIOMS template (backend/backend/app/templates/cioms.html)
and field-mapping logic (backend/backend/app/src/layers/domain/models/cioms.py).
Adapted for standalone Python rendering (no Django dependency).

Date format: DD Mon YYYY with 3-letter month abbreviation (e.g. "9 Oct 2008").
Overflow: long text fields are truncated with "CONTINUED ON NEXT PAGE" on the
main form; full content appears in the continuation section below.
"""

import html as _html_lib
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MONTH_ABBR: Tuple[str, ...] = (
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
)

_AGE_UNITS: Dict[str, str] = {
    '800': 'decade', '801': 'year', '802': 'month',
    '803': 'week',   '804': 'day',  '805': 'hour',
}

_DUR_UNITS: Dict[str, str] = {
    '800': 'decade', '801': 'year', '802': 'month',
    '803': 'week',   '804': 'day',  '805': 'hour',
}

_OUTCOMES: Dict[str, str] = {
    '1': 'Recovered/Resolved', '2': 'Recovering/Resolving',
    '3': 'Not Recovered/Not Resolved', '4': 'Recovered with Sequelae',
    '5': 'Fatal', '6': 'Unknown',
}

_ACT_NAMES: Dict[str, str] = {
    '1': 'Drug Withdrawn', '2': 'Dose Reduced', '3': 'Dose Increased',
    '4': 'Dose Not Changed', '5': 'Unknown', '6': 'Not Applicable',
}

# Character limits for long free-text fields on the main page
_LIMITS: Dict[str, int] = {
    'reactions':    900,
    'concomitant':  280,
    'history':      280,
    'manufacturer': 200,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(v: Any) -> str:
    return _html_lib.escape(str(v)) if v else ''


def _sv(val: Any, default: str = '') -> str:
    if val is None:
        return default
    if isinstance(val, dict):
        v = val.get('_value') or val.get('_null_flavor', '')
        return str(v) if v else default
    return str(val) if val else default


def _parse_date(s: Any) -> Tuple[str, str, str]:
    """Split compact HL7 date into (day_num_str, month_abbr, year_str)."""
    s = str(s or '').strip()
    year  = s[:4]  if len(s) >= 4 else ''
    month = s[4:6] if len(s) >= 6 else ''
    day   = s[6:8] if len(s) >= 8 else ''

    day_out = str(int(day)) if day else ''
    month_out = ''
    if month:
        try:
            m = int(month)
            if 1 <= m <= 12:
                month_out = _MONTH_ABBR[m - 1]
        except ValueError:
            pass
    return day_out, month_out, year


def _fmt_date(s: Any) -> str:
    """Format compact HL7 date as 'DD Mon YYYY' (combined string)."""
    d, m, y = _parse_date(s)
    return ' '.join(p for p in (d, m, y) if p)


def _cut(text: str, key: str) -> Tuple[str, bool]:
    """Return (display_text, overflowed)."""
    limit = _LIMITS.get(key, 0)
    if not limit or len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + ' (Cont...)', True


def _chk(flag: bool) -> str:
    return ' checked' if flag else ''


# ---------------------------------------------------------------------------
# Context builder  (E2B R3 dict → display fields)
# ---------------------------------------------------------------------------

def _build_context(data: Dict[str, Any]) -> Dict[str, Any]:  # noqa: C901
    d     = data.get('d_patient_characteristics') or {}
    c1    = data.get('c_1_identification_case_safety_report') or {}
    c2s   = data.get('c_2_r_primary_source_information') or []
    c3    = data.get('c_3_information_sender_case_safety_report') or {}
    rxns  = data.get('e_i_reaction_event') or []
    drugs = data.get('g_k_drug_information') or []
    hblk  = data.get('h_narrative_case_summary') or {}
    tests = data.get('f_r_results_tests_procedures_investigation_patient') or []
    lit   = data.get('c_4_r_literature_reference') or []

    c2 = c2s[0] if c2s else {}
    r0 = rxns[0] if rxns else {}   # primary (first) reaction event

    # ------------------------------------------------------------------
    # Fields 1 / 1a
    # ------------------------------------------------------------------
    initials = _sv(d.get('d_1_patient')) or 'UNK'
    # Country: prefer reaction country, fall back to reporter country
    country = (_sv(r0.get('e_i_9_identification_country_reaction'))
               or _sv(c2.get('c_2_r_3_reporter_country_code'))
               or 'UNK')

    # ------------------------------------------------------------------
    # Field 2 – Date of birth  (separate day / month / year for form boxes)
    # ------------------------------------------------------------------
    dob_d, dob_m, dob_y = _parse_date(_sv(d.get('d_2_1_date_birth')))

    # Field 2a – Age
    _UCUM_UNITS = {'a': 'year', 'mo': 'month', 'wk': 'week', 'd': 'day', 'h': 'hour'}
    age_n = _sv(d.get('d_2_2a_age_onset_reaction_num'))
    age_u = _sv(d.get('d_2_2b_age_onset_reaction_unit'))
    age_unit_name = _AGE_UNITS.get(age_u) or _UCUM_UNITS.get(age_u, '')
    if age_n:
        age = age_n if not age_unit_name or age_unit_name == 'year' else f"{age_n} {age_unit_name}s"
    else:
        age = 'UNK'

    # Field 3 – Sex
    sex = {'1': 'M', '2': 'F'}.get(_sv(d.get('d_5_sex')), '')

    # ------------------------------------------------------------------
    # Fields 4–6 – Reaction onset
    # ------------------------------------------------------------------
    onset_d, onset_m, onset_y = _parse_date(_sv(r0.get('e_i_4_date_start_reaction')))

    # ------------------------------------------------------------------
    # Fields 7+13 – Reaction description  +  8–12 seriousness
    # ------------------------------------------------------------------
    patient_died = hosp = disab = lifethr = other = False
    describe_parts: List[str] = []

    for r in rxns:
        def _b(f: str) -> bool:
            v = r.get(f)
            if isinstance(v, dict):
                v = v.get('_value', '')
            return str(v or '').lower() in ('1', 'true')

        patient_died |= _b('e_i_3_2a_results_death')
        hosp         |= _b('e_i_3_2c_caused_prolonged_hospitalisation')
        disab        |= _b('e_i_3_2d_disabling_incapacitating')
        lifethr      |= _b('e_i_3_2b_life_threatening')
        other        |= (_b('e_i_3_2e_congenital_anomaly')
                         or _b('e_i_3_2f_other_medically_important_condition'))

        native_lang = _sv(r.get('e_i_1_1b_reaction_primary_source_language'))
        native_txt  = _sv(r.get('e_i_1_1a_reaction_primary_source_native_language'))
        eng_txt     = _sv(r.get('e_i_1_2_reaction_primary_source_translation'))

        if native_txt:
            prefix = f"[{native_lang}] " if native_lang else ''
            describe_parts.append(f"{prefix}{native_txt}")
        if eng_txt:
            describe_parts.append(f"[ENG] {eng_txt}")

        outcome_code = _sv(r.get('e_i_7_outcome_reaction_last_observation'))
        if outcome_code:
            describe_parts.append(f"*{_OUTCOMES.get(outcome_code, outcome_code)}*")

    if describe_parts:
        describe_parts.append('')

    # Drug actions
    drug_actions: List[str] = []
    suspects_raw: List[Dict[str, Any]] = []
    conco_lines: List[str] = []

    for g in drugs:
        role   = _sv(g.get('g_k_1_characterisation_drug_role'))
        name   = _sv(g.get('g_k_2_2_medicinal_product_name_primary_source'))
        action = _sv(g.get('g_k_8_r_action_taken_drug'))

        if action and action != '5':
            drug_actions.append(f"{name} {_ACT_NAMES.get(action, action)}")

        dosages: List[Dict[str, str]] = []
        for dos in (g.get('g_k_4_r_dosage_information') or []):
            dn   = _sv(dos.get('g_k_4_r_1a_dose_num'))
            du   = _sv(dos.get('g_k_4_r_1b_dose_unit'))
            pv   = _sv(dos.get('g_k_4_r_2_number_units_interval'))
            pu   = _sv(dos.get('g_k_4_r_3_definition_interval_unit'))
            txt  = _sv(dos.get('g_k_4_r_8_dosage_text'))
            dura_n = _sv(dos.get('g_k_4_r_6a_duration_drug_administration_num'))
            dura_u = _sv(dos.get('g_k_4_r_6b_duration_drug_administration_unit'))

            dose_str = f"{dn} {du}".strip() if dn else ''
            if pv and pu:
                dose_str = (f"{dose_str}/{pv}{pu}" if dose_str else f"{pv}{pu}")
            # G.k.4.r.8 (dosage text) is the primary CIOMS field; calculated dose is fallback
            daily_dose = txt or dose_str or ''
            dura_u_name = _DUR_UNITS.get(dura_u, dura_u)

            dosages.append({
                'lot':        _sv(dos.get('g_k_4_r_7_batch_lot_number')),
                'daily_dose': daily_dose,
                'route':      _sv(dos.get('g_k_4_r_10_1_route_administration')),
                'from_dt':    _fmt_date(_sv(dos.get('g_k_4_r_4_date_time_drug'))),
                'to_dt':      _fmt_date(_sv(dos.get('g_k_4_r_5_date_time_last_administration'))),
                'duration':   (f"{dura_n} {dura_u_name}s".strip() if dura_n else ''),
            })

        indications: List[Dict[str, str]] = []
        for ind in (g.get('g_k_7_r_indication_use_case') or []):
            indications.append({
                'primary_source': _sv(ind.get('g_k_7_r_1_indication_primary_source')),
                'meddra':         _sv(ind.get('g_k_7_r_2b_indication_meddra_code')),
            })

        # Field 20 – abate after stopping?
        outcome_code = _sv(r0.get('e_i_7_outcome_reaction_last_observation'))
        if action in ('1', '2'):       # withdrawn or dose reduced
            if outcome_code in ('1', '2', '4'):
                abate = 'Y'
            elif outcome_code in ('3', '5'):
                abate = 'N'
            else:
                abate = ''
        elif action in ('3', '4', '6'):   # increased, unchanged, NA
            abate = 'NA'
        else:
            abate = ''

        # Field 21 – reappear after reintroduction?  (G.k.9.i.4 per CIOMS rules)
        reappear = ''
        # Primary source: G.k.9.i.4 drug-reaction matrix
        for dr in (g.get('g_k_9_i_drug_reaction_matrix') or []):
            rc = _sv(dr.get('g_k_9_i_4_reaction_recur_readministration'))
            if rc:
                if rc in ('1', 'YES_YES'):
                    reappear = 'Y'
                elif rc in ('2', 'YES_NO'):
                    reappear = 'N'
                elif rc in ('3', '4', 'NA', 'NOT_APPLICABLE'):
                    reappear = 'NA'
                break
        # Fallback: G.k.9.r case assessment rechallenge result
        if not reappear:
            for assess in (g.get('g_k_9_r_case_assessment') or []):
                rc = _sv(assess.get('g_k_9_r_4_result_rechallenge'))
                if rc:
                    reappear = {'1': 'Y', '2': 'N', '3': 'NA', '4': 'NA'}.get(rc, '')
                    break

        entry = {
            'name':        name,
            'dosages':     dosages,
            'indications': indications,
            'abate':       abate,
            'reappear':    reappear,
        }

        if role == '1':    # Suspect
            suspects_raw.append(entry)
        elif role == '2':  # Concomitant
            dose_dates = [
                f"{dos['from_dt']}—{dos['to_dt']}"
                for dos in dosages
                if dos['from_dt'] or dos['to_dt']
            ]
            line = name + (': ' + ', '.join(dose_dates) if dose_dates else '')
            if line.strip():
                conco_lines.append(line)

    # Drug actions → describe
    if drug_actions:
        describe_parts.append('Actions Taken with Drugs:')
        describe_parts.extend(drug_actions)
        describe_parts.append('')

    # Case narrative
    narr = _sv(hblk.get('h_1_case_narrative'))
    if narr:
        describe_parts.append(f"Case Narrative: {narr}")
        describe_parts.append('')

    # Lab/test results
    test_lines = [_sv(t.get('f_r_3_4_result_unstructured_data'))
                  for t in tests
                  if _sv(t.get('f_r_3_4_result_unstructured_data'))]
    if test_lines:
        describe_parts.append('Relevant tests/lab data:')
        describe_parts.extend(test_lines)

    reactions_full = '\n'.join(describe_parts).strip()
    conco_full     = '\n'.join(conco_lines)

    # History
    hist = _sv(d.get('d_7_2_text_medical_history'))
    if not hist:
        mh_list = d.get('d_7_1_r_structured_information_medical_history') or []
        hist_parts = []
        for m in mh_list:
            code  = _sv(m.get('d_7_1_r_1b_medical_history_meddra_code'))
            start = _fmt_date(_sv(m.get('d_7_1_r_2_start_date')))
            cont  = _sv(m.get('d_7_1_r_3_continuing'))
            if not code:
                continue
            entry = f'MedDRA {code}'
            if start:
                entry += f' (from {start})'
            if cont == 'true':
                entry += ', ongoing'
            hist_parts.append(entry)
        hist = '; '.join(hist_parts)
    history_full = hist or ''

    # Field 24a – manufacturer name/address
    # C.1.9.1.r.1 = source company name; supplement with sender address (C.3)
    mfr_parts: List[str] = []
    for src in (c1.get('c_1_9_1_r_source_case_id') or []):
        sid = _sv(src.get('c_1_9_1_r_1_source_case_id'))
        if sid:
            mfr_parts.append(sid)
    # Always append sender org + address as address lines
    for f in ('c_3_2_sender_organisation', 'c_3_3_1_sender_department',
              'c_3_3_3_sender_given_name', 'c_3_3_5_sender_family_name',
              'c_3_4_1_sender_street_address', 'c_3_4_2_sender_city',
              'c_3_4_3_sender_state_province', 'c_3_4_4_sender_postcode',
              'c_3_4_5_sender_country_code'):
        v = _sv(c3.get(f))
        if v and v not in mfr_parts:
            mfr_parts.append(v)
    mfr_full = ', '.join(mfr_parts)

    # Field 24b – MFR control no.
    # C.1.9.1.r.2 (case ID at source) preferred; fallback C.1.8.1 (worldwide unique ID)
    ctrl_no = ''
    for src in (c1.get('c_1_9_1_r_source_case_id') or []):
        cid = _sv(src.get('c_1_9_1_r_2_case_id'))
        if cid:
            ctrl_no = cid
            break
    if not ctrl_no:
        ctrl_no = _sv(c1.get('c_1_8_1_worldwide_unique_case_identification_number'))
    date_recv   = _fmt_date(_sv(c1.get('c_1_5_date_most_recent_information')))
    date_report = _fmt_date(_sv(c1.get('c_1_2_date_creation')))

    rtype     = _sv(c1.get('c_1_3_type_report'))
    src_study = (rtype == '1')
    src_lit   = bool(lit)
    src_hp    = any(_sv(s.get('c_2_r_4_qualification')) in ('1', '2', '3')
                    for s in c2s)
    rpt_initial = (rtype != '2')

    # Truncate
    reactions_disp, r_ov = _cut(reactions_full, 'reactions')
    conco_disp,     c_ov = _cut(conco_full,     'concomitant')
    hist_disp,      h_ov = _cut(history_full,   'history')
    mfr_disp,       m_ov = _cut(mfr_full,       'manufacturer')

    # Extra drugs beyond the first (go to continuation)
    d0             = suspects_raw[0] if suspects_raw else {}
    extra_drugs    = suspects_raw[1:]
    d0_extra_dos   = (d0.get('dosages', []) or [])[1:]
    d0_extra_ind   = (d0.get('indications', []) or [])[1:]
    has_extra_drugs = bool(extra_drugs or d0_extra_dos or d0_extra_ind)

    continuations: List[Tuple[str, str]] = []
    if r_ov:
        continuations.append(('7. DESCRIBE REACTION(S)', reactions_full))
    if c_ov:
        continuations.append(('22. CONCOMITANT DRUG(S) AND DATES OF ADMINISTRATION', conco_full))
    if h_ov:
        continuations.append(('23. OTHER RELEVANT HISTORY', history_full))
    if m_ov:
        continuations.append(('24a. NAME AND ADDRESS OF MANUFACTURER', mfr_full))

    return {
        'initials':    initials,
        'country':     country,
        'dob_d':       dob_d or 'UNK',
        'dob_m':       dob_m or 'UNK',
        'dob_y':       dob_y or 'UNK',
        'age':         age,
        'sex':         sex,
        'onset_d':     onset_d or 'UNK',
        'onset_m':     onset_m or 'UNK',
        'onset_y':     onset_y or 'UNK',
        'reactions':   reactions_disp,
        'reactions_full': reactions_full,
        'died':        patient_died,
        'hosp':        hosp,
        'disab':       disab,
        'lifethr':     lifethr,
        'other':       other,
        'drug0':       d0,
        'suspects':    suspects_raw,
        'extra_drugs': extra_drugs,
        'd0_extra_dos': d0_extra_dos,
        'd0_extra_ind': d0_extra_ind,
        'has_extra_drugs': has_extra_drugs,
        'concomitant': conco_disp,
        'conco_full':  conco_full,
        'history':     hist_disp,
        'history_full': history_full,
        'mfr':         mfr_disp,
        'mfr_full':    mfr_full,
        'ctrl_no':     ctrl_no,
        'date_recv':   date_recv,
        'src_study':   src_study,
        'src_lit':     src_lit,
        'src_hp':      src_hp,
        'rpt_initial': rpt_initial,
        'date_report': date_report,
        'continuations': continuations,
        'has_extra_drugs': has_extra_drugs,
    }


# ---------------------------------------------------------------------------
# Continuation drug table  (mirrors Django template's layout_continue table)
# ---------------------------------------------------------------------------

def _cont_drugs_html(ctx: Dict[str, Any]) -> str:
    """Render the extra suspect drug rows for the continuation section."""
    d0           = ctx['drug0']
    extra_drugs  = ctx['extra_drugs']
    d0_extra_dos = ctx['d0_extra_dos']
    d0_extra_ind = ctx['d0_extra_ind']

    if not ctx['has_extra_drugs']:
        return ''

    rows = ''

    def _dos_row(drug_name: str, dos: Dict, ind: Dict, abate: str, reappear: str,
                 show_name: bool) -> str:
        ind_txt = _esc(ind.get('primary_source', '')) if ind else ''
        meddra  = _esc(ind.get('meddra', ''))         if ind else ''
        if meddra:
            ind_txt += f'({meddra})'
        lot     = _esc(dos.get('lot', ''))
        dose    = _esc(dos.get('daily_dose', ''))
        route   = _esc(dos.get('route', ''))
        frm     = _esc(dos.get('from_dt', ''))
        to      = _esc(dos.get('to_dt', ''))
        dur     = _esc(dos.get('duration', ''))
        return f"""
        <tr>
          <th>{'{}({})'.format(_esc(drug_name), lot) if lot else _esc(drug_name) if show_name else ''}</th>
          <td><table><tr>
            <td style="width:20%">{lot}</td>
            <td style="width:30%">{dose}</td>
            <td style="width:30%">{route}</td>
            <td style="width:10%">{frm}/{to}</td>
            <td style="width:10%">{dur}</td>
          </tr></table></td>
          <td>{ind_txt}</td>
          <td>{_esc(abate)}</td>
          <td>{_esc(reappear)}</td>
        </tr>"""

    # Extra dosages/indications of the first drug
    if d0:
        n   = len(max(d0_extra_dos, d0_extra_ind, key=lambda x: 0, default=[]))
        max_rows = max(len(d0_extra_dos), len(d0_extra_ind))
        for i in range(max_rows):
            dos = d0_extra_dos[i] if i < len(d0_extra_dos) else {}
            ind = d0_extra_ind[i] if i < len(d0_extra_ind) else {}
            rows += _dos_row(d0.get('name', ''), dos, ind,
                             d0.get('abate', ''), d0.get('reappear', ''),
                             show_name=(i == 0))

    # Additional suspect drugs
    for drug in extra_drugs:
        dosages    = drug.get('dosages', [{}])
        indications = drug.get('indications', [{}])
        max_rows = max(len(dosages), len(indications))
        for i in range(max_rows):
            dos = dosages[i]     if i < len(dosages)     else {}
            ind = indications[i] if i < len(indications) else {}
            rows += _dos_row(drug.get('name', ''), dos, ind,
                             drug.get('abate', ''), drug.get('reappear', ''),
                             show_name=(i == 0))

    return f"""
<table style="word-wrap:break-word; width:100%; border-collapse:collapse;">
  <colgroup>
    <col style="width:15%"><col style="width:65%">
    <col style="width:14%"><col style="width:3%"><col style="width:3%">
  </colgroup>
  <thead><tr>
    <th></th>
    <th><table style="width:100%;border-collapse:collapse;"><tr>
      <th style="width:20%">14. SUSPECT DRUGS (lot)</th>
      <th style="width:30%">15. DAILY DOSES</th>
      <th style="width:30%">16. ROUTES</th>
      <th style="width:10%">18. THERAPY DATES</th>
      <th style="width:10%">19. DURATION</th>
    </tr></table></th>
    <th>17. INDICATIONS FOR USE</th>
    <th>20. AB?</th><th>21. RE?</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>"""


# ---------------------------------------------------------------------------
# Main HTML renderer
# ---------------------------------------------------------------------------

def _render(ctx: Dict[str, Any]) -> str:  # noqa: C901
    d0      = ctx['drug0']
    d0_dos0 = (d0.get('dosages') or [{}])[0]   if d0 else {}
    d0_ind0 = (d0.get('indications') or [{}])[0] if d0 else {}
    abate   = d0.get('abate', '')    if d0 else ''
    reappear = d0.get('reappear', '') if d0 else ''

    # Drug name + lot number for field 14
    lot     = _esc(d0_dos0.get('lot', ''))
    d_name  = _esc(d0.get('name', '')) if d0 else ''
    field14 = f"{d_name} {lot}".strip() if lot else d_name

    # Indication for field 17
    ind_src   = _esc(d0_ind0.get('primary_source', '')) if d0_ind0 else ''
    ind_meddra = _esc(d0_ind0.get('meddra', ''))        if d0_ind0 else ''
    field17   = f"{ind_src}({ind_meddra})" if ind_meddra else ind_src

    # Sex select
    sel_f = ' selected' if ctx['sex'] == 'F' else ''
    sel_m = ' selected' if ctx['sex'] == 'M' else ''

    # Abate / reappear radio
    ab_y  = _chk(abate    == 'Y')
    ab_n  = _chk(abate    == 'N')
    ab_na = _chk(abate    == 'NA')
    re_y  = _chk(reappear == 'Y')
    re_n  = _chk(reappear == 'N')
    re_na = _chk(reappear == 'NA')

    # Report type radio
    chk_init = _chk(ctx['rpt_initial'])
    chk_fup  = _chk(not ctx['rpt_initial'])

    # Continuation blocks
    cont_drugs = _cont_drugs_html(ctx)

    cont_text_blocks = ''
    for label, text in ctx['continuations']:
        # strip the "(Cont...)" marker from the full continuation text
        clean = text
        cont_text_blocks += f"""
<div style="border-top:0.05mm solid rgba(0,0,0,.5); padding:2px 4px;">
  <label style="font-weight:bold;">{_esc(label)}</label>
  <div style="white-space:pre-wrap; font-size:10px;">{_esc(clean)}</div>
</div>"""

    has_cont = bool(ctx['continuations'] or ctx['has_extra_drugs'])
    cont_display = '' if has_cont else 'display:none;'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CIOMS Form</title>
</head>
<body>

<style>
    @page {{
        size: A4;
    }}

    @media print {{
        button {{
            display: none;
        }}
        body {{
            margin: 0;
            padding: 0;
        }}
    }}

    html, body {{
        max-width: 190mm;
        margin: 0 auto;
    }}

    * {{
        font-family: sans-serif;
        font-size: 10px;
    }}

    h1, h2 {{
        font-size: 14px;
    }}

    textarea {{
        resize: none;
        height: 100%;
    }}

    h2 {{
        text-align: center;
    }}

    label, textarea, input[type="text"] {{
        padding: 2px 2px 2px 4px;
    }}

    table {{
        border-collapse: collapse;
    }}

    input[type="checkbox"], input[type="radio"] {{
        accent-color: black;
        vertical-align: middle;
        margin-top: -1px;
    }}

    input:not(input[type="checkbox"], input[type="radio"]), select, textarea {{
        box-sizing: border-box;
        width: 100%;
        border: none;
        background: #f8f8ff;
    }}

    .layout {{
        display: grid;
        grid:
        "cioms_form cioms_form cioms_form cioms_form cioms_form cioms_form cioms_form cioms_form cioms_form cioms_form cioms_form" 1.6fr
        "suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report dummy1 dummy1 dummy1 dummy1 dummy1" 1fr
        "suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report dummy_text dummy_text dummy_text dummy_text dummy_text" 1fr
        "suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report suspect_adverse_reaction_report dummy2 dummy2 dummy2 dummy3 dummy3" 1fr
        "reaction reaction reaction reaction reaction reaction reaction reaction reaction reaction reaction" auto
        "patient_initials patient_initials country country date_of_birth date_of_birth age sex reaction_onset reaction_onset severity" auto
        "describe_reaction describe_reaction describe_reaction describe_reaction describe_reaction describe_reaction describe_reaction describe_reaction describe_reaction describe_reaction severity" auto
        "suspect_drug suspect_drug suspect_drug suspect_drug suspect_drug suspect_drug suspect_drug suspect_drug suspect_drug suspect_drug suspect_drug" auto
        "suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name suspect_drug_1_name reaction_abate" auto
        "suspect_drug_1_daily_dose suspect_drug_1_daily_dose suspect_drug_1_daily_dose suspect_drug_1_daily_dose suspect_drug_1_daily_dose suspect_drug_1_daily_dose suspect_drug_1_route suspect_drug_1_route suspect_drug_1_route suspect_drug_1_route reaction_abate" auto
        "suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use suspect_drug_1_indication_for_use reaction_reappear" auto
        "suspect_drug_1_therapy_dates suspect_drug_1_therapy_dates suspect_drug_1_therapy_dates suspect_drug_1_therapy_dates suspect_drug_1_therapy_dates suspect_drug_1_therapy_dates suspect_drug_1_therapy_duration suspect_drug_1_therapy_duration suspect_drug_1_therapy_duration suspect_drug_1_therapy_duration reaction_reappear" auto
        "concomitant_drug concomitant_drug concomitant_drug concomitant_drug concomitant_drug concomitant_drug concomitant_drug concomitant_drug concomitant_drug concomitant_drug concomitant_drug" auto
        "concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration concomitant_drug_and_dates_of_administration" auto
        "other_relevant_history other_relevant_history other_relevant_history other_relevant_history other_relevant_history other_relevant_history other_relevant_history other_relevant_history other_relevant_history other_relevant_history other_relevant_history" auto
        "manufacturer manufacturer manufacturer manufacturer manufacturer manufacturer manufacturer manufacturer manufacturer manufacturer manufacturer" auto
        "name_and_address_of_manufacturer name_and_address_of_manufacturer name_and_address_of_manufacturer name_and_address_of_manufacturer name_and_address_of_manufacturer name_and_address_of_manufacturer text text text text text" auto
        "text2 text2 text2 manufacturer_control_number manufacturer_control_number manufacturer_control_number text text text text text" auto
        "date_received_by_manufacturer date_received_by_manufacturer date_received_by_manufacturer report_source report_source report_source text text text text text" auto
        "date_of_report date_of_report date_of_report report_type report_type report_type text text text text text" auto
        / 1.2fr 1fr 1fr 1fr 1fr 1.2fr 1fr 1fr 0.7fr 2fr 3fr;
        page-break-after: always;
    }}

    .cioms_form {{
        grid-area: cioms_form;
        text-align: right;
    }}

    .suspect_adverse_reaction_report {{
        grid-area: suspect_adverse_reaction_report;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    .reaction {{ grid-area: reaction; }}
    .patient_initials {{ grid-area: patient_initials; }}
    .country {{ grid-area: country; }}
    .date_of_birth {{ grid-area: date_of_birth; }}
    .age {{ grid-area: age; }}
    .sex {{ grid-area: sex; }}
    .reaction_onset {{ grid-area: reaction_onset; }}
    .severity {{ grid-area: severity; }}
    .describe_reaction {{ grid-area: describe_reaction; overflow: hidden; }}
    .suspect_drug {{ grid-area: suspect_drug; }}
    .suspect_drug_1_name {{ grid-area: suspect_drug_1_name; }}
    .suspect_drug_1_daily_dose {{ grid-area: suspect_drug_1_daily_dose; }}
    .suspect_drug_1_route {{ grid-area: suspect_drug_1_route; }}
    .suspect_drug_1_indication_for_use {{ grid-area: suspect_drug_1_indication_for_use; }}
    .suspect_drug_1_therapy_dates {{ grid-area: suspect_drug_1_therapy_dates; }}
    .suspect_drug_1_therapy_duration {{ grid-area: suspect_drug_1_therapy_duration; }}
    .reaction_abate {{ grid-area: reaction_abate; }}
    .reaction_reappear {{ grid-area: reaction_reappear; }}
    .concomitant_drug {{ grid-area: concomitant_drug; }}
    .concomitant_drug_and_dates_of_administration {{ grid-area: concomitant_drug_and_dates_of_administration; }}
    .other_relevant_history {{ grid-area: other_relevant_history; }}
    .manufacturer {{ grid-area: manufacturer; }}
    .name_and_address_of_manufacturer {{ grid-area: name_and_address_of_manufacturer; }}
    .manufacturer_control_number {{ grid-area: manufacturer_control_number; }}
    .date_received_by_manufacturer {{ grid-area: date_received_by_manufacturer; }}
    .report_source {{ grid-area: report_source; }}
    .date_of_report {{ grid-area: date_of_report; }}
    .report_type {{ grid-area: report_type; }}
    .dummy1 {{ grid-area: dummy1; }}
    .dummy2 {{ grid-area: dummy2; }}
    .dummy3 {{ grid-area: dummy3; flex-direction: row; justify-content: space-evenly; }}
    .dummy_text {{ grid-area: dummy_text; }}
    .text {{ grid-area: text; }}
    .text2 {{ grid-area: text2; }}

    section > div {{
        border-left: 0.05mm solid rgba(0, 0, 0, 0.5);
        border-top: 0.05mm solid rgba(0, 0, 0, 0.5);
        display: flex;
        flex-direction: column;
    }}

    section > div:not(.severity, .reaction_abate, .reaction_reappear, .report_source, .report_type,
                      .dummy3, .suspect_adverse_reaction_report) {{
        justify-content: space-between;
    }}

    .cioms_form, .reaction, .suspect_drug, .concomitant_drug, .manufacturer, .continue {{
        border: none;
    }}

    label[for="date_of_birth"], label[for="reaction_onset"],
    .suspect_adverse_reaction_report,
    .describe_reaction, .severity, .suspect_drug_1_therapy_dates, .suspect_drug_1_therapy_duration, .reaction_reappear,
    .other_relevant_history,
    .date_of_report, .report_type,
    .text, .dummy2, .dummy3 {{
        border-bottom: 0.05mm solid rgba(0, 0, 0, 0.5);
    }}

    .date div:not(:last-child), th:not(:last-child), td:not(:last-child),
    .cell, #suspect_drug_1_therapy_from,
    .severity,
    .reaction_abate, .reaction_reappear,
    .concomitant_drug_and_dates_of_administration, .other_relevant_history,
    .text, .dummy1, .dummy_text, .dummy3 {{
        border-right: 0.05mm solid rgba(0, 0, 0, 0.5);
    }}

    div:has(input[type="radio"]) {{
        display: flex;
    }}

    label:has(input[type="checkbox"]), label:has(input[type="radio"]) {{
        padding-left: 0;
        display: flex;
        align-items: flex-start;
    }}

    #suspect_drug_1_therapy_dates {{
        display: flex;
    }}

    .date {{
        height: 100%;
        display: flex;
    }}

    .day, .month, .year {{
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }}

    #severity {{
        display: flex;
        flex-direction: column;
    }}

    #report_source div {{
        display: flex;
    }}

    .dummy_text input, .text2 input {{
        height: 100%;
    }}

    tr {{
        border-top: 0.05mm solid rgba(0, 0, 0, 0.5);
    }}

    table table tr:first-child {{
        border-top: none;
    }}

    .layout_continue {{
        border-bottom: 0.05mm solid rgba(0, 0, 0, 0.5);
    }}

    .button {{
        display: flex;
        justify-content: space-around;
        margin: 10px 20px;
    }}
</style>

<section class="layout">
    <div class="cioms_form">
        <h1>CIOMS FORM</h1>
    </div>

    <div class="suspect_adverse_reaction_report">
        <h2>SUSPECT ADVERSE REACTION REPORT</h2>
    </div>

    <div class="dummy1"></div>
    <div class="dummy_text"><input type="text"></div>
    <div class="dummy2"></div>
    <div class="dummy3">
        <div class="cell"></div><div class="cell"></div><div class="cell"></div>
        <div class="cell"></div><div class="cell"></div><div class="cell"></div>
        <div class="cell"></div><div class="cell"></div><div class="cell"></div>
        <div class="cell"></div><div class="cell"></div><div class="cell"></div>
        <div class="cell"></div>
    </div>

    <div class="reaction"><h2>I. REACTION INFORMATION</h2></div>

    <div class="patient_initials">
        <label for="patient_initials">1. PATIENT INITIALS (first, last)</label>
        <input type="text" id="patient_initials" value="{_esc(ctx['initials'])}" readonly>
    </div>
    <div class="country">
        <label for="country">1a. COUNTRY</label>
        <input type="text" id="country" value="{_esc(ctx['country'])}" readonly>
    </div>
    <div class="date_of_birth">
        <label for="date_of_birth">2. DATE OF BIRTH</label>
        <div id="date_of_birth" class="date">
            <div class="day">
                <label for="day_of_birth">Day</label>
                <input type="text" id="day_of_birth" value="{_esc(ctx['dob_d'])}" readonly>
            </div>
            <div class="month">
                <label for="month_of_birth">Month</label>
                <input type="text" id="month_of_birth" value="{_esc(ctx['dob_m'])}" readonly>
            </div>
            <div class="year">
                <label for="year_of_birth">Year</label>
                <input type="text" id="year_of_birth" value="{_esc(ctx['dob_y'])}" readonly>
            </div>
        </div>
    </div>
    <div class="age">
        <label for="age">2a. AGE</label>
        <input type="text" id="age" value="{_esc(ctx['age'])}" readonly>
    </div>
    <div class="sex">
        <label for="sex">3. SEX</label>
        <select id="sex" disabled>
            <option value="F"{sel_f}>F</option>
            <option value="M"{sel_m}>M</option>
        </select>
    </div>
    <div class="reaction_onset">
        <label for="reaction_onset">4-6 REACTION ONSET</label>
        <div id="reaction_onset" class="date">
            <div class="day">
                <label for="reaction_onset_day">Day</label>
                <input type="text" id="reaction_onset_day" value="{_esc(ctx['onset_d'])}" readonly>
            </div>
            <div class="month">
                <label for="reaction_onset_month">Month</label>
                <input type="text" id="reaction_onset_month" value="{_esc(ctx['onset_m'])}" readonly>
            </div>
            <div class="year">
                <label for="reaction_onset_year">Year</label>
                <input type="text" id="reaction_onset_year" value="{_esc(ctx['onset_y'])}" readonly>
            </div>
        </div>
    </div>

    <div class="describe_reaction">
        <label for="describe_reaction">7 + 13 DESCRIBE REACTION(S) (including relevant tests/lab data)</label>
        <textarea rows="14" id="describe_reaction" readonly>{_esc(ctx['reactions'])}</textarea>
    </div>

    <div class="severity">
        <label>8-12 CHECK ALL APPROPRIATE TO ADVERSE REACTION</label>
        <div id="severity">
            <label for="severity_death">
                <input type="checkbox" id="severity_death"{_chk(ctx['died'])} disabled>
                PATIENT DIED
            </label>
            <label for="severity_hospitalization">
                <input type="checkbox" id="severity_hospitalization"{_chk(ctx['hosp'])} disabled>
                INVOLVED OR PROLONGED PATIENT HOSPITALISATION
            </label>
            <label for="severity_disability">
                <input type="checkbox" id="severity_disability"{_chk(ctx['disab'])} disabled>
                INVOLVED PERSISTENT OR SIGNIFICANT DISABILITY OR INCAPACITY
            </label>
            <label for="severity_life_threatening">
                <input type="checkbox" id="severity_life_threatening"{_chk(ctx['lifethr'])} disabled>
                LIFE THREATENING
            </label>
            <label for="severity_other">
                <input type="checkbox" id="severity_other"{_chk(ctx['other'])} disabled>
                OTHER
            </label>
        </div>
    </div>

    <div class="suspect_drug"><h2>II. SUSPECT DRUG(S) INFORMATION</h2></div>

    <div class="suspect_drug_1_name">
        <label for="suspect_drug_1_name">14. SUSPECT DRUG(S) (include generic name)</label>
        <input type="text" id="suspect_drug_1_name" value="{field14}" readonly>
    </div>
    <div class="suspect_drug_1_daily_dose">
        <label for="suspect_drug_1_daily_dose">15. DAILY DOSE(S)</label>
        <input type="text" id="suspect_drug_1_daily_dose"
               value="{_esc(d0_dos0.get('daily_dose', '') if d0_dos0 else '')}" readonly>
    </div>
    <div class="suspect_drug_1_route">
        <label for="suspect_drug_1_route">16. ROUTE(S) OF ADMINISTRATION</label>
        <input type="text" id="suspect_drug_1_route"
               value="{_esc(d0_dos0.get('route', '') if d0_dos0 else '')}" readonly>
    </div>
    <div class="suspect_drug_1_indication_for_use">
        <label for="suspect_drug_1_indication_for_use">17. INDICATION(S) FOR USE</label>
        <input type="text" id="suspect_drug_1_indication_for_use" value="{field17}" readonly>
    </div>
    <div class="suspect_drug_1_therapy_dates">
        <label>18. THERAPY DATES (from/to)</label>
        <div id="suspect_drug_1_therapy_dates">
            <input type="text" id="suspect_drug_1_therapy_from"
                   value="{_esc(d0_dos0.get('from_dt', '') if d0_dos0 else '')}" readonly>
            <input type="text" id="suspect_drug_1_therapy_to"
                   value="{_esc(d0_dos0.get('to_dt', '') if d0_dos0 else '')}" readonly>
        </div>
    </div>
    <div class="suspect_drug_1_therapy_duration">
        <label for="suspect_drug_1_therapy_duration">19. THERAPY DURATION</label>
        <input type="text" id="suspect_drug_1_therapy_duration"
               value="{_esc(d0_dos0.get('duration', '') if d0_dos0 else '')}" readonly>
    </div>

    <div class="reaction_abate">
        <label>20. DID REACTION ABATE AFTER STOPPING DRUG?</label>
        <div>
            <label><input type="radio" name="reaction_abate" value="Y"{ab_y} disabled> YES</label>
            <label><input type="radio" name="reaction_abate" value="N"{ab_n} disabled> NO</label>
            <label><input type="radio" name="reaction_abate" value="NA"{ab_na} disabled> NA</label>
        </div>
    </div>
    <div class="reaction_reappear">
        <label>21. DID REACTION REAPPEAR AFTER REINTRODUCTION?</label>
        <div>
            <label><input type="radio" name="reaction_reappear" value="Y"{re_y} disabled> YES</label>
            <label><input type="radio" name="reaction_reappear" value="N"{re_n} disabled> NO</label>
            <label><input type="radio" name="reaction_reappear" value="NA"{re_na} disabled> NA</label>
        </div>
    </div>

    <div class="concomitant_drug"><h2>III. CONCOMITANT DRUG(S) AND HISTORY</h2></div>
    <div class="concomitant_drug_and_dates_of_administration">
        <label for="concomitant_drug_and_dates_of_administration">
            22. CONCOMITANT DRUG(S) AND DATES OF ADMINISTRATION
            (exclude those used to treat reaction)
        </label>
        <textarea rows="4" id="concomitant_drug_and_dates_of_administration" readonly>{_esc(ctx['concomitant'])}</textarea>
    </div>
    <div class="other_relevant_history">
        <label for="other_relevant_history">
            23. OTHER RELEVANT HISTORY (e.g. diagnostics, allergics, pregnancy with last month of period, etc.)
        </label>
        <textarea rows="4" id="other_relevant_history" readonly>{_esc(ctx['history']) or 'UNK'}</textarea>
    </div>

    <div class="manufacturer"><h2>IV. MANUFACTURER INFORMATION</h2></div>
    <div class="name_and_address_of_manufacturer">
        <label for="name_and_address_of_manufacturer">24a. NAME AND ADDRESS OF MANUFACTURER</label>
        <textarea rows="6" id="name_and_address_of_manufacturer" readonly>{_esc(ctx['mfr'])}</textarea>
    </div>
    <div class="text"><textarea></textarea></div>
    <div class="text2"><input type="text"></div>
    <div class="manufacturer_control_number">
        <label for="manufacturer_control_number">24b. MFR CONTROL NO.</label>
        <input type="text" id="manufacturer_control_number" value="{_esc(ctx['ctrl_no'])}" readonly>
    </div>
    <div class="date_received_by_manufacturer">
        <label for="date_received_by_manufacturer">24c. DATE RECEIVED BY MANUFACTURER</label>
        <input type="text" id="date_received_by_manufacturer" value="{_esc(ctx['date_recv'])}" readonly>
    </div>
    <div class="report_source">
        <label>24d. REPORT SOURCE</label>
        <div id="report_source">
            <div>
                <label><input type="checkbox"{_chk(ctx['src_study'])} disabled> STUDY</label>
                <label><input type="checkbox"{_chk(ctx['src_lit'])} disabled> LITERATURE</label>
            </div>
            <label><input type="checkbox"{_chk(ctx['src_hp'])} disabled> HEALTH PROFESSIONAL</label>
        </div>
    </div>
    <div class="date_of_report">
        <label for="date_of_report">DATE OF THIS REPORT</label>
        <input type="text" id="date_of_report" value="{_esc(ctx['date_report'])}" readonly>
    </div>
    <div class="report_type">
        <label>25a. REPORT TYPE</label>
        <div id="report_type">
            <label><input type="radio" name="report_type" value="initial"{chk_init} disabled> INITIAL</label>
            <label><input type="radio" name="report_type" value="followup"{chk_fup} disabled> FOLLOWUP</label>
        </div>
    </div>
</section>

<!-- Continuation section -->
<section class="layout_continue" style="{cont_display}">
    <div class="continue"><h2>CONTINUES PREVIOUS PAGE</h2></div>
    {cont_drugs}
    {cont_text_blocks}
</section>

<div class="button">
    <button onclick="print()">Save as PDF</button>
</div>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _to_cioms(data: Dict[str, Any]) -> str:
    """Generate a standalone CIOMS I form HTML document from parsed E2B R3 data."""
    return _render(_build_context(data))
