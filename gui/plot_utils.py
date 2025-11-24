# gui/plot_utils.py

import numpy as np
from matplotlib.ticker import FuncFormatter, LogLocator

def _select_freq_unit(max_freq_hz: float) -> tuple[float, str]:
    """
    Decide a unidade mais adequada para exibir frequências.

    Retorna:
        (factor, unit)
        onde valor_em_unidade = valor_em_Hz / factor
    """
    if max_freq_hz >= 1e6:
        return 1e6, "MHz"
    elif max_freq_hz >= 1e3:
        return 1e3, "kHz"
    else:
        return 1.0, "Hz"


def setup_frequency_axis(ax, freqs):
    """
    Configura o eixo de frequência em escala log, com:
    - unidade escolhida de forma conservadora (Hz/kHz/MHz),
    - ticks legíveis (sem 0.01, 0.1, 1),
    - grid mais simétrica em décadas.

    Retorna:
        freq_factor  -> fator de conversão (1, 1e3, 1e6, ...)
        freq_unit    -> string da unidade ("Hz", "kHz", "MHz")
    """
    freqs = np.asarray(freqs)
    fmin = float(np.min(freqs))
    fmax = float(np.max(freqs))

    ax.set_xscale("log")

    # --- Escolha da unidade (mais conservadora) ---
    # Evita ir pra MHz muito cedo.
    if fmax >= 1e9:
        freq_unit = "GHz"
        freq_factor = 1e9
    elif fmax >= 5e6:
        freq_unit = "MHz"
        freq_factor = 1e6
    elif fmax >= 5e3:
        freq_unit = "kHz"
        freq_factor = 1e3
    else:
        freq_unit = "Hz"
        freq_factor = 1.0

    # --- Ajuste dos limites para ficar "bonito" na unidade escolhida ---
    scaled_min = fmin / freq_factor
    scaled_max = fmax / freq_factor

    dec_min = np.floor(np.log10(scaled_min))
    dec_max = np.ceil(np.log10(scaled_max))

    # volta para Hz
    nice_min = (10 ** dec_min) * freq_factor
    nice_max = (10 ** dec_max) * freq_factor
    ax.set_xlim(nice_min, nice_max)

    # --- Locators e formatters ---
    ax.xaxis.set_major_locator(LogLocator(base=10))
    ax.xaxis.set_minor_locator(LogLocator(base=10, subs=[2, 5]))

    def formatter(val, pos):
        scaled = val / freq_factor
        # evita label muito feio em float
        if scaled >= 10:
            return f"{scaled:.0f}"
        elif scaled >= 1:
            return f"{scaled:.2f}"
        elif scaled >= 0.1:
            return f"{scaled:.3f}"
        else:
            return f"{scaled:.4f}"

    ax.xaxis.set_major_formatter(FuncFormatter(formatter))
    ax.set_xlabel(f"Frequência ({freq_unit})")

    return freq_factor, freq_unit

def format_frequency_for_unit(value_hz: float, factor: float, unit: str) -> str:
    """
    Formata um valor de frequência em Hz usando o mesmo factor/unit
    retornados por setup_frequency_axis.

    Exemplo:
        value_hz = 50329.21, factor = 1e3, unit = "kHz"
        -> "50.33 kHz"
    """
    scaled = value_hz / factor
    if scaled >= 100:
        text = f"{scaled:.1f}"
    else:
        text = f"{scaled:.2f}"
    return f"{text} {unit}"