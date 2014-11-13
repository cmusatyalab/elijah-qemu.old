#!/usr/bin/env python 
#

import os
import sys
import traceback
import zipfile
import multiprocessing


QUEUE_SUCCESS_MESSAGE = "raslkjadsoy2,akjs1loius"
RAM_PAGE_SIZE = 4096


def save_to_queue(input_path, input_queue):
    print "start saving to queue"
    in_fd = open(input_path, "rb")
    while True:
        data = in_fd.read(1024*1024*1)
        if len(data) == 0:
            break
        input_queue.put(data)
    input_queue.put(QUEUE_SUCCESS_MESSAGE)
    print "finish saving to queue"


def process(input_queue):
    # data structure to handle pipelined data
    def chunks(l, n):
        return [l[i:i + n] for i in range(0, len(l), n)]

    recved_data = input_queue.get()
    memory_page_list = chunks(recved_data, RAM_PAGE_SIZE)
    is_end_of_stream = False
    index_counter = 0
    while is_end_of_stream == False or len(memory_page_list) != 0:
        if len(memory_page_list) < 2: # empty or partial data
            recved_data = input_queue.get()
            if recved_data == QUEUE_SUCCESS_MESSAGE:
                # End of the stream
                is_end_of_stream = True
            else:
                required_length = 0
                if len(memory_page_list) == 1: # handle partial data
                    last_data = memory_page_list.pop(0)
                    required_length = RAM_PAGE_SIZE-len(last_data)
                    last_data += recved_data[0:required_length]
                    memory_page_list.append(last_data)
                memory_page_list += chunks(recved_data[required_length:], RAM_PAGE_SIZE)

        memory_chunk = memory_page_list.pop(0)
        index_counter += 1
        print "%d: length : %d" % (index_counter, len(memory_chunk))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stdout.write("usage: %prog memory_snapshot\n")
        sys.exit(1)
    input_queue = multiprocessing.Queue()
    save_to_queue(sys.argv[1], input_queue)
    process(input_queue)
