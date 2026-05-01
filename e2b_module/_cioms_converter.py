"""
CIOMS form HTML generator for E2B R3 ICSR data.

Generates a printable CIOMS I form (Suspect Adverse Reaction Report) as a
standalone HTML document from a parsed E2B R3 data dictionary.
"""

import html as _html_lib
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(v: Any) -> str:
    return _html_lib.escape(str(v)) if v else ''


def _sv(val: Any, default: str = '') -> str:
    """Return string value, unwrapping null-flavor dicts."""
    if val is None:
        return default
    if isinstance(val, dict):
        v = val.get('_value') or val.get('_null_flavor', '')
        return str(v) if v else default
    return str(val) if val else default


def _fmt_date(date_str: str, part: str) -> str:
    s = str(date_str or '')
    if part == 'year':
        return s[:4] if len(s) >= 4 else ''
    if part == 'month':
        return s[4:6] if len(s) >= 6 else ''
    if part == 'day':
        return s[6:8] if len(s) >= 8 else ''
    return ''


def _checked(flag: bool) -> str:
    return ' checked' if flag else ''


def _selected(val: str, option: str) -> str:
    return ' selected' if val == option else ''


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context(data: Dict[str, Any]) -> Dict[str, Any]:
    d      = data.get('d_patient_characteristics') or {}
    c1     = data.get('c_1_identification_case_safety_report') or {}
    c2s    = data.get('c_2_r_primary_source_information') or []
    c3     = data.get('c_3_information_sender_case_safety_report') or {}
    rxns   = data.get('e_i_reaction_event') or []
    drugs  = data.get('g_k_drug_information') or []
    h_blk  = data.get('h_narrative_case_summary') or {}

    c2 = c2s[0] if c2s else {}
    ctx: Dict[str, Any] = {}

    # Patient
    ctx['f1_patient_initials'] = _sv(d.get('d_1_patient'), 'UNK')
    ctx['f1a_country'] = _sv(c2.get('c_2_r_3_reporter_country_code'), 'UNK')

    dob = _sv(d.get('d_2_1_date_birth'))
    ctx['f2_dob_day']   = _fmt_date(dob, 'day')   or 'UNK'
    ctx['f2_dob_month'] = _fmt_date(dob, 'month') or 'UNK'
    ctx['f2_dob_year']  = _fmt_date(dob, 'year')  or 'UNK'

    age_n = _sv(d.get('d_2_2a_age_onset_reaction_num'))
    age_u = _sv(d.get('d_2_2b_age_onset_reaction_unit'))
    ctx['f2a_age'] = f"{age_n} {age_u}".strip() if age_n else 'UNK'

    sex_code = _sv(d.get('d_5_sex'))
    ctx['f3_sex'] = {'1': 'M', '2': 'F'}.get(sex_code, '')

    # Reaction onset (first reaction)
    r0 = rxns[0] if rxns else {}
    onset = _sv(r0.get('e_i_4_date_start_reaction'))
    ctx['f4_onset_day']   = _fmt_date(onset, 'day')   or 'UNK'
    ctx['f5_onset_month'] = _fmt_date(onset, 'month') or 'UNK'
    ctx['f6_onset_year']  = _fmt_date(onset, 'year')  or 'UNK'

    # Reaction description + narrative
    rtexts: List[str] = []
    for r in rxns:
        t = _sv(r.get('e_i_1_1a_reaction_primary_source_native_language'))
        if t:
            rtexts.append(t)
    narr = _sv(h_blk.get('h_1_case_narrative'))
    if narr:
        rtexts.append(narr)
    ctx['f7_13_reactions'] = '\n'.join(rtexts)

    # Seriousness checkboxes
    def _any_sev(field: str) -> bool:
        for r in rxns:
            v = r.get(field)
            if isinstance(v, dict):
                v = v.get('_value', '')
            if str(v or '') == '1':
                return True
        return False

    ctx['f8_died']          = _any_sev('e_i_3_2a_results_death')
    ctx['f9_hosp']          = _any_sev('e_i_3_2c_caused_prolonged_hospitalisation')
    ctx['f10_disability']   = _any_sev('e_i_3_2d_disabling_incapacitating')
    ctx['f11_life_threat']  = _any_sev('e_i_3_2b_life_threatening')
    ctx['f12_other']        = _any_sev('e_i_3_2f_other_medically_important_condition')

    # Suspect and concomitant drugs
    suspect_drugs: List[Dict] = []
    concomitant_lines: List[str] = []

    for g in drugs:
        role = _sv(g.get('g_k_1_characterisation_drug_role'))
        name = _sv(g.get('g_k_2_2_medicinal_product_name_primary_source'))

        dosages: List[Dict] = []
        for dos in (g.get('g_k_4_r_dosage_information') or []):
            dn = _sv(dos.get('g_k_4_r_1a_dose_num'))
            du = _sv(dos.get('g_k_4_r_1b_dose_unit'))
            pv = _sv(dos.get('g_k_4_r_2_number_units_interval'))
            pu = _sv(dos.get('g_k_4_r_3_definition_interval_unit'))
            dosages.append({
                'daily_dose':           f"{dn} {du}".strip() if dn else '',
                'route':                _sv(dos.get('g_k_4_r_10_1_route_administration')),
                'from_date':            _sv(dos.get('g_k_4_r_4_date_time_drug')),
                'to_date':              _sv(dos.get('g_k_4_r_5_date_time_last_administration')),
                'duration':             f"{pv} {pu}".strip() if pv else '',
            })

        indications: List[Dict] = []
        for ind in (g.get('g_k_7_r_indication_use_case') or []):
            indications.append({
                'text':   _sv(ind.get('g_k_7_r_1_indication_primary_source')),
                'meddra': _sv(ind.get('g_k_7_r_2b_indication_meddra_code')),
            })

        entry = {
            'name':        name,
            'dosages':     dosages,
            'indications': indications,
            'abate':       '',
            'reappear':    '',
        }

        if role == '1':
            suspect_drugs.append(entry)
        else:
            dates = []
            for dos in (g.get('g_k_4_r_dosage_information') or []):
                frm = _sv(dos.get('g_k_4_r_4_date_time_drug'))
                to  = _sv(dos.get('g_k_4_r_5_date_time_last_administration'))
                if frm or to:
                    dates.append(f"{frm}–{to}")
            line = name + (f" ({', '.join(dates)})" if dates else '')
            if line.strip():
                concomitant_lines.append(line)

    ctx['suspect_drugs']    = suspect_drugs
    ctx['concomitant']      = '\n'.join(concomitant_lines)

    # Medical history
    hist_text = _sv(d.get('d_7_2_text_medical_history'))
    if not hist_text:
        mh_list = d.get('d_7_1_r_structured_information_medical_history') or []
        codes = [_sv(m.get('d_7_1_r_1b_medical_history_meddra_code'))
                 for m in mh_list
                 if _sv(m.get('d_7_1_r_1b_medical_history_meddra_code'))]
        hist_text = '; '.join(codes) if codes else ''
    ctx['f23_history'] = hist_text or 'UNK'

    # Manufacturer / sender
    sender_parts: List[str] = []
    for f in ('c_3_2_sender_organisation', 'c_3_3_1_sender_department',
              'c_3_3_3_sender_given_name', 'c_3_3_5_sender_family_name'):
        v = _sv(c3.get(f))
        if v:
            sender_parts.append(v)
    for f in ('c_3_4_1_sender_street_address', 'c_3_4_2_sender_city',
              'c_3_4_3_sender_state_province', 'c_3_4_4_sender_postcode',
              'c_3_4_5_sender_country_code'):
        v = _sv(c3.get(f))
        if v:
            sender_parts.append(v)
    ctx['f24a_manufacturer'] = '\n'.join(sender_parts)

    ctx['f24b_control_no']   = _sv(c1.get('c_1_8_1_worldwide_unique_case_identification_number'))
    ctx['f24c_date_recv']    = _sv(c1.get('c_1_4_date_report_first_received_source'))

    report_type = _sv(c1.get('c_1_3_type_report'))
    qual        = _sv(c2.get('c_2_r_4_qualification'))
    ctx['f24d_study']   = report_type == '1'
    ctx['f24d_lit']     = report_type == '2'
    ctx['f24d_hp']      = qual in ('1', '2', '3', '4')

    ctx['date_report']  = _sv(c1.get('c_1_5_date_most_recent_information'))
    ctx['f25a_initial'] = report_type == '1'

    return ctx


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _drug_row(d: Dict) -> str:
    dos = d['dosages'][0] if d['dosages'] else {}
    ind = d['indications'][0] if d['indications'] else {}
    ind_text = _esc(ind.get('text', ''))
    if ind.get('meddra'):
        ind_text += f" ({_esc(ind['meddra'])})"
    return f"""
        <tr>
          <td>{_esc(d['name'])}</td>
          <td>{_esc(dos.get('daily_dose',''))}</td>
          <td>{_esc(dos.get('route',''))}</td>
          <td>{_esc(dos.get('from_date',''))}/{_esc(dos.get('to_date',''))}</td>
          <td>{_esc(dos.get('duration',''))}</td>
          <td>{ind_text}</td>
          <td>{_esc(d['abate'])}</td>
          <td>{_esc(d['reappear'])}</td>
        </tr>"""


