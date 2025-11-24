# core/rlc_theory.py
"""
Módulo: rlc_theory
==================

Implementa o modelo teórico de um circuito RLC série para estudo de ressonância.

Hipóteses adotadas
------------------
- Circuito RLC série ideal: um resistor R em série com um indutor L e um
  capacitor C.
- Análise em regime senoidal permanente (domínio da frequência, fasores).
- A grandeza de interesse é a tensão de saída V_out medida sobre o resistor R.
- A fonte de entrada é uma tensão senoidal de amplitude V_in (Vpp no software).
- Componentes lineares, sem efeitos parasitas, sem saturação magnética, etc.

Modelo de impedâncias
---------------------
- Impedância do resistor:        Z_R = R
- Impedância do indutor:         Z_L = j * ω * L
- Impedância do capacitor:       Z_C = 1 / (j * ω * C)
- Impedância equivalente série:  Z_eq = Z_R + Z_L - Z_C

A corrente no circuito é:

    I = V_in / Z_eq

e a tensão medida no resistor (saída do sistema) é:

    V_out = I * R

A função de transferência em módulo (ganho de tensão) é então:

    |H(jω)| = |V_out / V_in| = R / |Z_eq|

ou, desenvolvendo o módulo:

    |H(jω)| = R / sqrt( R^2 + (X_L - X_C)^2 )

onde:
- X_L = ω * L     (reatância indutiva)
- X_C = 1 / (ω*C) (reatância capacitiva)

Este módulo é exatamente o que é usado para gerar as curvas no simulador teórico
e para calcular a resposta nominal e com tolerâncias.
"""

import numpy as np


def get_transfer_function(f, R, L, C):
    """
    Calcula o módulo da função de transferência |H(jω)| = |V_out / V_in|
    para o circuito RLC série, considerando a tensão de saída medida
    no resistor R.

    Parâmetros
    ----------
    freqs : array-like
        Frequências em Hz nas quais o módulo da função de transferência
        será avaliado.
    R : float
        Resistência em ohms (Ω).
    L : float
        Indutância em henry (H).
    C : float
        Capacitância em farad (F).

    Retorno
    -------
    H_mag : numpy.ndarray
        Vetor com o ganho em módulo |H(jω)| = |V_out / V_in| para cada
        frequência especificada em `freqs`.

    Modelo utilizado
    ----------------
    Seja ω = 2πf, temos:

        X_L = ω * L
        X_C = 1 / (ω * C)

    A impedância equivalente em série é:

        Z_eq = R + j (X_L - X_C)

    O módulo da função de transferência é:

        |H(jω)| = R / |Z_eq|
                 = R / sqrt( R^2 + (X_L - X_C)^2 )

    Esta expressão é aplicada ponto a ponto para o vetor de frequências.
    """
    f = np.array(f, dtype=float)
    w = 2 * np.pi * f

    # Impedâncias reativas
    # Pequeno termo 1e-15 só para evitar divisão exata por zero.
    Xc = 1.0 / (w * C + 1e-15)
    Xl = w * L

    # Módulo da impedância equivalente
    Z = np.sqrt(R**2 + (Xl - Xc)**2)

    # Ganho em módulo no resistor
    return R / Z


def calculate_f1_f2(R, L, C):
    """
    Calcula as frequências de meia-potência f1 e f2
    para o circuito RLC série (modelo padrão).
    """
    alpha = R / (2.0 * L)
    omega0_sq = 1.0 / (L * C)

    omega1 = -alpha + np.sqrt(alpha**2 + omega0_sq)
    omega2 = alpha + np.sqrt(alpha**2 + omega0_sq)

    f1 = omega1 / (2.0 * np.pi)
    f2 = omega2 / (2.0 * np.pi)
    return f1, f2


