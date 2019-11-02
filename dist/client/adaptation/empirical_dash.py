import config_dash
from adaptation.adaptation import calculate_rate_index
from adaptation.spectrum_calc import spectrum_calc
import numpy as np
from sortedcontainers import SortedDict
import math
import operator
import os
import csv

INIT_SEG=10
EPSILON=30
spectrum_log_file=config_dash.SPECTRUM_LOG_FILENAME
class SortedDisplayDict(dict):
   def __str__(self):
       return "{" + ", ".join("%r: %r" % (key, self[key]) for key in sorted(self)) + "}"

def percentile(x):
    pc = float(1)/(len(x)-1)
    return ["%.2f"%(n*pc) for n, i in enumerate(x)]

def empirical_dash(average_segment_sizes, segment_number, bitrates, segment_download_time, curr_rate, 
                   buffer_size, segment_size, next_segment_sizes, video_segment_duration, dl_rate_history, bitrate_history, segment_w_chunks, DOWNLOAD_CHUNK,phase):
    segment_number = segment_number - 1
    BIN_SIZE = 50
    INITIAL_TRAIN = 5

    if segment_size == 0:
        curr_rate = 0
    else:
        curr_rate = (segment_size)/segment_download_time
    bitrates = [float(i) for i in bitrates]
    bitrates.sort()
#    config_dash.LOG.info("EMPIRICAL: Buffer Size %f"%buffer_size)

    with open('empirical-dl-rate.txt', 'a') as dlrate:
        dlrate.write(str(segment_number) + '\t' + str(curr_rate) + '\n') 

    max_to_min_size_ratio = next_segment_sizes[bitrates[-1]] / next_segment_sizes[bitrates[0]]
    q_layer = 2

    if segment_number <= INIT_SEG: 
        #if bitrates[-1] / curr_rate <= video_segment_duration:
        if segment_number <= min(INITIAL_TRAIN+1, max_to_min_size_ratio):
            next_rate = bitrates[0]
#            print "1------next_rate: {}-------".format(str(next_rate))
            return next_rate
        else:
            #q_layer = (segment_number - 5) * 2 ** (segment_number - 5)
            q_layer = q_layer ** (segment_number - 5) 
            if int(q_layer) > 0 and q_layer < len(bitrates):
                for i in range(q_layer, int(q_layer/2), -1):
                    if average_segment_sizes[bitrates[q_layer]] / curr_rate <= (video_segment_duration * 2):
                        next_rate = bitrates[i]
                        config_dash.LOG.info("2------next_rate: {}-------".format(str(next_rate)))
                        return next_rate
            elif average_segment_sizes[bitrates[-1]] / curr_rate <= video_segment_duration:
                next_rate = bitrates[-1]
#                print "3------next_rate: {}-------".format(str(next_rate))
                return next_rate
            else:
                next_rate = bitrate_history[-1]
