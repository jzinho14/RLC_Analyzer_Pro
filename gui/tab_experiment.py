import customtkinter as ctk
import threading
import matplotlib.pyplot as plt
import os
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from core.experiment_worker import ExperimentWorker
import tkinter.messagebox as msgbox
from tkinter import filedialog
import numpy as np

class TabExperiment:
    def __init__(self, parent_frame, conn_manager, data_manager):
        self.parent = parent_frame
        self.manager = conn_manager
        self.worker = None 
        self.data_manager = data_manager
        self.last_results = None 
        self.last_metrics = {} # CORREÇÃO: Inicializar a variável

        self.parent.grid_columnconfigure(1, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(self.parent, width=300, corner_radius=0, label_text="Controles")
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self._build_connection_panel()
        self._build_sweep_panel()

        self.view_area = ctk.CTkFrame(self.parent, corner_radius=10)
        self.view_area.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        self._init_plot()
        
    def _analyze_sweep_data(self, df):
        """Calcula f0, Q, BW, f1, f2 a partir dos dados brutos do sweep."""
        if df.empty:
            return {'f0': 0, 'Q': 0, 'BW': 0, 'f1': 0, 'f2': 0}
            
        max_v = df['V_Resistor'].max()
        v_in = float(self.entry_vin.get())
        max_gain = max_v / v_in
        
        f0_idx = df['V_Resistor'].idxmax()
        f0_exp = df.loc[f0_idx, 'Frequency']
        
        target_gain = max_gain / np.sqrt(2)
        
        df_low = df[df['Frequency'] < f0_exp]
        f1_exp = df_low.loc[(np.abs(df_low['V_Resistor'] / v_in - target_gain)).idxmin(), 'Frequency'] if not df_low.empty else 0
        
        df_high = df[df['Frequency'] > f0_exp]
        f2_exp = df_high.loc[(np.abs(df_high['V_Resistor'] / v_in - target_gain)).idxmin(), 'Frequency'] if not df_high.empty else 0
        
        BW_exp = f2_exp - f1_exp
        Q_exp = f0_exp / BW_exp if BW_exp > 0 else 0
        
        return {'f0': f0_exp, 'Q': Q_exp, 'BW': BW_exp, 'f1': f1_exp, 'f2': f2_exp}


    def _build_connection_panel(self):
        lbl_title = ctk.CTkLabel(self.sidebar, text="Conexão Instrumentos", font=("Roboto", 16, "bold"))
        lbl_title.pack(pady=(20, 10), padx=10)

        self.btn_connect = ctk.CTkButton(
            self.sidebar, 
            text="Buscar Instrumentos (Auto)", 
            command=self.run_connection_thread,
            fg_color="#1f6aa5"
        )
        self.btn_connect.pack(pady=10, padx=20, fill="x")

        self.status_frame_afg = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.status_frame_afg.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.status_frame_afg, text="Gerador (AFG):", font=("Arial", 12, "bold")).pack(anchor="w")
        self.lbl_status_afg = ctk.CTkLabel(self.status_frame_afg, text="Desconectado", text_color="gray")
        self.lbl_status_afg.pack(anchor="w", padx=10)

        self.status_frame_dpo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.status_frame_dpo.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.status_frame_dpo, text="Osciloscópio (DPO):", font=("Arial", 12, "bold")).pack(anchor="w")
        self.lbl_status_dpo = ctk.CTkLabel(self.status_frame_dpo, text="Desconectado", text_color="gray")
        self.lbl_status_dpo.pack(anchor="w", padx=10)
        
        ctk.CTkProgressBar(self.sidebar, height=2).pack(fill="x", padx=10, pady=20)


    def _build_sweep_panel(self):
        lbl_sweep = ctk.CTkLabel(self.sidebar, text="Configuração Sweep", font=("Roboto", 16, "bold"))
        lbl_sweep.pack(pady=(0, 10), padx=10)

        ctk.CTkLabel(self.sidebar, text="Start Freq (Hz):").pack(anchor="w", padx=20)
        self.entry_start = ctk.CTkEntry(self.sidebar)
        self.entry_start.pack(fill="x", padx=20)
        self.entry_start.insert(0, "100")

        ctk.CTkLabel(self.sidebar, text="Stop Freq (Hz):").pack(anchor="w", padx=20)
        self.entry_stop = ctk.CTkEntry(self.sidebar)
        self.entry_stop.pack(fill="x", padx=20)
        self.entry_stop.insert(0, "10000")

        ctk.CTkLabel(self.sidebar, text="Passos (Steps):").pack(anchor="w", padx=20)
        self.entry_step = ctk.CTkEntry(self.sidebar)
        self.entry_step.pack(fill="x", padx=20)
        self.entry_step.insert(0, "50")

        ctk.CTkLabel(self.sidebar, text="V entrada (Vpp):").pack(anchor="w", padx=20)
        self.entry_vin = ctk.CTkEntry(self.sidebar)
        self.entry_vin.pack(fill="x", padx=20, pady=(0, 20))
        self.entry_vin.insert(0, "2.0")

        # Barra de Progresso
        self.progress_bar = ctk.CTkProgressBar(self.sidebar)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=20, pady=10)

        # Botão Run com nova lógica de Start
        self.btn_run = ctk.CTkButton(
            self.sidebar, 
            text="INICIAR EXPERIMENTO", 
            state="disabled",
            fg_color="green",
            command=self.start_experiment_logic 
        )
        self.btn_run.pack(pady=10, padx=20, fill="x")

        self.btn_stop = ctk.CTkButton(
            self.sidebar, 
            text="PARAR", 
            state="disabled",
            fg_color="red",
            command=self.stop_experiment
        )
        self.btn_stop.pack(pady=5, padx=20, fill="x")

        self.btn_save = ctk.CTkButton(
            self.sidebar, 
            text="SALVAR EXPERIMENTO", 
            state="disabled",
            fg_color="#00695C", # Um verde escuro
            command=self.save_experiment_gui
        )
        self.btn_save.pack(pady=10, padx=20, fill="x")

    def experiment_finished(self, results):
        """Chamado quando termina a coleta de dados."""
        self.last_results = results 
        
        if results:
            df = pd.DataFrame(results, columns=['Frequency', 'V_Resistor'])
            self.last_metrics = self._analyze_sweep_data(df) 
        else:
            self.last_metrics = {}
            
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_save.configure(state="normal")
        self.progress_bar.set(1.0)
        msgbox.showinfo("Sucesso", f"Experimento finalizado com {len(results)} pontos. Pronto para salvar.")
    
    def save_experiment_gui(self):
        """Abre a janela nativa para selecionar o nome e local do arquivo."""
        if not self.last_results:
            msgbox.showerror("Erro", "Nenhum dado recente para salvar.")
            return

        file_path = filedialog.asksaveasfilename(
            initialdir=self.data_manager.save_dir, 
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Salvar Dados do Experimento (Definir Nome)"
        )

        if file_path:
            exp_name = os.path.basename(file_path).replace('.csv', '').replace('.CSV', '')
            
            metadata = {
                'R_nominal': self.entry_start.get(), 
                'Start_Freq': self.entry_start.get(),
                'Stop_Freq': self.entry_stop.get(), 
                'Steps': self.entry_step.get(),
                'C_usado': 'C1 (Capacitor Manual)', 
                'V_in': self.entry_vin.get(),
                'metrics': self.last_metrics 
            }
            
            try:
                self.data_manager.save_experiment(exp_name, self.last_results, metadata)
                msgbox.showinfo("Salvo", f"Experimento '{exp_name}' salvo em:\n{self.data_manager.save_dir}\n(Dentro da pasta {exp_name})")
                self.btn_save.configure(state="disabled")
                
            except Exception as e:
                msgbox.showerror("Erro de I/O", f"Falha ao salvar o arquivo: {e}")
        else:
            return

    def _init_plot(self):
        plt.style.use('dark_background') 
        
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.fig.patch.set_facecolor('#242424')
        
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#242424') 
        
        self.ax.set_title("Curva de Resposta em Frequência (Tempo Real)", color='white')
        self.ax.set_xlabel("Frequência (Hz)", color='white')
        self.ax.set_ylabel("Tensão Resistor (Vpp)", color='white')
        self.ax.set_xscale('log') 
        self.ax.grid(True, which="both", ls="--", alpha=0.3, color='gray')

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.view_area)
        self.canvas.draw()
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.view_area, pack_toolbar=False)
        self.toolbar.update()
        
        self.toolbar.pack(side='bottom', fill='x', padx=10, pady=5) 
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        self.x_data = []
        self.y_data = []
        self.line, = self.ax.plot([], [], 'o-', color='gold', linewidth=1.5, markersize=4)

    def start_experiment_logic(self):
        """
        1. Valida Inputs
        2. Safety Check (Ping instrumentos)
        3. Confirmação de Novo Sweep (NOVO)
        4. Inicia Worker
        """
        # Validação simples
        try:
            start = float(self.entry_start.get())
            stop = float(self.entry_stop.get())
            steps = int(self.entry_step.get())
            vin = float(self.entry_vin.get())
        except ValueError:
            msgbox.showerror("Erro", "Verifique os valores numéricos.")
            return

        # --- NOVO: Confirmação de Início ---
        if self.last_results is not None and self.btn_save.cget("state") == "normal":
            if not msgbox.askyesno(
                "Confirmação de Novo Experimento", 
                "Você tem resultados não salvos do experimento anterior.\n"
                "Iniciar um novo sweep irá APAGAR estes resultados.\n"
                "Deseja continuar?"
            ):
                return # Usuário cancelou
        # ------------------------------------

        # Safety Check 
        if not self.manager.verify_connectivity():
            msgbox.showerror("Erro de Conexão", "Instrumentos não respondem. Verifique os cabos e reconecte.")
            self.btn_run.configure(state="disabled")
            self.lbl_status_afg.configure(text="ERRO", text_color="red")
            self.lbl_status_dpo.configure(text="ERRO", text_color="red")
            return

        # Prepara UI
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_save.configure(state="disabled")
        self.x_data.clear()
        self.y_data.clear()
        self.line.set_data([], [])
        self.canvas.draw()

        # Inicia Thread
        self.worker = ExperimentWorker(
            self.manager, start, stop, steps, vin,
            callback_step=self.update_plot_step,
            callback_finish=self.experiment_finished
        )
        self.worker.start()

    def update_plot_step(self, data_point, progress):
        """Chamado pela Thread a cada ponto novo"""
        freq, vpp = data_point
        self.x_data.append(freq)
        self.y_data.append(vpp)
        
        self.progress_bar.set(progress)

        self.line.set_data(self.x_data, self.y_data)
        self.ax.relim() 
        self.ax.autoscale_view() 
        self.canvas.draw_idle() 

    def stop_experiment(self):
        if self.worker:
            self.worker.stop()

    def run_connection_thread(self):
        self.btn_connect.configure(state="disabled", text="Buscando...")
        t = threading.Thread(target=self._connect_logic)
        t.start()

    def _connect_logic(self):
        status = self.manager.scan_and_connect()
        self._update_status_ui(status)

    def _update_status_ui(self, status):
        self.btn_connect.configure(state="normal", text="Buscar Instrumentos (Auto)")
        if status['afg_connected']:
            self.lbl_status_afg.configure(text="CONECTADO", text_color="#4CAF50")
        else:
            self.lbl_status_afg.configure(text="NÃO ENCONTRADO", text_color="#F44336")
        if status['dpo_connected']:
            self.lbl_status_dpo.configure(text="CONECTADO", text_color="#4CAF50")
        else:
            self.lbl_status_dpo.configure(text="NÃO ENCONTRADO", text_color="#F44336")
        if status['afg_connected'] and status['dpo_connected']:
            self.btn_run.configure(state="normal")