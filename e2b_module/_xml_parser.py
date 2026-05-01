import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from _constants import _LIST_TAGS

_HL7_NS = 'urn:hl7-org:v3'
_XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'


def _hl7(tag: str) -> str:
    return f'{{{_HL7_NS}}}{tag}'


def _xsi_type(elem: ET.Element) -> str:
    return elem.get(f'{{{_XSI_NS}}}type', '')


def _h(elem: Optional[ET.Element], *path: str) -> Optional[ET.Element]:
    """Walk a chain of HL7-namespaced child tags."""
    cur = elem
    for tag in path:
        if cur is None:
            return None
        cur = cur.find(_hl7(tag))
    return cur


def _htext(elem: Optional[ET.Element]) -> Optional[str]:
    if elem is None:
        return None
    t = elem.text
    return t.strip() if (t and t.strip()) else None


def _elem_to_value(elem: ET.Element) -> Any:
    """
    Recursively convert an XML element to a Python value.

    Handles the application's internal XML format produced by xmltodict.unparse():
      - <field><value>X</value></field>           → "X"
      - <field><value/><null_flavor>NF</null_flavor></field> → {"_null_flavor": "NF"}
      - <field>...</field> (nested)               → dict
      - repeated same-tag siblings collected by caller → list
    """
    children = list(elem)

    if not children:
        t = elem.text
        return t.strip() if (t and t.strip()) else None

    child_tags = [c.tag for c in children]

    if 'value' in child_tags:
        val_elem = elem.find('value')
        nf_elem  = elem.find('null_flavor')

        raw_val = None
        if val_elem is not None:
            raw_val = (val_elem.text or '').strip() or None

        raw_nf = None
        if nf_elem is not None:
            raw_nf = (nf_elem.text or '').strip() or None

        if raw_nf:
            return {'_null_flavor': raw_nf, '_value': raw_val}
        return raw_val

    tag_counts: Dict[str, int] = {}
    for c in children:
        tag_counts[c.tag] = tag_counts.get(c.tag, 0) + 1

    result: Dict[str, Any] = {}
    list_buf: Dict[str, list] = {}

    for c in children:
        if c.tag == 'id':
            continue
        if c.tag == 'uuid':
            continue

        parsed = _elem_to_value(c)

        if tag_counts[c.tag] > 1 or c.tag in _LIST_TAGS:
            if c.tag not in list_buf:
                list_buf[c.tag] = []
            if parsed is not None and parsed != {} and parsed != '':
                list_buf[c.tag].append(parsed)
        else:
            result[c.tag] = parsed

    result.update(list_buf)
    return result


