#!/usr/local/bin/python
"""
Author:            Parikshit Juluri
Contact:           pjuluri@umkc.edu
Testing:
    import dash_client
    mpd_file = <MPD_FILE>
    dash_client.playback_duration(mpd_file, 'http://198.248.242.16:8005/')

    From commandline:
    python dash_client.py -m "http://198.248.242.16:8006/media/mpd/x4ukwHdACDw.mpd" -p "all"
    python dash_client.py -m "http://127.0.0.1:8000/media/mpd/x4ukwHdACDw.mpd" -p "basic"

"""
from __future__ import division
import hyper
import read_mpd
import urllib
from contextlib import closing
import io
import httplib2
import random
import os
import csv
import sys
import errno
import time
import timeit
from string import ascii_letters, digits
from argparse import ArgumentParser
from multiprocessing import Process, Queue
import multiprocessing
from collections import defaultdict
from adaptation import basic_dash, basic_dash2, weighted_dash, netflix_dash, empirical_dash, retransmission
from adaptation.adaptation import WeightedMean
import config_dash
import dash_buffer
import requests
from configure_log_file import configure_log_file, write_json
import time
import threading
import sysv_ipc

try:
    WindowsError
except NameError:
    WindowsError = None

# Constants
DEFAULT_PLAYBACK = 'BASIC'
DOWNLOAD_CHUNK = 13500  # 8192
BUFFER_THRESHOLD_UPPER = 0.5
BUFFER_THRESHOLD_LOWER = 0.4
RETRANS_THRESHOLD_UPPER = 0.5
RETRANS_THRESHOLD_LOWER = 0.4
INIT_SEG=10
# normal_dw_count = 0

# Globals for arg parser with the default values
# Not sure if this is the correct way ....
MPD = None
LIST = False
PLAYBACK = DEFAULT_PLAYBACK
DOWNLOAD = False
SEGMENT_LIMIT = None
download_log_file = config_dash.DOWNLOAD_LOG_FILENAME
# lock = threading.Lock()
# multiprocessing lock
lock = threading.Lock()
retx_pending_q = Queue()
retx_done_q = Queue()
seg_pending_q = Queue()
seg_done_q = Queue()


class DashPlayback:
    """
    Audio[bandwidth] : {duration, url_list}
    Video[bandwidth] : {duration, url_list}
    """

    def __init__(self):
        self.min_buffer_time = None
        self.playback_duration = None
        self.audio = dict()
        self.video = dict()


def write_msg(list_cmd, mq):
    for i in list_cmd:
        print(i)
        mq.send(i, True)
    return


class SegmentDownloadStats:
    """
    Stats necessary after segment is downloaded
    """

    def __init__(self):
        self.segment_size = 0
        self.segment_filename = None
        self.segment_chunk_rates = []
        self.segment_dw_time = 0

class SpectrumHistory:
    """
    Objects to track Spectrum Calculation Related Data
    """
    def __init__(self):
        self.bitrate_history = []
def get_mpd(url):
    """ Module to download the MPD from the URL and save it to file"""
    global connection
    key_c_orig_r = 262144
    key_c_orig_w = 262145

    try:
        mq_orig_r = sysv_ipc.MessageQueue(key_c_orig_r, sysv_ipc.IPC_CREAT, max_message_size=15000)
    except:
        print("ERROR: Queue not created")
    try:
        mq_orig_w = sysv_ipc.MessageQueue(key_c_orig_w, sysv_ipc.IPC_CREAT, max_message_size=15000)
    except:
        print("ERROR: mq_orig_r Queue not created")
    mpd_file = url.split('/')[-1]
    #mpd_file_handle = open(mpd_file, 'wb')
    total_data_dl_time = 0
    mpd_url=urllib.parse.urlparse(url)
    cmd1 = ["conn","10.10.2.2,10.10.3.2","10.10.4.2:6121,10.10.4.2:6121",str(mpd_url.scheme)+"://"+str(mpd_url.netloc),str(mpd_url.path),mpd_file]
    process3 = threading.Thread(target=write_msg, args=(cmd1, mq_orig_w))
    # thread3=threading.Thread(target=write_msg,args=(cmd1,mqw1))
    # thread3.start()
    process3.start()
    chunk_start_time = timeit.default_timer()
    segment_start_time=chunk_start_time
    # ipc read

    # print("Py master reading chunks")
    while True:
        message= mq_orig_r.receive()
        m=str(message[0],'utf-8',errors='ignore').split('\x00')[0]
        print (m)
        # print("Reply:{}, content-length:{}\n".format(message,m[1]))
        # chunk_sizes.append(float(m[1]))
        if 'DONE' in m:
	        break
        	#mpd_file_handle.write(message[0])

    #mpd_file_handle.close()
    config_dash.LOG.info("Downloaded the MPD file {}".format(mpd_file))
    return mpd_file


def get_bandwidth(data, duration):
    """ Module to determine the bandwidth for a segment
    download"""
    return data * 8 / duration


def get_domain_name(url):
    """ Module to obtain the domain name from the URL
        From : http://stackoverflow.com/questions/9626535/get-domain-name-from-url
    """
    parsed_uri = urllib.parse.urlparse(url)
    domain = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
    return domain


def id_generator(id_size=6):
    """ Module to create a random string with uppercase 
        and digits.
    """
    return 'TEMP_' + ''.join(random.choice(ascii_letters + digits) for _ in range(id_size))


