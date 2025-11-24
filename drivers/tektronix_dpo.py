import time
from .instrument_base import InstrumentDriver

class TektronixDPO(InstrumentDriver):
    def configure_channel(self, channel=1, scale=1.0, position=0):
        """Configura escala vertical (Volts/div)"""
        self.write(f"CH{channel}:COUPling DC")
        self.write(f"CH{channel}:SCAle {scale}")
        self.write(f"CH{channel}:POSition {position}")

    def configure_timebase(self, scale=1e-3):
        """Configura escala horizontal (Segundos/div)"""
        self.write(f"HORizontal:SCAle {scale}")

    def setup_measurement_vpp(self, channel=1):
        """Prepara o osciloscópio para medir Vpp no canal especificado"""
        self.write(f"MEASUrement:IMMed:SOUrce1 CH{channel}")
        self.write("MEASUrement:IMMed:TYPe PK2Pk")

    def get_vpp(self):
        """Lê o valor medido imediatamente"""
        try:
            val = self.query("MEASUrement:IMMed:VALue?")
            return float(val)
        except:
            return 0.0

    def auto_set(self):
        """Executa o Autoset (Útil para setup inicial, evitar usar no loop)"""
        self.write("AUTOSet EXECute")
        # O Autoset demora, precisamos esperar terminar
        time.sleep(3)