def calculate_nominal_metrics(R_nom, L_nom, C_nom):
    """
    Calcula as principais métricas teóricas do circuito RLC série
    para um conjunto NOMINAL de componentes (sem tolerância):

    - Frequência de ressonância: f0
    - Fator de qualidade:        Q
    - Largura de banda:          BW
    - Frequências de meia-potência: f1, f2

    Parâmetros
    ----------
    R : float
        Resistência nominal em ohms (Ω).
    L : float
        Indutância nominal em henry (H).
    C : float
        Capacitância nominal em farad (F).

    Retorno
    -------
    metrics : dict
        Dicionário com as chaves:
            - 'f0' : frequência de ressonância (Hz)
            - 'Q'  : fator de qualidade (adimensional)
            - 'BW' : largura de banda (Hz)
            - 'f1' : frequência de meia-potência inferior (Hz)
            - 'f2' : frequência de meia-potência superior (Hz)

    Fórmulas utilizadas
    -------------------
    Frequência de ressonância (ressonância em RLC série):

        f0 = 1 / (2π * sqrt(L * C))

    Fator de qualidade:

        Q = (1 / R) * sqrt(L / C)

    As frequências de meia-potência f1 e f2 são obtidas a partir da
    equação do circuito amortecido, com:

        α = R / (2L)
        ω0² = 1 / (L*C)

        ω1 = -α + sqrt(α² + ω0²)
        ω2 =  α + sqrt(α² + ω0²)

        f1 = ω1 / (2π)
        f2 = ω2 / (2π)

    A largura de banda é definida por:

        BW = f2 - f1 = f0 / Q  (no modelo ideal)
    """

    w0 = 1.0 / np.sqrt(L_nom * C_nom)
    f0 = w0 / (2.0 * np.pi)
    Q = (1.0 / R_nom) * np.sqrt(L_nom / C_nom)
    f1_nom, f2_nom = calculate_f1_f2(R_nom, L_nom, C_nom)
    BW_nom = f2_nom - f1_nom

    return {
        "f0": f0,
        "Q": Q,
        "BW": BW_nom,
        "f1": f1_nom,
        "f2": f2_nom,
    }


def calculate_min_max_metrics(R_nom, L_nom, C_nom, tol_R, tol_L, tol_C):
    """
    Calcula faixas mínimas e máximas (min/max) das métricas teóricas
    f0, Q, BW, f1 e f2 considerando tolerâncias nos componentes.

    A abordagem utilizada é uma análise de "cantos" (corner analysis):
    são considerados todos os extremos de tolerância para R, L e C,
    e para cada combinação são calculadas as métricas do circuito.

    Parâmetros
    ----------
    R_nom : float
        Valor nominal do resistor (Ω).
    L_nom : float
        Valor nominal do indutor (H).
    C_nom : float
        Valor nominal do capacitor (F).
    tol_R : float
        Tolerância relativa do resistor (ex.: 0.05 para 5%).
    tol_L : float
        Tolerância relativa do indutor.
    tol_C : float
        Tolerância relativa do capacitor.

    Retorno
    -------
    ranges : dict
        Dicionário com as chaves:
            - 'f0' : (f0_min, f0_max)
            - 'Q'  : (Q_min,  Q_max)
            - 'BW' : (BW_min, BW_max)
            - 'f1' : (f1_min, f1_max)
            - 'f2' : (f2_min, f2_max)

        Cada par representa os valores mínimo e máximo encontrados
        ao percorrer todas as combinações extremas de tolerância:

            R ∈ { R_nom * (1 − tol_R), R_nom * (1 + tol_R) }
            L ∈ { L_nom * (1 − tol_L), L_nom * (1 + tol_L) }
            C ∈ { C_nom * (1 − tol_C), C_nom * (1 + tol_C) }

    Observação
    ----------
    Esse tipo de análise fornece uma estimativa conservadora da faixa
    de variação das métricas, compatível com o pior caso de tolerância
    dos componentes dentro das especificações.
    """

    metrics = {"f0": [], "Q": [], "BW": [], "f1": [], "f2": []}

    factors_r = [1.0 - tol_R, 1.0 + tol_R]
    factors_l = [1.0 - tol_L, 1.0 + tol_L]
    factors_c = [1.0 - tol_C, 1.0 + tol_C]

    for fr in factors_r:
        for fl in factors_l:
            for fc in factors_c:
                R = R_nom * fr
                L = L_nom * fl
                C = C_nom * fc

                w0 = 1.0 / np.sqrt(L * C)
                f0 = w0 / (2.0 * np.pi)
                Q = (1.0 / R) * np.sqrt(L / C)
                f1_val, f2_val = calculate_f1_f2(R, L, C)
                BW = f2_val - f1_val

                metrics["f0"].append(f0)
                metrics["Q"].append(Q)
                metrics["BW"].append(BW)
                metrics["f1"].append(f1_val)
                metrics["f2"].append(f2_val)

    return {
        "f0": (np.min(metrics["f0"]), np.max(metrics["f0"])),
        "Q": (np.min(metrics["Q"]), np.max(metrics["Q"])),
        "BW": (np.min(metrics["BW"]), np.max(metrics["BW"])),
        "f1": (np.min(metrics["f1"]), np.max(metrics["f1"])),
        "f2": (np.min(metrics["f2"]), np.max(metrics["f2"])),
    }

