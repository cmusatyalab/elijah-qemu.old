#!/usr/bin/env python 
#

import os
import sys
import libvirt
import traceback
import zipfile
import subprocess
import select
import multiprocessing
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import time
from multiprocessing import Process
from qmp_af_unix import *

# stop raw live after 20 seconds
# NOTE: qemu doesn't erase unix socket file,
# so might want to clean it up manually
def delayed_stop():
    waiting_time = 1
    for index in range(waiting_time):
        sys.stdout.write("waiting %d/%d seconds\n" % (index, waiting_time))
        time.sleep(1)
    qmp = QmpAfUnix(QMP_UNIX_SOCK)
    qmp.stop_raw_live_once()


class MemoryReadProcess(multiprocessing.Process):
    def __init__(self, input_path, result_queue):
        self.input_path = input_path
        self.result_queue = result_queue
        self.total_read_size = 0

        super(MemoryReadProcess, self).__init__(target=self.read_mem_snapshot)

    def read_mem_snapshot(self):
        # create memory snapshot aligned with 4KB
        time_s = time.time()

        for repeat in xrange(100):
            if os.path.exists(self.input_path) == False:
                print "waiting for %s: " % self.input_path
                time.sleep(0.1)
        try:
            self.in_fd = open(self.input_path, 'rb')

            while True:
                input_fd = [self.in_fd]
                input_ready, out_ready, err_ready = select.select(input_fd, [], [])
                if self.in_fd in input_ready:
                    data = self.in_fd.read(1024*1024*1)
                    if data == None or len(data) <= 0:
                        break
                    self.total_read_size += len(data)
                    self.result_queue.put(data)
                    #time.sleep(0.1)
        except Exception, e:
            sys.stdout.write("[MemorySnapshotting] Exception1n")
            sys.stderr.write(traceback.format_exc())
            sys.stderr.write("%s\n" % str(e))

        time_e = time.time()
        sys.stdout.write("[time] Memory snapshotting time : %f\n" % (time_e-time_s))
        self.result_queue.put("SNAPSHOT_END")
        self.finish()

    def finish(self):
        pass


def main(xml_path):
    conn = libvirt.open("qemu:///session")
    machine = conn.createXML(open(xml_path, "r").read(), 0)
    raw_input("VM started. Enter to suspend")

    p = Process(target=delayed_stop)
    p.start()

    # process for receiving memory
    output_filename = "./memory-snapshot"
    output_fifo = output_filename + ".fifo"
    if os.path.exists(output_fifo) == True:
        os.remove(output_fifo)
    os.mkfifo(output_fifo)
    output_queue = multiprocessing.Queue(maxsize=-1)
    memory_read_proc = MemoryReadProcess(output_fifo,
                                         output_queue)
    memory_read_proc.start()

    # start memory dump
    machine.save(output_fifo)
    p.join()
    if os.path.exists(output_fifo) == True:
        os.remove(output_fifo)

    # save output queue to file
    out_fd = open(output_filename, "wb+")
    while True:
        data = output_queue.get()
        if data == "SNAPSHOT_END":
            break
        out_fd.write(data)
    out_fd.close()


    print "finish"
    return machine


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stdout.write("usage: %prog path to libvirtxml\n")
        sys.stdout.write("ex. %prog ./vm-image/vm.xml\n")
        sys.exit(1)
    main(sys.argv[1])
