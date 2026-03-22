"""
scoring.py – Centralised ICU Clinical Scoring Engine
Module 25: ICU Vital Signs Monitoring

Implements:
  - NEWS2  (National Early Warning Score 2) — NHS gold standard
  - SOFA   (Sequential Organ Failure Assessment) — 6 organ systems
  - APACHE II stub — Acute Physiology and Chronic Health Evaluation
"""

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# NEWS2 — National Early Warning Score 2
# Reference: Royal College of Physicians, NEWS2 (2017)
# ---------------------------------------------------------------------------

ACVPU_SCORE = {
    "Alert":      0,
    "Confusion":  3,   # New confusion = immediate 3 pts
    "Voice":      3,
    "Pain":       3,
    "Unresponsive": 3,
}

def _news2_resp_rate(rr: float) -> int:
    if rr <= 8:                return 3
    if rr <= 11:               return 1
    if rr <= 20:               return 0
    if rr <= 24:               return 2
    return 3  # >= 25

def _news2_spo2_scale1(spo2: float) -> int:
    """Scale 1 — for patients NOT on supplemental oxygen, no hypercapnic risk."""
    if spo2 <= 91:   return 3
    if spo2 <= 93:   return 2
    if spo2 <= 95:   return 1
    return 0  # >= 96

def _news2_spo2_scale2(spo2: float, supplemental_o2: bool) -> int:
    """
    Scale 2 — for confirmed hypercapnic respiratory failure (COPD/Type 2 RF).
    Target SpO2 88-92%. Used when respiratory_support flag set.
    """
    if spo2 <= 83:             return 3
    if spo2 <= 85:             return 2
    if spo2 <= 87:             return 1
    if spo2 <= 92:             return 0 if not supplemental_o2 else 0
    if spo2 <= 94:             return 0 if not supplemental_o2 else 1
    if spo2 <= 96:             return 0 if not supplemental_o2 else 2
    return 0 if not supplemental_o2 else 3  # >= 97 on O2

def _news2_supplemental_o2(supplemental_o2: bool) -> int:
    return 2 if supplemental_o2 else 0

def _news2_systolic_bp(sbp: float) -> int:
    if sbp <= 90:  return 3
    if sbp <= 100: return 2
    if sbp <= 110: return 1
    if sbp <= 219: return 0
    return 3  # >= 220 also scores

def _news2_heart_rate(hr: float) -> int:
    if hr <= 40:   return 3
    if hr <= 50:   return 1
    if hr <= 90:   return 0
    if hr <= 110:  return 1
    if hr <= 130:  return 2
    return 3  # >= 131

def _news2_temp(temp_c: float) -> int:
    if temp_c <= 35.0: return 3
    if temp_c <= 36.0: return 1
    if temp_c <= 38.0: return 0
    if temp_c <= 39.0: return 1
    return 2  # >= 39.1

def _news2_acvpu(level: str) -> int:
    return ACVPU_SCORE.get(level, 0)

def _news2_risk_band(score: int) -> Dict[str, Any]:
    if score == 0:
        return {"band": "Low", "colour": "green", "frequency": "Minimum 12 hourly", "escalation": "Ward nurse"}
    if score <= 4:
        return {"band": "Low-Medium", "colour": "yellow", "frequency": "Minimum 4-6 hourly", "escalation": "Inform bedside nurse"}
    if score == 3 and False:    # single-parameter score=3 (handled separately in caller)
        return {"band": "Medium", "colour": "amber", "frequency": "Minimum 1 hourly", "escalation": "Urgent review"}
    if score <= 6:
        return {"band": "Medium", "colour": "amber", "frequency": "Minimum 1 hourly", "escalation": "Urgent clinical review"}
    return {"band": "High", "colour": "red", "frequency": "Continuous monitoring", "escalation": "Emergency assessment — consider ICU/HDU"}


def calculate_news2(
    resp_rate: float,
    spo2: float,
    supplemental_o2: bool,
    systolic_bp: float,
    heart_rate: float,
    temp_c: float,
    consciousness: str,
    use_spo2_scale2: bool = False,
) -> Dict[str, Any]:
    """
    Calculate NEWS2 score.

    Returns a detailed breakdown dict with component scores and risk band.
    """
    components = {
        "respiratory_rate": _news2_resp_rate(resp_rate),
        "spo2": (
            _news2_spo2_scale2(spo2, supplemental_o2)
            if use_spo2_scale2
            else _news2_spo2_scale1(spo2)
        ),
        "supplemental_o2": _news2_supplemental_o2(supplemental_o2),
        "systolic_bp": _news2_systolic_bp(systolic_bp),
        "heart_rate": _news2_heart_rate(heart_rate),
        "temperature": _news2_temp(temp_c),
        "consciousness": _news2_acvpu(consciousness),
    }

    total = sum(components.values())
    risk = _news2_risk_band(total)

    # Any single component scoring 3 → medium escalation regardless of total
    any_3 = any(v == 3 for v in components.values())
    if any_3 and total < 5:
        risk = {
            "band": "Medium",
            "colour": "amber",
            "frequency": "Minimum 1 hourly",
            "escalation": "Urgent clinical review (single parameter score=3)"
        }

    return {
        "total_news2": total,
        "components": components,
        "risk_band": risk["band"],
        "colour": risk["colour"],
        "monitoring_frequency": risk["frequency"],
        "escalation_action": risk["escalation"],
        "any_single_param_critical": any_3,
    }