def _transfer_gain(freqs, R, L, C):
    """
    G(f) = Vout/Vin do circuito RLC série,
    assumindo medição no resistor.
    """
    w = 2.0 * np.pi * freqs
    # evita divisão por zero em f -> 0
    Xc = 1.0 / (w * C + 1e-30)
    Xl = w * L
    Z = np.sqrt(R**2 + (Xl - Xc)**2)
    return R / Z


def _compute_metrics(R, L, C):
    """
    Calcula métricas nominais do circuito:
    f0, Q, BW, f1, f2.
    """
    # Frequência de ressonância
    w0 = 1.0 / np.sqrt(L * C)
    f0 = w0 / (2.0 * np.pi)

    # Fator de qualidade
    Q = (1.0 / R) * np.sqrt(L / C)

    # f1 e f2 (meia-potência) via solução em frequência
    alpha = R / (2.0 * L)
    omega0_sq = 1.0 / (L * C)
    omega1 = -alpha + np.sqrt(alpha**2 + omega0_sq)
    omega2 = alpha + np.sqrt(alpha**2 + omega0_sq)
    f1 = omega1 / (2.0 * np.pi)
    f2 = omega2 / (2.0 * np.pi)

    BW = f2 - f1

    return {
        "f0": f0,
        "Q": Q,
        "BW": BW,
        "f1": f1,
        "f2": f2,
    }