def download_segment(segment_url, dash_folder):
    """ Module to download the segment """
    parsed_uri = urllib.parse.urlparse(segment_url)
    segment_path = '{uri.path}'.format(uri=parsed_uri)
    # while segment_path.startswith('/'):
    #    segment_path = segment_path[1:]
    seg_dw_object = SegmentDownloadStats()
    # config_dash.LOG.info("ABSPATH_SEG %s" %(os.path.abspath(os.path.join(dash_folder, os.path.basename(segment_path)))))
    
    #seg_dw_object.segment_filename = segment_url
    seg_dw_object.segment_filename= os.path.abspath(os.path.join(dash_folder, os.path.basename(segment_path)))
    make_sure_path_exists(os.path.dirname(seg_dw_object.segment_filename))
    #config_dash.LOG.info("ORIG_DOWNLOAD:%s" % seg_dw_object.segment_filename)
    # print (seg_dw_object.segment_filename)
    # cmd1=["CREATE_STREAM",parsed_uri.path,seg_dw_object.segment_filename]
    #segment_file_handle = open(seg_dw_object.segment_filename, 'wb')
    print(parsed_uri.path)
    key_c_orig_r = 262144
    key_c_orig_w = 262145

    try:
        mq_orig_r = sysv_ipc.MessageQueue(key_c_orig_r, sysv_ipc.IPC_CREAT, max_message_size=15000)
    except:
        print("ERROR: Queue not created")
    try:
        mq_orig_w = sysv_ipc.MessageQueue(key_c_orig_w, sysv_ipc.IPC_CREAT, max_message_size=15000)
    except:
        print("ERROR: mq_orig_r Queue not created")

    chunk_number = 0
    total_data_dl_time = 0
    cmd1 = ["stream",str(parsed_uri.path),seg_dw_object.segment_filename]
    process3 = threading.Thread(target=write_msg, args=(cmd1, mq_orig_w))
    # thread3=threading.Thread(target=write_msg,args=(cmd1,mqw1))
    # thread3.start()
    process3.start()
    
    chunk_start_time = timeit.default_timer()
    segment_start_time=chunk_start_time
    # ipc read
    bytes_read=0
    # print("Py master reading chunks")
    while True:
        message = mq_orig_r.receive()
        #m=str(message[0],'utf-8',errors='ignore').split('\x00')[0]
        m=str(message[0],'utf-8',errors='ignore')
        #config_dash.LOG.info("Reading IPC message:%d m:%d"%(len(message[0]),len(m)))
        # print("Reply:{}, content-length:{}\n".format(message,m[1]))
        # chunk_sizes.append(float(m[1]))
        if "DONE" not in m:
            #segment_file_handle.write(message[0])
            seg_dw_object.segment_size += (int(m))
            #bytes_read+=int(m)
            #if bytes_read>=DOWNLOAD_CHUNK:
            timenow = timeit.default_timer()
            chunk_dl_time = timenow - chunk_start_time
            chunk_start_time = timenow
            chunk_number += 1
            total_data_dl_time += chunk_dl_time
            current_chunk_dl_rate = (seg_dw_object.segment_size * 8) / total_data_dl_time
            seg_dw_object.segment_chunk_rates.append(current_chunk_dl_rate)
        else:
            #if bytes_read>0:
            '''
            chunk_dl_time = timenow - chunk_start_time
            chunk_start_time = timenow
            chunk_number += 1
            total_data_dl_time += chunk_dl_time
            current_chunk_dl_rate = (seg_dw_object.segment_size * 8) / total_data_dl_time
            seg_dw_object.segment_chunk_rates.append(current_chunk_dl_rate)
            '''
            config_dash.LOG.info("Closing IPC: Seg URL %s Seg Size %d"%(segment_url,seg_dw_object.segment_size))
            #segment_file_handle.close()
            break

    # content_length = chunk_sizes.pop()
    # DONE part
    seg_dw_object.segment_dw_time = (timeit.default_timer()-segment_start_time)
    seg_dw_object.segment_size*=8
    #seg_dw_object.segment_size*=8
    segment_dw_rate = seg_dw_object.segment_size/seg_dw_object.segment_dw_time

    with open('/opt/SQUAD/chunk_rate_read_mod_chunk_squad_libcurl_HTTP2.txt', 'a') as chk:
        chk.write("{}".format(segment_url))
        for item in seg_dw_object.segment_chunk_rates:
            chk.write(",{}".format(item))
        chk.write("\n")
    # print("{} sum:{}, content_length:{}".format(p_no,sum(chunk_sizes), content_length))
    with open('/opt/SQUAD/segment_rate_squad_libcurl_HTTP2.txt', 'a') as chk:
        chk.write("{},{}\n".format(segment_url,segment_dw_rate))

    process3.join()
    # thread3.join()
    seg_done_q.put(seg_dw_object)
    return


def retx_download_segment(retx_segment_url, dash_folder, retrans_next_segment_size, video_segment_duration,
                          play_segment_number, retx_segment_number):
    config_dash.LOG.info("RETX_DOWNLOAD:Entered")
    parsed_uri = urllib.parse.urlparse(retx_segment_url)
    segment_path = '{uri.path}'.format(uri=parsed_uri)
    # while segment_path.startswith('/'):
    #    segment_path = segment_path[1:]
    retx_seg_dw_object = SegmentDownloadStats()
    retx_seg_dw_object.segment_filename = retx_segment_url
    # os.path.abspath(os.path.join(dash_folder, os.path.basename(segment_path)))
    config_dash.LOG.info("RETX_DOWNLOAD:%s" % retx_seg_dw_object.segment_filename)
    make_sure_path_exists(os.path.dirname(retx_seg_dw_object.segment_filename))
    print(retx_seg_dw_object.segment_filename)
    # cmd1=["CREATE_STREAM",parsed_uri.path,retx_seg_dw_object.segment_filename]
    #retx_segment_file_handle = open(retx_seg_dw_object.segment_filename, 'wb')
    key_c_retx_r = 362146
    key_c_retx_w = 462146

    with open('/opt/SQUAD/retx_seg_status_libcurl_HTTP2.txt', 'a') as chk:
        chk.write("RETX start:{}\n".format(retx_segment_url))


    try:
        mq_retx_r = sysv_ipc.MessageQueue(key_c_retx_r, sysv_ipc.IPC_CREAT, max_message_size=15000)
    except:
        print("ERROR: Queue not created")
    try:
        mq_retx_w = sysv_ipc.MessageQueue(key_c_retx_w, sysv_ipc.IPC_CREAT, max_message_size=15000)
    except:
        print("ERROR: mq_orig_r Queue not created")

    chunk_number = 0
    total_data_dl_time = 0
    # thread3=threading.Thread(target=write_msg,args=(cmd1,mqw1))
    cmd1 = ["stream",str(parsed_uri.path),retx_seg_dw_object.segment_filename]
    process3 = threading.Thread(target=write_msg, args=(cmd1, mq_retx_w))
    process3.start()
    config_dash.LOG.info("RETX_DOWNLOAD: Wrote retx to pipe\n")
    chunk_start_time = timeit.default_timer()
    retx_segment_start_time=chunk_start_time
    bytes_read = 0 
    # ipc read
    # thread3.start()
    while True:
        message = mq_retx_r.receive()
        m=str(message[0],'utf-8',errors='ignore')
        # print("Reply:{}, content-length:{}\n".format(message,m[1]))
        # chunk_sizes.append(float(m[1]))
        if "DONE" not in m:
            #retx_segment_file_handle.write(message[0])
            #if bytes_read>=DOWNLOAD_CHUNK:
            retx_seg_dw_object.segment_size += int(m)
            timenow = timeit.default_timer()
            chunk_dl_time = timenow - chunk_start_time
            chunk_start_time = timenow
            chunk_number += 1
            total_data_dl_time += chunk_dl_time
            current_chunk_dl_rate = (retx_seg_dw_object.segment_size * 8) / total_data_dl_time
            retx_seg_dw_object.segment_chunk_rates.append(current_chunk_dl_rate)
            bytes_read=0
        else:
            config_dash.LOG.info("Closing retrans IPC Size %d"%retx_seg_dw_object.segment_size)
            #retx_segment_file_handle.close()
            break
    # content_length = chunk_sizes.pop()
    # DONE part
    retx_seg_dw_object.segment_dw_time = (timeit.default_timer()-retx_segment_start_time)
    retx_seg_dw_object.segment_size *=8
    retx_segment_dw_rate = retx_seg_dw_object.segment_size/retx_seg_dw_object.segment_dw_time

    with open('/opt/SQUAD/chunk_rate_read_mod_chunk_squad_libcurl_HTTP2.txt', 'a') as chk:
        chk.write("RETX:{}".format(retx_segment_url))
        for item in retx_seg_dw_object.segment_chunk_rates:
            chk.write(",{}".format(item))
        chk.write("\n")
        
    with open('/opt/SQUAD/retx_seg_status_libcurl_HTTP2.txt', 'a') as chk:
        chk.write("RETX done:{},{}\n".format(retx_segment_url,retx_segment_dw_rate))
    
    with open('/opt/SQUAD/segment_rate_squad_libcurl_HTTP2.txt', 'a') as chk:
        chk.write("{},{}\n".format(retx_segment_url,retx_segment_dw_rate))

    # thread3.join()
    process3.join()
    retx_done_q.put(retx_seg_dw_object)

    return


def get_media_all(domain, media_info, file_identifier, done_queue):
    """ Download the media from the list of URL's in media
    """
    bandwidth, media_dict = media_info
    media = media_dict[bandwidth]
    media_start_time = timeit.default_timer()
    for segment in [media.initialization] + media.url_list:
        start_time = timeit.default_timer()
        segment_url = urllib.parse.urljoin(domain, segment)
        _, segment_file, _ = download_segment(segment_url, file_identifier)
        elapsed = timeit.default_timer() - start_time
        if segment_file:
            done_queue.put((bandwidth, segment_url, elapsed))
    media_download_time = timeit.default_timer() - media_start_time
    done_queue.put((bandwidth, 'STOP', media_download_time))
    return None


