import customtkinter as ctk
import pandas as pd
import numpy as np
import os
import json
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import tkinter.messagebox as msgbox
from tkinter import filedialog
from datetime import datetime

from gui.ui_helpers import ToolTip
from gui.plot_utils import setup_frequency_axis
from core.curve_fitting import fit_bandpass_rlc
from core.analysis_reconstruction import reconstruct_theoretical_curve, solve_rlc_from_f0_Q

from core.rlc_theory import design_rlc_for_target_f0

from core.units import (
    RESISTOR_UNITS,
    INDUCTOR_UNITS,
    CAPACITOR_UNITS,
    FREQUENCY_UNITS,
    get_multiplier,
)

class AnalysisViewManager(ctk.CTkFrame):
    """
    Componente central de visualização de dados RLC.
    Gerencia o layout, carregamento e comparação de curvas.
    """

    def __init__(self, master, data_manager, initial_curves=None, is_floating=False):
        super().__init__(master)

        self.dm = data_manager
        self.is_floating = is_floating
        self.active_curves = initial_curves if initial_curves is not None else {}
        self.open_window_callback = None
        self.current_focus_key = None  # curva "focada"

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=2)  # Sidebar
        self.grid_columnconfigure(1, weight=5)  # Plot

        self._build_sidebar()
        self._init_plot()

        self._update_metrics_list_ui()
        self.plot_curves()

    # ----------------------------------------------------------------------
    # Sidebar
    # ----------------------------------------------------------------------
    def _build_sidebar(self):
        self.sidebar = ctk.CTkScrollableFrame(
            self, width=250, label_text="Controle & Config"
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.btn_load = ctk.CTkButton(
            self.sidebar,
            text="Adicionar Curva (+)",
            command=self.load_and_add_curve,
            fg_color="#0055A4",
        )
        self.btn_load.pack(fill="x", padx=10, pady=15)

        self.btn_save_comparison = ctk.CTkButton(
            self.sidebar,
            text="Salvar Comparação (PNG/JSON)",
            command=self.save_comparison_gui,
            fg_color="#00695C",
        )
        self.btn_save_comparison.pack(fill="x", padx=10, pady=20)

        self.btn_clear_all = ctk.CTkButton(
            self.sidebar,
            text="EXCLUIR TODAS",
            command=self.clear_all_curves,
            fg_color="red",
        )
        self.btn_clear_all.pack(fill="x", padx=10, pady=10)

    def set_open_window_callback(self, callback):
        self.open_window_callback = callback
        self.btn_floating_view = ctk.CTkButton(
            self.sidebar,
            text="ABRIR NOVA JANELA (Solta)",
            command=self.open_window_callback,
            fg_color="#FF8C00",
        )
        self.btn_floating_view.pack(fill="x", padx=10, pady=10)

    # ----------------------------------------------------------------------
    # Estado / gerenciamento de curvas
    # ----------------------------------------------------------------------
    def clear_all_curves(self):
        if not msgbox.askyesno(
            "Confirmação", "Deseja realmente excluir todas as curvas plotadas?"
        ):
            return

        self.active_curves = {}
        self.current_focus_key = None
        self._update_metrics_list_ui()
        self.plot_curves()

    def remove_curve(self, key_to_remove):
        if key_to_remove in self.active_curves:
            del self.active_curves[key_to_remove]

            if self.current_focus_key == key_to_remove:
                self.current_focus_key = next(iter(self.active_curves), None)

            self._update_metrics_list_ui(focused_key=self.current_focus_key)
            self.plot_curves(focused_key=self.current_focus_key)

    def _init_curve_state(self, key: str) -> None:
        """
        Inicializa variáveis de controle (checkboxes) para uma curva.
        """
        curve = self.active_curves[key]

        # Sempre: f0 / f1f2
        if "show_f0_var" not in curve:
            curve["show_f0_var"] = ctk.BooleanVar(value=True)
        if "show_f1f2_var" not in curve:
            curve["show_f1f2_var"] = ctk.BooleanVar(value=True)

        if curve["type"] == "exp":
            # Ajuste e exibição de pontos originais
            if "use_fit_var" not in curve:
                curve["use_fit_var"] = ctk.BooleanVar(value=True)
            if "show_points_var" not in curve:
                curve["show_points_var"] = ctk.BooleanVar(value=True)
        else:
            curve["use_fit_var"] = None
            curve["show_points_var"] = None

    # ----------------------------------------------------------------------
    # Layout do plot
    # ----------------------------------------------------------------------
    def _init_plot(self):
        self.plot_frame = ctk.CTkFrame(self)
        self.plot_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.plot_frame.grid_rowconfigure(0, weight=1)
        self.plot_frame.grid_columnconfigure(0, weight=1)

        self._build_metrics_display()

        plt.style.use("dark_background")
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.fig.patch.set_facecolor("#242424")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#242424")
        self.ax.grid(True, which="both", alpha=0.3)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()

        self.toolbar = NavigationToolbar2Tk(
            self.canvas, self.plot_frame, pack_toolbar=False
        )
        self.toolbar.update()

        self.toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _build_metrics_display(self):
        self.metrics_container = ctk.CTkFrame(
            self.plot_frame,
            fg_color=("#cfcfcf", "#1f1f1f"),
            corner_radius=8,
        )
        self.metrics_container.pack(side="top", fill="x", padx=10, pady=(10, 0))

        self.list_frame = ctk.CTkFrame(
            self.metrics_container,
            fg_color="transparent",
        )
        self.list_frame.pack(fill="x", padx=10, pady=5)

        self.curve_list_content = ctk.CTkScrollableFrame(
            self.list_frame, label_text="Curvas Plotadas"
        )
        self.curve_list_content.pack(fill="x", expand=True)

    # ----------------------------------------------------------------------
    # UI cards
    # ----------------------------------------------------------------------
    def _update_metrics_list_ui(self, focused_key=None):
        for widget in self.curve_list_content.winfo_children():
            widget.destroy()

        if not self.active_curves:
            self.curve_list_content.configure(label_text="Curvas Plotadas")
            self.btn_clear_all.configure(state="disabled")
            self.list_frame.pack_forget()
            return

        self.list_frame.pack(fill="x", padx=10, pady=5)
        self.btn_clear_all.configure(state="normal")

        if focused_key is not None:
            self.current_focus_key = focused_key
        elif self.current_focus_key not in self.active_curves:
            self.current_focus_key = next(iter(self.active_curves), None)

        key_to_focus = self.current_focus_key

        for i, (key, curve) in enumerate(self.active_curves.items()):
            self._init_curve_state(key)
            is_focused = key == key_to_focus
            metrics = curve["metrics"]

            card_color = "#333333" if is_focused else "#2b2b2b"
            text_color = "gold" if is_focused else "white"

            card = ctk.CTkFrame(
                self.curve_list_content,
                fg_color=card_color,
                corner_radius=5,
            )
            card.pack(fill="x", padx=5, pady=5)

            # Título
            title_frame = ctk.CTkFrame(card, fg_color="transparent")
            title_frame.pack(fill="x", padx=10, pady=(5, 2))
            title_frame.grid_columnconfigure(0, weight=1)
            title_frame.grid_columnconfigure(1, weight=0)
            title_frame.grid_columnconfigure(2, weight=0)

            title_text = f"{i+1}. {curve['name'].split()[0]} ({curve['type'].upper()})"
            ctk.CTkLabel(
                title_frame,
                text=title_text,
                font=("Arial", 14, "bold"),
                text_color=text_color
            ).grid(row=0, column=0, sticky="w")

            # --- novo botão pequeno de projeto inverso ---
            btn_inverse = ctk.CTkButton(
                title_frame,
                text="INVERSO",
                width=80,
                fg_color="#7B1FA2",
                text_color="white",
                font=("Arial", 11, "bold"),
                command=lambda k=key: self._open_inverse_popup_for_curve(k),
            )
            btn_inverse.grid(row=0, column=1, padx=(0, 6), sticky="e")

            # botão EXCLUIR permanece
            btn_remove = ctk.CTkButton(
                title_frame,
                text="EXCLUIR",
                command=lambda k=key: self.remove_curve(k),
                width=80,
                fg_color="#CC0000",
            )
            btn_remove.grid(row=0, column=2, sticky="e")

            # Métricas
            metrics_frame = ctk.CTkFrame(card, fg_color="transparent")
            metrics_frame.pack(fill="x", padx=10, pady=(0, 4))
            metrics_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

            f0_val = metrics.get("f0", 0)
            q_val = metrics.get("Q", 0)
            bw_val = metrics.get("BW", 0)
            f1_val = metrics.get("f1", 0)
            f2_val = metrics.get("f2", 0)

            ctk.CTkLabel(
                metrics_frame,
                text=f"f0: {f0_val:.2f} Hz",
                text_color="#4da6ff",
                font=("Arial", 12),
            ).grid(row=0, column=0, sticky="w", padx=5)
            ctk.CTkLabel(
                metrics_frame,
                text=f"Q: {q_val:.2f}",
                text_color="#00c853",
                font=("Arial", 12),
            ).grid(row=0, column=1, sticky="w", padx=5)
            ctk.CTkLabel(
                metrics_frame,
                text=f"BW: {bw_val:.2f} Hz",
                text_color="#ff8c00",
                font=("Arial", 12),
            ).grid(row=0, column=2, sticky="w", padx=5)
            ctk.CTkLabel(
                metrics_frame,
                text=f"f1: {f1_val:.2f} Hz",
                text_color="aqua",
                font=("Arial", 12),
            ).grid(row=1, column=0, sticky="w", padx=5, pady=(2, 0))
            ctk.CTkLabel(
                metrics_frame,
                text=f"f2: {f2_val:.2f} Hz",
                text_color="aqua",
                font=("Arial", 12),
            ).grid(row=1, column=1, sticky="w", padx=5, pady=(2, 0))

            # Linha de checkboxes compacta
            controls_frame = ctk.CTkFrame(metrics_frame, fg_color="transparent")
            controls_frame.grid(
                row=2, column=0, columnspan=5, sticky="w", pady=(3, 4)
            )

            ctk.CTkCheckBox(
                controls_frame,
                text="Mostrar f₀",
                variable=curve["show_f0_var"],
                command=self.plot_curves,
            ).pack(side="left", padx=(0, 8))

            ctk.CTkCheckBox(
                controls_frame,
                text="Mostrar f₁ / f₂",
                variable=curve["show_f1f2_var"],
                command=self.plot_curves,
            ).pack(side="left", padx=(0, 12))

            if curve["type"] == "exp":
                ctk.CTkCheckBox(
                    controls_frame,
                    text="Ajuste (Gauss–Marquardt)",
                    variable=curve["use_fit_var"],
                    command=self.plot_curves,
                ).pack(side="left", padx=(0, 8))

                ctk.CTkCheckBox(
                    controls_frame,
                    text="Mostrar pontos",
                    variable=curve["show_points_var"],
                    command=self.plot_curves,
                ).pack(side="left")

            if is_focused:
                self.plot_curves(focused_key=key)

        self.curve_list_content.configure(
            label_text=f"Curvas Plotadas ({len(self.active_curves)})"
        )

    def _format_component_eng(self, value_SI: float, comp_type: str) -> str:
        """
        Formata R, L ou C em unidades de engenharia 'bonitas'
        (Ω/kΩ/MΩ, H/mH/µH, F/µF/nF/pF).
        """
        if value_SI is None or value_SI <= 0:
            return "---"

        comp_type = comp_type.upper()

        if comp_type == "R":
            table = [
                ("MΩ", 1e6),
                ("kΩ", 1e3),
                ("Ω", 1.0),
            ]
        elif comp_type == "L":
            table = [
                ("H", 1.0),
                ("mH", 1e-3),
                ("µH", 1e-6),
                ("nH", 1e-9),
            ]
        elif comp_type == "C":
            table = [
                ("F", 1.0),
                ("mF", 1e-3),
                ("µF", 1e-6),
                ("nF", 1e-9),
                ("pF", 1e-12),
            ]
        else:
            return f"{value_SI:.3g} (SI)"

        # escolhe unidade que deixe o número entre ~0.1 e 1000
        for unit, factor in table:
            val = value_SI / factor
            if 0.1 <= abs(val) < 1000:
                return f"{val:.3g} {unit}"

        # fallback: usa a menor unidade
        unit, factor = table[-1]
        val = value_SI / factor
        return f"{val:.3g} {unit}"
    
    def _open_inverse_design_info_popup(self):
        """
        Popup explicando a teoria do projeto inverso a partir de uma curva (f₀, Q).
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Teoria do projeto inverso (RLC série)")
        popup.geometry("620x460")
        popup.resizable(True, True)

        parent_win = self.winfo_toplevel()
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
            "Ideia geral:\n"
            "  A partir de uma curva medida (experimento) estimamos a frequência de\n"
            "  ressonância f₀ e, em alguns casos, o fator de qualidade Q.\n"
            "  No projeto inverso queremos encontrar combinações de R, L e C que\n"
            "  reproduzam aproximadamente essa ressonância.\n\n"
            "Equações básicas do RLC série:\n"
            "  • Frequência de ressonância:\n"
            "        f₀ = 1 / (2·π·√(L·C))\n\n"
            "  • Fator de qualidade (modelo ideal):\n"
            "        Q = (1 / R) · √(L / C)\n\n"
            "  • Largura de banda (aproximada):\n"
            "        BW = f₂ − f₁ ≈ f₀ / Q\n\n"
            "Como o projeto inverso é feito aqui:\n"
            "  1. Definimos uma frequência alvo f₀ (normalmente vinda da curva medida).\n"
            "  2. Opcionalmente fixamos um ou dois componentes (R, L ou C).\n"
            "  3. O algoritmo percorre uma grade de valores comerciais (L e C) e,\n"
            "     para cada combinação, calcula o f₀ obtido pela expressão acima.\n"
            "  4. Calcula-se o erro relativo entre f₀_calc e f₀_alvo e ordena-se as\n"
            "     soluções da menor para a maior diferença.\n"
            "  5. Quando um R é fornecido, também é estimado Q pela fórmula de Q.\n\n"
            "Interpretação prática:\n"
            "  • Fixar R e deixar L/C livres é útil quando a resistência é imposta\n"
            "    pelo circuito de medição ou pela carga.\n"
            "  • Fixar L (indutor físico que você já tem) permite dimensionar apenas C.\n"
            "  • Fixar C (capacitor disponível) permite dimensionar L.\n\n"
            "A partir disso, você escolhe o par L/C (e eventualmente R) que for mais\n"
            "viável em termos de componentes reais e verifica o quão próximo fica da\n"
            "curva experimental em f₀ e Q."
        )

        txt.insert("1.0", content)
        txt.configure(state="disabled")

        btn_close = ctk.CTkButton(
            frame,
            text="Fechar",
            command=popup.destroy,
            fg_color="#0055A4",
        )
        btn_close.pack(pady=(0, 5))
    
    def _open_inverse_popup_for_curve(self, curve_key: str):
        """
        Abre um popup de projeto inverso (igual ao do simulador, mas
        usando f0 da curva selecionada como alvo).
        Apenas calcula e mostra combinações L/C (não altera nada no simulador).
        """
        if curve_key not in self.active_curves:
            return

        curve = self.active_curves[curve_key]
        metrics = curve.get("metrics", {}) or {}
        f0_hz = metrics.get("f0", None)

        if f0_hz is None or f0_hz <= 0:
            msgbox.showerror(
                "Projeto inverso",
                "Esta curva não possui f₀ válido nos metadados."
            )
            return

        # Escolhe unidade "boa" para pré-preencher f0 alvo
        if f0_hz >= 1e6:
            f0_val = f0_hz / 1e6
            f0_unit_default = "MHz"
        elif f0_hz >= 1e3:
            f0_val = f0_hz / 1e3
            f0_unit_default = "kHz"
        else:
            f0_val = f0_hz
            f0_unit_default = "Hz"

        popup = ctk.CTkToplevel(self)
        popup.title(f"Projeto inverso a partir de: {curve['name']}")
        popup.geometry("900x600")
        popup.resizable(True, True)

        parent_win = self.winfo_toplevel()
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
            text=f"Projeto inverso (RLC série) – {curve['name']}",
            font=("Arial", 16, "bold"),
            anchor="w",
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        # Botão de informação (teoria / fórmulas)
        info_btn = ctk.CTkLabel(
            header,
            text="i",
            width=24,
            height=24,
            corner_radius=12,
            fg_color="#444444",
            font=("Arial", 14, "bold"),
        )
        info_btn.grid(row=0, column=1, padx=(8, 0), sticky="e")
        ToolTip(
            info_btn,
            "Clique para ver a teoria e as fórmulas usadas no projeto inverso (f₀, Q, R, L, C)."
        )
        info_btn.bind("<Button-1>", lambda e: self._open_inverse_design_info_popup())

        # Pequeno texto explicando que f0 vem da curva
        subtitle = ctk.CTkLabel(
            header,
            text=f"f₀ alvo inicial baseado na curva: {f0_hz:.2f} Hz",
            font=("Arial", 11),
            anchor="w",
            text_color="#aaaaaa",
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # ================= ÁREA DE ENTRADA =================
        input_frame = ctk.CTkFrame(root_frame, corner_radius=6)
        input_frame.pack(fill="x", pady=(8, 8))
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
        ent_f0.insert(0, f"{f0_val:.3g}")

        freq_options = list(FREQUENCY_UNITS.keys())
        cmb_f0_unit = ctk.CTkOptionMenu(
            f0_frame,
            values=freq_options,
            width=70,
        )
        cmb_f0_unit.pack(side="left")
        cmb_f0_unit.set(f0_unit_default)

        # --- Booleans para componentes fixos ---
        var_R = ctk.BooleanVar(value=False)
        var_L = ctk.BooleanVar(value=False)
        var_C = ctk.BooleanVar(value=False)

        # --- R fixo (opcional) ---
        R_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        R_frame.grid(row=1, column=0, sticky="w", padx=5, pady=2)

        chk_R = ctk.CTkCheckBox(R_frame, text="R fixo =", variable=var_R, width=80)
        chk_R.pack(side="left", padx=(0, 4))

        ent_R = ctk.CTkEntry(R_frame, width=80)
        ent_R.pack(side="left", padx=(0, 4))
        # deixa em branco, usuário escolhe

        cmb_R_unit = ctk.CTkOptionMenu(
            R_frame,
            values=list(RESISTOR_UNITS.keys()),
            width=70,
        )
        cmb_R_unit.pack(side="left")
        cmb_R_unit.set("Ω")

        # --- L fixa (opcional) ---
        L_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        L_frame.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        chk_L = ctk.CTkCheckBox(L_frame, text="L fixa =", variable=var_L, width=80)
        chk_L.pack(side="left", padx=(0, 4))

        ent_L = ctk.CTkEntry(L_frame, width=80)
        ent_L.pack(side="left", padx=(0, 4))

        cmb_L_unit = ctk.CTkOptionMenu(
            L_frame,
            values=list(INDUCTOR_UNITS.keys()),
            width=70,
        )
        cmb_L_unit.pack(side="left")
        cmb_L_unit.set("mH")

        # --- C fixa (opcional) ---
        C_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        C_frame.grid(row=1, column=2, sticky="w", padx=5, pady=2)

        chk_C = ctk.CTkCheckBox(C_frame, text="C fixa =", variable=var_C, width=80)
        chk_C.pack(side="left", padx=(0, 4))

        ent_C = ctk.CTkEntry(C_frame, width=80)
        ent_C.pack(side="left", padx=(0, 4))

        cmb_C_unit = ctk.CTkOptionMenu(
            C_frame,
            values=list(CAPACITOR_UNITS.keys()),
            width=70,
        )
        cmb_C_unit.pack(side="left")
        cmb_C_unit.set("nF")

        # --- Botão CALCULAR ---
        btn_calc = ctk.CTkButton(
            input_frame,
            text="CALCULAR COMPONENTES",
            fg_color="#7B1FA2",
            text_color="white",
            font=("Arial", 12, "bold"),
        )
        btn_calc.grid(row=0, column=3, rowspan=2, sticky="nsew", padx=5, pady=5)

        # ================= RESULTADOS =================
        results_header = ctk.CTkFrame(root_frame, fg_color="transparent")
        results_header.pack(fill="x", pady=(4, 0))
        results_header.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkLabel(results_header, text="L", font=("Arial", 12, "bold")).grid(row=0, column=0, padx=5)
        ctk.CTkLabel(results_header, text="C", font=("Arial", 12, "bold")).grid(row=0, column=1, padx=5)
        ctk.CTkLabel(results_header, text="f₀ obtido", font=("Arial", 12, "bold")).grid(row=0, column=2, padx=5)
        ctk.CTkLabel(results_header, text="Erro (%)", font=("Arial", 12, "bold")).grid(row=0, column=3, padx=5)
        ctk.CTkLabel(results_header, text="Q (aprox.)", font=("Arial", 12, "bold")).grid(row=0, column=4, padx=5)

        results_frame = ctk.CTkScrollableFrame(root_frame, fg_color="transparent")
        results_frame.pack(fill="both", expand=True, pady=(2, 0))

        # ===== helper interno para habilitar/desabilitar campos/checkboxes =====
        def update_fixed_states():
            checked = [var_R.get(), var_L.get(), var_C.get()]
            count = sum(1 for v in checked if v)

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

            # no máximo 2 marcados ao mesmo tempo
            for var, chk in [
                (var_R, chk_R),
                (var_L, chk_L),
                (var_C, chk_C),
            ]:
                if not var.get() and count >= 2:
                    chk.configure(state="disabled")
                else:
                    chk.configure(state="normal")

        chk_R.configure(command=update_fixed_states)
        chk_L.configure(command=update_fixed_states)
        chk_C.configure(command=update_fixed_states)
        update_fixed_states()

        # ===== callback do botão CALCULAR =====
        def on_calculate():
            # f0 alvo
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

            # Componentes fixos (opcionais)
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

            # Se R não foi dado, usa 1 Ω só para conseguir calcular Q aproximado
            R_for_calc = R_fixed if R_fixed is not None else 1.0

            try:
                results = design_rlc_for_target_f0(
                    target_f0_hz=target_f0_hz,
                    R_fixed=R_for_calc,
                    L_candidates_h=L_candidates,
                    C_candidates_f=C_candidates,
                    max_results=50,
                    max_error_pct=50.0,
                )
            except Exception as e:
                msgbox.showerror("Erro no cálculo", f"Ocorreu um erro no projeto inverso:\n{e}")
                return

            for w in results_frame.winfo_children():
                w.destroy()

            if not results:
                msgbox.showinfo(
                    "Nenhuma combinação",
                    "Não foram encontradas combinações L/C dentro do erro máximo configurado.",
                )
                return

            # mostrar resultados usando as unidades "naturais" (H/F) com prefixo
            for res in results:
                row = ctk.CTkFrame(results_frame, fg_color=("#2b2b2b", "#2b2b2b"), corner_radius=4)
                row.pack(fill="x", padx=2, pady=2)
                row.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

                L_H = res["L_H"]
                C_F = res["C_F"]
                f0_calc = res["f0_calc_Hz"]
                err = res["error_pct"]
                Q_val = res["Q"]

                # formatação simples de engenharia
                def fmt_eng(val, kind):
                    if kind == "L":
                        unit_tbl = [("H", 1.0), ("mH", 1e-3), ("µH", 1e-6)]
                    else:
                        unit_tbl = [("F", 1.0), ("mF", 1e-3), ("µF", 1e-6), ("nF", 1e-9)]
                    for u, fac in unit_tbl:
                        if abs(val) >= fac:
                            return f"{val/fac:.4g} {u}"
                    return f"{val:.4g}"

                ctk.CTkLabel(row, text=fmt_eng(L_H, "L"), font=("Arial", 11)).grid(row=0, column=0, padx=5, sticky="w")
                ctk.CTkLabel(row, text=fmt_eng(C_F, "C"), font=("Arial", 11)).grid(row=0, column=1, padx=5, sticky="w")
                ctk.CTkLabel(row, text=f"{f0_calc:.2f} Hz", font=("Arial", 11)).grid(row=0, column=2, padx=5)
                ctk.CTkLabel(row, text=f"{err:.2f} %", font=("Arial", 11)).grid(row=0, column=3, padx=5)
                ctk.CTkLabel(row, text=f"{Q_val:.2f}", font=("Arial", 11)).grid(row=0, column=4, padx=5)

        btn_calc.configure(command=on_calculate)

        # Botão fechar no rodapé
        btn_close = ctk.CTkButton(
            root_frame,
            text="Fechar",
            fg_color="#555555",
            command=popup.destroy,
        )
        btn_close.pack(pady=(6, 0))

    # ----------------------------------------------------------------------
    # Carregamento de curvas
    # ----------------------------------------------------------------------
    def load_and_add_curve(self):
        exp_dir = filedialog.askdirectory(
            initialdir=self.dm.save_dir, title="Selecione o Experimento"
        )
        if not exp_dir:
            return

        exp_name = os.path.basename(exp_dir)

        df_exp, meta_exp = self.dm.load_experiment_data(exp_name)
        df_theory, meta_theory = self.dm.load_theoretical_data(exp_name)

        metrics_default = {"f0": 0, "Q": 0, "BW": 0, "f1": 0, "f2": 0}

        if df_exp is not None:
            v_in = float(meta_exp.get("V_in", 1.0))
            df_exp = df_exp.copy()
            df_exp["Gain"] = df_exp["V_Resistor"] / v_in

            metrics = meta_exp.get("metrics", metrics_default)

            data = {
                "name": exp_name + " (Prático)",
                "type": "exp",
                "data": df_exp,
                "metrics": metrics,
            }

            try:
                fit_result = fit_bandpass_rlc(
                    df_exp["Frequency"].to_numpy(),
                    df_exp["Gain"].to_numpy(),
                )
            except Exception:
                fit_result = None

            data["fit_result"] = fit_result

        elif meta_theory is not None:
            df_final, metrics = reconstruct_theoretical_curve(meta_theory)
            data = {
                'name': exp_name + " (Teórico)",
                'type': 'theory',
                'data': df_final,
                'metrics': metrics or metrics_default,
            }

        else:
            msgbox.showerror("Erro", f"Pasta '{exp_name}' não contém dados válidos.")
            return

        new_key = data["name"] + "_" + str(datetime.now().timestamp())
        self.active_curves[new_key] = data
        self._init_curve_state(new_key)

        self._update_metrics_list_ui(focused_key=new_key)
        self.plot_curves(focused_key=new_key)

        current_window = self.master.winfo_toplevel()
        current_window.lift()
        current_window.attributes("-topmost", True)
        current_window.after_idle(current_window.attributes, "-topmost", False)

    # ----------------------------------------------------------------------
    # Plot
    # ----------------------------------------------------------------------
    def plot_curves(self, focused_key=None):
        self.ax.clear()

        if not self.active_curves:
            self.ax.set_title("Nenhum Dado para Análise.", color="gray")
            self.ax.axis("off")
            self.canvas.draw()
            return

        if focused_key is not None:
            self.current_focus_key = focused_key
        elif self.current_focus_key not in self.active_curves:
            self.current_focus_key = next(iter(self.active_curves), None)
        key_to_focus = self.current_focus_key

        colors = ["#1055CC", "#FF8C00", "#00C853", "#FF4500", "#8A2BE2"]
        all_freqs = []
        max_gain_global = 0.0

        self.ax.set_title(
            f"Comparação Dinâmica ({len(self.active_curves)} Curva(s))",
            color="white",
        )
        self.ax.set_ylabel("Ganho normalizado (Vout/Vin)", color="white")
        self.ax.grid(True, which="both", alpha=0.3, color="gray")

        curve_handles = []
        curve_labels = []
        marker_handles = []
        marker_labels = []

        # --- Curvas e pontos ---
        for i, (key, curve) in enumerate(self.active_curves.items()):
            color = colors[i % len(colors)]
            curve_type = curve["type"]
            data = curve["data"]

            freqs = np.asarray(data["Frequency"], dtype=float)
            gains = np.asarray(data["Gain"], dtype=float)

            mask_valid = np.isfinite(freqs) & np.isfinite(gains) & (freqs > 0)
            if np.count_nonzero(mask_valid) == 0:
                continue

            freqs = freqs[mask_valid]
            gains = gains[mask_valid]

            peak = float(np.nanmax(gains))
            if peak <= 0:
                continue

            gain_norm = gains / peak
            curve["_freqs_raw"] = freqs
            curve["_gain_norm_raw"] = gain_norm

            all_freqs.extend(freqs.tolist())
            max_gain_global = max(max_gain_global, float(np.nanmax(gain_norm)))

            alpha = 1.0 if key == key_to_focus else 0.7

            line_x = freqs
            line_y = gain_norm
            label_suffix = ""

            if curve_type == "exp":
                use_fit = (
                    curve.get("use_fit_var") is not None
                    and curve["use_fit_var"].get()
                    and curve.get("fit_result") is not None
                )
                if use_fit:
                    fit = curve["fit_result"]
                    f_fit = np.asarray(fit["freq_smooth"], dtype=float)
                    g_fit = np.asarray(fit["gain_smooth"], dtype=float)
                    if np.nanmax(g_fit) > 0:
                        g_fit_norm = g_fit / np.nanmax(g_fit)
                    else:
                        g_fit_norm = g_fit
                    curve["_freqs_fit"] = f_fit
                    curve["_gain_norm_fit"] = g_fit_norm
                    line_x = f_fit
                    line_y = g_fit_norm
                    label_suffix = " (ajuste)"

            # Linha principal
            line = self.ax.plot(
                line_x,
                line_y,
                "-",
                color=color,
                linewidth=2.0 if curve_type == "theory" else 1.8,
                alpha=alpha,
            )[0]
            curve_handles.append(line)
            curve_labels.append(curve["name"] + label_suffix)

            # Pontos originais (controlados por checkbox)
            if curve_type == "exp":
                show_points = (
                    curve.get("show_points_var") is None
                    or curve["show_points_var"].get()
                )
                if show_points:
                    self.ax.plot(
                        freqs,
                        gain_norm,
                        "o",
                        color=color,
                        markersize=4,
                        alpha=0.9 if key == key_to_focus else 0.6,
                    )

        # --- Eixo X/Y ---
        if all_freqs:
            freqs_array = np.array(all_freqs, dtype=float)
            setup_frequency_axis(self.ax, freqs_array)

            if max_gain_global > 0:
                self.ax.set_ylim(0, max_gain_global * 1.1)
            else:
                self.ax.set_ylim(0, 1.1)

        # --- f0, f1, f2 por curva ---
        for key, curve in self.active_curves.items():
            metrics = curve["metrics"] or {}
            f0 = metrics.get("f0", 0.0)
            f1_val = metrics.get("f1", 0.0)
            f2_val = metrics.get("f2", 0.0)

            show_f0 = (
                curve.get("show_f0_var").get() if "show_f0_var" in curve else False
            )
            show_f1f2 = (
                curve.get("show_f1f2_var").get()
                if "show_f1f2_var" in curve
                else False
            )

            curve_label = curve["name"]

            if show_f0 and f0 > 0:
                lbl = f"f₀ – {curve_label}"
                line = self.ax.axvline(
                    x=f0,
                    color="red",
                    alpha=0.8,
                    linestyle="--",
                    label=lbl,
                )
                marker_handles.append(line)
                marker_labels.append(lbl)

            if show_f1f2:
                if f1_val > 0:
                    lbl = f"f₁ – {curve_label}"
                    line = self.ax.axvline(
                        x=f1_val,
                        color="aqua",
                        alpha=0.7,
                        linestyle=":",
                        label=lbl,
                    )
                    marker_handles.append(line)
                    marker_labels.append(lbl)

                if f2_val > 0:
                    lbl = f"f₂ – {curve_label}"
                    line = self.ax.axvline(
                        x=f2_val,
                        color="aqua",
                        alpha=0.7,
                        linestyle=":",
                        label=lbl,
                    )
                    marker_handles.append(line)
                    marker_labels.append(lbl)

        # --- Linha de meia potência da curva em foco ---
        if key_to_focus in self.active_curves:
            curve = self.active_curves[key_to_focus]
            gain_focus = (
                curve.get("_gain_norm_fit")
                if curve.get("use_fit_var") is not None
                and curve["use_fit_var"].get()
                and curve.get("_gain_norm_fit") is not None
                else curve.get("_gain_norm_raw")
            )
            if gain_focus is not None and len(gain_focus) > 0:
                max_gain_focus = float(np.nanmax(gain_focus))
                if max_gain_focus > 0:
                    target = max_gain_focus / np.sqrt(2.0)
                    hp = self.ax.axhline(
                        y=target,
                        color="darkgray",
                        alpha=0.6,
                        linestyle="-",
                    )
                    marker_handles.append(hp)
                    marker_labels.append(f"Meia potência – {curve['name']}")

        # --- Legendas separadas ---
        if curve_handles:
            leg1 = self.ax.legend(
                curve_handles,
                curve_labels,
                loc="upper right",
                fontsize="small",
                title="Curvas",
            )
            self.ax.add_artist(leg1)

        if marker_handles:
            self.ax.legend(
                marker_handles,
                marker_labels,
                loc="upper left",
                fontsize="small",
                title="Marcadores",
            )

        self.canvas.draw()

    # ----------------------------------------------------------------------
    # Reconstrução teórica
    # ----------------------------------------------------------------------
    def _simulate_theoretical_data(self, params):
        def get_multiplier(unit_str):
            table = {
                "Ω": 1,
                "kΩ": 1e3,
                "MΩ": 1e6,
                "H": 1,
                "mH": 1e-3,
                "µH": 1e-6,
                "mF": 1e-3,
                "µF": 1e-6,
                "nF": 1e-9,
                "pF": 1e-12,
            }
            return table.get(unit_str, 1.0)

        R = float(params["R"]) * get_multiplier(params["R_unit"])
        L = float(params["L"]) * get_multiplier(params["L_unit"])
        C = float(params["C"]) * get_multiplier(params["C_unit"])

        metrics = params["metrics"]
        f0 = metrics["f0"]

        def get_H(f, R, L, C):
            w = 2 * np.pi * f
            Xc = 1 / (w * C + 1e-15)
            Xl = w * L
            Z = np.sqrt(R**2 + (Xl - Xc) ** 2)
            return R / Z

        freqs = np.logspace(np.log10(f0 * 0.2), np.log10(f0 * 5), 600)
        gain_curve = get_H(freqs, R, L, C)
        peak = np.max(gain_curve)
        if peak > 0:
            gain_curve = gain_curve / peak

        df = pd.DataFrame({"Frequency": freqs, "Gain": gain_curve})
        return df, metrics

    # ----------------------------------------------------------------------
    # Salvamento
    # ----------------------------------------------------------------------
    def save_comparison_gui(self):
        if not self.active_curves:
            msgbox.showerror("Erro", "Nenhuma curva ativa para salvar!")
            return

        file_path = filedialog.asksaveasfilename(
            initialdir=self.dm.save_dir,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg")],
            title="Salvar Comparação de Análise",
        )

        if file_path:
            try:
                self.fig.savefig(file_path, bbox_inches="tight")

                data_to_save = {
                    "metadata_comparacao": {
                        "num_curvas": len(self.active_curves),
                        "title": self.ax.get_title(),
                        "saved_timestamp": str(datetime.now()),
                    },
                    "curvas_comparadas": {},
                }

                for name, curve in self.active_curves.items():
                    data_to_save["curvas_comparadas"][name] = {
                        "tipo": curve["type"],
                        "f0": curve["metrics"]["f0"],
                        "Q": curve["metrics"]["Q"],
                        "pontos_csv": curve["data"][
                            ["Frequency", "Gain"]
                        ].to_json(orient="records"),
                    }

                json_path = file_path.rsplit(".", 1)[0] + "_metadata.json"
                with open(json_path, "w") as f:
                    json.dump(data_to_save, f, indent=4)

                msgbox.showinfo(
                    "Sucesso",
                    f"Comparação salva em:\n{os.path.dirname(file_path)}",
                )

            except Exception as e:
                msgbox.showerror(
                    "Erro", f"Falha ao salvar a comparação: {e}"
                )