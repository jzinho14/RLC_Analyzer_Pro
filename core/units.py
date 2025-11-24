# core/units.py

"""
Módulo: units
=============

Define tabelas de conversão de unidades para os componentes do circuito RLC
e funções utilitárias para trabalhar com múltiplos de engenharia.

Componentes cobertos:
- Resistores: ohm, mili-ohm, quilo-ohm, mega-ohm
- Indutores: henry, mili-henry, micro-henry, nano-henry
- Capacitores: farad, mili-farad, micro-farad, nano-farad, pico-farad

A ideia é centralizar os multiplicadores em um único lugar para que
a GUI apenas consulte as unidades disponíveis e converta valores de
entrada para o SI (Ω, H, F) de forma consistente.
"""

# =============================
# Unidades de Resistência
# =============================
RESISTOR_UNITS = {
    "Ω": 1.0,
    "kΩ": 1e3,
    "MΩ": 1e6,
}

# =============================
# Unidades de Indutância
# =============================
INDUCTOR_UNITS = {
    "H": 1.0,
    "mH": 1e-3,
    "µH": 1e-6,
    "nH": 1e-9,
}

# =============================
# Unidades de Capacitância
# =============================
CAPACITOR_UNITS = {
    "F": 1.0,
    "mF": 1e-3,
    "µF": 1e-6,
    "nF": 1e-9,
    "pF": 1e-12,
}

# =============================
# Unidades de Frequência
# =============================
FREQUENCY_UNITS = {
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "GHz": 1e9,
}

# =============================
# Função genérica de multiplicador
# =============================
def get_multiplier(unit: str) -> float:
    """Retorna o multiplicador numérico baseado na unidade fornecida."""
    # busca em todos os dicionários
    for table in (RESISTOR_UNITS, INDUCTOR_UNITS, CAPACITOR_UNITS, FREQUENCY_UNITS):
        if unit in table:
            return table[unit]
    return 1.0