def make_sure_path_exists(path):
    """ Module to make sure the path exists if not create it
    """
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def print_representations(dp_object):
    """ Module to print the representations"""
    print("The DASH media has the following video representations/bitrates")
    for bandwidth in dp_object.video:
        print(bandwidth)


def start_playback_smart(dp_object, domain, playback_type=None, download=False, video_segment_duration=None,
                         retrans=False):
    """ Module that downloads the MPD-FIle and download
        all the representations of the Module to download
        the MPEG-DASH media.
        Example: start_playback_smart(dp_object, domain, "SMART", DOWNLOAD, video_segment_duration)

        :param dp_object:       The DASH-playback object
        :param domain:          The domain name of the server (The segment URLS are domain + relative_address)
        :param playback_type:   The type of playback
                                1. 'BASIC' - The basic adapataion scheme
                                2. 'SARA' - Segment Aware Rate Adaptation
                                3. 'NETFLIX' - Buffer based adaptation used by Netflix
                                4. 'VLC' - VLC adaptation scheme
        :param download: Set to True if the segments are to be stored locally (Boolean). Default False
        :param video_segment_duration: Playback duratoin of each segment
        :return:
    """
    # Initialize the DASH buffer
    video_segment_duration = 2
    dash_player = dash_buffer.DashPlayer(dp_object.playback_duration, video_segment_duration)
    start_dload_time = timeit.default_timer()
    pl_phase="INC"
    dash_player.start()
    # A folder to save the segments in
    file_identifier = id_generator()
    config_dash.LOG.info("The segments are stored in %s" % file_identifier)
    dp_list = defaultdict(defaultdict)
    # Creating a Dictionary of all that has the URLs for each segment and different bitrates
    for bitrate in dp_object.video:
        # Getting the URL list for each bitrate
        dp_object.video[bitrate] = read_mpd.get_url_list(dp_object.video[bitrate], video_segment_duration,
                                                         dp_object.playback_duration, bitrate)
        if "$Bandwidth$" in dp_object.video[bitrate].initialization:
            dp_object.video[bitrate].initialization = dp_object.video[bitrate].initialization.replace(
                "$Bandwidth$", str(bitrate))
        media_urls = [dp_object.video[bitrate].initialization] + dp_object.video[bitrate].url_list
        for segment_count, segment_url in enumerate(media_urls, dp_object.video[bitrate].start):
            # segment_duration = dp_object.video[bitrate].segment_duration
            dp_list[segment_count][bitrate] = segment_url
    bitrates = sorted(dp_object.video.keys())
    average_dwn_time = 0
    segment_files = []
    # For basic adaptation
    global segment_w_chunks
    init_dl_start_time = timeit.default_timer()
    segment_w_chunks = []
    previous_segment_times = []
    recent_download_sizes = []
    bitrate_history = []
    # segment_dl_rates = []
    weighted_mean_object = None
    current_bitrate = bitrates[0]
    retx_current_bitrate = bitrates[0]
    previous_bitrate = None
    total_downloaded = 0
    bitrate_holder = 0
    dl_rate_history = []
    # Delay in terms of the number of segments
    delay = 0
    normal_dw_count = 0
    segment_duration = 0
    segment_download_time = 0
    # Netflix Variables
    average_segment_sizes = netflix_rate_map = None
    netflix_state = "INITIAL"
    RETRANSMISSION_SWITCH = False
    # retransmission_delay = 0 ''' not sure why its created, Unused'''
    retx_flag = False
    retx_thread = False
    cmdline_retrans = retrans
    # Start playback of all the segments
    # for segment_number, segment in enumerate(dp_list, dp_object.video[current_bitrate].start):
    # for segment_number in dp_list:s
    segment_size = 0
    segment_number = 1
    retx_segment_number = 1
    original_segment_number = 1
    while segment_number < len(dp_list):
        try:
            # if retx_flag==False:
            while thread_seg.is_alive():
                pass
            # else:
            # while thread_seg.is_alive() and retx_thread==True:
            #	pass
        except NameError as e:
            print("Thread not Created {}".format(e))

        # if retransmission_delay_switch == True:
        # segment_number = original_segment_number
        # retransmission_delay_switch = False
        segment = segment_number
        # print len(dp_list)
        # print "dp_list"
        # print segment
        # print segment_number
        # print "++++++++++++"
        config_dash.LOG.info(" {}: Processing the segment {}".format(playback_type.upper(), segment_number))
        write_json()
        if not previous_bitrate:
            previous_bitrate = current_bitrate
        if SEGMENT_LIMIT:
            if not dash_player.segment_limit:
                dash_player.segment_limit = int(SEGMENT_LIMIT)
            if segment_number > int(SEGMENT_LIMIT):
                config_dash.LOG.info("Segment limit reached")
                break
        if segment_number == dp_object.video[bitrate].start:
            current_bitrate = bitrates[0]
        else:
            if playback_type.upper() == "BASIC":
                current_bitrate, average_dwn_time = basic_dash2.basic_dash2(segment_number, bitrates, average_dwn_time,
                                                                            recent_download_sizes,
                                                                            previous_segment_times, current_bitrate)

                # if dash_player.buffer.qsize() > config_dash.BASIC_THRESHOLD:
                if dash_player.buffer.__len__() > config_dash.BASIC_THRESHOLD:  # MZ
                    # delay = dash_player.buffer.qsize() - config_dash.BASIC_THRESHOLD
                    delay = dash_player.buffer.__len__() - config_dash.BASIC_THRESHOLD  # MZ
                config_dash.LOG.info("Basic-DASH: Selected {} for the segment {}".format(current_bitrate,
                                                                                         segment_number + 1))
            elif playback_type.upper() == "SMART":
                if not weighted_mean_object:
                    weighted_mean_object = WeightedMean(config_dash.SARA_SAMPLE_COUNT)
                    config_dash.LOG.debug("Initializing the weighted Mean object")
                # Checking the segment number is in acceptable range
                segment_download_rate = segment_size / segment_download_time
                if segment_number < len(dp_list) - 1 + dp_object.video[bitrate].start:
                    try:
                        current_bitrate, delay = weighted_dash.weighted_dash(bitrates, dash_player,
                                                                             weighted_mean_object.weighted_mean_rate,
                                                                             current_bitrate, segment_number,
                                                                             segment_size, segment_download_time,
                                                                             get_segment_sizes(dp_object,
                                                                                               segment_number + 1))
                    except IndexError as e:
                        config_dash.LOG.error(e)
                # with open('sara-dash-chosen-rate.txt', 'a') as sara:
                # sara.write(str(current_bitrate) + '\t' + str(segment_download_rate) + '\n')
                if not os.path.exists(download_log_file):
                    header_row = "EpochTime,CurrentBufferSize,Bitrate,DownloadRate".split(",")
                    stats = (
                    (timeit.default_timer() - start_dload_time), str(dash_player.buffer.__len__()), current_bitrate,
                    segment_download_rate)
                else:
                    header_row = None
                    stats = (
                    (timeit.default_timer() - start_dload_time), str(dash_player.buffer.__len__()), current_bitrate,
                    segment_download_rate)
                str_stats = [str(i) for i in stats]
                with open(download_log_file, "a") as log_file_handle:
                    result_writer = csv.writer(log_file_handle, delimiter=",")
                    if header_row:
                        result_writer.writerow(header_row)
                    result_writer.writerow(str_stats)
            elif playback_type.upper() == "NETFLIX":
                config_dash.LOG.info("Playback is NETFLIX")
                # Calculate the average segment sizes for each bitrate
                if not average_segment_sizes:
                    average_segment_sizes = get_average_segment_sizes(dp_object)
                if segment_number < len(dp_list) - 1 + dp_object.video[bitrate].start:
                    try:
                        if segment_size and segment_download_time:
                            segment_download_rate = segment_size / segment_download_time
                        else:
                            segment_download_rate = 0
                        current_bitrate, netflix_rate_map, netflix_state = netflix_dash.netflix_dash(
                            bitrates, dash_player, segment_download_rate, current_bitrate, average_segment_sizes,
                            netflix_rate_map, netflix_state)
                        config_dash.LOG.info("NETFLIX: Next bitrate = {}".format(current_bitrate))
                    except IndexError as e:
                        config_dash.LOG.error(e)
                else:
                    config_dash.LOG.critical("Completed segment playback for Netflix")
                    break
                if not os.path.exists(download_log_file):
                    header_row = "EpochTime, CurrentBufferSize, Bitrate, DownloadRate".split(",")
                    stats = (
                    timeit.default_timer() - start_dload_time, str(dash_player.buffer.__len__()), current_bitrate,
                    segment_download_rate)
                else:
                    header_row = None
                    stats = (
                    timeit.default_timer() - start_dload_time, str(dash_player.buffer.__len__()), current_bitrate,
                    segment_download_rate)
                str_stats = [str(i) for i in stats]
                with open(download_log_file, "ab") as log_file_handle:
                    result_writer = csv.writer(log_file_handle, delimiter=",")
                    if header_row:
                        result_writer.writerow(header_row)
                    result_writer.writerow(str_stats)
                # If the buffer is full wait till it gets empty
                # if dash_player.buffer.qsize() >= config_dash.NETFLIX_BUFFER_SIZE:
                if dash_player.buffer.__len__() >= config_dash.NETFLIX_BUFFER_SIZE:  # MZ
                    # delay = (dash_player.buffer.qsize() - config_dash.NETFLIX_BUFFER_SIZE + 1) * segment_duration
                    delay = (
                                        dash_player.buffer.__len__() - config_dash.NETFLIX_BUFFER_SIZE + 1) * segment_duration  # MZ
                    config_dash.LOG.info("NETFLIX: delay = {} seconds".format(delay))
            elif playback_type.upper() == "VLC":
                config_dash.LOG.info("Unknown playback type:{}. Continuing with basic playback".format(playback_type))
                config_dash.LOG.info("VLC: Current Bitrate %d" % current_bitrate)
                # current_bitrate = basic_dash.basic_dash(segment_number, bitrates, segment_download_time, current_bitrate, dash_player.buffer.qsize(), segment_size)
                current_bitrate = basic_dash.basic_dash(segment_number, bitrates, segment_download_time,
                                                        current_bitrate, dash_player.buffer.__len__(),
                                                        segment_size)  # MZ
                with open('vlc-dash-chosen-rate.txt', 'a') as vlc:
                    vlc.write(str(current_bitrate) + '\n')
                # if dash_player.buffer.qsize() >= (config_dash.NETFLIX_BUFFER_SIZE):
                if dash_player.buffer.__len__() >= (config_dash.NETFLIX_BUFFER_SIZE):  # MZ
                    delay = 1
                else:
                    delay = 0
                if segment_number < len(dp_list) - 1 + dp_object.video[bitrate].start:
                    try:
                        if segment_size and segment_download_time:
                            segment_download_rate = segment_size / segment_download_time
                        else:
                            segment_download_rate = 0
                    except IndexError as e:
                        config_dash.LOG.error(e)
                if not os.path.exists(download_log_file):
                    header_row = "EpochTime,CurrentBufferSize,Bitrate,DownloadRate".split(",")
                    stats = (
                    timeit.default_timer() - start_dload_time, str(dash_player.buffer.__len__()), current_bitrate,
                    segment_download_rate)
                else:
                    header_row = None
                    stats = (
                    timeit.default_timer() - start_dload_time, str(dash_player.buffer.__len__()), current_bitrate,
                    segment_download_rate)
                str_stats = [str(i) for i in stats]
                with open(download_log_file, "ab") as log_file_handle:
                    result_writer = csv.writer(log_file_handle, delimiter=",")
                    if header_row:
                        result_writer.writerow(header_row)
                    result_writer.writerow(str_stats)

            elif playback_type.upper() == "EMPIRICAL":
                buffer_upper = config_dash.NETFLIX_BUFFER_SIZE * BUFFER_THRESHOLD_UPPER
                buffer_lower = config_dash.NETFLIX_BUFFER_SIZE * BUFFER_THRESHOLD_LOWER
                # segment_sizes_test = get_segment_sizes(dp_object,segment_number)
                # print "================"
                # print segment_sizes_test
                # print segment_number
                # print "================"
                if segment_size == 0:
                    curr_rate = 0
                else:
                    print("Segment size:{}, Dw_time:{}".format(segment_size,segment_download_time))
                    curr_rate = (segment_size) / segment_download_time
                # segment_dl_rates.append(curr_rate)
                average_segment_sizes = get_average_segment_sizes(dp_object)
                dl_rate_history.append(curr_rate)
                # print "-----------!!!!!!!!"
                # print dl_rate_history
                # print "!!!!!!!------------"
                if len(dl_rate_history) > 10:
                    dl_rate_history.pop(0)
                # current_bitrate = empirical_dash.empirical_dash(average_segment_sizes, segment_number, bitrates, segment_download_time, current_bitrate, dash_player.buffer.qsize(), segment_size, get_segment_sizes(dp_object,segment_number-2), video_segment_duration, dl_rate_history, bitrate_history, segment_w_chunks, DOWNLOAD_CHUNK)
                emp_func_time = timeit.default_timer()
                print(len(segment_w_chunks))
                current_bitrate = empirical_dash.empirical_dash(average_segment_sizes, segment_number, bitrates,
                                                                segment_download_time, current_bitrate,
                                                                dash_player.buffer.__len__(), segment_size,
                                                                get_segment_sizes(dp_object, segment_number - 2),
                                                                video_segment_duration, dl_rate_history,
                                                                bitrate_history, segment_w_chunks, DOWNLOAD_CHUNK,pl_phase)  # MZ

                with open("/opt/SQUAD/http2_seg_time", 'a') as seg_time:
                    seg_time.write("{},{}\n".format(segment_number, timeit.default_timer() - emp_func_time))

                bitrates = [float(i) for i in bitrates]

                if len(segment_w_chunks) > 10:
                    # segment_w_chunks = numpy.delete(segment_w_chunks, (0), axis=0)
                    segment_w_chunks.pop(0)
                    print("deleted elements!")
                # print bitrates
                # if dash_player.buffer.qsize() >= buffer_upper and segment_number > 10:
                if segment_number > INIT_SEG:
                    if current_bitrate <= bitrate_history[-1] or dash_player.buffer.__len__() < buffer_lower:
                        print("current_bitrate <= bitrate_history[-1] or dash_player.buffer.__len__() < buffer_lower")
                        if dash_player.buffer.__len__() >= buffer_upper:
                            pl_phase="INC"
                            br_index=max(0,int(bitrates.index(bitrate_history[-1]) - 2))
                            with open('empirical-buffer-holder.txt', 'a') as buh:
                                buh.write(str(segment_number) + '\t' + '1' + '\n')
                            if bitrate_holder == 1:
                                # print "bitrate holder: ON"
                                # print "bitrate_history[-1]: " + str(bitrate_history[-1])
                                # print bitrate_history
                                current_bitrate = bitrate_history[-1]
                            elif len(bitrates) > 1 and current_bitrate < bitrates[br_index]:
                                # print "current_rate! : " + str(current_bitrate)
                                # current_bitrate = bitrate_history[-1]
                                	next_bitrate = int(round(bitrate_history[-1] + current_bitrate) / 2)
                                	current_bitrate = min(bitrates, key=lambda x: abs(x - next_bitrate))
                                # next_q_layer = int(round((bitrates.index(bitrate_history[-1]) + bitrates.index(current_bitrate)) / 2))
                                # print "next_q_layer! : " + str(next_q_layer)
                                # current_bitrate = bitrates[next_q_layer]
                                # print "changed current_rate! : " + str(current_bitrate)
                                	bitrate_holder = 1
                                	pl_phase="DEC"
                            # elif (current_bitrate > bitrates[int(bitrates.index(bitrate_history[-1]) - 2)]) and (current_bitrate < bitrates[int(bitrates.index(bitrate_history[-1]))]):
                            elif len(bitrates) > 1 and (current_bitrate >= bitrates[br_index]) and (current_bitrate < bitrate_history[-1]):
                                # print "holding bitrate!"
                                # print bitrate_history
                                        current_bitrate = bitrate_history[-1]
                            elif bitrate_holder == 0 and current_bitrate < bitrates[-1] and (current_bitrate == bitrates[int(bitrates.index(bitrate_history[-1]) + 1)]):
                                current_bitrate = bitrate_history[-1]
                            elif bitrate_holder == 0:
                                print("go ahead!")
                        elif bitrate_holder == 1 and dash_player.buffer.__len__() >= buffer_lower:
                            # print "bitrate holder: ON; buffer > lower_bound"
                            # print bitrate_history
                            # print "bitrate_history[-1]: " + str(bitrate_history[-1]
                            pl_phase="STEADY"
                            current_bitrate = bitrate_history[-1]
                        if dash_player.buffer.__len__() < buffer_lower:
                            # print "buffer < lower"
                            # print dash_player.buffer.__len__()
                            # print buffer_lower
                            bitrate_holder = 0
                            pl_phase="DEC"
                        if current_bitrate != bitrates[-1] and bitrate_history[-1] < bitrates[-1] and (
                                current_bitrate == bitrates[int(bitrates.index(bitrate_history[-1]) + 1)]):
                            current_bitrate = bitrate_history[-1]
                    elif current_bitrate > bitrate_history[-1] and dash_player.buffer.__len__() >= buffer_upper:
			# print "current_bitrate > bitrate_history[-1] and dash_player.buffer.__len__() >= buffer_lower"
                        # print current_bitrate
                        # print bitrate_history[-1]
                        # print buffer_lower
                        # print "current_bitrate > bitrate_history[-1] and dash_player.buffer.__len__() >= buffer_lower"
                        bitrate_holder = 0
                        pl_phase="INC"
                # if (bitrates.index(current_bitrate) - bitrates.index(bitrate_history[-1])) <= 2 and (bitrates.index(current_bitrate) - bitrates.index(bitrate_history[-1])) >= 0:
                #    current_bitrate = bitrate_history[-1]
                # current_bitrate = bitrates[bitrates.index(bitrate_history[-1])/2]
                print("---------------current_bitrate: " + str(current_bitrate))
                bitrate_actual_time = timeit.default_timer() - init_dl_start_time
                # if dash_player.buffer.qsize() >= (config_dash.NETFLIX_BUFFER_SIZE):
                if segment_size and segment_download_time:
                    segment_download_rate = segment_size / segment_download_time
                    # with open('/opt/SQUAD/http2_read_modif_seg_size_rate.txt', 'a') as rate_f:
                    # rate_f.write(str(segment_size)+'\t'+str(segment_download_rate)+'\n')
                else:
                    segment_download_rate = 0
                RETRANS_OFFSET = False

                # original_segment_number = segment_number
                ''' TODO: check if retx is ongoing before entering this case'''
                with open("/opt/SQUAD/retx_decision", 'a') as rtx_decision:
                    rtx_decision.write(
                        "seg#: {}, retx cmdline: {}, retx_thread:{}, retx_flag:{}\n".format(segment_number,
                                                                                            cmdline_retrans,
                                                                                            retx_thread, retx_flag))

                if segment_number > INIT_SEG and cmdline_retrans and retx_thread == False:

                    print('++++++++++++++++++++++++++')
                    print(dash_player.buffer.__len__())
                    print(RETRANS_THRESHOLD_UPPER * config_dash.NETFLIX_BUFFER_SIZE)
                    print(RETRANSMISSION_SWITCH)
                    print('++++++++++++++++++++++++++')
                    if dash_player.buffer.__len__() >= (
                            RETRANS_THRESHOLD_UPPER * config_dash.NETFLIX_BUFFER_SIZE) or RETRANSMISSION_SWITCH == True:
                        with open('empirical-retrans.txt', 'a') as retrans:
                            retrans.write(str(segment_number) + '\t' + '2' + '\n')
                        with open('empirical-debug.txt', 'a') as emp:
                            emp.write("!!!!!!!RETRANSMISSION!!!!!!!!" + '\n')
                        print("RETRANSMISSION_SWITCH = True !")
                        RETRANSMISSION_SWITCH = True
                        ''' Don't need these as parallel streams need 2 segs and quals '''
                        # original_segment_number = segment_number
                        # original_current_bitrate = current_bitrate
                        retx_current_bitrate, retx_segment_number, retx_flag = retransmission.retransmission(dp_object,
                                                                                                             current_bitrate,
                                                                                                             segment_number,
                                                                                                             dash_player.buffer,
                                                                                                             bitrates,
                                                                                                             segment_download_rate,
                                                                                                             config_dash.NETFLIX_BUFFER_SIZE,
                                                                                                             video_segment_duration)
                        if dash_player.buffer.__len__() < (RETRANS_THRESHOLD_LOWER * config_dash.NETFLIX_BUFFER_SIZE):
                            RETRANSMISSION_SWITCH = False
                            '''DOUBT: does this the buffer size check change decision about retx'''
                            retx_flag = False
                        # dl_rate based retransmission:
                        # if segment_number != original_segment_number and (curr_rate - current_bitrate >= original_current_bitrate):
                        if retx_flag:  # segment_number != original_segment_number:
                            retx_thread = True
                            # retransmission_delay_switch = True
                            # seg_num_offset = - (original_segment_number - segment_number + 1)
                            seg_num_offset = - (segment_number - retx_segment_number + 1)
                            bitrate_history.pop(seg_num_offset)
                            bitrate_history.insert(seg_num_offset, retx_current_bitrate)
                            RETRANS_OFFSET = True
                            # retransmission_delay += 1
                            retrans_next_segment_size = get_segment_sizes(dp_object, segment_number - 2)[
                                current_bitrate]
                        with open('empirical-debug.txt', 'a') as emp:
                            # for item in bitrate_history:
                            #    emp.write("%s " % item)
                            emp.write('\n' + str(segment_number) + '\t' + str(bitrate_actual_time) + '\t' + str(
                                current_bitrate) + '\t' + str(dash_player.buffer.__len__()) + 'retr' + '\n')
                # print "###########"
                with open('empirical-dash-chosen-rate.txt', 'a') as emp:
                    emp.write(str(segment_number) + '\t' + str(bitrate_actual_time) + '\t' + str(
                        segment_download_rate * 8) + '\t' + str(current_bitrate) + '\t' + str(
                        dash_player.buffer.__len__()) + '\n')
                if dash_player.buffer.__len__() >= (config_dash.NETFLIX_BUFFER_SIZE):  # MZ
                    delay = 1
                else:
                    delay = 0
                # print segment_number
                # print "=============="
                # print dp_object.video[current_bitrate]
                # print "=============="
                if RETRANS_OFFSET == False:
                    bitrate_history.append(current_bitrate)
                    # segment_number -= retransmission_delay
                    # retransmission_delay_done = True
                print("-------------+++++++++++++")
                print(dp_list[segment][current_bitrate])
                print(urllib.parse.urljoin(domain, segment_path))
                print("-------------+++++++++++++")
                '''
                if not os.path.exists(download_log_file):
                            header_row = "EpochTime, CurrentBufferSize, Bitrate, DownloadRate, SegmentNumber".split(",")
                            stats = (timeit.default_timer()-start_dload_time, str(dash_player.buffer.__len__()), current_bitrate, segment_download_rate, segment_number)
                else:
                            header_row=None
                            stats = (timeit.default_timer()-start_dload_time, str(dash_player.buffer.__len__()), current_bitrate, segment_download_rate,segment_number)
                str_stats = [str(i) for i in stats]
                with open(download_log_file, "a") as log_file_handle:
                            result_writer = csv.writer(log_file_handle, delimiter=",")
                            if header_row:
                                result_writer.writerow(header_row)
                            result_writer.writerow(str_stats) 
                '''
        segment_path = dp_list[segment][current_bitrate]
        segment_url = urllib.parse.urljoin(domain, segment_path)
        # print "+++++++++++++"
        # print segment_path
        # print segment_url
        # print dp_list[segment]
        # print "+++++++++++++"
        config_dash.LOG.info("{}: Segment URL = {}".format(playback_type.upper(), segment_url))

        ''' We want both if retx'''
        ''' DOUBT(solved): Don't check for delay (buff full?) as we replace'''
        ''' DOUBT(solved): should we wait (thread join) for retx_seg to download (have to check b4 retx.py called)?'''
        if retx_flag:
            retx_segment_path = dp_list[retx_segment_number][retx_current_bitrate]  # due to implementation
            retx_segment_url = urllib.parse.urljoin(domain, retx_segment_path)

        try:
            with open("/opt/SQUAD/retx_decision", 'a') as retx_state:
                retx_state.write("retx_flag: {}, retx_url :{}\n".format(retx_flag, retx_segment_url))
        except:
            with open("/opt/SQUAD/retx_decision", 'a') as retx_state:
                retx_state.write("retx_flag: {}, normal_url: {}\n".format(retx_flag, segment_url))

        # debugging retx_flag start
        # ----------------#
        # trying to solve "Same thread can't enter" problem
        # get the data from retx_segment_download()-> retx_seg_dw_object
        # might consider doing retx_seg_dw_object = SegmentDownloadStats() earlier

        try:
            if (not thread_retx.is_alive()):
                if retx_done_q.qsize() > 0:
                    lock.acquire()
                    retx_seg_dw_object = retx_done_q.get()
		    #retx_segment_download_time = retx_seg_dw_object.segment_dw_time#timeit.default_timer() - retx_start_time
                    lock.release()
                    # with open("/opt/SQUAD/retx_thread_decision",'a') as retx_state:
                    #        retx_state.write("retx_flag: {}, retx_seg_size: {},normal_url: {}\n".format(retx_flag, retx_seg_dw_object.segment_size, segment_url))

                    if (retx_seg_dw_object.segment_size > 0):  # retx_abandonment
                        # retx_thread = False # retx_thread free
                        # with open("/opt/SQUAD/retx_abandonment",'a') as retx_abandon:
                        # retx_abandon.write("Retx of seg {}\n".format(retx_seg_dw_object.segment_filename))
                        config_dash.LOG.info(
                            "{}: Downloaded debug Retxsegment {} Chunk Rate len {}".format(playback_type.upper(),
                                                                                           retx_segment_url, len(
                                    retx_seg_dw_object.segment_chunk_rates)))
                        retx_segment_download_time = retx_seg_dw_object.segment_dw_time # timeit.default_timer() - retx_start_time #lock this as this is given to emperical_dash.py
                        retx_segment_download_rate = retx_seg_dw_object.segment_size / retx_segment_download_time
                        lock.acquire()
                        segment_w_chunks.append(retx_seg_dw_object.segment_chunk_rates)
                        lock.release()
                        '''TODO: Create json'''
                        # Updating the JSON information
                        retx_segment_name = os.path.split(retx_segment_url)[1]
                        if "segment_info" not in config_dash.JSON_HANDLE:
                            config_dash.JSON_HANDLE["segment_info"] = list()

                        config_dash.JSON_HANDLE["segment_info"].append((retx_segment_name, retx_current_bitrate,
                                                                        retx_seg_dw_object.segment_size,
                                                                        retx_segment_download_time))

                        total_downloaded += retx_seg_dw_object.segment_size
                        config_dash.LOG.info(
                            "{} : RETX: The total downloaded = {}, segment_size = {}, segment_number = {}".format(
                                playback_type.upper(), total_downloaded, retx_seg_dw_object.segment_size,
                                retx_segment_number))

                        with open(download_log_file, 'a') as rtx_api_proof:
                        	rtx_api_proof.write("{},{},{},{},{},{},{},{}\n".format(time.time(),timeit.default_timer() - start_dload_time,
                                                                          str(dash_player.buffer.__len__()),
                                                                          retx_current_bitrate,
                                                                          (retx_segment_download_rate),
                                                                          retx_segment_number,retx_seg_dw_object.segment_size,pl_phase))

                        retx_segment_info = {'playback_length': video_segment_duration,
                                             'size': retx_seg_dw_object.segment_size,
                                             'bitrate': retx_current_bitrate,
                                             'data': retx_seg_dw_object.segment_filename,
                                             'URI': retx_segment_url,
                                             'segment_number': retx_segment_number,
                                             'segment_layer': bitrates.index(retx_current_bitrate)}

                        segment_duration = retx_segment_info['playback_length']

                        with open("/opt/SQUAD/retx_API_proof.txt", 'a') as rtx_api_proof:
                            rtx_api_proof.write("retx_seg_info: {}\n".format(retx_segment_info))
                        segment_size = retx_seg_dw_object.segment_size  # lock this as this is given to emperical_dash.py
                        segment_download_time = retx_seg_dw_object.segment_dw_time
                        '''TODO: Write json to buffer'''
                        dash_player.write(retx_segment_info)
                        # del retx_seg_dw_object
                        retx_thread = False  # retx_thread free, set after retx_download/abandonment
                        retx_flag = False  # not req
                        with open("/opt/SQUAD/retx_API_proof.txt", 'a') as rtx_api_proof:
                            rtx_api_proof.write("{},{},{},{},{}\n".format(timeit.default_timer() - start_dload_time,
                                                                          str(dash_player.buffer.__len__()),
                                                                          retx_current_bitrate,
                                                                          retx_segment_download_rate,
                                                                          retx_segment_number))

                    else:
                        retx_thread = False  # retx_thread free
                        retx_flag = False  #
                        with open("/opt/SQUAD/retx_abandonment", 'a') as retx_abandon:
                            retx_abandon.write("Abandoned Retx, not writing in the buffer, retx_url:{}\n".format(
                                thread_retx.is_alive(), retx_segment_url))



        except:
            print("")
        # debugging retx_thread end
        # --------------------------------------------------------#
        # --------------------------------------------------------#

        if retx_flag and (retx_segment_url is not segment_url):
            '''TODO: call retx_dw_seg retx thread'''
            retx_seg_dw_object = SegmentDownloadStats()
            config_dash.LOG.info(
                "{}: Started downloading retx_segment {}".format(playback_type.upper(), retx_segment_url))
            #retx_start_time = timeit.default_timer()
            try:
                if (not thread_retx.is_alive()):
                    config_dash.LOG.info(
                        "{}: Started 2nd downloading retx_segment {}".format(playback_type.upper(), retx_seg_dw_object))
                    config_dash.LOG.info("{}: 2nd downloading territory retx_segment {}".format(playback_type.upper(),
                                                                                                retx_seg_dw_object))
                    retx_flag = False  # set before starting retx
                    thread_retx = threading.Thread(target=retx_download_segment, args=(
                    retx_segment_url, file_identifier, retrans_next_segment_size, video_segment_duration,
                    dash_player.current_play_segment, retx_segment_number))
                    thread_retx.start()
                    # retx_thread=True
            except NameError as e:
                config_dash.LOG.info(
                    "{}: Started downloading 1st retx_segment {}".format(playback_type.upper(), retx_segment_url))
                config_dash.LOG.info("RETX_SEGMENT_ERROR: {}".format(e))
                retx_flag = False
                thread_retx = threading.Thread(target=retx_download_segment, args=(
                retx_segment_url, file_identifier, retrans_next_segment_size, video_segment_duration,
                dash_player.current_play_segment, retx_segment_number))
                # thread_retx=threading.Thread(target=retx_download_segment,args=(retx_segment_url, file_identifier, retrans_next_segment_size, video_segment_duration, dash_player.current_play_segment, retx_segment_number))
                thread_retx.start()
                # retx_thread=True
                config_dash.LOG.info("RETX_START")

        ''' TODO: Check it for normal case (not retx case)'''
        if delay:
            delay_start = time.time()
            config_dash.LOG.info("SLEEPING for {}seconds ".format(delay * segment_duration))
            while time.time() - delay_start < (delay * segment_duration):
                time.sleep(1)
            delay = 0
            config_dash.LOG.debug("SLEPT for {}seconds ".format(time.time() - delay_start))
        try:
            config_dash.LOG.info("{}: Started downloading segment {}".format(playback_type.upper(), segment_url))
            seg_dw_object = SegmentDownloadStats()
            ''' TODO: thread join for normal segment (Optional: then join retx thread)'''
            # segment_size, segment_filename

            normal_dw_count += 1
            with open("/opt/SQUAD/dw_cnt", 'a') as dw_cnt:
                dw_cnt.write("{}\n".format(normal_dw_count))

            try:
                if not thread_seg.is_alive():
                    if seg_done_q.qsize() > 0:
                        lock.acquire()
                        seg_dw_object = seg_done_q.get()
                        segment_download_time = seg_dw_object.segment_dw_time #timeit.default_timer() - start_time
                        lock.release()
                    # else:
                    # seg_dw_object=None
                    seg_pending_q.put([segment_url, file_identifier])
                    #start_time = timeit.default_timer()
                    thread_seg = threading.Thread(target=download_segment, args=(seg_pending_q.get()))
                    # thread_seg=threading.Thread(target=download_segment,args=(seg_pending_q.get()))
                    thread_seg.start()
            # else:
            # seg_pending_q.put([segment_url, file_identifier])
            except (NameError) as e: # (UnboundLocalError) as e:
                #start_time = timeit.default_timer()
                thread_seg = threading.Thread(target=download_segment, args=(segment_url, file_identifier,))
                # thread_seg=threading.Thread(target=download_segment,args=(segment_url, file_identifier,))
                thread_seg.start()
                seg_dw_object = seg_done_q.get()
                config_dash.LOG.error("Segment size %s"%seg_dw_object.segment_size)
                segment_download_time = seg_dw_object.segment_dw_time # timeit.default_timer() - start_time
            # seg_dw_object = download_segment(segment_url, file_identifier)
            # segment_size=seg_dw_object.segment_size #lock this as this is given to emperical_dash.py
            ''' lock apped into segment_w_chunks'''
            # segment_w_chunks.append(seg_dw_object.segment_chunk_rates)
        except IOError as e:
            config_dash.LOG.error("Unable to save segment %s" % e)
            return None
        ''' retx_seg_dw seperate and global (as one retx at a time) NO join?'''
        #segment_download_time = seg_dw_object.segment_dw_time # timeit.default_timer() - start_time #lock this as this is given to emperical_dash.py
        ''' Create global and update in dw_seg()    (as one retx at a time)'''
        if seg_dw_object.segment_size > 0:
            segment_size = seg_dw_object.segment_size
            segment_download_time = seg_dw_object.segment_dw_time
            config_dash.LOG.info("{}: Finished Downloaded segment {}".format(playback_type.upper(), segment_url))
            lock.acquire()
            segment_w_chunks.append(seg_dw_object.segment_chunk_rates)
            lock.release()
            segment_download_rate = seg_dw_object.segment_size / segment_download_time
            # with open('/opt/SQUAD/hyper_http2_read_mod_chunk_seg_time_rate.txt', 'a') as rate_f:
            #    rate_f.write(str(segment_size)+'\t'+str(segment_download_time)+'\t'+str(segment_download_rate*8)+'\n')
            previous_segment_times.append(segment_download_time)
            '''not used for Emperical (SQUAD Case) '''
            recent_download_sizes.append(segment_size)
            '''not used for Emperical (SQUAD Case) '''
            # Updating the JSON information
            segment_name = os.path.split(segment_url)[1]
            if "segment_info" not in config_dash.JSON_HANDLE:
                config_dash.JSON_HANDLE["segment_info"] = list()
            config_dash.JSON_HANDLE["segment_info"].append((segment_name, current_bitrate, segment_size,
                                                            segment_download_time))
            total_downloaded += seg_dw_object.segment_size
            config_dash.LOG.info("{} : The total downloaded = {}, segment_size = {}, segment_number = {}".format(
                playback_type.upper(),
                total_downloaded, segment_size, segment_number))

            segment_info = {'playback_length': video_segment_duration,
                            'size': seg_dw_object.segment_size,
                            'bitrate': current_bitrate,
                            'data': seg_dw_object.segment_filename,
                            'URI': segment_url,
                            'segment_number': segment_number,
                            'segment_layer': bitrates.index(current_bitrate)}
            segment_duration = segment_info['playback_length']
            dash_player.write(segment_info)
            '''TODO: Write seg_dw and retx_seg_dw stats'''
            if not os.path.exists(download_log_file):
                header_row = "EpochTime,RelTime,CurrentBufferSize,Bitrate,DownloadRate,SegmentNumber,SegmentSize,Phase".split(",")
                stats = (time.time(),timeit.default_timer() - start_dload_time, str(dash_player.buffer.__len__()), current_bitrate,
                         (segment_download_rate), segment_number,segment_size, pl_phase)
            else:
                header_row = None
                stats = (time.time(),timeit.default_timer() - start_dload_time, str(dash_player.buffer.__len__()), current_bitrate,
                         (segment_download_rate), segment_number,segment_size, pl_phase)
            str_stats = [str(i) for i in stats]
            with open(download_log_file, "a") as log_file_handle:
                result_writer = csv.writer(log_file_handle, delimiter=",")
                if header_row:
                    result_writer.writerow(header_row)
                result_writer.writerow(str_stats)
            segment_files.append(seg_dw_object.segment_filename)
            segment_number += 1
            '''not used in parallel streams as we have 2 diff segs qual levels on 2 streams '''
            # if retransmission_delay_switch == True:
            #    segment_number = original_segment_number
            # if segment_number > 10:
            #    if original_segment_number != segment_number:
            #        print "!!!!!!!!! not equal !!!!!!!!!!!!"
            #        print "segment_number " + str(segment_number)
            #        print "original segment number : " + str(original_segment_number)
            #        retransmission_delay_switch = True
            #        #original_segment_number += 1
            config_dash.LOG.info("Download info: segment URL: %s. Size = %s in %s seconds" % (
                segment_url, seg_dw_object.segment_size, str(segment_download_time)))
            if previous_bitrate:
                if previous_bitrate < current_bitrate:
                    config_dash.JSON_HANDLE['playback_info']['up_shifts'] += 1
                elif previous_bitrate > current_bitrate:
                    config_dash.JSON_HANDLE['playback_info']['down_shifts'] += 1
                previous_bitrate = current_bitrate
        # waiting for the player to finish playing
        if playback_type.upper() == "SMART" and weighted_mean_object:
            weighted_mean_object.update_weighted_mean(segment_size, segment_download_time)
    while dash_player.playback_state not in dash_buffer.EXIT_STATES:
        time.sleep(1)
    write_json()
    if not download:
        clean_files(file_identifier)