def _parse_hl7_xml(root: ET.Element) -> Dict[str, Any]:
    """
    Parse the official ICH E2B R3 HL7 v3 XML format
    (root tag MCCI_IN200100UV01 with namespace urn:hl7-org:v3).
    Returns an internal dict compatible with all converters.
    """
    data: Dict[str, Any] = {}

    local = root.tag.split('}')[-1]
    if local == 'MCCI_IN200100UV01':
        porr = root.find(_hl7('PORR_IN049016UV'))
    else:
        porr = root

    if porr is None:
        return data

    ctrl   = _h(porr, 'controlActProcess')
    invstg = _h(ctrl, 'subject', 'investigationEvent') if ctrl is not None else None

    if invstg is None:
        return data

    # C.1  Identification
    c1: Dict[str, Any] = {}

    for id_el in invstg.findall(_hl7('id')):
        r   = id_el.get('root', '')
        ext = id_el.get('extension', '')
        if r.endswith('.3.1'):
            c1['c_1_1_sender_safety_report_unique_id'] = ext
        elif r.endswith('.3.2'):
            c1['c_1_8_1_worldwide_unique_case_identification_number'] = ext

    # C.1.2  date of creation — effectiveTime of controlActProcess
    eff_ctrl = _h(ctrl, 'effectiveTime')
    if eff_ctrl is not None:
        c1['c_1_2_date_creation'] = eff_ctrl.get('value', '')

    # C.1.4  effectiveTime/low of investigationEvent
    low = _h(invstg, 'effectiveTime', 'low')
    if low is not None:
        c1['c_1_4_date_report_first_received_source'] = low.get('value', '')

    # C.1.5  availabilityTime
    avail = _h(invstg, 'availabilityTime')
    if avail is not None:
        c1['c_1_5_date_most_recent_information'] = avail.get('value', '')

    # C.1.3 / C.1.6.1 / C.1.7 / C.1.9.1  — from subjectOf2
    for s2 in invstg.findall(_hl7('subjectOf2')):
        ic = _h(s2, 'investigationCharacteristic')
        if ic is None:
            continue
        ic_code = _h(ic, 'code')
        ic_val  = _h(ic, 'value')
        if ic_code is None:
            continue
        cv = ic_code.get('code', '')
        if cv == '1' and ic_val is not None:
            c1['c_1_3_type_report'] = ic_val.get('code', '')
        elif cv == '2' and ic_val is not None:
            nf = ic_val.get('nullFlavor')
            c1['c_1_9_1_other_case_ids_previous_transmissions'] = (
                {'_null_flavor': nf} if nf else ic_val.get('value', ''))

    # C.1.6.1 / C.1.7  — from component > observationEvent
    for comp in invstg.findall(_hl7('component')):
        oe   = _h(comp, 'observationEvent')
        if oe is None:
            continue
        oe_c = _h(oe, 'code')
        oe_v = _h(oe, 'value')
        if oe_c is None or oe_v is None:
            continue
        cv = oe_c.get('code', '')
        if cv == '1':
            c1['c_1_6_1_additional_documents_available'] = oe_v.get('value', '')
        elif cv == '23':
            c1['c_1_7_fulfil_local_criteria_expedited_report'] = oe_v.get('value', '')

    # C.1.8.2  first sender — outboundRelationship code=1
    for obr in invstg.findall(_hl7('outboundRelationship')):
        ri   = _h(obr, 'relatedInvestigation')
        if ri is None:
            continue
        ri_c = _h(ri, 'code')
        if ri_c is not None and ri_c.get('code') == '1':
            ae_code = ri.find(
                f'.//{_hl7("subjectOf2")}/{_hl7("controlActEvent")}'
                f'/{_hl7("author")}/{_hl7("assignedEntity")}/{_hl7("code")}')
            if ae_code is not None:
                c1['c_1_8_2_first_sender'] = ae_code.get('code', '')

    # C.4  Literature reference
    lit_list = []
    for ref in invstg.findall(_hl7('reference')):
        doc  = _h(ref, 'document')
        bib  = _h(doc, 'bibliographicDesignationText') if doc is not None else None
        if bib is not None and bib.text:
            lit_list.append({'c_4_r_1_literature_reference': bib.text.strip()})

    data['c_1_identification_case_safety_report'] = c1
    if lit_list:
        data['c_4_r_literature_reference'] = lit_list

    aea = invstg.find(
        f'{_hl7("component")}/{_hl7("adverseEventAssessment")}')
    if aea is None:
        return data

    primary_role = _h(aea, 'subject1', 'primaryRole')

    # D  Patient characteristics
    if primary_role is not None:
        d: Dict[str, Any] = {}
        player = _h(primary_role, 'player1')
        if player is not None:
            name_el = _h(player, 'name')
            if name_el is not None and name_el.text:
                d['d_1_patient'] = name_el.text.strip()
            gender = _h(player, 'administrativeGenderCode')
            if gender is not None:
                d['d_5_sex'] = gender.get('code', '')
            birth = _h(player, 'birthTime')
            if birth is not None:
                d['d_2_1_date_birth'] = birth.get('value', '')

        for s2 in primary_role.findall(_hl7('subjectOf2')):
            obs = _h(s2, 'observation')
            if obs is not None:
                obs_c = _h(obs, 'code')
                obs_v = _h(obs, 'value')
                if obs_c is None:
                    continue
                cv = obs_c.get('code', '')
                if cv == '3' and obs_v is not None:
                    d['d_2_2a_age_onset_reaction_num'] = obs_v.get('value', '')
                    d['d_2_2b_age_onset_reaction_unit'] = obs_v.get('unit', '')
                elif cv == '7' and obs_v is not None:
                    d['d_3_body_weight'] = obs_v.get('value', '')
                elif cv == '17' and obs_v is not None:
                    d['d_4_height'] = obs_v.get('value', '')
                elif cv == '22':
                    if obs_v is not None:
                        nf = obs_v.get('nullFlavor')
                        d['d_6_last_menstrual_period_date'] = (
                            {'_null_flavor': nf} if nf else obs_v.get('value', ''))

            org = _h(s2, 'organizer')
            if org is not None:
                org_c = _h(org, 'code')
                if org_c is not None and org_c.get('code') == '1':
                    mh_list = []
                    for comp2 in org.findall(_hl7('component')):
                        obs2 = _h(comp2, 'observation')
                        if obs2 is None:
                            continue
                        mh: Dict[str, Any] = {}
                        oc2 = _h(obs2, 'code')
                        if oc2 is not None:
                            mh['d_7_1_r_1a_meddra_version_medical_history'] = oc2.get('codeSystemVersion', '')
                            mh['d_7_1_r_1b_medical_history_meddra_code']    = oc2.get('code', '')
                        low2 = obs2.find(f'.//{_hl7("effectiveTime")}/{_hl7("low")}')
                        if low2 is not None:
                            mh['d_7_1_r_2_start_date'] = low2.get('value', '')
                        cont = obs2.find(
                            f'.//{_hl7("inboundRelationship")}/{_hl7("observation")}/{_hl7("value")}')
                        if cont is not None:
                            mh['d_7_1_r_3_continuing'] = cont.get('value', '')
                        if mh:
                            mh_list.append(mh)
                    if mh_list:
                        d['d_7_1_r_structured_information_medical_history'] = mh_list

            obs_e = _h(s2, 'observation')
            if obs_e is not None:
                obs_ec = _h(obs_e, 'code')
                if obs_ec is not None and obs_ec.get('code') == '29':
                    e: Dict[str, Any] = {}
                    eff_e = _h(obs_e, 'effectiveTime')
                    if eff_e is not None:
                        for comp_e in eff_e.findall(_hl7('comp')):
                            tp = _xsi_type(comp_e)
                            if 'IVL_TS' in tp and 'operator' not in comp_e.attrib:
                                low_e = _h(comp_e, 'low')
                                high_e = _h(comp_e, 'high')
                                if low_e is not None:
                                    e['e_i_4_date_start_reaction'] = low_e.get('value', '')
                                if high_e is not None:
                                    e['e_i_5_date_end_reaction'] = high_e.get('value', '')
                            elif 'IVL_TS' in tp and comp_e.get('operator') == 'A':
                                w = _h(comp_e, 'width')
                                if w is not None:
                                    e['e_i_6a_duration_reaction_num']  = w.get('value', '')
                                    e['e_i_6b_duration_reaction_unit'] = w.get('unit', '')

                    val_e = _h(obs_e, 'value')
                    if val_e is not None:
                        e['e_i_2_1a_meddra_version_reaction'] = val_e.get('codeSystemVersion', '')
                        e['e_i_2_1b_reaction_meddra_code']    = val_e.get('code', '')
                        orig_e = _h(val_e, 'originalText')
                        if orig_e is not None and orig_e.text:
                            e['e_i_1_1a_reaction_primary_source_native_language'] = orig_e.text.strip()
                            e['e_i_1_1b_reaction_primary_source_language']        = orig_e.get('language', '')

                    country_e = obs_e.find(
                        f'.//{_hl7("locatedPlace")}/{_hl7("code")}')
                    if country_e is not None:
                        e['e_i_9_identification_country_reaction'] = country_e.get('code', '')

                    _SERIOUSNESS = {
                        '34': 'e_i_3_2a_results_death',
                        '21': 'e_i_3_2b_life_threatening',
                        '33': 'e_i_3_2c_caused_prolonged_hospitalisation',
                        '35': 'e_i_3_2d_disabling_incapacitating',
                        '12': 'e_i_3_2e_congenital_anomaly_birth_defect',
                        '26': 'e_i_3_2f_other_medically_important_condition',
                    }
                    for obr2 in obs_e.findall(_hl7('outboundRelationship2')):
                        obs2 = _h(obr2, 'observation')
                        if obs2 is None:
                            continue
                        c2_el = _h(obs2, 'code')
                        v2_el = _h(obs2, 'value')
                        if c2_el is None:
                            continue
                        cv2 = c2_el.get('code', '')
                        if cv2 == '30' and v2_el is not None:
                            e['e_i_1_2_reaction_primary_source_translation'] = (
                                v2_el.text.strip() if v2_el.text else '')
                        elif cv2 == '37' and v2_el is not None:
                            e['e_i_3_1_term_highlighted_reporter'] = v2_el.get('code', '')
                        elif cv2 == '27' and v2_el is not None:
                            e['e_i_7_outcome_reaction_last_observation'] = v2_el.get('code', '')
                        elif cv2 in _SERIOUSNESS and v2_el is not None:
                            nf = v2_el.get('nullFlavor')
                            e[_SERIOUSNESS[cv2]] = (
                                {'_null_flavor': nf} if nf else v2_el.get('value', ''))

                    reactions = data.get('e_i_reaction_event', [])
                    reactions.append(e)
                    data['e_i_reaction_event'] = reactions

            org_f = _h(s2, 'organizer')
            if org_f is not None:
                org_fc = _h(org_f, 'code')
                if org_fc is not None and org_fc.get('code') == '3':
                    f_list = []
                    for comp_f in org_f.findall(_hl7('component')):
                        obs_f = _h(comp_f, 'observation')
                        if obs_f is None:
                            continue
                        f_entry: Dict[str, Any] = {}
                        oc_f = _h(obs_f, 'code')
                        eff_f = _h(obs_f, 'effectiveTime')
                        if eff_f is not None:
                            f_entry['f_r_1_test_date'] = eff_f.get('value', '')
                        if oc_f is not None:
                            f_entry['f_r_2_2b_test_name_meddra_code']     = oc_f.get('code', '')
                            f_entry['f_r_2_2a_meddra_version_test_name']  = oc_f.get('codeSystemVersion', '')
                            orig_f = _h(oc_f, 'originalText')
                            if orig_f is not None and orig_f.text:
                                f_entry['f_r_2_1_test_name'] = orig_f.text.strip()
                        val_f = _h(obs_f, 'value')
                        if val_f is not None:
                            tp_f = _xsi_type(val_f)
                            if 'IVL_PQ' in tp_f:
                                ctr = _h(val_f, 'center')
                                if ctr is not None:
                                    f_entry['f_r_3_2_test_result_val_qual'] = ctr.get('value', '')
                                    f_entry['f_r_3_3_test_result_unit']     = ctr.get('unit', '')
                            elif 'PQ' in tp_f:
                                f_entry['f_r_3_2_test_result_val_qual'] = val_f.get('value', '')
                                f_entry['f_r_3_3_test_result_unit']     = val_f.get('unit', '')
                            elif 'ED' in tp_f:
                                f_entry['f_r_3_4_result_unstructured_data'] = (
                                    val_f.text.strip() if val_f.text else '')
                                mt = val_f.get('mediaType', '')
                                if mt:
                                    f_entry['f_r_3_4_result_media_type'] = mt
                        rr = obs_f.find(
                            f'.//{_hl7("referenceRange")}/{_hl7("observationRange")}')
                        if rr is not None:
                            rr_v    = _h(rr, 'value')
                            rr_interp = _h(rr, 'interpretationCode')
                            if rr_v is not None and rr_interp is not None:
                                key = ('f_r_5_normal_high_value'
                                       if rr_interp.get('code') == 'H'
                                       else 'f_r_4_normal_low_value')
                                f_entry[key] = rr_v.get('value', '')
                        for obr2f in obs_f.findall(_hl7('outboundRelationship2')):
                            obs2f = _h(obr2f, 'observation')
                            if obs2f is None:
                                continue
                            c2f = _h(obs2f, 'code')
                            v2f = _h(obs2f, 'value')
                            if c2f is not None and c2f.get('code') == '25' and v2f is not None:
                                f_entry['f_r_7_more_information_available'] = v2f.get('value', '')
                        if f_entry:
                            f_list.append(f_entry)
                    if f_list:
                        data['f_r_results_tests_procedures_investigation_patient'] = f_list

            org_g = _h(s2, 'organizer')
            if org_g is not None:
                org_gc = _h(org_g, 'code')
                if org_gc is not None and org_gc.get('code') == '4':
                    for comp_g in org_g.findall(_hl7('component')):
                        sa = _h(comp_g, 'substanceAdministration')
                        if sa is None:
                            continue
                        g: Dict[str, Any] = {}
                        kind = sa.find(f'.//{_hl7("kindOfProduct")}')
                        if kind is not None:
                            nm = _h(kind, 'name')
                            if nm is not None and nm.text:
                                g['g_k_2_2_medicinal_product_name_primary_source'] = nm.text.strip()
                            kc = _h(kind, 'code')
                            if kc is not None:
                                g['g_k_2_1_1a_mpid_version'] = kc.get('codeSystemVersion', '')
                                g['g_k_2_1_1b_mpid']         = kc.get('code', '')
                            approval = kind.find(f'.//{_hl7("approval")}')
                            if approval is not None:
                                apid = _h(approval, 'id')
                                if apid is not None:
                                    g['g_k_3_1_authorisation_application_number'] = apid.get('extension', '')
                                holder_nm = approval.find(
                                    f'.//{_hl7("playingOrganization")}/{_hl7("name")}')
                                if holder_nm is not None and holder_nm.text:
                                    g['g_k_3_3_name_holder_applicant'] = holder_nm.text.strip()
                                terr = approval.find(f'.//{_hl7("territory")}/{_hl7("code")}')
                                if terr is not None:
                                    g['g_k_3_2_country_authorisation_application'] = terr.get('code', '')
                            ingr = _h(kind, 'ingredient')
                            if ingr is not None:
                                subst = _h(ingr, 'ingredientSubstance')
                                if subst is not None:
                                    g_sub: Dict[str, Any] = {}
                                    sn = _h(subst, 'name')
                                    if sn is not None and sn.text:
                                        g_sub['g_k_2_3_r_1_substance_name'] = sn.text.strip()
                                    sc = _h(subst, 'code')
                                    if sc is not None:
                                        g_sub['g_k_2_3_r_2a_substance_termid_version'] = sc.get('codeSystemVersion', '')
                                        g_sub['g_k_2_3_r_2b_substance_termid']         = sc.get('code', '')
                                    num = _h(ingr, 'quantity', 'numerator')
                                    if num is not None:
                                        g_sub['g_k_2_3_r_3a_strength_num']  = num.get('value', '')
                                        g_sub['g_k_2_3_r_3b_strength_unit'] = num.get('unit', '')
                                    if g_sub:
                                        g['g_k_2_3_r_substance_id_strength'] = [g_sub]
                            country_obt = kind.find(
                                f'.//{_hl7("addr")}/{_hl7("country")}')
                            if country_obt is not None and country_obt.text:
                                g['g_k_2_4_identification_country_drug_obtained'] = country_obt.text.strip()

                        dos_list = []
                        for obr2g in sa.findall(_hl7('outboundRelationship2')):
                            sa2 = _h(obr2g, 'substanceAdministration')
                            if sa2 is None:
                                continue
                            dos: Dict[str, Any] = {}
                            dq = _h(sa2, 'doseQuantity')
                            if dq is not None:
                                dos['g_k_4_r_1a_dose_num']  = dq.get('value', '')
                                dos['g_k_4_r_1b_dose_unit'] = dq.get('unit', '')
                            eff_g = _h(sa2, 'effectiveTime')
                            if eff_g is not None:
                                for comp2g in eff_g.findall(_hl7('comp')):
                                    tp2 = _xsi_type(comp2g)
                                    if 'IVL_TS' in tp2:
                                        low_g  = _h(comp2g, 'low')
                                        high_g = _h(comp2g, 'high')
                                        if low_g is not None:
                                            dos['g_k_4_r_4_date_time_drug'] = low_g.get('value', '')
                                        if high_g is not None:
                                            dos['g_k_4_r_5_date_time_last_administration'] = high_g.get('value', '')
                                    elif 'PIVL_TS' in tp2:
                                        per = _h(comp2g, 'period')
                                        if per is not None:
                                            dos['g_k_4_r_2_number_units_interval']   = per.get('value', '')
                                            dos['g_k_4_r_3_definition_interval_unit'] = per.get('unit', '')
                            rc = _h(sa2, 'routeCode')
                            if rc is not None:
                                orig_r = _h(rc, 'originalText')
                                dos['g_k_4_r_10_1_route_administration'] = (
                                    orig_r.text.strip() if (orig_r is not None and orig_r.text)
                                    else rc.get('code', ''))
                            fc = sa2.find(f'.//{_hl7("formCode")}/{_hl7("originalText")}')
                            if fc is not None and fc.text:
                                dos['g_k_4_r_9_1_pharmaceutical_dose_form'] = fc.text.strip()
                            if dos:
                                dos_list.append(dos)
                        if dos_list:
                            g['g_k_4_r_dosage_information'] = dos_list

                        ind_list = []
                        for ibr in sa.findall(_hl7('inboundRelationship')):
                            ibr_obs = _h(ibr, 'observation')
                            ibr_act = _h(ibr, 'act')
                            if ibr_obs is not None:
                                ibr_c = _h(ibr_obs, 'code')
                                ibr_v = _h(ibr_obs, 'value')
                                if ibr_c is not None and ibr_c.get('code') == '19' and ibr_v is not None:
                                    ind: Dict[str, Any] = {
                                        'g_k_7_r_2a_meddra_version_indication': ibr_v.get('codeSystemVersion', ''),
                                        'g_k_7_r_2b_indication_meddra_code':    ibr_v.get('code', ''),
                                    }
                                    orig_i = _h(ibr_v, 'originalText')
                                    if orig_i is not None and orig_i.text:
                                        ind['g_k_7_r_1_indication_primary_source'] = orig_i.text.strip()
                                    ind_list.append(ind)
                            if ibr_act is not None:
                                ac = _h(ibr_act, 'code')
                                if ac is not None:
                                    g['g_k_8_action_taken_drug'] = ac.get('code', '')
                        if ind_list:
                            g['g_k_7_r_indication_use_case'] = ind_list

                        drugs = data.get('g_k_drug_information', [])
                        drugs.append(g)
                        data['g_k_drug_information'] = drugs

        if d:
            data['d_patient_characteristics'] = d

    # G.k.1 drug role — from causalityAssessment code=20
    drugs = data.get('g_k_drug_information', [])
    drug_roles: List[str] = []
    for comp_ca in aea.findall(_hl7('component')):
        ca = _h(comp_ca, 'causalityAssessment')
        if ca is None:
            continue
        ca_c = _h(ca, 'code')
        ca_v = _h(ca, 'value')
        if ca_c is not None and ca_c.get('code') == '20' and ca_v is not None:
            drug_roles.append(ca_v.get('code', ''))
    for i, role in enumerate(drug_roles):
        if i < len(drugs):
            drugs[i]['g_k_1_characterisation_drug_role'] = role

    # C.2  Primary source
    c2_list = []
    for obr in invstg.findall(_hl7('outboundRelationship')):
        ri   = _h(obr, 'relatedInvestigation')
        if ri is None:
            continue
        ri_c = _h(ri, 'code')
        if ri_c is None or ri_c.get('code') != '2':
            continue
        ae   = _h(ri, 'subjectOf2', 'controlActEvent', 'author', 'assignedEntity')
        if ae is None:
            continue
        c2: Dict[str, Any] = {}
        pri = _h(obr, 'priorityNumber')
        if pri is not None:
            c2['c_2_r_5_primary_source_regulatory_purposes'] = pri.get('value', '')
        addr = _h(ae, 'addr')
        if addr is not None:
            for tag_name, field in [
                ('streetAddressLine', 'c_2_r_2_3_reporter_street'),
                ('city',              'c_2_r_2_4_reporter_city'),
                ('state',             'c_2_r_2_5_reporter_state_province'),
                ('postalCode',        'c_2_r_2_6_reporter_postcode'),
            ]:
                el = _h(addr, tag_name)
                if el is not None and el.text:
                    c2[field] = el.text.strip()
        person = _h(ae, 'assignedPerson')
        if person is not None:
            nm = _h(person, 'name')
            if nm is not None:
                gv = _h(nm, 'given')
                fm = _h(nm, 'family')
                if gv is not None and gv.text:
                    c2['c_2_r_1_2_reporter_given_name'] = gv.text.strip()
                if fm is not None and fm.text:
                    c2['c_2_r_1_4_reporter_family_name'] = fm.text.strip()
            qual_c = person.find(f'.//{_hl7("asQualifiedEntity")}/{_hl7("code")}')
            if qual_c is not None:
                c2['c_2_r_4_qualification'] = qual_c.get('code', '')
            cnt_c = person.find(f'.//{_hl7("asLocatedEntity")}/{_hl7("location")}/{_hl7("code")}')
            if cnt_c is not None:
                c2['c_2_r_3_reporter_country_code'] = cnt_c.get('code', '')
        org = _h(ae, 'representedOrganization')
        if org is not None:
            dep = _h(org, 'name')
            if dep is not None and dep.text:
                c2['c_2_r_2_2_reporter_department'] = dep.text.strip()
            sub_org = org.find(
                f'.//{_hl7("assignedEntity")}/{_hl7("representedOrganization")}/{_hl7("name")}')
            if sub_org is not None and sub_org.text:
                c2['c_2_r_2_1_reporter_organisation'] = sub_org.text.strip()
        c2_list.append(c2)
    if c2_list:
        data['c_2_r_primary_source_information'] = c2_list

    # C.3  Sender
    sender_ae = invstg.find(
        f'.//{_hl7("subjectOf1")}/{_hl7("controlActEvent")}'
        f'/{_hl7("author")}/{_hl7("assignedEntity")}')
    if sender_ae is not None:
        c3: Dict[str, Any] = {}
        sc = _h(sender_ae, 'code')
        if sc is not None:
            c3['c_3_1_sender_type'] = sc.get('code', '')
        addr3 = _h(sender_ae, 'addr')
        if addr3 is not None:
            for tag_name, field in [
                ('streetAddressLine', 'c_3_4_1_sender_street_address'),
                ('city',              'c_3_4_2_sender_city'),
                ('state',             'c_3_4_3_sender_state_province'),
                ('postalCode',        'c_3_4_4_sender_postcode'),
            ]:
                el = _h(addr3, tag_name)
                if el is not None and el.text:
                    c3[field] = el.text.strip()
        for tc in sender_ae.findall(_hl7('telecom')):
            v = tc.get('value', '')
            if v.startswith('tel:'):
                c3['c_3_4_6_sender_telephone'] = v[4:]
            elif v.startswith('fax:'):
                c3['c_3_4_7_sender_fax'] = v[4:]
            elif v.startswith('mailto:'):
                c3['c_3_4_8_sender_email'] = v[7:]
        p3 = _h(sender_ae, 'assignedPerson')
        if p3 is not None:
            nm3 = _h(p3, 'name')
            if nm3 is not None:
                gv3 = _h(nm3, 'given')
                fm3 = _h(nm3, 'family')
                if gv3 is not None and gv3.text:
                    c3['c_3_3_3_sender_given_name'] = gv3.text.strip()
                if fm3 is not None and fm3.text:
                    c3['c_3_3_5_sender_family_name'] = fm3.text.strip()
            cnt3 = p3.find(f'.//{_hl7("asLocatedEntity")}/{_hl7("location")}/{_hl7("code")}')
            if cnt3 is not None:
                c3['c_3_4_5_sender_country_code'] = cnt3.get('code', '')
        org3 = _h(sender_ae, 'representedOrganization')
        if org3 is not None:
            dep3 = _h(org3, 'name')
            if dep3 is not None and dep3.text:
                c3['c_3_3_1_sender_department'] = dep3.text.strip()
            sub3 = org3.find(
                f'.//{_hl7("assignedEntity")}/{_hl7("representedOrganization")}/{_hl7("name")}')
            if sub3 is not None and sub3.text:
                c3['c_3_2_sender_organisation'] = sub3.text.strip()
        data['c_3_information_sender_case_safety_report'] = c3

    # H  Narrative
    h: Dict[str, Any] = {}
    txt_el = _h(invstg, 'text')
    if txt_el is not None and txt_el.text:
        h['h_1_case_narrative'] = txt_el.text.strip()

    for comp_h in aea.findall(_hl7('component1')):
        oe_h  = _h(comp_h, 'observationEvent')
        if oe_h is None:
            continue
        oe_hc = _h(oe_h, 'code')
        oe_hv = _h(oe_h, 'value')
        auth_c = oe_h.find(
            f'.//{_hl7("author")}/{_hl7("assignedEntity")}/{_hl7("code")}')
        if oe_hc is None or oe_hv is None:
            continue
        if oe_hc.get('code') != '10':
            continue
        val_text = oe_hv.text.strip() if oe_hv.text else ''
        ac = auth_c.get('code', '') if auth_c is not None else ''
        if ac == '3':
            h['h_2_reporter_comments'] = val_text
        elif ac == '1':
            h['h_4_sender_comments'] = val_text

    h5_list = []
    for comp_h5 in invstg.findall(_hl7('component')):
        oe5 = _h(comp_h5, 'observationEvent')
        if oe5 is None:
            continue
        c5 = _h(oe5, 'code')
        v5 = _h(oe5, 'value')
        if c5 is None or c5.get('code') != '36' or v5 is None:
            continue
        h5_list.append({
            'h_5_r_1a_case_summary_reporter_comments_text':     v5.text.strip() if v5.text else '',
            'h_5_r_1b_case_summary_reporter_comments_language': v5.get('language', ''),
        })
    if h5_list:
        h['h_5_r_case_summary_reporter_comments_native_language'] = h5_list

    if h:
        data['h_narrative_case_summary'] = h

    return data


def _parse_xml(xml_string: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse E2B R3 XML. Auto-detects format:
      - Standard ICH HL7 v3 XML (MCCI_IN200100UV01 / urn:hl7-org:v3)
      - Application internal XML (produced by the to-xml endpoint)
    Returns (root_tag, data_dict).
    """
    xml_string = xml_string.strip()
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        raise ValueError(f'Invalid XML: {exc}') from exc

    hl7_ns = 'urn:hl7-org:v3'
    local_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
    is_hl7 = (hl7_ns in root.tag or
              root.get('xmlns') == hl7_ns or
              local_tag in ('MCCI_IN200100UV01', 'PORR_IN049016UV'))

    if is_hl7:
        data = _parse_hl7_xml(root)
        return 'ICSR', data

    data = _elem_to_value(root)
    return root.tag, (data or {})