# ---------------------------------------------------------------------------
# SOFA — Sequential Organ Failure Assessment (6 organ systems)
# Reference: Vincent JL et al, Intensive Care Med 1996
# ---------------------------------------------------------------------------

def _sofa_respiratory(spo2: float, supplemental_o2: bool) -> int:
    """
    Respiratory: PaO2/FiO2 ratio is ideal but SpO2-based approximation used here.
    SpO2/FiO2 (SF ratio) approximation per Rice et al.
    FiO2 estimated: room air=0.21, supplemental O2=0.40
    """
    fio2 = 0.40 if supplemental_o2 else 0.21
    sf = spo2 / fio2
    if sf >= 400: return 0
    if sf >= 300: return 1
    if sf >= 200: return 2
    if sf >= 100: return 3
    return 4

def _sofa_cardiovascular(systolic_bp: float, map_bp: Optional[float] = None) -> int:
    """
    Cardiovascular: MAP < 70 = score 1, vasopressor requirement assumed from MAP.
    Vasopressor doses not available from vital signs alone — simplified by MAP/SBP.
    """
    effective = map_bp if map_bp else systolic_bp * 0.7  # rough MAP if not given
    if effective >= 70: return 0
    return 1  # MAP < 70 (vasopressor data not captured at form level)

def _sofa_cns(consciousness: str) -> int:
    """CNS: GCS approximation from ACVPU level."""
    gcs_map = {
        "Alert":        15,
        "Confusion":    13,
        "Voice":        10,
        "Pain":         7,
        "Unresponsive": 3,
    }
    gcs = gcs_map.get(consciousness, 15)
    if gcs >= 15: return 0
    if gcs >= 13: return 1
    if gcs >= 10: return 2
    if gcs >= 6:  return 3
    return 4

def _sofa_renal(urine_output_ml_hr: Optional[float]) -> int:
    """Renal: urine output < 0.5 ml/kg/hr for 12h = failure. Using raw ml/hr."""
    if urine_output_ml_hr is None: return 0
    if urine_output_ml_hr >= 0.5: return 0   # normal (per ~70 kg patient)
    if urine_output_ml_hr >= 200/24: return 2  # < 500 ml/day
    return 3   # < 200 ml/day level

def _sofa_coagulation(platelet_count: Optional[float] = None) -> int:
    """Coagulation: platelets (x10^3/μL). Not captured at bedside; default 0."""
    if platelet_count is None: return 0
    if platelet_count >= 150: return 0
    if platelet_count >= 100: return 1
    if platelet_count >= 50:  return 2
    if platelet_count >= 20:  return 3
    return 4

def _sofa_liver(bilirubin_umol: Optional[float] = None) -> int:
    """Liver: bilirubin μmol/L. Lab value; default 0 if not provided."""
    if bilirubin_umol is None: return 0
    if bilirubin_umol < 20:   return 0
    if bilirubin_umol < 33:   return 1
    if bilirubin_umol < 102:  return 2
    if bilirubin_umol < 204:  return 3
    return 4

def _sofa_risk(total: int) -> str:
    if total <= 1:  return "Low"
    if total <= 6:  return "Moderate"
    if total <= 11: return "High"
    return "Very High"

def _sofa_mortality(total: int) -> str:
    if total <= 1:  return "<10%"
    if total <= 6:  return "15–20%"
    if total <= 11: return "40–50%"
    return ">80%"


