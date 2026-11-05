import Time_Measure

import time

while True:
    delta_times = Time_Measure.measure()

    if delta_times is None:
        print("Zeitmessung: Timeout")
    else:
        labels = ("Pin 1-2", "Pin 1-3", "Pin 1-4")
        for label, delta_time in zip(labels, delta_times):
            print("{}: {:.6f} ms".format(label, delta_time * 1000))

    time.sleep_ms(1000)