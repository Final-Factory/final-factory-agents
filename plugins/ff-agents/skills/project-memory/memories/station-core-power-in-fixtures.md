# A Station Core powers a small fixture by itself

**Fact.** A Station Core supplies about 418 kW to its grid (Station Info read "11.0kW of 418.0kW"
on a flat-map fixture with an Assembler, a Laser Turret, a Power Transmitter, a Battery, a
Capacitor and three Solar Panels; built player of FinalFactory master 07b0492f06, lothdesktop,
2026-11-13, w4062). Switching every Solar Panel off by circuit left the Battery charging: its charge
rose 6114 -> 6510 over 64 heartbeats.

**Apply.** A scenario that needs a Battery or Capacitor *discharging* (or at 0 %) needs a load above
the core's supply, or storage on a grid the core does not feed. Do not assert "charge falls" just
because the producers are off; read Station Info first. A storage at full can stand in through a
Capacitor that fills fast.
