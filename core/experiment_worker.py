import threading
import time
import numpy as np

class ExperimentWorker(threading.Thread):
    def __init__(self, connection_manager, start_f, stop_f, steps, vin, callback_step, callback_finish):
        super().__init__()
        self.manager = connection_manager
        self.start_f = start_f
        self.stop_f = stop_f
        self.steps = steps
        self.vin = vin
        self.callback_step = callback_step   # Função para atualizar gráfico a cada ponto
        self.callback_finish = callback_finish # Função para chamar quando acabar
        self.running = True
        self.daemon = True # Mata a thread se fechar o app

    def run(self):
        afg = self.manager.afg
        dpo = self.manager.dpo

        # 1. Configuração Inicial
        try:
            # Gerar frequências (Escala Logarítmica é melhor para Bode Plot)
            frequencies = np.logspace(np.log10(self.start_f), np.log10(self.stop_f), self.steps)
            
            # Configura Hardware
            afg.set_impedance_high_z()
            afg.set_waveform("SIN", self.start_f, self.vin)
            afg.output_on()

            dpo.configure_channel(1, scale=self.vin/2) # Escala inicial segura
            dpo.setup_measurement_vpp(1)
            
            time.sleep(5) # Estabilização inicial

            results = [] # Lista para guardar (freq, vpp)

            # 2. Loop de Varredura
            for i, freq in enumerate(frequencies):
                if not self.running: break

                # Setar Frequência
                afg.set_frequency(freq)
                
                # Ajustar Base de Tempo do Scope (importante para ler correto)
                # Regra prática: manter ~2 a 5 ciclos na tela. T = 1/f.
                # 3 ciclos = 3/f. Timebase (sec/div) tem 10 div -> (3/f)/10
                period = 1/freq
                dpo.configure_timebase(scale=(period * 3) / 10)
                
                # Pequeno delay para o Scope sincronizar o Trigger
                time.sleep(0.5)

                # Ler Vpp
                vpp = dpo.get_vpp()

                # Auto-Range Vertical Simplificado (se Vpp for muito pequeno ou clipar)
                # (Pode ser refinado depois, por enquanto vamos confiar na leitura)

                # Salvar e Notificar GUI
                data_point = (freq, vpp)
                results.append(data_point)
                
                # Chama a função da GUI para plotar (passa o progresso e o ponto)
                progress = (i + 1) / self.steps
                self.callback_step(data_point, progress)

        except Exception as e:
            print(f"Erro no Worker: {e}")
        
        finally:
            afg.output_off()
            self.callback_finish(results)

    def stop(self):
        self.running = False