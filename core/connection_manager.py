import pyvisa
from drivers.tektronix_afg import TektronixAFG
from drivers.tektronix_dpo import TektronixDPO

class ConnectionManager:
    def __init__(self):
        self.rm = pyvisa.ResourceManager()
        self.afg = None # Guarda a instância do Gerador
        self.dpo = None # Guarda a instância do Osciloscópio

    def scan_and_connect(self):
        """
        Varre recursos conectados, identifica pelo IDN e conecta.
        Retorna um dicionário com o status.
        """
        status = {
            "afg_connected": False,
            "afg_name": "Não encontrado",
            "dpo_connected": False,
            "dpo_name": "Não encontrado",
            "errors": []
        }

        try:
            resources = self.rm.list_resources()
        except Exception as e:
            status["errors"].append(f"Erro ao listar recursos: {str(e)}")
            return status

        print(f"Recursos encontrados: {resources}")

        for res in resources:
            try:
                # Abre temporariamente para perguntar quem é
                temp_inst = self.rm.open_resource(res)
                idn = temp_inst.query("*IDN?").strip()
                temp_inst.close()

                # Lógica de Identificação (Heurística)
                if "AFG" in idn:
                    self.afg = TektronixAFG(res, self.rm)
                    self.afg.connect()
                    status["afg_connected"] = True
                    status["afg_name"] = idn
                
                elif "DPO" in idn or "MSO" in idn or "TDS" in idn:
                    self.dpo = TektronixDPO(res, self.rm)
                    self.dpo.connect()
                    status["dpo_connected"] = True
                    status["dpo_name"] = idn

            except Exception as e:
                status["errors"].append(f"Falha ao interrogar {res}: {str(e)}")

        return status

    def close_all(self):
        if self.afg: self.afg.disconnect()
        if self.dpo: self.dpo.disconnect()

    def verify_connectivity(self):
        """
        Verifica se os instrumentos conectados ainda respondem.
        Retorna True se ambos estiverem OK, False caso contrário.
        """
        try:
            if self.afg and self.afg.connected:
                self.afg.query("*OPC?") # Operation Complete Query (ping rápido)
            else:
                return False

            if self.dpo and self.dpo.connected:
                self.dpo.query("*OPC?")
            else:
                return False
            
            return True
        except:
            return False