import customtkinter as ctk
from core.connection_manager import ConnectionManager
from core.data_manager import DataManager
from .tab_experiment import TabExperiment
from .tab_simulator import TabSimulator
from .tab_analysis import TabAnalysis

class RLCApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configurações da Janela
        self.title("RLC Analyzer Pro - Tektronix Control")
        self.geometry("1200x800")
        
        # Instancia o Gerenciador de Hardware (Backend)
        self.conn_manager = ConnectionManager()
        self.data_manager = DataManager()

        # Layout de Grid (1x1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Criação das Abas
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Adicionando as Abas
        self.tab_view.add("Simulador Teórico")
        self.tab_view.add("Experimento & Controle")
        self.tab_view.add("Análise de Dados")

        # --- Configuração da Aba de Experimento ---
        # Criamos a classe específica para gerenciar o conteúdo dessa aba
        self.experiment_tab = TabExperiment(
            self.tab_view.tab("Experimento & Controle"), 
            self.conn_manager,
            self.data_manager
        )

        self.simulator_tab = TabSimulator(
            self.tab_view.tab("Simulador Teórico"),
            self.data_manager
        )

        self.analysis_tab = TabAnalysis(
            self.tab_view.tab("Análise de Dados"), # O 'parent_frame'
            self.data_manager # O 'data_manager'
        )
        
        # Corrigido: Dispor o frame da TabAnalysis para que ele ocupe o espaço da aba
        self.tab_view.tab("Análise de Dados").grid_rowconfigure(0, weight=1)
        self.tab_view.tab("Análise de Dados").grid_columnconfigure(0, weight=1)
        
        # Setar aba inicial
        self.tab_view.set("Simulador Teórico")

        # Auto detecção dos instrumentos
        self.after(500, lambda: self.experiment_tab.run_connection_thread())

    def on_closing(self):
        """Garante que fechamos as conexões ao sair"""
        self.conn_manager.close_all()
        self.destroy()