def simulate_response_with_tolerances(
    R_nom,
    L_nom,
    C_nom,
    tol_R,
    tol_L,
    tol_C,
    V_in_plot,
    freq_min=None,
    freq_max=None,
    num_points=500,
):
    """
    Gera a resposta em frequência teórica de um circuito RLC série,
    considerando o conjunto nominal de componentes e a influência
    das tolerâncias de R, L e C.

    É a função de alto nível utilizada pelo simulador para construir:
    - Curva nominal V_out(f)
    - Envelope mínimo/máximo de V_out(f) devido às tolerâncias
    - Métricas nominais e faixas min/max de f0, Q, BW, f1, f2
    - Valor máximo global de V_out (útil para ajustar o eixo Y do gráfico)

    Parâmetros
    ----------
    R_nom : float
        Resistência nominal (Ω).
    L_nom : float
        Indutância nominal (H).
    C_nom : float
        Capacitância nominal (F).
    tol_R : float
        Tolerância relativa do resistor (ex.: 0.05 para 5%).
    tol_L : float
        Tolerância relativa do indutor.
    tol_C : float
        Tolerância relativa do capacitor.
    V_in_plot : float
        Amplitude de entrada em Vpp usada para escalar as curvas de
        tensão de saída V_out(f) no gráfico.
    n_points : int, opcional
        Número de pontos na malha de frequência (escala log).
        Default: 600.
    span_low_factor : float, opcional
        Fator que define o limite inferior do varrimento de frequência
        em relação a f0. A frequência mínima é:

            f_min = f0 * span_low_factor

        Default: 0.2 (20% de f0).
    span_high_factor : float, opcional
        Fator que define o limite superior do varrimento de frequência:

            f_max = f0 * span_high_factor

        Default: 5.0 (500% de f0).

    Retorno
    -------
    freqs : numpy.ndarray
        Vetor de frequências em Hz (escala logarítmica).
    nom_curve_Vout : numpy.ndarray
        Curva nominal de tensão de saída em Vpp para cada frequência.
    min_curve_Vout : numpy.ndarray
        Curva mínima de V_out(f) considerando as combinações extremas
        de tolerância (menor V_out obtida em cada frequência).
    max_curve_Vout : numpy.ndarray
        Curva máxima de V_out(f) considerando as combinações extremas
        de tolerância (maior V_out obtida em cada frequência).
    metrics_nom : dict
        Métricas nominais do circuito, conforme `calculate_nominal_metrics`.
    ranges : dict
        Faixas min/max das métricas, conforme `calculate_min_max_metrics`.
    Vout_max_global : float
        Maior valor de V_out encontrado em toda a banda e em todas as
        combinações de tolerância. Usado para dimensionar o eixo Y.

    Descrição do algoritmo
    ----------------------
    1. Calcula as métricas nominais (f0, Q, BW, f1, f2) a partir de
       R_nom, L_nom e C_nom.
    2. Gera um vetor logarítmico de frequências de f_min até f_max,
       usando f0 como referência e os fatores `span_low_factor` e
       `span_high_factor`.
    3. Calcula a função de transferência nominal |H(jω)| e obtém a
       curva nominal V_out_nom(f) = |H(jω)| * V_in_plot.
    4. Para cada combinação extrema de tolerância em R, L e C, calcula
       o módulo da função de transferência e obtém um conjunto de
       curvas V_out(f). A partir delas, extrai:
           - envelope mínimo: min_curve_Vout
           - envelope máximo: max_curve_Vout
    5. A partir de min/max das métricas (f0, Q, BW, f1, f2) em cada
       canto de tolerância, monta o dicionário `ranges`.
    6. Calcula Vout_max_global = max( max_curve_Vout ), usado para
       normalizar o eixo vertical na interface gráfica.
    """

    # 1) Métricas NOMINAIS (também serve para escolher faixa automática)
    metrics_nom = _compute_metrics(R_nom, L_nom, C_nom)
    f0 = metrics_nom["f0"]

    # 2) Define faixa de frequência efetiva
    if freq_min is None or freq_max is None:
        # Faixa automática: por padrão uma década abaixo/acima de f0
        freq_min_eff = f0 / 10.0 if f0 > 0 else 10.0
        freq_max_eff = f0 * 10.0 if f0 > 0 else 1e6
    else:
        freq_min_eff = float(freq_min)
        freq_max_eff = float(freq_max)

        # Sanidade básica
        if freq_min_eff <= 0:
            freq_min_eff = f0 / 10.0 if f0 > 0 else 10.0
        if freq_max_eff <= freq_min_eff:
            freq_max_eff = freq_min_eff * 10.0

    freqs = np.logspace(
        np.log10(freq_min_eff),
        np.log10(freq_max_eff),
        int(num_points),
    )

    # 3) Curva nominal
    gain_nom = _transfer_gain(freqs, R_nom, L_nom, C_nom)
    nom_curve_Vout = gain_nom * V_in_plot

    # Inicializa min/max com a curva nominal
    min_curve_Vout = nom_curve_Vout.copy()
    max_curve_Vout = nom_curve_Vout.copy()

    # 4) Varredura de tolerâncias (R, L, C nos extremos)
    metrics_lists = {k: [] for k in metrics_nom.keys()}

    factors_r = [1.0 - tol_R, 1.0 + tol_R]
    factors_l = [1.0 - tol_L, 1.0 + tol_L]
    factors_c = [1.0 - tol_C, 1.0 + tol_C]

    for fr in factors_r:
        for fl in factors_l:
            for fc in factors_c:
                R = R_nom * fr
                L = L_nom * fl
                C = C_nom * fc

                # Proteção básica contra valores degenerados
                if R <= 0 or L <= 0 or C <= 0:
                    continue

                # Métricas para essa combinação
                m = _compute_metrics(R, L, C)
                for k in metrics_lists.keys():
                    metrics_lists[k].append(m[k])

                # Curva para essa combinação extrema
                gain_ext = _transfer_gain(freqs, R, L, C)
                vout_ext = gain_ext * V_in_plot

                min_curve_Vout = np.minimum(min_curve_Vout, vout_ext)
                max_curve_Vout = np.maximum(max_curve_Vout, vout_ext)

    # 5) Ranges min/max das métricas
    ranges = {}
    for k, arr in metrics_lists.items():
        if len(arr) == 0:
            # Se nada foi acumulado (caso extremo), usa o nominal
            ranges[k] = (metrics_nom[k], metrics_nom[k])
        else:
            ranges[k] = (float(np.min(arr)), float(np.max(arr)))

    # 6) Máximo global da curva (para auto-escala no eixo Y)
    Vout_max_global = float(np.max(max_curve_Vout)) if max_curve_Vout.size > 0 else 0.0

    return (
        freqs,
        nom_curve_Vout,
        min_curve_Vout,
        max_curve_Vout,
        metrics_nom,
        ranges,
        Vout_max_global,
    )

# ============================================================
# CÁLCULO REVERSO: PROJETAR L E C PARA UM f0 ALVO
# ============================================================