def _render(ctx: Dict[str, Any]) -> str:
    sex = ctx['f3_sex']
    f_sel = _selected(sex, 'F')
    m_sel = _selected(sex, 'M')

    drug_rows = ''.join(_drug_row(d) for d in ctx['suspect_drugs'])
    if not drug_rows:
        drug_rows = '<tr><td colspan="8"><em>No suspect drugs recorded</em></td></tr>'

    abate   = _esc(ctx['suspect_drugs'][0]['abate'])   if ctx['suspect_drugs'] else ''
    reappear = _esc(ctx['suspect_drugs'][0]['reappear']) if ctx['suspect_drugs'] else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CIOMS Form</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  @media print {{ .no-print {{ display: none; }} body {{ margin: 0; }} }}
  * {{ font-family: sans-serif; font-size: 10px; box-sizing: border-box; }}
  body {{ max-width: 190mm; margin: 0 auto; padding: 4mm; }}
  h1, h2 {{ font-size: 13px; text-align: center; margin: 2px 0; }}
  h3 {{ font-size: 11px; margin: 4px 0 2px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 4px; }}
  th, td {{ border: 0.3px solid #888; padding: 2px 4px; vertical-align: top; }}
  th {{ background: #f0f0f0; text-align: left; font-weight: bold; }}
  .label {{ color: #444; font-size: 9px; display: block; margin-bottom: 1px; }}
  .field {{ background: #f8f8ff; border: 0.3px solid #ccc; padding: 2px 4px;
            width: 100%; min-height: 16px; }}
  .section {{ border: 0.5px solid #555; margin-bottom: 4px; padding: 3px 5px; }}
  .row {{ display: flex; gap: 6px; margin-bottom: 3px; flex-wrap: wrap; }}
  .col {{ flex: 1; min-width: 60px; }}
  .col-2 {{ flex: 2; }}
  .col-3 {{ flex: 3; }}
  .col-4 {{ flex: 4; }}
  .col-6 {{ flex: 6; }}
  textarea {{ width: 100%; border: 0.3px solid #ccc; background: #f8f8ff;
              resize: none; padding: 2px 4px; }}
  input[type=text] {{ width: 100%; border: 0.3px solid #ccc; background: #f8f8ff;
                      padding: 2px 4px; }}
  .btn {{ display: flex; justify-content: center; margin: 8px; }}
  button {{ padding: 4px 20px; font-size: 12px; }}
</style>
</head>
<body>

<h1>CIOMS FORM</h1>
<h2>SUSPECT ADVERSE REACTION REPORT</h2>

<!-- I. Reaction Information -->
<div class="section">
  <h3>I. REACTION INFORMATION</h3>
  <div class="row">
    <div class="col col-2">
      <span class="label">1. PATIENT INITIALS (first, last)</span>
      <input type="text" value="{_esc(ctx['f1_patient_initials'])}" readonly>
    </div>
    <div class="col">
      <span class="label">1a. COUNTRY</span>
      <input type="text" value="{_esc(ctx['f1a_country'])}" readonly>
    </div>
    <div class="col col-2">
      <span class="label">2. DATE OF BIRTH (Day / Month / Year)</span>
      <div style="display:flex;gap:4px;">
        <input type="text" value="{_esc(ctx['f2_dob_day'])}" readonly style="width:33%">
        <input type="text" value="{_esc(ctx['f2_dob_month'])}" readonly style="width:33%">
        <input type="text" value="{_esc(ctx['f2_dob_year'])}" readonly style="width:34%">
      </div>
    </div>
    <div class="col">
      <span class="label">2a. AGE</span>
      <input type="text" value="{_esc(ctx['f2a_age'])}" readonly>
    </div>
    <div class="col">
      <span class="label">3. SEX</span>
      <select disabled>
        <option value="F"{f_sel}>F</option>
        <option value="M"{m_sel}>M</option>
      </select>
    </div>
  </div>
  <div class="row">
    <div class="col col-2">
      <span class="label">4–6. REACTION ONSET (Day / Month / Year)</span>
      <div style="display:flex;gap:4px;">
        <input type="text" value="{_esc(ctx['f4_onset_day'])}" readonly style="width:33%">
        <input type="text" value="{_esc(ctx['f5_onset_month'])}" readonly style="width:33%">
        <input type="text" value="{_esc(ctx['f6_onset_year'])}" readonly style="width:34%">
      </div>
    </div>
    <div class="col col-6">
      <span class="label">8–12. CHECK ALL APPROPRIATE TO ADVERSE REACTION</span>
      <div style="display:flex;gap:10px;flex-wrap:wrap;padding-top:2px;">
        <label><input type="checkbox"{_checked(ctx['f8_died'])} disabled> PATIENT DIED</label>
        <label><input type="checkbox"{_checked(ctx['f9_hosp'])} disabled> PROLONGED HOSPITALISATION</label>
        <label><input type="checkbox"{_checked(ctx['f10_disability'])} disabled> DISABILITY/INCAPACITY</label>
        <label><input type="checkbox"{_checked(ctx['f11_life_threat'])} disabled> LIFE THREATENING</label>
        <label><input type="checkbox"{_checked(ctx['f12_other'])} disabled> OTHER</label>
      </div>
    </div>
  </div>
  <div>
    <span class="label">7 + 13. DESCRIBE REACTION(S) (including relevant tests/lab data)</span>
    <textarea rows="6" readonly>{_esc(ctx['f7_13_reactions'])}</textarea>
  </div>
</div>

<!-- II. Suspect Drug(s) -->
<div class="section">
  <h3>II. SUSPECT DRUG(S) INFORMATION</h3>
  <table>
    <thead>
      <tr>
        <th>14. Drug (generic name)</th>
        <th>15. Daily dose</th>
        <th>16. Route</th>
        <th>18. Therapy dates (from/to)</th>
        <th>19. Duration</th>
        <th>17. Indication</th>
        <th>20. Abate?</th>
        <th>21. Reappear?</th>
      </tr>
    </thead>
    <tbody>
      {drug_rows}
    </tbody>
  </table>
</div>

<!-- III. Concomitant Drugs and History -->
<div class="section">
  <h3>III. CONCOMITANT DRUG(S) AND HISTORY</h3>
  <div>
    <span class="label">22. CONCOMITANT DRUG(S) AND DATES OF ADMINISTRATION (exclude those used to treat reaction)</span>
    <textarea rows="4" readonly>{_esc(ctx['concomitant'])}</textarea>
  </div>
  <div>
    <span class="label">23. OTHER RELEVANT HISTORY (diagnostics, allergies, pregnancy, etc.)</span>
    <textarea rows="3" readonly>{_esc(ctx['f23_history'])}</textarea>
  </div>
</div>

<!-- IV. Manufacturer Information -->
<div class="section">
  <h3>IV. MANUFACTURER INFORMATION</h3>
  <div class="row">
    <div class="col col-3">
      <span class="label">24a. NAME AND ADDRESS OF MANUFACTURER</span>
      <textarea rows="4" readonly>{_esc(ctx['f24a_manufacturer'])}</textarea>
    </div>
    <div class="col col-2">
      <div>
        <span class="label">24b. MFR CONTROL NO.</span>
        <input type="text" value="{_esc(ctx['f24b_control_no'])}" readonly>
      </div>
      <div style="margin-top:4px;">
        <span class="label">24c. DATE RECEIVED BY MANUFACTURER</span>
        <input type="text" value="{_esc(ctx['f24c_date_recv'])}" readonly>
      </div>
    </div>
    <div class="col col-2">
      <span class="label">24d. REPORT SOURCE</span>
      <div style="padding-top:2px;">
        <label><input type="checkbox"{_checked(ctx['f24d_study'])} disabled> STUDY</label><br>
        <label><input type="checkbox"{_checked(ctx['f24d_lit'])} disabled> LITERATURE</label><br>
        <label><input type="checkbox"{_checked(ctx['f24d_hp'])} disabled> HEALTH PROFESSIONAL</label>
      </div>
    </div>
    <div class="col">
      <div>
        <span class="label">DATE OF THIS REPORT</span>
        <input type="text" value="{_esc(ctx['date_report'])}" readonly>
      </div>
      <div style="margin-top:4px;">
        <span class="label">25a. REPORT TYPE</span>
        <div>
          <label><input type="radio" name="rtype" value="initial"{"  checked" if ctx["f25a_initial"] else ""} disabled> INITIAL</label>
          <label><input type="radio" name="rtype" value="followup"{"  checked" if not ctx["f25a_initial"] else ""} disabled> FOLLOW-UP</label>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="no-print btn">
  <button onclick="window.print()">Save as PDF / Print</button>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _to_cioms(data: Dict[str, Any], root_tag: str = '') -> str:
    """Generate a standalone CIOMS form HTML document from parsed E2B R3 data."""
    ctx = _build_context(data)
    return _render(ctx)
