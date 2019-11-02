__author__ = 'pjuluri'

import config_dash
from adaptation.adaptation import calculate_rate_index
from adaptation.empirical_dash import empirical_dash


def basic_dash(segment_number, bitrates,
               segment_download_time, curr_rate, buffer_size, segment_size):
    """
    Module to predict the next_bitrate using the basic_dash algorithm
    :param segment_number: Current segment number
    :param bitrates: A tuple/list of available bitrates
    :param average_dwn_time: Average download time observed so far
    :param segment_download_time:  Time taken to download the current segment
    :param curr_rate: Current bitrate being used
    :return: next_rate : Bitrate for the next segment
    :return: updated_dwn_time: Updated average downlaod time
    """
    
    if segment_size == 0:
        curr_rate = 0
    else:
        curr_rate = (segment_size*8)/segment_download_time
    with open("vlc_dash-dl-rate.txt", "a") as outf:
        outf.write(str(segment_number) + '\t' + str(curr_rate) + '\n') # str(download_rate) + '\n')    
    config_dash.LOG.info("Current Rate%f"%curr_rate)
    '''
    if average_dwn_time > 0 and segment_number > 0:
        updated_dwn_time = (average_dwn_time * (segment_number + 1) + segment_download_time) / (segment_number + 1)
    else:
        updated_dwn_time = segment_download_time
    config_dash.LOG.debug("The average download time upto segment {} is {}. Before it was {}".format(segment_number,
                                                                                                     updated_dwn_time,
                                                                                                     average_dwn_time))

    '''
    
    bitrates = [float(i) for i in bitrates]
    bitrates.sort()
    buffer_sec = buffer_size * 2
    with open("vlc_buffer.txt", "a") as outf:
        outf.write(str(buffer_sec) + '\n') # str(download_rate) + '\n') 
#    for j in bitrates:
#        config_dash.LOG.info("Bitrates %f \n",j )
    buffer_size_sec = buffer_size * 2
    config_dash.LOG.info("Empirical DASH: Buffer Size %f"%buffer_size)
    with open("vlc-dl-rate.txt", "a") as buffera:
        buffera.write(str(curr_rate) + '\n')
    if buffer_size < 4 or curr_rate == 0:
        next_rate = bitrates[0]
        return next_rate
    elif curr_rate == bitrates[-1]:   
        next_rate = curr_rate   
    else:
        try:
            curr = bitrates.index(curr_rate)
        except ValueError:
            config_dash.LOG.error("Current Bitrate not in the bitrate lsit. Setting to minimum")
            curr = calculate_rate_index(bitrates, curr_rate) 
        next_rate=curr    
    return next_rate
'''
def empirical_dash(segment_number, bitrates, segment_download_time, curr_rate, 
                   buffer_size, segment_size, next_segment_sizes, video_segment_duration):

    BIN_SIZE = 50
    INITIAL_TRAIN = 5

    if segment_size == 0:
        curr_rate = 0
    else:
        curr_rate = (segment_size*8)/segment_download_time
    bitrates = [float(i) for i in bitrates]
    bitrates.sort()
    config_dash.LOG.info("VLC: Buffer Size %f"%buffer_size)
    print "-------------------------"
    bitrates_window4 = bitrate_history[-4:]
    bitrates_window8 = bitrate_history[-8:]
    bitrates_window16 = bitrate_history[-16:]
    br_spectrum = {}
    spectrums = []
    next_dl_times = []
    for n in (0,len(bitrates)):
        br_ratio = n / bitrates[-1]
        br_weight = (1 / br_ratio) ** (1 / bitrates.index(n))
        if float(next_segment_sizes[n])/weighted_dwn_rate > video_segment_duration:
            continue
        bitrates_window4 =  bitrates_window4.append(n)
        bitrates_window8 = bitrates_window8.append(n)
        bitrates_window16 = bitrates_window16.append(n)
        spectrum = (br_weight * spectrum(bitrates_window4)) + (br_weight * spectrum(bitrates_window8)) + (br_weight * spectrum(bitrates_window16))
        spectrums.append(spectrum)
        next_dl_time = next_segment_sizes[n] / curr_rate
        next_dl_times.append(next_dl_times)
        br_spectrum.update({bitrates[n]:spectrum})
    sorted_by_spectrum = sorted(br_spectrum.items(), key=operator.itemgetter(1))
    next_spectrum_rates = [i[0] for i in sorted_by_spectrum]

    max_to_min_size_ratio = next_segment_sizes[-1] / next_segment_sizes[0]

    if segment_number <= 10:
        if bitrates[-1] / curr_rate <= video_segment_duration:
            if segment_number <= min(INITIAL_TRAIN, max_to_min_ratio):
                next_rate = bitrates[0]
                return next_rate

            else:
                q_layer = (segment_number - 5) * 2 ** (segment_number - 5)
                if q_layer <= len(bitrates):
                    for i in range(q_layer, q_layer/2, -1):
                        if bitrates[q_layer] / curr_rate <= video_segment_duration:
                            next_rate = bitrates[i]
                            return next_rate

                elif bitrates[-1] / curr_rate <= video_segment_duration:
                    next_rate = bitrates[-1]
                    return next_rate

                else:
                    next_rate = curr_rate
                    return next_rate

    if buffer_size < min(5, max_to_min_ratio) or curr_rate == 0:
        next_rate = bitrates[0]        
        bitrate_history.append(next_rate)
#        print bitrate_history
        return next_rate
    elif curr_rate == bitrates[-1]:   
        next_rate = curr_rate   
    else:
        try:
            curr = bitrates.index(next_spectrum_rate[0])
        except ValueError:
            config_dash.LOG.error("Current Bitrate not in the bitrate list. Setting to minimum")
            curr = calculate_rate_index(bitrates, curr_rate) 
        next_rate=curr
        next_buffer = buffer_size + video_segment_duration - next_dl_times[curr]
    bitrate_history.append(next_rate)
    
    chosen_rates = []
    if len(bitrate_history) >= BIN_SIZE:
        for i in bitrate_history:
            next_dl_rate = np.percentile(map(int,i),5)
            for i in (0,len(next_segment_sizes)):
                if next_spectrum_rates[i] / next_dl_rate > video_segment_duration:
                    i += 1
                    continue
                chosen_rates.append(next_spectrum_rates[i])
                for n in (0,len(bitrates)):
                    if float(next_segment_sizes[n])/next_dl_rate > video_segment_duration:
                        continue
                    bitrates_window4 = bitrates_window4.append(n)
                    bitrates_window8 = bitrates_window8.append(n)
                    bitrates_window16 = bitrates_window16.append(n)
                    spectrum = (br_weight * spectrum(bitrates_window4)) + (br_weight * spectrum(bitrates_window8)) + (br_weight * spectrum(bitrates_window16))
                    spectrums.append(spectrum)
                    br_spectrum.update({bitrates[n]:spectrum})
                sorted_by_spectrum = sorted(br_spectrum.items(), key=operator.itemgetter(1))
                next_spectrum_rates = [i[0] for i in sorted_by_spectrum]
                next_rate = next_spectrum_rates[0]
        bitrate_history.pop(1)
    return next_rate
    '''