#                print "4------next_rate: {}-------".format(str(next_rate))
                return next_rate

    br_spectrum = {}
    spectrums = []
    next_dl_times = []
    chunk_by_index = list(map(lambda *row: list(row), *segment_w_chunks))
    for n in range(len(bitrates)):
        size1 = next_segment_sizes[bitrates[n]]
        ick = size1 / DOWNLOAD_CHUNK
        index_of_chunk = round(ick)
        
        while True:
            #print "===========while========="
            #print chunk_by_index
            #print len(chunk_by_index)
            #print index_of_chunk
            #print "===========while========="
            if index_of_chunk <= 2:
                if index_of_chunk < len(chunk_by_index):
                    hi = chunk_by_index[int(index_of_chunk)]
                else:
                    print (len(chunk_by_index))
                    hi = chunk_by_index[0]
                chunk_by_index_rm_none = [x for x in hi if x is not None]
                next_dl_rate = sum(chunk_by_index_rm_none) / float(len(chunk_by_index_rm_none))
                config_dash.LOG.info("ok average........ {}".format(str(next_dl_rate)))
                break
            if index_of_chunk < len(list(chunk_by_index)):
                hi = chunk_by_index[int(index_of_chunk)]
                chunk_by_index_rm_none = [x for x in hi if x is not None]
                if len(chunk_by_index_rm_none) > 5:
                    next_dl_rate = sum(chunk_by_index_rm_none) / float(len(chunk_by_index_rm_none))
                    config_dash.LOG.info("Yay average!!!!!!i {}".format(str(next_dl_rate)))
                    break
                index_of_chunk = index_of_chunk - 1
            elif index_of_chunk == 0:
                next_dl_rate = curr_rate
                config_dash.LOG.info ("index_of_chunk = 0 average") 
                break
            else:
                index_of_chunk = index_of_chunk - 1
        test = float(average_segment_sizes[bitrates[n]])/next_dl_rate

        next_bitrate = 0
        #br_weight = (bitrates[1] / bitrates[-1]) ** (1 / (n + 1))
        if len(bitrates)>1:
            br_weight = (bitrates[1] / bitrates[-1]) ** (1 / (len(bitrates) - n + 1))
        else:
                br_weight = (bitrates[0] / bitrates[-1]) ** (1 / (len(bitrates) - n + 1))
                #br_weight = 1 - (1 / 2) ** (len(bitrates) - n + 1)
        print ("##################")
        print (bitrates[n])
        print (average_segment_sizes[bitrates[n]])
        print (float(average_segment_sizes[bitrates[n]])/next_dl_rate)
        print (next_dl_rate)
        print ("##################")
        if float(average_segment_sizes[bitrates[n]])/next_dl_rate < video_segment_duration:
            next_bitrate = bitrates[n]
        else:
            continue

        bitrates_window2 = bitrate_history[-3:]
        bitrates_window4 = bitrate_history[-4:]
        bitrates_window5 = bitrate_history[-5:]
        bitrates_window8 = bitrate_history[-8:]
        if len(bitrate_history) > 50:
            bitrates_window16 = bitrate_history[-50:]
        else:
            bitrates_window16 = bitrate_history
        bitrate_history.append(next_bitrate)
        bitrates_window2.append(next_bitrate)
        bitrates_window4.append(next_bitrate)
        bitrates_window5.append(next_bitrate)
        bitrates_window8.append(next_bitrate)
        bitrates_window16.append(next_bitrate)
        weighted_spectrum = (1.0/len(bitrates_window16))*br_weight*spectrum_calc(bitrates_window16)
        #weighted_spectrum =(1.0/len(bitrates_window5))*br_weight*spectrum_calc(bitrates_window5)+(1.0/len(bitrates_window16))*br_weight*spectrum_calc(bitrates_window16)
        #weighted_spectrum = (1/2.0)*(br_weight*spectrum_calc(bitrates_window2))+(1/4.0)*(br_weight * spectrum_calc(bitrates_window4)) + (1/8.0)*(br_weight * spectrum_calc(bitrates_window8))
        #weighted_spectrum = (1/min(len(bitrates_window16),16))*(br_weight * spectrum_calc(bitrates_window16))
        #weighted_spectrum=(1/3.0)*spectrum_calc(bitrates_window2)/br_weight
        #weighted_spectrum = (1/8.0)*(br_weight * spectrum_calc(bitrates_window8)) 
        if not os.path.exists(spectrum_log_file):
                    header_row = "EpochTime,Bitrate,WeightedSpectrum,DownloadRate,SegmentSize".split(",")
                    stats = (
                    segment_number,next_bitrate,weighted_spectrum,next_dl_rate,float(average_segment_sizes[bitrates[n]]))
        else:
                    header_row = None
                    stats = (
                    segment_number,next_bitrate,weighted_spectrum,next_dl_rate,float(average_segment_sizes[bitrates[n]]))
        str_stats = [str(i) for i in stats]
        with open(spectrum_log_file, "a") as log_file_handle:
                result_writer = csv.writer(log_file_handle, delimiter=",")
                if header_row:
                        result_writer.writerow(header_row)
                result_writer.writerow(str_stats)
        config_dash.LOG.info("QUALITY {} WEIGHTED SPECTRUM: {} W16 {} W8 {} W4{}".format(next_bitrate,weighted_spectrum, spectrum_calc(bitrates_window16),spectrum_calc(bitrates_window8),spectrum_calc(bitrates_window4)))
        #if (phase=="DEC"):
                #weighted_spectrum = (br_weight * spectrum_calc(bitrates_window4))
        spectrums.append(weighted_spectrum)
        next_dl_time = next_segment_sizes[next_bitrate] / next_dl_rate
        next_dl_times.append(next_dl_time)
        #br_spectrum.update({weighted_spectrum: next_bitrate})
        br_spectrum.update({next_bitrate: weighted_spectrum})
    #next_spectrum_rates = [x[0] for x in (sorted(br_spectrum.items(), key=operator.itemgetter(1)))]
    next_spectrum_rates = [x[0] for x in (sorted(br_spectrum.items(), key=operator.itemgetter(1)))]
    next_spectrum_values = [x[1] for x in (sorted(br_spectrum.items(), key=operator.itemgetter(1)))]
    config_dash.LOG.info("NEXT_SPECTRUM_RATES1: {} \n NEXT_SPECTRUM_VALUES {}".format(next_spectrum_rates,next_spectrum_values))
    #for i in next_spectrum_rates:
    #    inti = int(i)
    #    next_spectrum_rates.index(inti)
    #    if average_segment_sizes[inti]/next_dl_rate > 2 * video_segment_duration:
    #        next_spectrum_rates.pop(int(next_spectrum_rates.index(inti)))    
    if not next_spectrum_rates:
        next_rate = bitrate_history[-1]
        return next_rate
    #ANOTHER WAY: sorted_by_spectrum = SortedDisplayDict(br_spectrum)
    next_rate = next_spectrum_rates[0]
    
    br_spectrum = {}
    spectrums = []
    next_dl_times = []
    if next_rate <= bitrate_history[-1]: #BIN_SIZE:
        for n in range(len(bitrates)):
          size = next_segment_sizes[bitrates[n]]
          ick = size / DOWNLOAD_CHUNK
          index_of_chunk = round(ick)

          while True:
            if index_of_chunk <= 2:
                if index_of_chunk < len(chunk_by_index):
                    hi = chunk_by_index[int(index_of_chunk)]
                else:
                    hi = chunk_by_index[0]
                #hi = chunk_by_index[int(index_of_chunk)]
                #chunk_by_index_rm_none = [x for x in hi if x is not None]
                int_array = [int(i) for i in chunk_by_index_rm_none]
                next_dl_rate = np.percentile(int_array,EPSILON)
                config_dash.LOG.info("ok percentile........ {}".format(str(next_dl_rate)))
                break
            if index_of_chunk < len(chunk_by_index):
                hi = chunk_by_index[int(index_of_chunk)]
                chunk_by_index_rm_none = [x for x in hi if x is not None]
                if len(chunk_by_index_rm_none) > 5:
                    int_array = [int(i) for i in chunk_by_index_rm_none]
                    next_dl_rate = np.percentile(int_array,EPSILON)
                    config_dash.LOG.info("Yay percentile!!!!!! {}".format(str(next_dl_rate)))
                    break
                index_of_chunk = index_of_chunk - 1
            elif index_of_chunk == 0:
                next_dl_rate = curr_rate
                print ("index_of_chunk = 0 percentile") 
                break
            else:
                index_of_chunk = index_of_chunk - 1

          next_bitrate = 0
            #br_weight = (bitrates[-1] / bitrates[n]) ** (1 / (n + 1))
            #br_weight = (bitrates[-1] / bitrates[n]) ** (1 - (1 / 2) ** (len(bitrates) - n + 1)
          if len(bitrates)>1:
                br_weight = (bitrates[1] / bitrates[-1]) ** (1 / (len(bitrates) - n + 1))
          else:
                br_weight = (bitrates[0] / bitrates[-1]) ** (1 / (len(bitrates) - n + 1))
          if average_segment_sizes[bitrates[n]]/next_dl_rate < video_segment_duration:
                next_bitrate = bitrates[n]
          else:
                continue
          bitrates_window2 = bitrate_history[-2:]
          bitrates_window4 = bitrate_history[-4:]
          bitrates_window5 = bitrate_history[-5:]
          bitrates_window8 = bitrate_history[-8:]
          if len(bitrate_history) > 50:
                bitrates_window16 = bitrate_history[-50:]
          else:
                bitrates_window16 = bitrate_history
          bitrate_window=bitrate_history
          bitrate_window.append(next_bitrate)
          bitrates_window2.append(next_bitrate)
          bitrates_window4.append(next_bitrate)
          bitrates_window5.append(next_bitrate)
          bitrates_window8.append(next_bitrate)
          bitrates_window16.append(next_bitrate)
          #weighted_spectrum = (1/4.0)*(br_weight * spectrum_calc(bitrates_window4)) + (1/8.0)*(br_weight * spectrum_calc(bitrates_window8)) + (1/16.0)*(br_weight * spectrum_calc(bitrates_window16))  
          #weighted_spectrum = (1/2)*(br_weight*spectrum_calc(bitrates_window2))+(1/4.0)*(br_weight * spectrum_calc(bitrates_window4)) + (1/8.0)*(br_weight * spectrum_calc(bitrates_window8))
          weighted_spectrum = (1.0/len(bitrates_window16))*br_weight*spectrum_calc(bitrates_window16)
          #weighted_spectrum =(1.0/len(bitrates_window5))*br_weight*spectrum_calc(bitrates_window5)+(1.0/len(bitrates_window16))*br_weight*spectrum_calc(bitrates_window16)
          #weighted_spectrum = (1/8.0)*(br_weight * spectrum_calc(bitrates_window8))
          config_dash.LOG.info("WEIGHTED SPECTRUM: {} W16 {} W8 {} W4{}".format(weighted_spectrum, spectrum_calc(bitrates_window16),spectrum_calc(bitrates_window8),spectrum_calc(bitrates_window4)))
          #if (phase=="DEC"):
             #    weighted_spectrum = (br_weight * spectrum_calc(bitrates_window4)) 
          spectrums.append(weighted_spectrum)
          next_dl_time = next_segment_sizes[next_bitrate] / curr_rate
          next_dl_times.append(next_dl_time)
          br_spectrum.update({next_bitrate: weighted_spectrum})
          #br_spectrum.update({weighted_spectrum: next_bitrate})
        next_spectrum_rates = [x[0] for x in (sorted(br_spectrum.items(), key=operator.itemgetter(1)))]
        #next_spectrum_rates = [x[1] for x in reversed(sorted(br_spectrum.items(), key=operator.itemgetter(1)))]
        if not os.path.exists(spectrum_log_file):
                    header_row = "EpochTime,Bitrate,Spectrum2,Spectrum4,Spectrum8,Spectrum16,DownloadRate,SegmentSize".split(",")
                    stats = (
                    segment_number,next_bitrate,weighted_spectrum,next_dl_rate,float(average_segment_sizes[bitrates[n]]))
        else:
                    header_row = None
                    stats = (
                    segment_number,next_bitrate,weighted_spectrum,next_dl_rate,float(average_segment_sizes[bitrates[n]]))
        str_stats = [str(i) for i in stats]
        with open(spectrum_log_file, "a") as log_file_handle:
        	result_writer = csv.writer(log_file_handle, delimiter=",")
        	if header_row:
        		result_writer.writerow(header_row)
        	result_writer.writerow(str_stats)
        config_dash.LOG.info("UPDATED_BITRATE: {} NEXT_SPECTRUM_RATES: {}".format(next_bitrate,next_spectrum_rates))
	#for i in next_spectrum_rates:
        #    inti = int(i)
        #    next_spectrum_rates.index(inti)
        #    if average_segment_sizes[inti]/next_dl_rate > 1.2 * video_segment_duration:
        #        next_spectrum_rates.pop(int(next_spectrum_rates.index(inti)))
        if not next_spectrum_rates:
            next_rate = bitrates[0]
            return next_rate
        next_rate = next_spectrum_rates[0]
        #bitrate_history.pop()
        print (next_rate)
        return next_rate        
    return next_rate
