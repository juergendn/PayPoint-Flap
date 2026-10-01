"""Gemeinsame Ausnahme aller Treiber.

Kern und Modus fangen nur diese eine Ausnahme und setzen daraufhin das Fach auf
`gestoert` – sie müssen nicht wissen, ob Modbus, Seriell oder etwas anderes klemmt.
"""


class HardwareFehler(Exception):
    pass
