from itertools import cycle

def spectrum_calc(bitrate_history):
    #licycle = cycle(bitrate_history)

    zh = 0
    zt = 0
    second_half_total = 0
    for br1 in bitrate_history:
        for br,j in zip(bitrate_history, bitrate_history[1:]):
            zi = 0
            if j == br:
                zh += br
                zi += 1
            if zi == 0:
                zi = 1
        second_half = (br1 - (1 / zi) * zh) ** 2
        second_half_total += second_half
        zt += 1
    #print second_half_total
    spectrum = zt * second_half
    return spectrum