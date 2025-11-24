import pyvisa
from abc import ABC, abstractmethod

class InstrumentDriver(ABC):
    def __init__(self, resource_name: str, resource_manager: pyvisa.ResourceManager):
        self.resource_name = resource_name
        self.rm = resource_manager
        self.instrument = None
        self.connected = False

    def connect(self):
        try:
            self.instrument = self.rm.open_resource(self.resource_name)
            # Timeout padrão de 5s para evitar travamentos longos
            self.instrument.timeout = 5000 
            self.connected = True
            print(f"Conectado a: {self.get_idn()}")
        except Exception as e:
            self.connected = False
            print(f"Erro ao conectar em {self.resource_name}: {e}")
            raise e

    def disconnect(self):
        if self.instrument:
            self.instrument.close()
            self.connected = False

    def write(self, command):
        if self.connected:
            self.instrument.write(command)

    def query(self, command):
        if self.connected:
            return self.instrument.query(command).strip()
        return None

    def get_idn(self):
        return self.query("*IDN?")

    def reset(self):
        self.write("*RST")
        self.write("*CLS") # Limpa status register