def get_segment_sizes(dp_object, segment_number):
    """ Module to get the segment sizes for the segment_number
    :param dp_object:
    :param segment_number:
    :return:
    """
    # for bitrate in dp_object.video:
    #    print "hellohello-------------"
    #    print dp_object.video[bitrate].segment_sizes[segment_number]
    #    print bitrate
    #    print segment_number
    #    print "+++++++++++++++++"
    #    segment_sizes = dict([(bitrate, dp_object.video[bitrate].segment_sizes[segment_number]))
    segment_sizes = dict(
        [(bitrate, dp_object.video[bitrate].segment_sizes[segment_number]) for bitrate in dp_object.video])
    # print "hellohello-------------segment_size"
    # print segment_sizes
    # print "+++++++++++++++++"
    config_dash.LOG.debug("The segment sizes of {} are {}".format(segment_number, segment_sizes))
    return segment_sizes


def get_average_segment_sizes(dp_object):
    """
    Module to get the avearge segment sizes for each bitrate
    :param dp_object:
    :return: A dictionary of aveage segment sizes for each bitrate
    """
    average_segment_sizes = dict()
    for bitrate in dp_object.video:
        segment_sizes = dp_object.video[bitrate].segment_sizes
        segment_sizes = [float(i) for i in segment_sizes]
        average_segment_sizes[bitrate] = sum(segment_sizes) / len(segment_sizes)
    config_dash.LOG.info("The avearge segment size for is {}".format(average_segment_sizes.items()))
    return average_segment_sizes