def design_rlc_for_target_f0(
    target_f0_hz,
    R_fixed=None,
    L_candidates_h=None,
    C_candidates_f=None,
    max_results=20,
    max_error_pct=None,
):
    """
    Calcula combinações de L e C que aproximam uma frequência de
    ressonância alvo f0, usando listas de valores "comerciais".

    Parâmetros
    ----------
    target_f0_hz : float
        Frequência de ressonância desejada, em Hz.
    R_fixed : float ou None
        Valor de R (Ω) usado apenas para cálculo de Q. Se None, Q fica None.
    L_candidates_h : iterável ou None
        Lista/array de valores possíveis de indutância em Henry (H).
        Se None, é usada uma grade padrão estilo E12 em algumas décadas.
    C_candidates_f : iterável ou None
        Lista/array de valores possíveis de capacitância em Farad (F).
        Se None, é usada uma grade padrão estilo E12 em algumas décadas.
    max_results : int
        Número máximo de combinações a retornar (ordenadas pelo erro relativo em f0).
    max_error_pct : float ou None
        Se fornecido, descarta combinações cujo erro relativo em f0 seja maior
        que esse limite (em %).

    Retorno
    -------
    results : list[dict]
        Lista de dicionários, cada um com chaves:
            - 'L_H'        : valor de L em Henry
            - 'C_F'        : valor de C em Farad
            - 'f0_calc_Hz' : f0 calculado para essa combinação
            - 'error_pct'  : erro relativo em %
            - 'Q'          : fator de qualidade (ou None se R_fixed=None)
    """
    target_f0_hz = float(target_f0_hz)
    if target_f0_hz <= 0:
        raise ValueError("target_f0_hz deve ser > 0.")

    # ------------------------------
    # 1) Gera listas padrão (E12-like) se não forem fornecidas
    # ------------------------------
    E12 = np.array([1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2])

    if L_candidates_h is None:
        # Faixa típica: 0.1 mH ... 100 mH
        decades_L = np.array([-4, -3, -2])  # 10^-4, 10^-3, 10^-2 H
        vals_L = []
        for d in decades_L:
            vals_L.extend(E12 * (10.0 ** d))
        L_candidates_h = np.array(vals_L, dtype=float)

    if C_candidates_f is None:
        # Faixa típica: 100 pF ... 1 µF
        decades_C = np.array([-10, -9, -8, -7, -6])  # 10^-10 ... 10^-6 F
        vals_C = []
        for d in decades_C:
            vals_C.extend(E12 * (10.0 ** d))
        C_candidates_f = np.array(vals_C, dtype=float)

    L_candidates_h = np.asarray(L_candidates_h, dtype=float)
    C_candidates_f = np.asarray(C_candidates_f, dtype=float)

    # Remove valores não físicos
    L_candidates_h = L_candidates_h[L_candidates_h > 0]
    C_candidates_f = C_candidates_f[C_candidates_f > 0]

    if L_candidates_h.size == 0 or C_candidates_f.size == 0:
        raise ValueError("Listas de candidatos L/C vazias após filtragem.")

    # ------------------------------
    # 2) Varre todas as combinações
    # ------------------------------
    results = []
    for L in L_candidates_h:
        for C in C_candidates_f:
            try:
                f0_calc = 1.0 / (2.0 * np.pi * np.sqrt(L * C))
            except FloatingPointError:
                continue

            if not np.isfinite(f0_calc) or f0_calc <= 0:
                continue

            error_pct = abs(f0_calc - target_f0_hz) / target_f0_hz * 100.0

            if (max_error_pct is not None) and (error_pct > max_error_pct):
                continue

            if R_fixed is not None and R_fixed > 0:
                Q = (1.0 / R_fixed) * np.sqrt(L / C)
            else:
                Q = None

            results.append(
                {
                    "L_H": float(L),
                    "C_F": float(C),
                    "f0_calc_Hz": float(f0_calc),
                    "error_pct": float(error_pct),
                    "Q": None if Q is None else float(Q),
                }
            )

    # ------------------------------
    # 3) Ordena por erro (asc) e depois por Q (desc)
    # ------------------------------
    if not results:
        return []

    def sort_key(d):
        q = d["Q"] if d["Q"] is not None else 0.0
        return (d["error_pct"], -q)

    results.sort(key=sort_key)
    return results[:max_results]