from .instrument_base import InstrumentDriver

class TektronixAFG(InstrumentDriver):
    def set_impedance_high_z(self):
        # Garante que o gerador não assuma carga de 50 ohms, 
        # o que dobraria a voltagem lida se o circuito for de alta impedância.
        self.write("OUTPut1:IMPedance INFinity")

    def set_waveform(self, shape="SIN", frequency=1000, amplitude=1.0, offset=0):
        """
        Configura a onda completa.
        shape: SIN, SQU, RAMP, PULS, etc.
        amplitude: Vpp (Pico a Pico)
        """
        self.write(f"SOURce1:FUNCtion:SHAPe {shape}")
        self.write(f"SOURce1:FREQuency:FIXed {frequency}")
        self.write(f"SOURce1:VOLTage:LEVel:IMMediate:AMPlitude {amplitude}")
        self.write(f"SOURce1:VOLTage:LEVel:IMMediate:OFFSet {offset}")

    def set_frequency(self, frequency):
        self.write(f"SOURce1:FREQuency:FIXed {frequency}")

    def output_on(self):
        self.write("OUTPut1:STATe ON")

    def output_off(self):
        self.write("OUTPut1:STATe OFF")