def clean_files(folder_path):
    """
    :param folder_path: Local Folder to be deleted
    """
    if os.path.exists(folder_path):
        try:
            for video_file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, video_file)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            os.rmdir(folder_path)
        except (WindowsError, OSError) as e:
            config_dash.LOG.info("Unable to delete the folder {}. {}".format(folder_path, e))
        config_dash.LOG.info("Deleted the folder '{}' and its contents".format(folder_path))


def start_playback_all(dp_object, domain):
    """ Module that downloads the MPD-FIle and download all the representations of 
        the Module to download the MPEG-DASH media.
    """
    # audio_done_queue = Queue()
    video_done_queue = Queue()
    processes = []
    file_identifier = id_generator(6)
    config_dash.LOG.info("File Segments are in %s" % file_identifier)
    # for bitrate in dp_object.audio:
    #     # Get the list of URL's (relative location) for the audio
    #     dp_object.audio[bitrate] = read_mpd.get_url_list(bitrate, dp_object.audio[bitrate],
    #                                                      dp_object.playback_duration)
    #     # Create a new process to download the audio stream.
    #     # The domain + URL from the above list gives the
    #     # complete path
    #     # The fil-identifier is a random string used to
    #     # create  a temporary folder for current session
    #     # Audio-done queue is used to exchange information
    #     # between the process and the calling function.
    #     # 'STOP' is added to the queue to indicate the end
    #     # of the download of the sesson
    #     process = Process(target=get_media_all, args=(domain, (bitrate, dp_object.audio),
    #                                                   file_identifier, audio_done_queue))
    #     process.start()
    #     processes.append(process)

    for bitrate in dp_object.video:
        dp_object.video[bitrate] = read_mpd.get_url_list(bitrate, dp_object.video[bitrate],
                                                         dp_object.playback_duration,
                                                         dp_object.video[bitrate].segment_duration)
        # Same as download audio
        process = Process(target=get_media_all, args=(domain, (bitrate, dp_object.video),
                                                      file_identifier, video_done_queue))
        process.start()
        processes.append(process)
    for process in processes:
        process.join()
    count = 0
    for queue_values in iter(video_done_queue.get, None):
        bitrate, status, elapsed = queue_values
        if status == 'STOP':
            config_dash.LOG.critical("Completed download of %s in %f " % (bitrate, elapsed))
            count += 1
            if count == len(dp_object.video):
                # If the download of all the videos is done the stop the
                config_dash.LOG.critical("Finished download of all video segments")
                break


