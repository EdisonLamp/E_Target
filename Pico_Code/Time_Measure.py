import machine
import rp2
import time
from machine import Pin

# Overclocking
CPU_FREQ = 240_000_000
machine.freq(CPU_FREQ)

# Inputs
MIC1_PIN = Pin(2, Pin.IN, Pin.PULL_DOWN)
MIC2_PIN = Pin(3, Pin.IN, Pin.PULL_DOWN)
MIC3_PIN = Pin(4, Pin.IN, Pin.PULL_DOWN)
MIC4_PIN = Pin(5, Pin.IN, Pin.PULL_DOWN)

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

sm3 = rp2.StateMachine(
    2,
    edge_counter,
    freq=CPU_FREQ,
    jmp_pin=MIC3_PIN
)

sm4 = rp2.StateMachine(
    3,
    edge_counter,
    freq=CPU_FREQ,
    jmp_pin=MIC4_PIN
)

state_machines = (sm1, sm2, sm3, sm4)


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

    # Alle vier Messungen starten
    for sm in state_machines:
        arm(sm)

    start = time.ticks_ms()
    results = [None, None, None, None]

    # Auf alle vier Mikrofone warten
    while True:
        for index, sm in enumerate(state_machines):
            if results[index] is None and sm.rx_fifo():
                results[index] = sm.get()

        if all(result is not None for result in results):
            break

        if time.ticks_diff(time.ticks_ms(), start) > 2000:
            for sm in state_machines:
                sm.active(0)
            return None

    # Abwärtszähler in aufwärtszählende Werte umwandeln
    counts = [0xFFFFFFFF - result for result in results]
    reference_count = counts[0]

    # Zeiten von Pin 1 zu Pin 2, Pin 3 und Pin 4 in Sekunden
    delta_times = []
    for count in counts[1:]:
        delta_counts = count - reference_count - OFFSET_COUNTS
        # Zwei PIO-Instruktionen pro Zählschleife
        delta_times.append((delta_counts * 2) / CPU_FREQ)

    return tuple(delta_times)