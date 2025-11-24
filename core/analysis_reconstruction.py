# core/analysis_reconstruction.py

from __future__ import annotations

import numpy as np
import pandas as pd
import math

from core.rlc_theory import simulate_response_with_tolerances
from core.units import get_multiplier


def _safe_float(value, default=None):
    try:
        if isinstance(value, str):
            value = value.replace(",", ".")
        return float(value)
    except Exception:
        return default

def solve_rlc_from_f0_Q(
    f0_hz: float,
    Q: float,
    known_type: str,
    known_value_SI: float,
):
    """
    Resolve os componentes de um RLC série a partir de:
      - f0 (Hz) medido a partir da curva,
      - Q medido a partir da curva,
      - um componente fixo (R, L ou C) em unidades SI.

    known_type:
        "R", "L" ou "C"
    known_value_SI:
        se R -> ohms
        se L -> henry
        se C -> farad

    Retorna:
        dict com R, L, C (em SI) e f0_calc, Q_calc recalculados.
    """

    if f0_hz is None or f0_hz <= 0:
        raise ValueError("f₀ inválido para projeto inverso.")
    if Q is None or Q <= 0:
        raise ValueError("Q inválido para projeto inverso.")
    if known_value_SI is None or known_value_SI <= 0:
        raise ValueError("Valor do componente fixo deve ser > 0.")

    omega0 = 2.0 * math.pi * float(f0_hz)
    known_type = str(known_type).upper()

    if known_type == "R":
        # R conhecido -> resolve L e C
        R = float(known_value_SI)
        p = 1.0 / (omega0 ** 2)          # p = L*C
        sqrt_p = math.sqrt(p)

        # L/C = (Q*R)^2  e  LC = p
        L = Q * R * sqrt_p
        C = sqrt_p / (Q * R)

    elif known_type == "L":
        # L conhecido -> resolve C e R
        L = float(known_value_SI)
        C = 1.0 / (omega0 ** 2 * L)
        if C <= 0:
            raise ValueError("C calculado não físico (<= 0).")

        R = (1.0 / Q) * math.sqrt(L / C)

    elif known_type == "C":
        # C conhecido -> resolve L e R
        C = float(known_value_SI)
        L = 1.0 / (omega0 ** 2 * C)
        if L <= 0:
            raise ValueError("L calculado não físico (<= 0).")

        R = (1.0 / Q) * math.sqrt(L / C)
    else:
        raise ValueError("Tipo conhecido deve ser 'R', 'L' ou 'C'.")

    if R <= 0:
        raise ValueError("R calculado não físico (<= 0).")

    # Recalcula f0 e Q teóricos para conferir o ajuste
    f0_calc = 1.0 / (2.0 * math.pi * math.sqrt(L * C))
    Q_calc = (1.0 / R) * math.sqrt(L / C)

    return {
        "R": R,
        "L": L,
        "C": C,
        "f0_calc": f0_calc,
        "Q_calc": Q_calc,
    }

def reconstruct_theoretical_curve(params: dict, num_points: int | None = None):
    """
    Reconstrói a curva teórica para a Análise de Dados.

    Estratégia:
    - Se params tiver 'curve_points', usa diretamente os pontos salvos
      (freqs_Hz, gain_norm), garantindo curva idêntica ao simulador.
    - Caso contrário (arquivos antigos), re-simula via core.rlc_theory.

    Retorna:
        df: DataFrame com colunas ["Frequency", "Gain"]
        metrics: dict com f0, Q, BW, f1, f2
    """

    # =================== CAMINHO 1: usar pontos salvos ===================
    curve_points = params.get("curve_points")
    if curve_points is not None:
        try:
            freqs = np.asarray(curve_points.get("freqs_Hz", []), dtype=float)
            gain_norm = np.asarray(curve_points.get("gain_norm", []), dtype=float)

            if freqs.size > 0 and gain_norm.size == freqs.size:
                df = pd.DataFrame(
                    {
                        "Frequency": freqs,
                        "Gain": gain_norm,
                    }
                )

                # Métricas: prioriza as salvas
                metrics_saved = params.get("metrics") or {}
                metrics = {
                    "f0": _safe_float(metrics_saved.get("f0")),
                    "Q": _safe_float(metrics_saved.get("Q")),
                    "BW": _safe_float(metrics_saved.get("BW")),
                    "f1": _safe_float(metrics_saved.get("f1")),
                    "f2": _safe_float(metrics_saved.get("f2")),
                }
                return df, metrics
        except Exception as e:
            print(f"[WARN] Falha ao usar curve_points salvos, caindo na re-simulação: {e}")

    # =================== CAMINHO 2: fallback – re-simular ===================

    # 1) Componentes em SI
    R_nom = _safe_float(params.get("R"), 0.0) * get_multiplier(params.get("R_unit", "Ω"))
    L_nom = _safe_float(params.get("L"), 0.0) * get_multiplier(params.get("L_unit", "H"))
    C_nom = _safe_float(params.get("C"), 0.0) * get_multiplier(params.get("C_unit", "F"))

    tol_R = _safe_float(params.get("R_tol"), 0.0) / 100.0
    tol_L = _safe_float(params.get("L_tol"), 0.0) / 100.0
    tol_C = _safe_float(params.get("C_tol"), 0.0) / 100.0

    V_in_plot = _safe_float(params.get("V_in"), 1.0)
    if V_in_plot is None or V_in_plot <= 0:
        V_in_plot = 1.0

    # 2) Faixa de frequência
    freq_range = params.get("freq_range") or {}
    f_min_Hz = _safe_float(freq_range.get("f_min_Hz"))
    f_max_Hz = _safe_float(freq_range.get("f_max_Hz"))

    if f_min_Hz is not None and f_min_Hz <= 0:
        f_min_Hz = None
    if f_max_Hz is not None and f_max_Hz <= 0:
        f_max_Hz = None
    if f_min_Hz is not None and f_max_Hz is not None and f_min_Hz >= f_max_Hz:
        f_min_Hz = None
        f_max_Hz = None

    sim_kwargs = dict(
        R_nom=R_nom,
        L_nom=L_nom,
        C_nom=C_nom,
        tol_R=tol_R,
        tol_L=tol_L,
        tol_C=tol_C,
        V_in_plot=V_in_plot,
        freq_min=f_min_Hz,
        freq_max=f_max_Hz,
    )
    if num_points is not None:
        sim_kwargs["num_points"] = int(num_points)

    (
        freqs,
        nom_curve_Vout,
        min_curve_Vout,
        max_curve_Vout,
        metrics_nom,
        ranges,
        Vout_max_global,
    ) = simulate_response_with_tolerances(**sim_kwargs)

    freqs = np.asarray(freqs, dtype=float)
    gain = nom_curve_Vout / V_in_plot
    max_gain = float(np.max(gain)) if gain.size > 0 else 0.0
    gain_norm = gain / max_gain if max_gain > 0 else gain

    df = pd.DataFrame(
        {
            "Frequency": freqs,
            "Gain": gain_norm,
        }
    )

    metrics_saved = params.get("metrics") or {}
    metrics = dict(metrics_nom)

    for key in ("f0", "Q", "BW", "f1", "f2"):
        val = metrics_saved.get(key)
        if val is not None:
            metrics[key] = _safe_float(val, metrics.get(key))

    return df, metrics