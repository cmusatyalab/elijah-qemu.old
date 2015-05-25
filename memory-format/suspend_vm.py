#!/usr/bin/env python 
#

import os
import sys
import libvirt
import traceback
import zipfile
import subprocess
import struct
import select
import threading
import multiprocessing
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import time
from multiprocessing import Process
from qmp_af_unix import *

# NOTE: qemu doesn't erase unix socket file,
# so might want to clean it up manually
def delayed_stop():
    qmp = QmpAfUnix(QMP_UNIX_SOCK)
    ts = qmp.iterate_raw_live_once()
    print "VM suspended at %.6f" % ts

#class MemoryReadProcess(multiprocessing.Process):
class MemoryReadProcess(threading.Thread):
    def __init__(self, input_path, result_queue):
        self.input_path = input_path
        self.result_queue = result_queue
        self.total_read_size = 0

        #super(MemoryReadProcess, self).__init__(target=self.read_mem_snapshot)
        threading.Thread.__init__(self, target=self.read_mem_snapshot)

    def process_libvirt_header(self, mem_file_fd):
        data = mem_file_fd.read(4096*10)
        libvirt_header = _QemuMemoryHeaderData(data)
        header = libvirt_header.get_header()
        import pdb;pdb.set_trace()
        return libvirt_header._xml, data[len(header):]

    def read_mem_snapshot(self):
        # create memory snapshot aligned with 4KB
        time_s = time.time()

        for repeat in xrange(100):
            if os.path.exists(self.input_path) == False:
                print "waiting for %s: " % self.input_path
                time.sleep(0.1)
        try:
            self.in_fd = open(self.input_path, 'rb')
            input_fd = [self.in_fd]
            # skip libvirt header
            header_xml, remaining_data = self.process_libvirt_header(self.in_fd)
            # read 8 bytes of qemu header (total size of memory snapshot)
            import pdb;pdb.set_trace()
            qemu_header = self.in_fd.read(8)

            while True:
                input_ready, out_ready, err_ready = select.select(input_fd, [], [])
                if self.in_fd in input_ready:
                    data = self.in_fd.read(4096+8)
                    if data == None or len(data) <= 0:
                        break
                    self.total_read_size += len(data)
                    self.result_queue.put(data)
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


class _QemuMemoryHeader(object):
    HEADER_MAGIC = 'LibvirtQemudSave'
    HEADER_VERSION = 2
    # Header values are stored "native-endian".  We only support x86, so
    # assume we don't need to byteswap.
    HEADER_FORMAT = str(len(HEADER_MAGIC)) + 's19I'
    HEADER_LENGTH = struct.calcsize(HEADER_FORMAT)
    HEADER_UNUSED_VALUES = 15

    COMPRESS_RAW = 0
    COMPRESS_XZ = 3
    COMPRESS_CLOUDLET = 4

    EXPECTED_HEADER_LENGTH = 4096*2

    def __init__(self, f):
        # Read header struct
        f.seek(0)
        buf = f.read(self.HEADER_LENGTH)
        header = list(struct.unpack(self.HEADER_FORMAT, buf))
        magic = header.pop(0)
        version = header.pop(0)
        self._xml_len = header.pop(0)
        self.was_running = header.pop(0)
        self.compressed = header.pop(0)

        # Check header
        if magic != self.HEADER_MAGIC:
            raise MachineGenerationError('Invalid memory image magic')
        if version != self.HEADER_VERSION:
            raise MachineGenerationError('Unknown memory image version %d' %
                    version)
        if header != [0] * self.HEADER_UNUSED_VALUES:
            raise MachineGenerationError('Unused header values not 0')

        libvirt_header_len = self._xml_len + self.HEADER_LENGTH
        if libvirt_header_len != self.EXPECTED_HEADER_LENGTH:
            LOG.warning("libvirt header length is not aligned with 8KB")

        # Read XML, drop trailing NUL padding
        self.xml = f.read(self._xml_len - 1).rstrip('\0')
        if f.read(1) != '\0':
            raise MachineGenerationError('Missing NUL byte after XML')

    def seek_body(self, f):
        f.seek(self.HEADER_LENGTH + self._xml_len)

    def write(self, f):
        # Calculate header
        header = [self.HEADER_MAGIC,
                self.HEADER_VERSION,
                self._xml_len,
                self.was_running,
                self.compressed]
        header.extend([0] * self.HEADER_UNUSED_VALUES)

        # Write data
        f.seek(0)
        f.write(struct.pack(self.HEADER_FORMAT, *header))
        f.write(struct.pack('%ds' % self._xml_len, self.xml))
