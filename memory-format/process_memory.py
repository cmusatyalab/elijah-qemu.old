#!/usr/bin/env python 

import os
import sys
import libvirt
import traceback
import zipfile
import subprocess
import struct
import threading
import multiprocessing
import time
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from multiprocessing import Process
from qmp_af_unix import *



def delayed_stop():
    qmp = QmpAfUnix(QMP_UNIX_SOCK)
    qmp.connect()
    ret = qmp.qmp_negotiate()
    ret = qmp.unrandomize_raw_live()  # make page output order sequential
    if not ret:
        print "Failed"
        return
    time.sleep(20); ret = qmp.iterate_raw_live()   # new iteration
    time.sleep(10); ret = qmp.iterate_raw_live()   # new ieration
    time.sleep(10); ret = qmp.stop_raw_live()      # stop migration
    qmp.disconnect()


class MemoryReadProcess(threading.Thread):
    # header format for each memory page
    CHUNK_HEADER_FMT = "=Q"
    CHUNK_HEADER_SIZE = struct.calcsize("=Q")
    ITER_SEQ_BITS   = 16
    ITER_SEQ_SHIFT  = CHUNK_HEADER_SIZE * 8 - ITER_SEQ_BITS
    CHUNK_POS_MASK   = (1 << ITER_SEQ_SHIFT) - 1
    ITER_SEQ_MASK   = ((1 << (CHUNK_HEADER_SIZE * 8)) - 1) - CHUNK_POS_MASK
    ALIGNED_HEADER_SIZE = 4096*2

    def __init__(self, input_path, output_path):
        self.input_path = input_path
        self.output_path = output_path
        self.iteration_seq = 0
        threading.Thread.__init__(self, target=self.read_mem_snapshot)

    def process_header(self, mem_file_fd, output_fd):
        data = mem_file_fd.read(4096*10)
        libvirt_header = _QemuMemoryHeaderData(data)
        header = libvirt_header.get_header()
        header_size = len(header)

        # read 8 bytes of qemu header
        snapshot_size_data = data[header_size:header_size+self.CHUNK_HEADER_SIZE]
        snapshot_size, = struct.unpack(self.CHUNK_HEADER_FMT,
                                       snapshot_size_data)
        remaining_data = data[len(header)+self.CHUNK_HEADER_SIZE:]

        # write aligned header (8KB) to file
        aligned_header = libvirt_header.get_aligned_header(self.ALIGNED_HEADER_SIZE)
        output_fd.write(aligned_header)
        return libvirt_header.xml, snapshot_size, remaining_data

    def read_mem_snapshot(self):
        # waiting for named pipe
        for repeat in xrange(100):
            if os.path.exists(self.input_path) == False:
                print "waiting for %s: " % self.input_path
                time.sleep(0.1)
            else:
                break

        # read memory snapshot from the named pipe
        try:
            self.in_fd = open(self.input_path, 'rb')
            self.out_fd = open(self.output_path, 'wb')
            input_fd = [self.in_fd]
            # skip libvirt header
            header_xml, snapshot_size, remaining_data =\
                self.process_header(self.in_fd, self.out_fd)
            print "snapshot size of the first iteration: %d" % snapshot_size

            # remaining data are all about memory page
            # [(8 bytes header, 4KB page), (8 bytes header, 4KB page), ...]
            chunk_size = self.CHUNK_HEADER_SIZE + 4096
            leftover = self._data_chunking(remaining_data, chunk_size)
            while True:
                data = self.in_fd.read(10*4096)
                if not data:
                    break
                leftover = self._data_chunking(leftover+data, chunk_size)
        except Exception, e:
            sys.stdout.write("[MemorySnapshotting] Exception1n")
            sys.stderr.write(traceback.format_exc())
            sys.stderr.write("%s\n" % str(e))
        self.finish()

    def _data_chunking(self, l, n):
        leftover = ''
        for index in range(0, len(l), n):
            chunked_data = l[index:index+n]
            chunked_data_size = len(chunked_data)
            if chunked_data_size == n:
                header = chunked_data[0:self.CHUNK_HEADER_SIZE]
                header_data, = struct.unpack(self.CHUNK_HEADER_FMT, header)
                iter_seq = (header_data& self.ITER_SEQ_MASK) >> self.ITER_SEQ_SHIFT
                ram_offset = (header_data & self.CHUNK_POS_MASK)
                print("iter #:%d\toffset:%ld" % (iter_seq, ram_offset+self.ALIGNED_HEADER_SIZE))
                if iter_seq != self.iteration_seq:
                    self.iteration_seq = iter_seq
                    print "start new iteration %d" % self.iteration_seq
                # save the snapshot data
                self.out_fd.seek(ram_offset + self.ALIGNED_HEADER_SIZE)
                self.out_fd.write(chunked_data[self.CHUNK_HEADER_SIZE:])
            else:
                # last iteration
                leftover = chunked_data
        return leftover

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
    raw_input("VM started. Enter to start live migration")

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
    memory_read_proc = MemoryReadProcess(output_fifo, output_filename)
    memory_read_proc.start()

    # start memory dump
    machine.save(output_fifo)
    p.join()
    if os.path.exists(output_fifo) == True:
        os.remove(output_fifo)
    memory_read_proc.join()
    print "finish"
    return machine


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stdout.write("usage: %prog path to libvirtxml\n")
        sys.stdout.write("ex. %prog ./vm-image/vm.xml\n")
        sys.exit(1)
    main(sys.argv[1])