def calculate_sofa(
    spo2: float,
    supplemental_o2: bool,
    systolic_bp: float,
    consciousness: str,
    urine_output_ml_hr: Optional[float] = None,
    platelet_count: Optional[float] = None,
    bilirubin_umol: Optional[float] = None,
    map_bp: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Full 6-organ SOFA score.
    Returns per-organ scores, total, risk level and estimated mortality.
    """
    organs = {
        "respiratory":    _sofa_respiratory(spo2, supplemental_o2),
        "cardiovascular": _sofa_cardiovascular(systolic_bp, map_bp),
        "cns":            _sofa_cns(consciousness),
        "renal":          _sofa_renal(urine_output_ml_hr),
        "coagulation":    _sofa_coagulation(platelet_count),
        "liver":          _sofa_liver(bilirubin_umol),
    }

    total = sum(organs.values())

    return {
        "total_sofa": total,
        "organ_scores": organs,
        "risk_level": _sofa_risk(total),
        "estimated_mortality": _sofa_mortality(total),
        "multi_organ_dysfunction": total >= 6,
    }


# ---------------------------------------------------------------------------
# APACHE II — Acute Physiology and Chronic Health Evaluation II
# Reference: Knaus WA et al, Crit Care Med 1985
# ---------------------------------------------------------------------------

def calculate_apache2(
    age: int,
    heart_rate: float,
    systolic_bp: float,  # Used to estimate MAP or use map_est
    temp_c: float,
    resp_rate: float,
    consciousness: str,
    chronic_health_points: int = 0,
    # Labs / ABG
    spo2: Optional[float] = None,
    pao2_mmhg: Optional[float] = None,
    fio2_pct: Optional[float] = None,
    ph: Optional[float] = None,
    sodium: Optional[float] = None,
    potassium: Optional[float] = None,
    creatinine_mg_dl: Optional[float] = None,
    hematocrit: Optional[float] = None,
    wbc_count: Optional[float] = None,
) -> Dict[str, Any]:
    """
    APACHE II implementation with lab support.
    Falls back to partial scoring if labs are unavailable.
    """
    score = 0
    
    # Age points
    if age >= 75:  score += 6
    elif age >= 65: score += 5
    elif age >= 55: score += 3
    elif age >= 45: score += 2

    # Heart rate
    if heart_rate >= 180 or heart_rate <= 39:   score += 4
    elif heart_rate >= 140 or heart_rate <= 54:  score += 3
    elif heart_rate >= 110:                      score += 2
    elif heart_rate <= 69:                       score += 1

    # Mean BP (approx from SBP)
    map_est = systolic_bp * 0.7
    if map_est >= 160 or map_est <= 49:   score += 4
    elif map_est >= 130 or map_est <= 69: score += 2
    elif map_est >= 110:                  score += 1

    # Temperature
    if temp_c >= 41.0 or temp_c <= 29.9: score += 4
    elif temp_c >= 39.0 or temp_c <= 31.9: score += 3
    elif temp_c <= 33.9:                 score += 2
    elif temp_c >= 38.5 or temp_c <= 35.9: score += 1

    # Respiratory rate
    if resp_rate >= 50 or resp_rate <= 5: score += 4
    elif resp_rate >= 35:                 score += 3
    elif resp_rate <= 9:                  score += 2
    elif resp_rate >= 25:                 score += 1

    # Oxygenation
    if fio2_pct is not None and fio2_pct >= 50 and pao2_mmhg is not None:
        aado2 = (713 * (fio2_pct / 100)) - (pao2_mmhg / 0.8) - pao2_mmhg
        if aado2 >= 500: score += 4
        elif aado2 >= 350: score += 3
        elif aado2 >= 200: score += 2
    elif pao2_mmhg is not None:
        if pao2_mmhg < 55: score += 4
        elif pao2_mmhg <= 60: score += 3
        elif pao2_mmhg <= 70: score += 1
    elif spo2 is not None:
        if spo2 < 70:   score += 4
        elif spo2 < 80: score += 3
        elif spo2 < 90: score += 1

    # pH
    if ph is not None:
        if ph >= 7.7 or ph < 7.15: score += 4
        elif ph >= 7.6 or ph <= 7.24: score += 3
        elif ph <= 7.32: score += 2
        elif ph >= 7.5: score += 1
        
    # Serum Sodium
    if sodium is not None:
        if sodium >= 180 or sodium <= 110: score += 4
        elif sodium >= 160 or sodium <= 119: score += 3
        elif sodium >= 155 or sodium <= 129: score += 2
        elif sodium >= 150: score += 1

    # Serum Potassium
    if potassium is not None:
        if potassium >= 7.0 or potassium < 2.5: score += 4
        elif potassium >= 6.0: score += 3
        elif potassium <= 2.9: score += 2
        elif potassium >= 5.5 or potassium <= 3.4: score += 1

    # Creatinine
    if creatinine_mg_dl is not None:
        cr = creatinine_mg_dl
        if cr >= 3.5: score += 4
        elif cr >= 2.0: score += 3
        elif cr >= 1.5 or cr < 0.6: score += 2

    # Hematocrit
    if hematocrit is not None:
        if hematocrit >= 60.0 or hematocrit < 20.0: score += 4
        elif hematocrit >= 50.0 or hematocrit < 30.0: score += 2
        elif hematocrit >= 46.0: score += 1

    # WBC
    if wbc_count is not None:
        if wbc_count >= 40.0 or wbc_count < 1.0: score += 4
        elif wbc_count >= 20.0 or wbc_count < 3.0: score += 2
        elif wbc_count >= 15.0: score += 1

    # GCS via ACVPU
    gcs_approx = {"Alert": 15, "Confusion": 13, "Voice": 10, "Pain": 7, "Unresponsive": 3}
    gcs = gcs_approx.get(consciousness, 15)
    score += (15 - gcs)

    score += chronic_health_points

    # Predicted hospital mortality (Knaus logistic regression approximation)
    import math
    ln_odds = -3.517 + (score * 0.146)
    probability = 1 / (1 + math.exp(-ln_odds))

    base_note = "Lab values utilized for scoring." if pao2_mmhg or wbc_count else "Warning: limited bedside parameters only."
    return {
        "apache2_score": score,
        "estimated_hospital_mortality_pct": round(probability * 100, 1),
        "note": base_note,
    }


# ---------------------------------------------------------------------------
# SAPS II — Simplified Acute Physiology Score II
# Reference: Le Gall JR et al, JAMA 1993
# ---------------------------------------------------------------------------

def calculate_saps2(
    age: int,
    heart_rate: float,
    systolic_bp: float,
    temp_c: float,
    consciousness: str,             # For GCS estimation
    urine_output_ml_hr: Optional[float] = None, # Used for 24h estimation if provided
    bun_mg_dl: Optional[float] = None,
    wbc_count: Optional[float] = None,
    potassium: Optional[float] = None,
    sodium: Optional[float] = None,
    hco3_meq_l: Optional[float] = None,
    bilirubin_umol: Optional[float] = None,
    pao2_mmhg: Optional[float] = None,
    fio2_pct: Optional[float] = None,
    admission_type: str = "Medical", # Medical, ScheduledSurgical, UnscheduledSurgical
    chronic_diseases: bool = False,  # Simplified chronic disease boolean
) -> Dict[str, Any]:
    score = 0
    
    # Age
    if age >= 75: score += 18
    elif age >= 70: score += 16
    elif age >= 60: score += 12
    elif age >= 40: score += 7

    # Heart Rate
    if heart_rate >= 160: score += 11
    elif heart_rate >= 120: score += 7
    elif heart_rate < 40: score += 11
    elif heart_rate < 70: score += 2

    # Systolic BP
    if systolic_bp >= 200: score += 2
    elif systolic_bp < 70: score += 13
    elif systolic_bp < 100: score += 5
    
    # Temperature
    if temp_c >= 39.0: score += 3

    # PaO2/FiO2 (if mechanical ventilation assumed, using ratio if fio2 > 0)
    if pao2_mmhg is not None and fio2_pct is not None and fio2_pct > 0:
        pf_ratio = pao2_mmhg / (fio2_pct / 100.0)
        if pf_ratio < 100: score += 11
        elif pf_ratio < 200: score += 9
        elif pf_ratio < 1000: score += 6 

    # Urine Output (estimating 24h from hourly)
    if urine_output_ml_hr is not None:
        uo_24h = urine_output_ml_hr * 24
        if uo_24h < 500: score += 11
        elif uo_24h < 1000: score += 4

    # BUN
    if bun_mg_dl is not None:
        if bun_mg_dl >= 84.0: score += 10
        elif bun_mg_dl >= 28.0: score += 6

    # WBC
    if wbc_count is not None:
        if wbc_count >= 20.0: score += 3
        elif wbc_count < 1.0: score += 12

    # Potassium
    if potassium is not None:
        if potassium >= 5.0: score += 3
        elif potassium < 3.0: score += 3

    # Sodium
    if sodium is not None:
        if sodium >= 145: score += 1
        elif sodium < 125: score += 5
        
    # HCO3
    if hco3_meq_l is not None:
        if hco3_meq_l < 15.0: score += 6
        elif hco3_meq_l < 20.0: score += 3

    # Bilirubin
    if bilirubin_umol is not None:
        if bilirubin_umol >= 102.6: score += 9
        elif bilirubin_umol >= 68.4: score += 4

    # GCS
    gcs_approx = {"Alert": 15, "Confusion": 13, "Voice": 10, "Pain": 7, "Unresponsive": 3}
    gcs = gcs_approx.get(consciousness, 15)
    if gcs < 6: score += 26
    elif gcs < 9: score += 13
    elif gcs < 11: score += 7
    elif gcs < 14: score += 5

    # Chronic diseases
    if chronic_diseases:
        score += 9

    # Admission type
    if admission_type == "UnscheduledSurgical": score += 8
    elif admission_type == "Medical": score += 6

    # Logit for mortality
    import math
    logit = -7.7631 + 0.0737 * score + 0.9971 * math.log(score + 1) if score > 0 else -7.7631
    probability = math.exp(logit) / (1 + math.exp(logit))

    return {
        "saps2_score": score,
        "estimated_hospital_mortality_pct": round(probability * 100, 1),
    }