# pylint: enable=C0103

    def overwrite(self, f, new_xml):
        # Calculate header
        if len(new_xml) > self._xml_len - 1:
            # If this becomes a problem, we could write out a larger xml_len,
            # though this must be page-aligned.
            raise MachineGenerationError('self.xml is too large')
        header = [self.HEADER_MAGIC,
                self.HEADER_VERSION,
                self._xml_len,
                self.was_running,
                self.compressed]
        header.extend([0] * self.HEADER_UNUSED_VALUES)

        # Write data
        f.seek(0)
        f.write(struct.pack(self.HEADER_FORMAT, *header))
        f.write(struct.pack('%ds' % self._xml_len, new_xml))


class _QemuMemoryHeaderData(_QemuMemoryHeader):
    HEADER_MAGIC_PARTIAL = 'LibvirtQemudPart'

    def __init__(self, data):
        # Read header struct
        buf = data[:self.HEADER_LENGTH]
        header = list(struct.unpack(self.HEADER_FORMAT, buf))
        magic = header.pop(0)
        version = header.pop(0)
        self._xml_len = header.pop(0)
        self.was_running = header.pop(0)
        self.compressed = header.pop(0)

        # Check header
        if magic != self.HEADER_MAGIC and magic != self.HEADER_MAGIC_PARTIAL:
            # libvirt replace magic_partial to magic after finishing saving
            msg = 'Invalid memory image magic'
            LOG.error(msg)
            raise MachineGenerationError(msg)
        if version != self.HEADER_VERSION:
            msg = 'Unknown memory image version %d' % version
            LOG.error(msg)
            raise MachineGenerationError(msg)
        if header != [0] * self.HEADER_UNUSED_VALUES:
            msg = 'Unused header values not 0'
            LOG.error(msg)
            raise MachineGenerationError(msg)

        # Read XML, drop trailing NUL padding
        self.xml = data[self.HEADER_LENGTH:self.HEADER_LENGTH+self._xml_len]
        if self.xml[-1] != '\0':
            raise MachineGenerationError('Missing NUL byte after XML')

    def get_aligned_header(self, expected_header_size):
        current_size = self.HEADER_LENGTH + len(self.xml)
        padding_size = expected_header_size - current_size
        if padding_size < 0:
            msg = "WE FIXED LIBVIRT HEADER SIZE TO 2*4096\n" + \
                    "But given xml size is bigger than 2*4096"
            raise MachineGenerationError(msg)
        elif padding_size > 0:
            new_xml = self.xml + ("\0" * padding_size)
            self._xml_len = len(new_xml)
            self.xml = new_xml
        return self.get_header()

    def get_header(self):
        # Calculate header
        header = [self.HEADER_MAGIC,
                self.HEADER_VERSION,
                self._xml_len,
                self.was_running,
                self.compressed]
        header.extend([0] * self.HEADER_UNUSED_VALUES)

        # Write data
        header_binary = struct.pack(self.HEADER_FORMAT, *header)
        header_binary += struct.pack('%ds' % self._xml_len, self.xml)
        return header_binary


def main(xml_path):
    conn = libvirt.open("qemu:///session")
    machine = conn.createXML(open(xml_path, "r").read(), 0)
    raw_input("VM started. Enter to suspend")

    p = Process(target=delayed_stop)
    p.start()
    time.sleep(10)  # give time to process randomization request

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
