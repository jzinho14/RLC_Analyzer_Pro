# core/curve_fitting.py

"""
Ferramentas de ajuste de curva (Gauss–Marquardt) para o RLC Analyzer.

Aqui usamos um modelo de segunda ordem do tipo band-pass, parametrizado por:
    A  -> ganho de pico
    f0 -> frequência de ressonância
    Q  -> fator de qualidade

O ajuste é feito com Levenberg–Marquardt via scipy.optimize.curve_fit
(quando disponível). Se SciPy não estiver instalado, usamos apenas o
chute inicial (sem refino iterativo), o que já aproxima bem a forma
da curva.
"""

from __future__ import annotations
import numpy as np

try:
    from scipy.optimize import curve_fit  # Levenberg–Marquardt
except Exception:  # SciPy ausente ou incompatível
    curve_fit = None


def _bandpass_model(f: np.ndarray, A: float, f0: float, Q: float) -> np.ndarray:
    """
    Modelo de magnitude de um sistema 2ª ordem tipo passa-faixa, normalizado:

        H(f) = A * ( (f/f0) / Q ) / sqrt( (1 - (f/f0)^2)^2 + ((f/f0)/Q)^2 )

    Em f = f0, o ganho é ~ A.
    """
    f = np.asarray(f, dtype=float)
    x = f / f0

    num = x / Q
    den = np.sqrt((1.0 - x**2) ** 2 + (x / Q) ** 2)

    # Evita divisão maluca em pontos degenerados
    den = np.where(den == 0, np.finfo(float).eps, den)
    return A * num / den


def _initial_guess(freqs: np.ndarray, gains: np.ndarray) -> tuple[float, float, float]:
    """
    Chutes iniciais (A0, f0_0, Q0) a partir dos dados medidos.
    """
    freqs = np.asarray(freqs, dtype=float)
    gains = np.asarray(gains, dtype=float)

    idx_peak = int(np.nanargmax(gains))
    A0 = float(gains[idx_peak])
    f0_0 = float(freqs[idx_peak])

    # Estimar Q pela largura de banda em -3dB (ganho / sqrt(2))
    target = A0 / np.sqrt(2.0)
    mask_bw = gains >= target

    if np.count_nonzero(mask_bw) >= 2:
        f_bw = freqs[mask_bw]
        f1 = float(f_bw[0])
        f2 = float(f_bw[-1])
        BW = max(f2 - f1, 1e-9)
        Q0 = max(f0_0 / BW, 0.1)
    else:
        Q0 = 1.0

    # Limita Q0 em um intervalo razoável
    Q0 = float(np.clip(Q0, 0.1, 200.0))
    return A0, f0_0, Q0


def fit_bandpass_rlc(
    freqs: np.ndarray,
    gains: np.ndarray,
    n_points: int = 600,
) -> dict | None:
    """
    Ajusta uma curva experimental de ganho (Vout/Vin) usando um modelo
    de 2ª ordem passa-faixa via Gauss–Marquardt (quando SciPy disponível).

    Parâmetros
    ----------
    freqs : array
        Frequências em Hz (mesmos pontos do experimento).
    gains : array
        Ganho medido (Vout/Vin) para cada frequência.
    n_points : int
        Número de pontos na curva ajustada (freq_smooth).

    Retorna
    -------
    dict ou None:
        {
            "A": A_otimo,
            "f0": f0_otimo,
            "Q": Q_otimo,
            "freq_smooth": array com frequências (Hz),
            "gain_smooth": array com ganho ajustado (mesmos units de 'gains')
        }

        Retorna None se não for possível ajustar (dados insuficientes).
    """
    freqs = np.asarray(freqs, dtype=float)
    gains = np.asarray(gains, dtype=float)

    # Limpeza básica
    mask = np.isfinite(freqs) & np.isfinite(gains) & (freqs > 0) & (gains > 0)
    if np.count_nonzero(mask) < 5:
        return None

    f = freqs[mask]
    g = gains[mask]

    # Chute inicial
    A0, f0_0, Q0 = _initial_guess(f, g)

    if curve_fit is not None:
        try:
            # LM (Gauss–Marquardt) é o default para problema sem bounds
            popt, _ = curve_fit(
                _bandpass_model,
                f,
                g,
                p0=[A0, f0_0, Q0],
                maxfev=10000,
            )
            A_opt, f0_opt, Q_opt = popt
        except Exception:
            # fallback para o chute inicial se o ajuste divergir
            A_opt, f0_opt, Q_opt = A0, f0_0, Q0
    else:
        # SciPy indisponível -> usamos apenas o chute inicial
        A_opt, f0_opt, Q_opt = A0, f0_0, Q0

    # Gera curva lisa em log-freq
    f_min = float(np.min(f))
    f_max = float(np.max(f))
    f_smooth = np.logspace(np.log10(f_min), np.log10(f_max), n_points)

    g_smooth = _bandpass_model(f_smooth, A_opt, f0_opt, Q_opt)

    return {
        "A": float(A_opt),
        "f0": float(f0_opt),
        "Q": float(Q_opt),
        "freq_smooth": f_smooth,
        "gain_smooth": g_smooth,
    }
