
import machine
import rp2
import time
from machine import Pin

# ==========================================
# KONFIGURATION
# ==========================================

# Overclocking
CPU_FREQ = 240_000_000
machine.freq(CPU_FREQ)

# Mikrofone
MIC1_PIN = Pin(2, Pin.IN, Pin.PULL_DOWN)
MIC2_PIN = Pin(3, Pin.IN, Pin.PULL_DOWN)

# Abstand zwischen den Mikrofonen in mm
MIC_DISTANCE_MM = 500.0

# Geschätzte Wellengeschwindigkeit im Holz
# Muss experimentell kalibriert werden!
WAVE_SPEED = 1250.0

# Korrektur der Startzeitdifferenz beider PIOs
OFFSET_COUNTS = 0

# ==========================================
# PIO ZEITMESSUNG
# ==========================================

@rp2.asm_pio()
def edge_counter():

    # 32-Bit-Abwärtszähler starten
    mov(y, invert(null))

    label("count_loop")

    # Auf steigende Flanke warten
    jmp(pin, "finished")

    # Zähler reduzieren
    jmp(y_dec, "count_loop")

    label("finished")

    # Restwert übertragen
    mov(isr, y)
    push(block)


# ==========================================
# PIO STATE MACHINES
# ==========================================

sm1 = rp2.StateMachine(
    0,
    edge_counter,
    freq=CPU_FREQ,
    jmp_pin=MIC1_PIN
)

sm2 = rp2.StateMachine(
    1,
    edge_counter,
    freq=CPU_FREQ,
    jmp_pin=MIC2_PIN
)


def arm(sm):
    sm.active(0)
    sm.restart()

    while sm.rx_fifo():
        sm.get()

    sm.active(1)


# ==========================================
# MESSUNG
# ==========================================

def measure():

    # Beide Messungen starten
    arm(sm1)
    arm(sm2)

    start = time.ticks_ms()

    result1 = None
    result2 = None

    # Auf beide Mikrofone warten
    while True:

        if result1 is None and sm1.rx_fifo():
            result1 = sm1.get()

        if result2 is None and sm2.rx_fifo():
            result2 = sm2.get()

        if result1 is not None and result2 is not None:
            break

        if time.ticks_diff(time.ticks_ms(), start) > 2000:
            sm1.active(0)
            sm2.active(0)
            return None

    # Abwärtszähler in aufwärtszählende Werte umwandeln
    count1 = 0xFFFFFFFF - result1
    count2 = 0xFFFFFFFF - result2

    # Differenz der Zählerstände
    delta_counts = count2 - count1 - OFFSET_COUNTS

    # Zwei PIO-Instruktionen pro Zählschleife
    delta_time = (delta_counts * 2) / CPU_FREQ

    # Position relativ zu Mikrofon 1
    distance = (
        MIC_DISTANCE_MM -
        WAVE_SPEED * delta_time * 1000
    ) / 2

    return delta_time, distance


# ==========================================
# HAUPTPROGRAMM
# ==========================================

print("Mikrofon-Messsystem gestartet")
print("CPU-Takt:", machine.freq() / 1_000_000, "MHz")

while True:

    result = measure()

    if result is not None:

        dt, distance = result

        print(
            "Zeitdifferenz:",
            round(dt * 1_000_000, 3),
            "us | Position:",
            round(distance, 2),
            "mm"
        )

    else:
        print("Timeout: Kein Impuls an beiden Mikrofonen")

    time.sleep_ms(50)
