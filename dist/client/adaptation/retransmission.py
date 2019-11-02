#import dash_client
import config_dash

def get_segment_sizes(dp_object, segment_number):
    segment_sizes = dict([(bitrate, dp_object.video[bitrate].segment_sizes[segment_number]) for bitrate in dp_object.video])
    return segment_sizes

def retransmission(dp_object, current_bitrate, segment_number, buffer_dict, bitrates, segment_download_rate, buffer_max, video_segment_duration):
    #segment_download_rate *= 8
    MAX_GAP_WIDTH = 7
    retx_flag = False
    q_layers_in_buffer = []
    bitrates_in_buffer = []
    segment_numbers = []
    shortest_gap = buffer_max
    segment_index = segment_number
    largest_jump = 0
    lowest_layer = bitrates[-1]
    if q_layers_in_buffer:
        q_layer_retransmit = q_layers_in_buffer[-1]
    RETRANSMIT = False
    for i in range(len(buffer_dict)):
        q_layers_in_buffer.append(buffer_dict[i]['segment_layer'])
        bitrates_in_buffer.append(buffer_dict[i]['bitrate'])
        segment_numbers.append(buffer_dict[i]['segment_number'])
#    with open('empirical-debug.txt', 'a') as emp:
#        emp.write('first segment number: ' + str(segment_numbers[0]) + '\n')
    print (segment_numbers)
    print (q_layers_in_buffer)
    #Temporary quality degradation:
    for i in range(len(q_layers_in_buffer)-MAX_GAP_WIDTH):
        if q_layers_in_buffer[i] > q_layers_in_buffer[i+1]:
            segment_index_tmp = segment_number - len(q_layers_in_buffer) + i + 1
            with open('empirical-debug.txt', 'a') as emp2:
                emp2.write("########FIND QUALITY DEGRADATION############" + '\t' + str(segment_index_tmp) + '\n')
            for j in range(i+1, i+MAX_GAP_WIDTH):
                if q_layers_in_buffer[j] < q_layers_in_buffer[j+1]:
                    if j - i == shortest_gap:
                        with open('empirical-debug.txt', 'a') as emp3:
                            emp3.write('j - i == shortest_gap' + '\n')
                        if largest_jump != 0 and ((q_layers_in_buffer[j - 1] - q_layers_in_buffer[j]) > largest_jump):
                            if get_segment_sizes(dp_object,segment_index)[bitrates[q_layers_in_buffer[i+1]]] / segment_download_rate < (video_segment_duration * 2):
                                if q_layers_in_buffer[j+1] - q_layers_in_buffer[j] > q_layers_in_buffer[i+1] - q_layers_in_buffer[i]:
                                    q_layer_retransmit = q_layers_in_buffer[i]
                                else:
                                    q_layer_retransmit = q_layers_in_buffer[j+1]
                                #segment_index = segment_number - len(q_layers_in_buffer) + i + 1
                                segment_index = segment_index_tmp
                                RETRANSMIT = True
                                largest_jump = q_layers_in_buffer[j - 1] - q_layers_in_buffer[j]
                        elif ((q_layers_in_buffer[j - 1] - q_layers_in_buffer[j]) == largest_jump) and q_layers_in_buffer[i+1] < lowest_layer:
                            if get_segment_sizes(dp_object,segment_index)[bitrates[q_layers_in_buffer[i+1]]] / segment_download_rate < (video_segment_duration * 2):
                                if q_layers_in_buffer[j+1] - q_layers_in_buffer[j] > q_layers_in_buffer[i+1] - q_layers_in_buffer[i]:
                                    q_layer_retransmit = q_layers_in_buffer[i]
                                else:
                                    q_layer_retransmit = q_layers_in_buffer[j+1]
                                q_layer_retransmit = q_layers_in_buffer[i]
                                segment_index = segment_index_tmp
                                #segment_index = segment_number - len(q_layers_in_buffer) + i + 1
                                lowest_layer = q_layers_in_buffer[i+1]
                                RETRANSMIT = True
                        else:
                            segment_index = segment_index_tmp

                    elif j - i < shortest_gap:
                        with open('empirical-debug.txt', 'a') as emp4:
                            emp4.write('j - i < shortest_gap' + '\n')
                        shortest_gap = j - i                        
                        if get_segment_sizes(dp_object,segment_index)[bitrates[q_layers_in_buffer[i+1]]] / segment_download_rate < (video_segment_duration * 2):
                            if q_layers_in_buffer[j+1] - q_layers_in_buffer[j] > q_layers_in_buffer[i+1] - q_layers_in_buffer[i]:
                                q_layer_retransmit = q_layers_in_buffer[i]
                            else:
                                q_layer_retransmit = q_layers_in_buffer[j+1]
                            q_layer_retransmit = q_layers_in_buffer[i]
                            segment_index = segment_index_tmp
                            #segment_index = segment_number - len(q_layers_in_buffer) + i + 1
                            with open('empirical-dash-chosen-rate.txt', 'a') as emp:
                                emp.write('segment_index: ' + str(segment_index) + '\n')
                            RETRANSMIT = True
                        else:
                            with open('empirical-debug.txt', 'a') as emp:
                                emp.write('not enough time to download!' + '\n')
                else:
                    with open('empirical-debug.txt', 'a') as emp5:
                        emp5.write('stay low' + '\n')
                    #q_layer_retransmit = q_layers_in_buffer[i]
                    #segment_index = segment_number - len(q_layers_in_buffer) + i + 1
                    #with open('empirical-debug.txt', 'a') as emp5:
                    #    emp5.write('i' + str(i) + 'segment_index:' + str(segment_index) + 'segment_number: ' + str(segment_number) + '\n')
                    #RETRANSMIT = True
            lowest_layer = q_layers_in_buffer[i]
    #Quality drops and stay low:
    if segment_index == segment_number:
        for i in range(len(q_layers_in_buffer)-1):
            if q_layers_in_buffer[i] > q_layers_in_buffer[i]:
                with open('empirical-debug.txt', 'a') as emp6:
                    emp6.write('stay low 2' + '\n')
                segment_index = segment_number - len(q_layers_in_buffer) + i + 1
                if get_segment_sizes(dp_object,segment_index)[bitrates[q_layers_in_buffer[i+1]]] / segment_download_rate < (video_segment_duration * 2):
                    q_layer_retransmit = q_layers_in_buffer[i]
                    RETRANSMIT = True
    if RETRANSMIT == True and segment_index >= segment_numbers[0]:
        print ("---------------Retransmit initialized----------------")
        print ("NEW Bitrate:" + str(bitrates[q_layer_retransmit]))
        retx_flag = True
        with open("/opt/SQUAD/retx_api.txt",'a') as retx_api:
            retx_api.write("{},{},{}\n".format(bitrates[q_layer_retransmit], segment_index, retx_flag))
        return bitrates[q_layer_retransmit], segment_index, retx_flag
    else:
        return current_bitrate, segment_number, retx_flag
