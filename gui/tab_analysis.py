# gui/tab_analysis.py

import customtkinter as ctk

from gui.analysis_view_manager import AnalysisViewManager


class TabAnalysis:
    """
    Aba de 'Análise de Dados'.

    Cria uma instância de AnalysisViewManager embutida na aba e
    fornece um callback para abrir uma janela flutuante com outra
    instância de análise (útil para comparar em paralelo).
    """

    def __init__(self, parent_frame, data_manager):
        self.parent = parent_frame
        self.data_manager = data_manager

        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)

        self.main_view = AnalysisViewManager(
            self.parent,
            data_manager=self.data_manager,
            initial_curves=None,
            is_floating=False,
        )
        self.main_view.grid(row=0, column=0, sticky="nsew")

        # Conecta o callback para abrir nova janela
        self.main_view.set_open_window_callback(self.open_floating_window)

    def open_floating_window(self):
        """
        Abre uma nova janela (Toplevel) contendo outra instância de AnalysisViewManager.
        A nova janela pode receber as curvas ativas da janela principal, se desejado.
        """
        top = ctk.CTkToplevel(self.parent)
        top.title("Análise de Dados - Janela Flutuante")
        top.geometry("1100x700")

        view = AnalysisViewManager(
            top,
            data_manager=self.data_manager,
            initial_curves=self.main_view.active_curves.copy(),
            is_floating=True,
        )
        view.pack(fill="both", expand=True)