def create_arguments(parser):
    """ Adding arguments to the parser """
    parser.add_argument('-m', '--MPD',
                        help="Url to the MPD File")
    parser.add_argument('-l', '--LIST', action='store_true',
                        help="List all the representations")
    parser.add_argument('-p', '--PLAYBACK',
                        default=DEFAULT_PLAYBACK,
                        help="Playback type (basic, sara, netflix, or all)")
    parser.add_argument('-n', '--SEGMENT_LIMIT',
                        default=SEGMENT_LIMIT,
                        help="The Segment number limit")
    parser.add_argument('-d', '--DOWNLOAD', action='store_true',
                        default=False,
                        help="Keep the video files after playback")
    parser.add_argument('-r', '--RETRANS', action='store_true',
                        default=False,
                        help="enable retransmission")


def main():
    """ Main Program wrapper """
    # configure the log file
    # Create arguments
    parser = ArgumentParser(description='Process Client parameters')
    create_arguments(parser)
    args = parser.parse_args()
    globals().update(vars(args))
    configure_log_file(playback_type=PLAYBACK.lower())
    config_dash.JSON_HANDLE['playback_type'] = PLAYBACK.lower()
    if not MPD:
        print("ERROR: Please provide the URL to the MPD file. Try Again..")
        return None
    config_dash.LOG.info('Downloading MPD file %s' % MPD)
    # Retrieve the MPD files for the video
    mpd_file = get_mpd(MPD)
    domain = get_domain_name(MPD)
    dp_object = DashPlayback()
    # Reading the MPD file created
    dp_object, video_segment_duration = read_mpd.read_mpd(mpd_file, dp_object)
    config_dash.LOG.info("The DASH media has %d video representations" % len(dp_object.video))
    if LIST:
        # Print the representations and EXIT
        print_representations(dp_object)
        return None
    if "all" in PLAYBACK.lower():
        if mpd_file:
            config_dash.LOG.critical("Start ALL Parallel PLayback")
            start_playback_all(dp_object, domain)
    elif "basic" in PLAYBACK.lower():
        config_dash.LOG.critical("Started Basic-DASH Playback")
        start_playback_smart(dp_object, domain, "BASIC", DOWNLOAD, video_segment_duration, RETRANS)
    elif "sara" in PLAYBACK.lower():
        config_dash.LOG.critical("Started SARA-DASH Playback")
        start_playback_smart(dp_object, domain, "SMART", DOWNLOAD, video_segment_duration, RETRANS)
    elif "netflix" in PLAYBACK.lower():
        config_dash.LOG.critical("Started Netflix-DASH Playback")
        start_playback_smart(dp_object, domain, "NETFLIX", DOWNLOAD, video_segment_duration, RETRANS)
    elif "vlc" in PLAYBACK.lower():
        config_dash.LOG.critical("Started Basic2-DASH Playback")
        start_playback_smart(dp_object, domain, "VLC", DOWNLOAD, video_segment_duration, RETRANS)
    elif "empirical" in PLAYBACK.lower():
        config_dash.LOG.critical("Started Hello-DASH Playback")
        start_playback_smart(dp_object, domain, "EMPIRICAL", DOWNLOAD, video_segment_duration, RETRANS)

    else:
        config_dash.LOG.error("Unknown Playback parameter {}".format(PLAYBACK))
        return None


if __name__ == "__main__":
    sys.exit(main())
