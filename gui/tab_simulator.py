import customtkinter as ctk
import numpy as np
import matplotlib.pyplot as plt
import os
from tkinter import filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import tkinter.messagebox as msgbox

from gui.ui_helpers import ToolTip
from gui.plot_utils import setup_frequency_axis, format_frequency_for_unit
from core.rlc_theory import simulate_response_with_tolerances, design_rlc_for_target_f0
from core.units import (
    get_multiplier,
    RESISTOR_UNITS,
    INDUCTOR_UNITS,
    CAPACITOR_UNITS,
    FREQUENCY_UNITS,
)

# Opções de unidade para faixa de frequência (derivadas do units.py)
FREQ_OPTIONS = list(FREQUENCY_UNITS.keys())


class TabSimulator:
    LATEX_F0 = r'$f_0 = \frac{1}{2\pi\sqrt{LC}}$'
    LATEX_Q = r'$Q = \frac{1}{R}\sqrt{\frac{L}{C}}$'
    LATEX_BW = r'$\Delta f = f_2 - f_1 = \frac{f_0}{Q}$'

    def __init__(self, parent_frame, data_manager):
        self.parent = parent_frame
        self.data_manager = data_manager

        # Configurações padrão iniciais do simulador
        self.default_config = {
            "R": {"value": 330.0, "unit": "Ω",  "tol": 5.0},
            "L": {"value": 1.0,   "unit": "mH", "tol": 10.0},
            "C": {"value": 10.0,  "unit": "nF", "tol": 20.0},
        }
        self.default_vin = 2.0

        # Referências de unidades nominais
        self.units_refs = {}

        # Sliders e ranges dinâmicos
        self.sliders = {}                  # 'R'/'L'/'C' -> slider
        self.effective_labels = {}         # 'R'/'L'/'C' -> label "Atual: ..."
        self.center_values_SI = {}         # centro do range em SI (Ω, H, F)
        self.last_center_entry_text = {}   # texto do entry quando o center foi definido

        # Range em torno do centro (center/FACTOR_BELOW .. center*FACTOR_ABOVE)
        self.RANGE_FACTOR_BELOW = 10.0
        self.RANGE_FACTOR_ABOVE = 10.0

        # Métricas nominais auxiliares
        self.f1_nom = 0.0
        self.f2_nom = 0.0

        # Últimas métricas nominais e faixa de frequência usada
        self.last_metrics_nom = None
        self.last_freq_min_Hz_used = None
        self.last_freq_max_Hz_used = None

        # Última curva simulada (para salvar pontos teóricos)
        self.last_freqs = None
        self.last_nom_curve_Vout = None
        self.last_V_in_plot = None

        # Flags de visualização
        self.show_tolerance = ctk.BooleanVar(value=True)
        self.show_f0 = ctk.BooleanVar(value=True)
        self.show_f1f2 = ctk.BooleanVar(value=True)

        # Controle de faixa de frequência (eixo X / simulação)
        self.freq_auto = ctk.BooleanVar(value=True)  # True = range automático
        self.freq_min_entry = None
        self.freq_min_unit = None
        self.freq_max_entry = None
        self.freq_max_unit = None

        self.parent.grid_columnconfigure(1, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(
            self.parent, width=300, corner_radius=0, label_text="Configuração"
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.view_area = ctk.CTkFrame(self.parent, corner_radius=10)
        self.view_area.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        self._build_controls()
        self._init_plot()

        # Aplica os padrões na primeira carga (centraliza sliders e plota)
        self._apply_default_config(run_sim=True)

    # ==================== PLOT E CARDS ====================

    def _init_plot(self):

        plt.style.use('dark_background')
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.fig.patch.set_facecolor('#242424')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#242424')

        # ====== CARDS DE RESULTADOS ======
        self.metrics_frame = ctk.CTkFrame(
            self.view_area,
            fg_color=("#202020", "#202020"),
            corner_radius=8,
        )
        self.metrics_frame.pack(side="top", fill="x", padx=10, pady=(10, 0))

        # 4 colunas com mesmo peso e mesmo “grupo” de largura
        self.metrics_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="metrics")

        # ---- Card f0 ----
        card_f0 = ctk.CTkFrame(
            self.metrics_frame,
            fg_color=("#2E2E2E", "#2E2E2E"),
            corner_radius=8,
        )
        card_f0.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        card_f0.grid_columnconfigure(0, weight=1)

        header_f0 = ctk.CTkFrame(card_f0, fg_color="transparent")
        header_f0.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        header_f0.grid_columnconfigure(0, weight=1)

        title_f0 = ctk.CTkLabel(
            header_f0,
            text="Frequência de Ressonância (f₀)",
            font=("Arial", 12, "bold"),
        )
        title_f0.grid(row=0, column=0, sticky="w")

        info_f0 = ctk.CTkLabel(
            header_f0,
            text="i",
            width=20,
            height=20,
            corner_radius=10,
            fg_color="#444444",
            font=("Arial", 13, "bold"),
        )
        info_f0.grid(row=0, column=1, padx=(6, 0))
        ToolTip(info_f0, "Clique aqui para ver detalhes.")
        info_f0.bind("<Button-1>", lambda e: self._open_info_popup("f0"))

        self.lbl_f0_nom = ctk.CTkLabel(
            card_f0,
            text="---",
            font=("Arial", 18, "bold"),
            text_color="#4da6ff",
        )
        self.lbl_f0_nom.grid(row=1, column=0, pady=(6, 4), padx=10, sticky="n")

        chk_f0 = ctk.CTkCheckBox(
            card_f0,
            text="Mostrar f₀",
            variable=self.show_f0,
            command=self.run_simulation,
            font=("Arial", 11),
        )
        chk_f0.grid(row=2, column=0, pady=(0, 8), padx=10, sticky="w")

        # ---- Card f1 / f2 ----
        card_f1f2 = ctk.CTkFrame(
            self.metrics_frame,
            fg_color=("#2E2E2E", "#2E2E2E"),
            corner_radius=8,
        )
        card_f1f2.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        card_f1f2.grid_columnconfigure(0, weight=1)

        header_f1f2 = ctk.CTkFrame(card_f1f2, fg_color="transparent")
        header_f1f2.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        header_f1f2.grid_columnconfigure(0, weight=1)

        title_f1f2 = ctk.CTkLabel(
            header_f1f2,
            text="Frequências de Meia Potência (f₁, f₂)",
            font=("Arial", 12, "bold"),
        )
        title_f1f2.grid(row=0, column=0, sticky="w")

        info_f1f2 = ctk.CTkLabel(
            header_f1f2,
            text="i",
            width=20,
            height=20,
            corner_radius=10,
            fg_color="#444444",
            font=("Arial", 13, "bold"),
        )
        info_f1f2.grid(row=0, column=1, padx=(6, 0))
        ToolTip(
            info_f1f2,
            "f₁ e f₂: frequências de meia potência (ganho ≈ 0,707 do máximo).\n"
            "BW = f₂ - f₁.",
        )

        # valor central do card (texto f₁ e f₂)
        self.lbl_f1f2 = ctk.CTkLabel(
            card_f1f2,
            text="---",
            font=("Arial", 16, "bold"),
            text_color="#4da6ff",
        )
        self.lbl_f1f2.grid(row=1, column=0, pady=(6, 4), padx=10, sticky="n")

        # checkbox alinhado na MESMA linha (row=2) dos outros cards
        chk_f1f2 = ctk.CTkCheckBox(
            card_f1f2,
            text="Mostrar f₁ / f₂",
            variable=self.show_f1f2,
            command=self.run_simulation,
            font=("Arial", 11),
        )
        chk_f1f2.grid(row=2, column=0, pady=(0, 8), padx=10, sticky="w")

        # ---- Card Q ----
        card_q = ctk.CTkFrame(
            self.metrics_frame,
            fg_color=("#2E2E2E", "#2E2E2E"),
            corner_radius=8,
        )
        card_q.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        card_q.grid_columnconfigure(0, weight=1)

        header_q = ctk.CTkFrame(card_q, fg_color="transparent")
        header_q.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        header_q.grid_columnconfigure(0, weight=1)

        title_q = ctk.CTkLabel(
            header_q,
            text="Fator de Qualidade (Q)",
            font=("Arial", 12, "bold"),
        )
        title_q.grid(row=0, column=0, sticky="w")

        info_q = ctk.CTkLabel(
            header_q,
            text="i",
            width=20,
            height=20,
            corner_radius=10,
            fg_color="#444444",
            font=("Arial", 13, "bold"),
        )
        info_q.grid(row=0, column=1, padx=(6, 0))
        # ToolTip(info_q, "…")  # já tinha

        self.lbl_q_nom = ctk.CTkLabel(
            card_q,
            text="---",
            font=("Arial", 18, "bold"),
            text_color="#4da6ff",
        )
        self.lbl_q_nom.grid(row=1, column=0, pady=(6, 4), padx=10, sticky="n")

        # ---- Card BW ----
        card_bw = ctk.CTkFrame(
            self.metrics_frame,
            fg_color=("#2E2E2E", "#2E2E2E"),
            corner_radius=8,
        )
        card_bw.grid(row=0, column=3, sticky="nsew", padx=5, pady=5)
        card_bw.grid_columnconfigure(0, weight=1)

        header_bw = ctk.CTkFrame(card_bw, fg_color="transparent")
        header_bw.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        header_bw.grid_columnconfigure(0, weight=1)

        title_bw = ctk.CTkLabel(
            header_bw,
            text="Largura de Banda (BW)",
            font=("Arial", 12, "bold"),
        )
        title_bw.grid(row=0, column=0, sticky="w")

        info_bw = ctk.CTkLabel(
            header_bw,
            text="i",
            width=20,
            height=20,
            corner_radius=10,
            fg_color="#444444",
            font=("Arial", 13, "bold"),
        )
        info_bw.grid(row=0, column=1, padx=(6, 0))
        ToolTip(info_bw, "Clique aqui para ver detalhes.")
        info_bw.bind("<Button-1>", lambda e: self._open_info_popup("BW"))

        self.lbl_bw_nom = ctk.CTkLabel(
            card_bw,
            text="---",
            font=("Arial", 18, "bold"),
            text_color="#4da6ff",
        )
        self.lbl_bw_nom.grid(row=1, column=0, pady=(6, 8), padx=10, sticky="n")

        # ====== FIGURA ======
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.view_area)
        self.canvas.draw()
        self.toolbar = NavigationToolbar2Tk(
            self.canvas, self.view_area, pack_toolbar=False
        )
        self.toolbar.update()

        self.toolbar.pack(side='bottom', fill='x', padx=10, pady=5)
        self.canvas.get_tk_widget().pack(
            side="top", fill="both", expand=True, padx=10, pady=(5, 10)
        )

    # ==================== CONTROLES / SLIDERS ====================

    def _build_controls(self):

        def create_param_input(key, label_text, default_val, default_tol,
                              unit_options, default_unit):
            """
            Para cada componente (R, L, C) cria:
            - entrada nominal + unidade + tolerância
            - botão OK para definir esse valor como centro do slider
            - slider que varre um range em torno do centro (/10 .. ×10)
            - label com o valor efetivo atual (em unidade nominal)
            """
            container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
            container.pack(fill="x", padx=5, pady=5)

            ctk.CTkLabel(
                container,
                text=label_text,
                anchor="w",
                font=("Arial", 12, "bold")
            ).pack(fill="x")

            # Linha: valor nominal + unidade + tolerância + botão OK
            row_nom = ctk.CTkFrame(container, fg_color="transparent")
            row_nom.pack(fill="x", pady=2)

            entry_val = ctk.CTkEntry(row_nom, width=70)
            entry_val.pack(side="left", padx=(0, 2))
            entry_val.insert(0, str(default_val))

            combo_unit = ctk.CTkOptionMenu(
                row_nom,
                values=unit_options,
                width=60,
            )
            combo_unit.pack(side="left", padx=2)
            combo_unit.set(default_unit)
            self.units_refs[key] = combo_unit

            ctk.CTkLabel(row_nom, text="±", width=10).pack(side="left")
            entry_tol = ctk.CTkEntry(row_nom, width=40)
            entry_tol.pack(side="left", padx=2)
            entry_tol.insert(0, str(default_tol))
            ctk.CTkLabel(row_nom, text="%", width=10).pack(side="left")

            # Botão OK para “fixar” o centro do range do slider
            btn_ok = ctk.CTkButton(
                row_nom,
                text="OK",
                width=40,
                fg_color="#555555",
                command=lambda k=key: self._recenter_range_from_entry(k, True),
            )
            btn_ok.pack(side="left", padx=(6, 0))

            # Linha: slider + label de valor efetivo
            slider_row = ctk.CTkFrame(container, fg_color="transparent")
            slider_row.pack(fill="x", pady=(4, 0))

            slider = ctk.CTkSlider(
                slider_row,
                from_=0.0,
                to=1.0,
                number_of_steps=100,
                command=lambda v, k=key: self._on_range_slider_change(k, v),
            )
            slider.pack(side="left", fill="x", expand=True, padx=(0, 5))
            slider.set(0.5)  # meio termo

            lbl_eff = ctk.CTkLabel(
                slider_row,
                text="Atual: --",
                width=140,
                anchor="e",
                font=("Arial", 10),
            )
            lbl_eff.pack(side="right")

            self.sliders[key] = slider
            self.effective_labels[key] = lbl_eff

            return entry_val, entry_tol

        # Entradas com slider por componente
        self.ent_r, self.ent_r_tol = create_param_input(
            "R", "Resistor", 330, 5, list(RESISTOR_UNITS.keys()), "Ω"
        )
        self.ent_l, self.ent_l_tol = create_param_input(
            "L", "Indutor", 1, 10, list(INDUCTOR_UNITS.keys()), "mH"
        )
        self.ent_c, self.ent_c_tol = create_param_input(
            "C", "Capacitor", 10, 20, list(CAPACITOR_UNITS.keys()), "nF"
        )

        # Checkbox de tolerância abaixo dos componentes
        self.chk_tolerance_sidebar = ctk.CTkCheckBox(
            self.sidebar,
            text="Mostrar banda de tolerância no gráfico",
            variable=self.show_tolerance,
            command=self.run_simulation,
            font=("Arial", 11),
        )
        self.chk_tolerance_sidebar.pack(fill="x", padx=20, pady=(5, 5))

        # Vin
        ctk.CTkLabel(
            self.sidebar,
            text="Amplitude de Entrada (Vpp):",
            anchor="w",
            font=("Arial", 12, "bold"),
        ).pack(fill="x", padx=20, pady=(10, 0))

        self.ent_vin = ctk.CTkEntry(self.sidebar)
        self.ent_vin.pack(fill="x", padx=20)
        self.ent_vin.insert(0, "2.0")

        # ================== CONTROLE DE FAIXA DE FREQUÊNCIA ==================
        freq_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        freq_frame.pack(fill="x", padx=15, pady=(10, 0))

        ctk.CTkLabel(
            freq_frame,
            text="Faixa de Frequência (curva simulada):",
            anchor="w",
            font=("Arial", 12, "bold"),
        ).pack(fill="x", pady=(0, 4))

        # Modo automático / manual
        chk_auto = ctk.CTkCheckBox(
            freq_frame,
            text="Ajuste automático em função do circuito",
            variable=self.freq_auto,
            command=self._on_freq_mode_change,
            font=("Arial", 10),
        )
        chk_auto.pack(fill="x", pady=(0, 6))
        self.freq_auto.set(True)

        # Linha f_min
        row_fmin = ctk.CTkFrame(freq_frame, fg_color="transparent")
        row_fmin.pack(fill="x", pady=2)

        ctk.CTkLabel(
            row_fmin,
            text="f_min:",
            width=45,
            anchor="w",
            font=("Arial", 10),
        ).pack(side="left")

        self.freq_min_entry = ctk.CTkEntry(row_fmin, width=70)
        self.freq_min_entry.pack(side="left", padx=(0, 4))
        self.freq_min_entry.insert(0, "10")

        self.freq_min_unit = ctk.CTkOptionMenu(
            row_fmin,
            values=FREQ_OPTIONS,
            width=70,
        )
        self.freq_min_unit.pack(side="left")
        self.freq_min_unit.set("Hz")

        # Linha f_max
        row_fmax = ctk.CTkFrame(freq_frame, fg_color="transparent")
        row_fmax.pack(fill="x", pady=2)

        ctk.CTkLabel(
            row_fmax,
            text="f_max:",
            width=45,
            anchor="w",
            font=("Arial", 10),
        ).pack(side="left")

        self.freq_max_entry = ctk.CTkEntry(row_fmax, width=70)
        self.freq_max_entry.pack(side="left", padx=(0, 4))
        self.freq_max_entry.insert(0, "100")

        self.freq_max_unit = ctk.CTkOptionMenu(
            row_fmax,
            values=FREQ_OPTIONS,
            width=70,
        )
        self.freq_max_unit.pack(side="left")
        self.freq_max_unit.set("kHz")

        # Inicialmente desabilita os inputs (modo auto ligado)
        self._set_freq_inputs_state()

        # Botão SIMULAR
        self.btn_sim = ctk.CTkButton(
            self.sidebar,
            text="SIMULAR CURVA",
            command=self.run_simulation,
            fg_color="#00C853",
            text_color="black",
            font=("Arial", 12, "bold"),
        )
        self.btn_sim.pack(pady=20, padx=10, fill="x")

        # Botão Redefinir para padrão
        def on_reset_defaults():
            if msgbox.askyesno(
                "Redefinir parâmetros",
                "Deseja realmente redefinir R, L, C, tolerâncias e Vin para os valores padrão?",
            ):
                self._apply_default_config(run_sim=True)

        self.btn_reset_defaults = ctk.CTkButton(
            self.sidebar,
            text="REDEFINIR PARA PADRÃO",
            command=on_reset_defaults,
            fg_color="#444444",
            text_color="white",
            font=("Arial", 11, "bold"),
        )
        self.btn_reset_defaults.pack(pady=5, padx=10, fill="x")

        # Botão Salvar Parâmetros Teóricos
        self.btn_save_theory = ctk.CTkButton(
            self.sidebar,
            text="SALVAR TEÓRICO",
            command=self.save_theory_gui,
            fg_color="#0055A4",
            state="disabled",
        )
        self.btn_save_theory.pack(pady=5, padx=10, fill="x")

        # ================== CALCULADORA DE PROJETO INVERSO ==================
        btn_rev = ctk.CTkButton(
            self.sidebar,
            text="CALCULADORA f₀ (PROJETO INVERSO)",
            command=self.open_reverse_calculator_popup,
            fg_color="#7B1FA2",
            text_color="white",
            font=("Arial", 11, "bold"),
        )
        btn_rev.pack(fill="x", padx=15, pady=(5, 10))

    # ==================== HELPERS DE VALIDAÇÃO E RANGE ====================

    def _parse_float_entry(self, entry: ctk.CTkEntry, field_name: str, show_errors: bool = True):
        """
        Converte o conteúdo de um CTkEntry em float.
        Se falhar, pode mostrar erro (show_errors=True) e retorna None.
        """
        try:
            text = entry.get().strip().replace(",", ".")
            value = float(text)
            return value
        except ValueError:
            if show_errors:
                msgbox.showerror(
                    "Valor inválido",
                    f"O campo '{field_name}' deve ser um número válido.\n"
                    f"Valor atual: '{entry.get()}'"
                )
            return None

    def _apply_default_config(self, run_sim: bool = True):
        """
        Aplica os valores padrão de R, L, C, tolerâncias e Vin.
        Recentraliza os sliders em torno desses valores
        e atualiza os labels 'Atual: ...'.
        """
        # R, L, C
        for key, cfg in self.default_config.items():
            if key == "R":
                entry = self.ent_r
                entry_tol = self.ent_r_tol
            elif key == "L":
                entry = self.ent_l
                entry_tol = self.ent_l_tol
            elif key == "C":
                entry = self.ent_c
                entry_tol = self.ent_c_tol
            else:
                continue

            # Valor nominal
            entry.delete(0, "end")
            entry.insert(0, str(cfg["value"]))

            # Tolerância
            entry_tol.delete(0, "end")
            entry_tol.insert(0, str(cfg["tol"]))

            # Unidade
            if key in self.units_refs:
                self.units_refs[key].set(cfg["unit"])

            # Reseta centro para este novo valor
            if key in self.center_values_SI:
                del self.center_values_SI[key]
            self.last_center_entry_text[key] = entry.get().strip()
            self._recenter_range_from_entry(key, show_errors=False)

        # Vin
        self.ent_vin.delete(0, "end")
        self.ent_vin.insert(0, str(self.default_vin))

        # Banda de tolerância ligada por padrão
        self.show_tolerance.set(True)

        # Roda uma simulação rápida se pedido
        if run_sim:
            self.run_simulation(show_errors=False)

    def _set_freq_inputs_state(self):
        """Habilita ou desabilita os inputs de f_min/f_max conforme modo auto/manual."""
        state = "disabled" if self.freq_auto.get() else "normal"
        widgets = [
            self.freq_min_entry,
            self.freq_min_unit,
            self.freq_max_entry,
            self.freq_max_unit,
        ]
        for w in widgets:
            if w is not None:
                w.configure(state=state)

    def _on_freq_mode_change(self):
        """Callback quando alterna auto/manual da faixa de frequência."""
        self._set_freq_inputs_state()
        self.run_simulation(show_errors=False)

    def _ensure_center_initialized(self, key: str, show_errors: bool = False):
        """
        Garante que existe um center_values_SI[key] definido.
        Se ainda não houver, usa o valor do entry correspondente
        como centro inicial.

        Não mexe na posição do slider aqui.
        Slider só é recentrado em:
        - _recenter_range_from_entry (botão OK ou reset),
        - _apply_default_config.
        """
        if key in self.center_values_SI:
            return

        entry_map = {"R": self.ent_r, "L": self.ent_l, "C": self.ent_c}
        if key not in entry_map or key not in self.units_refs:
            return

        entry = entry_map[key]
        val = self._parse_float_entry(entry, f"Componente {key}", show_errors)
        if val is None:
            return

        unit = self.units_refs[key].get()
        center_SI = val * get_multiplier(unit)

        self.center_values_SI[key] = center_SI
        self.last_center_entry_text[key] = entry.get().strip()

        # Atualiza label com o centro atual
        self._update_effective_label(key, center_SI)

    def _recenter_range_from_entry(self, key: str, show_errors: bool = True):
        """
        Botão OK (ou SIMULAR CURVA) chamam isso:
        - Lê o valor do input correspondente,
        - Converte para SI,
        - Define como novo centro do range do slider,
        - Centraliza o slider,
        - Atualiza o label 'Atual: ...'.
        """
        entry_map = {"R": self.ent_r, "L": self.ent_l, "C": self.ent_c}
        if key not in entry_map or key not in self.units_refs:
            return

        entry = entry_map[key]
        val = self._parse_float_entry(entry, f"Componente {key}", show_errors)
        if val is None:
            return

        unit = self.units_refs[key].get()
        center_SI = val * get_multiplier(unit)

        self.center_values_SI[key] = center_SI
        self.last_center_entry_text[key] = entry.get().strip()

        if key in self.sliders:
            self.sliders[key].set(0.5)

        self._update_effective_label(key, center_SI)

        # Se veio de clique manual no OK, já dispara uma simulação rápida
        if show_errors:
            self.run_simulation(show_errors=False)

    def _compute_effective_component_value(self, key: str):
        """
        Retorna o valor efetivo do componente (em SI: Ω, H, F)
        com base no centro e na posição do slider.

        Range multiplicativo:
            fator_min = 1 / RANGE_FACTOR_BELOW   (ex.: 0.1)
            fator_max = RANGE_FACTOR_ABOVE       (ex.: 10)

        Interpolação é feita em escala log:

            pos = 0   -> center * fator_min  (center/10)
            pos = 0.5 -> center * 1          (center)
            pos = 1   -> center * fator_max  (center*10)
        """
        import math

        self._ensure_center_initialized(key, show_errors=False)
        if key not in self.center_values_SI or key not in self.sliders:
            return None

        center = float(self.center_values_SI[key])

        fmin = 1.0 / float(self.RANGE_FACTOR_BELOW)
        fmax = float(self.RANGE_FACTOR_ABOVE)

        pos = float(self.sliders[key].get())  # 0..1

        # interpolação log10 nos fatores
        log_fmin = math.log10(fmin)
        log_fmax = math.log10(fmax)
        log_f = log_fmin + pos * (log_fmax - log_fmin)
        factor = 10 ** log_f

        val_SI = center * factor
        return val_SI

    def _update_effective_label(self, key: str, value_SI: float):
        """
        Atualiza o label 'Atual: ...' convertendo o valor em SI para a
        unidade nominal selecionada (GUI).
        """
        if key not in self.effective_labels or key not in self.units_refs:
            return

        unit_display = self.units_refs[key].get()
        factor = get_multiplier(unit_display)
        value_disp = value_SI / factor
        text = f"Atual: {value_disp:.3g} {unit_display}"
        self.effective_labels[key].configure(text=text)

    def _on_range_slider_change(self, key: str, slider_pos: float):
        """
        Callback do slider: ajusta o valor efetivo em torno do centro,
        atualiza o label e recalcula a simulação sem popups.
        """
        val_SI = self._compute_effective_component_value(key)
        if val_SI is not None:
            self._update_effective_label(key, val_SI)
        else:
            if key in self.effective_labels:
                self.effective_labels[key].configure(text="Atual: --")

        self.run_simulation(show_errors=False)

    def _format_freq_eng(self, f_hz: float) -> str:
        """
        Formata frequência em unidades de engenharia fixas,
        independentes do eixo do gráfico.
        """
        if f_hz is None or f_hz <= 0:
            return "---"

        f = abs(f_hz)
        if f >= 1e9:
            return f"{f_hz / 1e9:.2f} GHz"
        elif f >= 1e6:
            return f"{f_hz / 1e6:.2f} MHz"
        elif f >= 1e3:
            return f"{f_hz / 1e3:.2f} kHz"
        else:
            return f"{f_hz:.2f} Hz"
        
    def _apply_reverse_result(self, L_H: float, C_F: float):
        """
        Aplica uma combinação L/C vinda do cálculo reverso:
        - converte para as unidades atuais dos inputs,
        - atualiza entries de L e C,
        - recentraliza sliders em torno desses valores,
        - roda simulação.
        """
        # L
        L_unit = self.units_refs["L"].get()
        L_factor = get_multiplier(L_unit)
        L_display = L_H / L_factor

        self.ent_l.delete(0, "end")
        self.ent_l.insert(0, f"{L_display:.6g}")

        # C
        C_unit = self.units_refs["C"].get()
        C_factor = get_multiplier(C_unit)
        C_display = C_F / C_factor

        self.ent_c.delete(0, "end")
        self.ent_c.insert(0, f"{C_display:.6g}")

        # Recentraliza slider em torno desses novos valores (sem popup)
        self._recenter_range_from_entry("L", show_errors=False)
        self._recenter_range_from_entry("C", show_errors=False)

        # Roda simulação com novos componentes
        self.run_simulation(show_errors=False)

    def open_reverse_calculator_popup(self):
        """
        Abre a calculadora de projeto inverso em um único popup:
        - define f0 alvo e componentes fixos;
        - botão CALCULAR gera combinações;
        - resultados aparecem na própria janela;
        - cada linha tem botão 'Aplicar' que injeta L/C no simulador.
        """
        popup = ctk.CTkToplevel(self.parent)
        popup.title("Calculadora de Projeto Inverso (f₀ alvo)")
        popup.geometry("900x600")
        popup.resizable(True, True)

        parent_win = self.parent.winfo_toplevel()
        popup.transient(parent_win)
        popup.lift()
        popup.grab_set()
        popup.focus_force()

        root_frame = ctk.CTkFrame(popup, corner_radius=8)
        root_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # ================= HEADER =================
        header = ctk.CTkFrame(root_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        title_lbl = ctk.CTkLabel(
            header,
            text="Calculadora de Projeto Inverso (RLC série)",
            font=("Arial", 16, "bold"),
            anchor="w",
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        info_btn = ctk.CTkLabel(
            header,
            text="i",
            width=24,
            height=24,
            corner_radius=12,
            fg_color="#444444",
            font=("Arial", 14, "bold"),
        )
        info_btn.grid(row=0, column=1, padx=(8, 0))
        ToolTip(info_btn, "Clique para ver como esta calculadora funciona.")
        info_btn.bind("<Button-1>", lambda e: self._open_reverse_design_info_popup())

        # ================= ÁREA DE ENTRADA =================
        input_frame = ctk.CTkFrame(root_frame, corner_radius=6)
        input_frame.pack(fill="x", pady=(0, 8))
        input_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # --- f0 alvo ---
        f0_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        f0_frame.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        ctk.CTkLabel(
            f0_frame,
            text="f₀ alvo:",
            font=("Arial", 12, "bold"),
        ).pack(side="left", padx=(0, 4))

        ent_f0 = ctk.CTkEntry(f0_frame, width=80)
        ent_f0.pack(side="left", padx=(0, 4))
        ent_f0.insert(0, "50.0")  # default 50 kHz

        cmb_f0_unit = ctk.CTkOptionMenu(
            f0_frame,
            values=FREQ_OPTIONS,
            width=70,
        )
        cmb_f0_unit.pack(side="left")
        cmb_f0_unit.set("kHz")

        # --- Booleans para componentes fixos ---
        var_R = ctk.BooleanVar(value=False)
        var_L = ctk.BooleanVar(value=False)
        var_C = ctk.BooleanVar(value=False)

        # --- R fixo ---
        R_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        R_frame.grid(row=1, column=0, sticky="w", padx=5, pady=2)

        chk_R = ctk.CTkCheckBox(R_frame, text="R fixo =", variable=var_R, width=80)
        chk_R.pack(side="left", padx=(0, 4))

        ent_R = ctk.CTkEntry(R_frame, width=80)
        ent_R.pack(side="left", padx=(0, 4))
        # sugere o R atual do simulador
        ent_R.insert(0, self.ent_r.get())

        cmb_R_unit = ctk.CTkOptionMenu(
            R_frame,
            values=list(RESISTOR_UNITS.keys()),
            width=70,
        )
        cmb_R_unit.pack(side="left")
        cmb_R_unit.set(self.units_refs["R"].get())

        # --- L fixa ---
        L_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        L_frame.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        chk_L = ctk.CTkCheckBox(L_frame, text="L fixa =", variable=var_L, width=80)
        chk_L.pack(side="left", padx=(0, 4))

        ent_L = ctk.CTkEntry(L_frame, width=80)
        ent_L.pack(side="left", padx=(0, 4))
        ent_L.insert(0, self.ent_l.get())

        cmb_L_unit = ctk.CTkOptionMenu(
            L_frame,
            values=list(INDUCTOR_UNITS.keys()),
            width=70,
        )
        cmb_L_unit.pack(side="left")
        cmb_L_unit.set(self.units_refs["L"].get())

        # --- C fixa ---
        C_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        C_frame.grid(row=1, column=2, sticky="w", padx=5, pady=2)

        chk_C = ctk.CTkCheckBox(C_frame, text="C fixa =", variable=var_C, width=80)
        chk_C.pack(side="left", padx=(0, 4))

        ent_C = ctk.CTkEntry(C_frame, width=80)
        ent_C.pack(side="left", padx=(0, 4))
        ent_C.insert(0, self.ent_c.get())

        cmb_C_unit = ctk.CTkOptionMenu(
            C_frame,
            values=list(CAPACITOR_UNITS.keys()),
            width=70,
        )
        cmb_C_unit.pack(side="left")
        cmb_C_unit.set(self.units_refs["C"].get())

        # --- Botão CALCULAR ---
        btn_calc = ctk.CTkButton(
            input_frame,
            text="CALCULAR",
            fg_color="#7B1FA2",
            text_color="white",
            font=("Arial", 12, "bold"),
        )
        btn_calc.grid(row=0, column=3, rowspan=2, sticky="nsew", padx=5, pady=5)

        # ================= RESULTADOS =================
        results_header = ctk.CTkFrame(root_frame, fg_color="transparent")
        results_header.pack(fill="x", pady=(4, 0))
        results_header.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        ctk.CTkLabel(results_header, text="L", font=("Arial", 12, "bold")).grid(row=0, column=0, padx=5)
        ctk.CTkLabel(results_header, text="C", font=("Arial", 12, "bold")).grid(row=0, column=1, padx=5)
        ctk.CTkLabel(results_header, text="f₀ obtido", font=("Arial", 12, "bold")).grid(row=0, column=2, padx=5)
        ctk.CTkLabel(results_header, text="Erro (%)", font=("Arial", 12, "bold")).grid(row=0, column=3, padx=5)
        ctk.CTkLabel(results_header, text="Q", font=("Arial", 12, "bold")).grid(row=0, column=4, padx=5)
        ctk.CTkLabel(results_header, text="Ação", font=("Arial", 12, "bold")).grid(row=0, column=5, padx=5)

        results_frame = ctk.CTkScrollableFrame(root_frame, fg_color="transparent")
        results_frame.pack(fill="both", expand=True, pady=(2, 0))

        # ===== helper interno para habilitar/desabilitar campos/checkboxes =====
        def update_fixed_states():
            checked = [var_R.get(), var_L.get(), var_C.get()]
            count = sum(1 for v in checked if v)

            # habilita/desabilita entries e optionmenus conforme checkbox
            for var, entry, menu in [
                (var_R, ent_R, cmb_R_unit),
                (var_L, ent_L, cmb_L_unit),
                (var_C, ent_C, cmb_C_unit),
            ]:
                if var.get():
                    entry.configure(state="normal")
                    menu.configure(state="normal")
                else:
                    entry.configure(state="disabled")
                    menu.configure(state="disabled")

            # no máximo 2 componentes fixos: se já tem 2, desabilita o terceiro checkbox
            for var, chk in [
                (var_R, chk_R),
                (var_L, chk_L),
                (var_C, chk_C),
            ]:
                if not var.get() and count >= 2:
                    chk.configure(state="disabled")
                else:
                    chk.configure(state="normal")

        # conectar mudança de estado
        chk_R.configure(command=update_fixed_states)
        chk_L.configure(command=update_fixed_states)
        chk_C.configure(command=update_fixed_states)
        update_fixed_states()  # inicial

        # ===== callback do botão CALCULAR =====
        def on_calculate():
            # --- lê f0 alvo ---
            try:
                target_val = float(ent_f0.get().replace(",", "."))
            except ValueError:
                msgbox.showerror("Valor inválido", "f₀ alvo deve ser numérico.")
                return

            unit = cmb_f0_unit.get()
            target_f0_hz = target_val * get_multiplier(unit)
            if target_f0_hz <= 0:
                msgbox.showerror("Valor inválido", "f₀ alvo deve ser maior que zero.")
                return

            # --- componentes fixos opcionais ---
            R_fixed = None
            L_candidates = None
            C_candidates = None

            if var_R.get():
                try:
                    vR = float(ent_R.get().replace(",", "."))
                except ValueError:
                    msgbox.showerror("Valor inválido", "R fixo deve ser numérico.")
                    return
                R_fixed = vR * get_multiplier(cmb_R_unit.get())

            if var_L.get():
                try:
                    vL = float(ent_L.get().replace(",", "."))
                except ValueError:
                    msgbox.showerror("Valor inválido", "L fixa deve ser numérica.")
                    return
                L_candidates = [vL * get_multiplier(cmb_L_unit.get())]

            if var_C.get():
                try:
                    vC = float(ent_C.get().replace(",", "."))
                except ValueError:
                    msgbox.showerror("Valor inválido", "C fixa deve ser numérica.")
                    return
                C_candidates = [vC * get_multiplier(cmb_C_unit.get())]

            # se R ainda não definido, usa o R efetivo do simulador
            if R_fixed is None:
                R_eff = self._compute_effective_component_value("R")
                if R_eff is not None:
                    R_fixed = R_eff
                else:
                    try:
                        base_R = float(self.ent_r.get().replace(",", "."))
                    except ValueError:
                        msgbox.showerror("Valor inválido", "Valor de R no simulador é inválido.")
                        return
                    R_fixed = base_R * get_multiplier(self.units_refs["R"].get())

            if R_fixed <= 0:
                msgbox.showerror("Valor inválido", "R deve ser maior que zero para cálculo de Q.")
                return

            # --- chama core ---
            try:
                results = design_rlc_for_target_f0(
                    target_f0_hz=target_f0_hz,
                    R_fixed=R_fixed,
                    L_candidates_h=L_candidates,
                    C_candidates_f=C_candidates,
                    max_results=50,
                    max_error_pct=50.0,
                )
            except Exception as e:
                msgbox.showerror("Erro no cálculo", f"Ocorreu um erro no projeto inverso:\n{e}")
                return

            # limpa lista
            for w in results_frame.winfo_children():
                w.destroy()

            if not results:
                msgbox.showinfo(
                    "Nenhuma combinação",
                    "Não foram encontradas combinações L/C dentro do erro máximo configurado.",
                )
                return

            # unidades de exibição = as mesmas do simulador
            L_unit = self.units_refs["L"].get()
            L_factor = get_multiplier(L_unit)
            C_unit = self.units_refs["C"].get()
            C_factor = get_multiplier(C_unit)

            for res in results:
                row = ctk.CTkFrame(results_frame, fg_color=("#2b2b2b", "#2b2b2b"), corner_radius=4)
                row.pack(fill="x", padx=2, pady=2)
                row.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

                L_H = res["L_H"]
                C_F = res["C_F"]
                f0_calc = res["f0_calc_Hz"]
                err = res["error_pct"]
                Q = res["Q"]

                L_disp = L_H / L_factor
                C_disp = C_F / C_factor

                ctk.CTkLabel(row, text=f"{L_disp:.4g} {L_unit}", font=("Arial", 11)).grid(row=0, column=0, padx=5, sticky="w")
                ctk.CTkLabel(row, text=f"{C_disp:.4g} {C_unit}", font=("Arial", 11)).grid(row=0, column=1, padx=5, sticky="w")
                ctk.CTkLabel(row, text=self._format_freq_eng(f0_calc), font=("Arial", 11)).grid(row=0, column=2, padx=5)
                ctk.CTkLabel(row, text=f"{err:.2f} %", font=("Arial", 11)).grid(row=0, column=3, padx=5)
                ctk.CTkLabel(row, text=f"{Q:.2f}" if Q is not None else "-", font=("Arial", 11)).grid(row=0, column=4, padx=5)

                btn_apply = ctk.CTkButton(
                    row,
                    text="Aplicar",
                    width=80,
                    fg_color="#00C853",
                    text_color="black",
                    command=lambda L=L_H, C=C_F: self._apply_reverse_result(L, C),
                )
                btn_apply.grid(row=0, column=5, padx=5)

        btn_calc.configure(command=on_calculate)

    def _open_reverse_design_info_popup(self):
        """
        Popup explicando como funciona o cálculo inverso de f0 (projeto RLC).
        """
        popup = ctk.CTkToplevel(self.parent)
        popup.title("Como funciona o projeto inverso (f₀ alvo)")
        popup.geometry("600x420")
        popup.resizable(True, True)

        parent_win = self.parent.winfo_toplevel()
        popup.transient(parent_win)
        popup.lift()
        popup.grab_set()
        popup.focus_force()

        frame = ctk.CTkFrame(popup, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        lbl_title = ctk.CTkLabel(
            frame,
            text="Projeto inverso de circuito RLC série",
            font=("Arial", 16, "bold"),
            anchor="w",
        )
        lbl_title.pack(fill="x", pady=(0, 10))

        txt = ctk.CTkTextbox(frame, wrap="word", font=("Consolas", 12))
        txt.pack(fill="both", expand=True, pady=(0, 10))

        content = (
            "O projeto inverso parte de uma frequência de ressonância desejada f₀\n"
            "e tenta encontrar combinações de L e C que satisfaçam aproximadamente:\n\n"
            "    f₀ ≈ 1 / (2·π·√(L·C))\n\n"
            "Estratégia usada:\n"
            "  • Se nenhum valor fixo de L/C for informado, o programa usa uma grade\n"
            "    de valores comerciais (estilo série E12) em algumas décadas típicas.\n"
            "  • Para cada combinação possível de L e C, é calculado f₀_calc e o erro\n"
            "    relativo em relação ao f₀ alvo.\n"
            "  • Opcionalmente, R é usado para calcular o fator de qualidade Q por:\n"
            "        Q = (1/R) · √(L/C)\n\n"
            "Componentes fixos:\n"
            "  • Se você marcar L fixa, essa indutância é mantida e apenas C varia.\n"
            "  • Se marcar C fixa, C é mantido e L varia.\n"
            "  • Se marcar L e C ao mesmo tempo, o sistema avalia exatamente essa\n"
            "    combinação, mostrando o f₀ obtido e o erro em relação ao alvo.\n\n"
            "O resultado é uma lista ordenada pelas menores diferenças de f₀, para\n"
            "facilitar a escolha de um par L/C fisicamente realizável e próximo da\n            "
            "frequência desejada.\n"
        )

        txt.insert("1.0", content)
        txt.configure(state="disabled")

        btn_close = ctk.CTkButton(frame, text="Fechar", command=popup.destroy, fg_color="#0055A4")
        btn_close.pack(pady=(0, 5))

    # ==================== POPUP TEÓRICO ====================

    def _open_info_popup(self, metric: str):
        """
        Abre um popup com explicação teórica detalhada
        para a métrica selecionada: 'f0', 'Q' ou 'BW'.
        """
        if metric == "f0":
            title = "Frequência de Ressonância (f₀)"
            text = (
                "A frequência de ressonância f₀ é o ponto em que o circuito RLC série\n"
                "apresenta máxima transferência de energia para o resistor.\n\n"
                "No circuito RLC série ideal (R em série com L e C), f₀ depende apenas\n"
                "de L e C, dada por:\n\n"
                "    f₀ = 1 / (2·π·√(L·C))\n\n"
                "Em termos físicos:\n"
                "  • A reatância indutiva:   X_L = 2·π·f·L   (cresce com a frequência)\n"
                "  • A reatância capacitiva: X_C = 1 / (2·π·f·C)   (decresce com a frequência)\n\n"
                "Em f₀ temos X_L = X_C, as reatâncias se cancelam e o circuito é puramente\n"
                "resistivo.\n\n"
                "Neste ponto, a corrente é máxima e a tensão medida no resistor atinge o\n"
                "valor máximo para uma dada tensão de entrada."
            )
        elif metric == "Q":
            title = "Fator de Qualidade (Q)"
            text = (
                "O fator de qualidade Q mede quão seletivo é o circuito em torno da\n"
                "frequência de ressonância f₀.\n\n"
                "Para o RLC série, vale:\n\n"
                "    Q = (1 / R) · √(L / C)\n\n"
                "Interpretação:\n"
                "  • Q alto  → pico de ressonância estreito e mais alto (mais seletivo).\n"
                "  • Q baixo → resposta mais larga e menos pronunciada.\n\n"
                "Q se relaciona com a largura de banda BW por:\n\n"
                "    Q = f₀ / BW\n\n"
                "onde BW = f₂ − f₁ e f₁, f₂ são as frequências de meia-potência\n"
                "(pontos em que a potência cai para metade do valor máximo,\n"
                "ou seja, |V| ≈ 0,707·|Vₘₐₓ|)."
            )
        elif metric == "BW":
            title = "Largura de Banda (BW)"
            text = (
                "A largura de banda BW indica a faixa de frequências em torno de f₀\n"
                "onde o circuito ainda apresenta ganho significativo.\n\n"
                "Definição de meia-potência:\n\n"
                "    BW = f₂ − f₁\n\n"
                "onde f₁ e f₂ são as frequências em que a potência cai para metade do\n"
                "valor máximo.\n\n"
                "No RLC série, vale ainda a relação:\n\n"
                "    BW = f₀ / Q\n\n"
                "Assim:\n"
                "  • Q alto  → BW estreita (circuito bem seletivo).\n"
                "  • Q baixo → BW larga (resposta mais espalhada em frequência)."
            )
        else:
            title = "Informação"
            text = "Métrica não reconhecida."

        popup = ctk.CTkToplevel(self.parent)
        popup.title(title)
        popup.geometry("620x440")
        popup.resizable(False, False)

        parent_win = self.parent.winfo_toplevel()
        popup.transient(parent_win)
        popup.lift()
        popup.grab_set()
        popup.focus_force()

        frame = ctk.CTkFrame(popup, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        lbl_title = ctk.CTkLabel(
            frame,
            text=title,
            font=("Arial", 16, "bold"),
            anchor="w",
        )
        lbl_title.pack(fill="x", pady=(5, 10))

        txt = ctk.CTkTextbox(
            frame,
            wrap="word",
            font=("Consolas", 12),
        )
        txt.pack(fill="both", expand=True, pady=(0, 10))
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        btn_close = ctk.CTkButton(
            frame,
            text="Fechar",
            command=popup.destroy,
            fg_color="#0055A4",
        )
        btn_close.pack(pady=(0, 5))

    # ==================== SIMULAÇÃO ====================

    def run_simulation(self, show_errors: bool = True):
        try:
            # Se veio do botão SIMULAR (show_errors=True), tratar como se todos os "OK"
            # tivessem sido pressionados, se os inputs mudaram.
            if show_errors:
                for key, entry in (("R", self.ent_r), ("L", self.ent_l), ("C", self.ent_c)):
                    txt = entry.get().strip()
                    last = self.last_center_entry_text.get(key, None)
                    if last is None or txt != last:
                        # Recentraliza com base no input atual
                        self._recenter_range_from_entry(key, show_errors=True)

            # ---------- Leitura de valores NOMINAIS (fallback) ----------
            R_base = self._parse_float_entry(self.ent_r, "Resistor (R)", show_errors)
            L_base = self._parse_float_entry(self.ent_l, "Indutor (L)", show_errors)
            C_base = self._parse_float_entry(self.ent_c, "Capacitor (C)", show_errors)

            if R_base is None or L_base is None or C_base is None:
                return

            R_base *= get_multiplier(self.units_refs["R"].get())
            L_base *= get_multiplier(self.units_refs["L"].get())
            C_base *= get_multiplier(self.units_refs["C"].get())

            # Valores efetivos via center + slider (se válidos)
            R_eff = self._compute_effective_component_value("R")
            L_eff = self._compute_effective_component_value("L")
            C_eff = self._compute_effective_component_value("C")

            R_nom = R_eff if R_eff is not None else R_base
            L_nom = L_eff if L_eff is not None else L_base
            C_nom = C_eff if C_eff is not None else C_base

            # Atualiza labels "Atual: ..." mesmo se a simulação veio do botão
            if R_eff is not None:
                self._update_effective_label("R", R_nom)
            if L_eff is not None:
                self._update_effective_label("L", L_nom)
            if C_eff is not None:
                self._update_effective_label("C", C_nom)

            # ---------- Tolerâncias ----------
            tol_R = self._parse_float_entry(self.ent_r_tol, "Tolerância de R (%)", show_errors)
            tol_L = self._parse_float_entry(self.ent_l_tol, "Tolerância de L (%)", show_errors)
            tol_C = self._parse_float_entry(self.ent_c_tol, "Tolerância de C (%)", show_errors)

            if tol_R is None or tol_L is None or tol_C is None:
                return

            tol_R /= 100.0
            tol_L /= 100.0
            tol_C /= 100.0

            # ---------- V_in ----------
            V_in_plot = self._parse_float_entry(self.ent_vin, "Amplitude de Entrada (Vpp)", show_errors)
            if V_in_plot is None:
                return

            # ---------- Faixa de frequência para simulação ----------
            freq_min_Hz = None
            freq_max_Hz = None

            if not self.freq_auto.get():
                fmin = self._parse_float_entry(
                    self.freq_min_entry,
                    "f_min (frequência mínima)",
                    show_errors,
                )
                fmax = self._parse_float_entry(
                    self.freq_max_entry,
                    "f_max (frequência máxima)",
                    show_errors,
                )

                if fmin is not None and fmax is not None:
                    umin = self.freq_min_unit.get()
                    umax = self.freq_max_unit.get()
                    freq_min_Hz = fmin * get_multiplier(umin)
                    freq_max_Hz = fmax * get_multiplier(umax)

                    if (
                        freq_min_Hz <= 0
                        or freq_max_Hz <= 0
                        or freq_min_Hz >= freq_max_Hz
                    ):
                        if show_errors:
                            msgbox.showerror(
                                "Faixa de frequência inválida",
                                "Verifique se f_min e f_max são positivos e f_min < f_max."
                            )
                        # se inválido, volta para automático
                        freq_min_Hz = None
                        freq_max_Hz = None

            # ---------- Chamada ao core ----------
            (
                freqs,
                nom_curve_Vout,
                min_curve_Vout,
                max_curve_Vout,
                metrics_nom,
                ranges,
                Vout_max_global,
            ) = simulate_response_with_tolerances(
                R_nom=R_nom,
                L_nom=L_nom,
                C_nom=C_nom,
                tol_R=tol_R,
                tol_L=tol_L,
                tol_C=tol_C,
                V_in_plot=V_in_plot,
                freq_min=freq_min_Hz,
                freq_max=freq_max_Hz,
            )

            # Guarda a curva nominal e Vin para salvar como teórico depois
            self.last_freqs = np.array(freqs, dtype=float)
            self.last_nom_curve_Vout = np.array(nom_curve_Vout, dtype=float)
            self.last_V_in_plot = float(V_in_plot)

            f0 = metrics_nom["f0"]
            Q = metrics_nom["Q"]
            BW_nom = metrics_nom["BW"]
            f1_nom = metrics_nom["f1"]
            f2_nom = metrics_nom["f2"]

            self.f1_nom = f1_nom
            self.f2_nom = f2_nom

            # Guarda métricas cruas e faixa real usada (do vetor freqs)
            self.last_metrics_nom = dict(metrics_nom)  # cópia simples
            if freqs is not None and len(freqs) > 0:
                self.last_freq_min_Hz_used = float(freqs[0])
                self.last_freq_max_Hz_used = float(freqs[-1])
            else:
                self.last_freq_min_Hz_used = None
                self.last_freq_max_Hz_used = None

            # ---------- Gráfico ----------
            self.ax.clear()
            freq_factor, freq_unit = setup_frequency_axis(self.ax, freqs)

            f0_str = format_frequency_for_unit(f0, freq_factor, freq_unit)
            self.ax.set_title(f"Simulação RLC (f0={f0_str}, Q={Q:.2f})")
            self.ax.set_ylabel(f"Tensão de Saída (Vpp) | V_in = {V_in_plot:.1f} V")
            self.ax.grid(True, which="both", alpha=0.3)

            if Vout_max_global > 0:
                self.ax.set_ylim(0, Vout_max_global * 1.1)
            else:
                self.ax.set_ylim(0, 1.1)

            # ---------- Cards ----------
            self.lbl_f0_nom.configure(text=self._format_freq_eng(f0))
            self.lbl_q_nom.configure(text=f"{Q:.2f}")
            self.lbl_bw_nom.configure(text=self._format_freq_eng(BW_nom))

            if hasattr(self, "lbl_f1f2"):
                f1_txt = format_frequency_for_unit(f1_nom, freq_factor, freq_unit)
                f2_txt = format_frequency_for_unit(f2_nom, freq_factor, freq_unit)
                self.lbl_f1f2.configure(text=f"f₁ = {f1_txt} | f₂ = {f2_txt}")

            # ---------- Tolerância ----------
            if self.show_tolerance.get():
                self.ax.fill_between(
                    freqs,
                    min_curve_Vout,
                    max_curve_Vout,
                    color='aliceblue',
                    alpha=0.1,
                    label='Incerteza Tolerância',
                )
                self.ax.plot(
                    freqs,
                    max_curve_Vout,
                    color='lime',
                    linestyle='--',
                    linewidth=1,
                    alpha=0.6,
                )
                self.ax.plot(
                    freqs,
                    min_curve_Vout,
                    color='orangered',
                    linestyle='--',
                    linewidth=1,
                    alpha=0.6,
                )

            # ---------- Curva nominal ----------
            self.ax.plot(
                freqs,
                nom_curve_Vout,
                color='gold',
                linewidth=2.5,
                label='Nominal',
            )

            # ---------- f0 / f1 / f2 ----------
            if self.show_f0.get():
                self.ax.axvline(x=f0, color='red', alpha=0.8, label='f0')

            if self.show_f1f2.get():
                self.ax.axvline(x=f1_nom, color='aqua', alpha=0.7, label='f1')
                self.ax.axvline(x=f2_nom, color='aqua', alpha=0.7, label='f2')

            self.ax.legend(loc='upper right', fontsize='small')
            self.canvas.draw()

            self.btn_save_theory.configure(state="normal")

        except ZeroDivisionError:
            if show_errors:
                msgbox.showerror(
                    "Erro",
                    "Divisão por Zero. Verifique se R, L ou C não são zero.",
                )
        except Exception as e:
            if show_errors:
                msgbox.showerror("Erro de Simulação", f"Ocorreu um erro: {e}")

    # ==================== SALVAR TEÓRICO ====================

    def save_theory_gui(self):
        file_path = filedialog.asksaveasfilename(
            initialdir=self.data_manager.save_dir,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="Salvar Parâmetros Teóricos (Definir Nome)",
        )

        if not file_path:
            return

        exp_name = os.path.basename(file_path).replace(".json", "").replace(".JSON", "")

        metrics = self.last_metrics_nom or {}

        # ---------- bloco básico de parâmetros ----------
        params = {
            "R": self.ent_r.get(),
            "R_tol": self.ent_r_tol.get(),
            "R_unit": self.units_refs["R"].get(),
            "L": self.ent_l.get(),
            "L_tol": self.ent_l_tol.get(),
            "L_unit": self.units_refs["L"].get(),
            "C": self.ent_c.get(),
            "C_tol": self.ent_c_tol.get(),
            "C_unit": self.units_refs["C"].get(),
            "V_in": self.ent_vin.get(),
            "metrics": {
                "f0": float(metrics.get("f0")) if metrics.get("f0") is not None else None,
                "Q": float(metrics.get("Q")) if metrics.get("Q") is not None else None,
                "BW": float(metrics.get("BW")) if metrics.get("BW") is not None else None,
                "f1": float(self.f1_nom),
                "f2": float(self.f2_nom),
            },
            "freq_range": {
                "f_min_Hz": float(self.last_freq_min_Hz_used) if self.last_freq_min_Hz_used is not None else None,
                "f_max_Hz": float(self.last_freq_max_Hz_used) if self.last_freq_max_Hz_used is not None else None,
            },
        }

        # ---------- salva também os pontos da curva nominal (ganho normalizado) ----------
        try:
            if (
                self.last_freqs is not None
                and self.last_nom_curve_Vout is not None
                and self.last_V_in_plot is not None
            ):
                freqs = np.asarray(self.last_freqs, dtype=float)
                vout = np.asarray(self.last_nom_curve_Vout, dtype=float)
                vin = float(self.last_V_in_plot)

                if vin <= 0:
                    vin = 1.0

                gain = vout / vin
                max_gain = float(np.max(gain)) if gain.size > 0 else 0.0
                if max_gain > 0:
                    gain_norm = gain / max_gain
                else:
                    gain_norm = gain

                params["curve_points"] = {
                    "freqs_Hz": freqs.tolist(),
                    "gain_norm": gain_norm.tolist(),
                }
        except Exception as e:
            # Se der algo errado aqui, ainda assim salvamos o resto
            print(f"[WARN] Falha ao preparar curve_points para '{exp_name}': {e}")

        # ---------- grava arquivo ----------
        try:
            self.data_manager.save_theoretical_params(exp_name, params)
            msgbox.showinfo(
                "Salvo",
                f"Parâmetros teóricos '{exp_name}' salvos com sucesso!",
            )
            self.btn_save_theory.configure(state="disabled")
        except Exception as e:
            msgbox.showerror("Erro de I/O", f"Falha ao salvar: {e}")