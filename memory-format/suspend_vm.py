#!/usr/bin/env python 
#

import os
import sys
import libvirt
import traceback
import zipfile
import subprocess
import multiprocessing
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

def main(xml_path):
    conn = libvirt.open("qemu:///session")
    machine = conn.createXML(open(xml_path, "r").read(), 0)

    #Get VNC port
    vnc_port = 5900
    try:
        running_xml_string = machine.XMLDesc(libvirt.VIR_DOMAIN_XML_SECURE)
        running_xml = ElementTree.fromstring(running_xml_string)
        vnc_port = running_xml.find("devices/graphics").get("port")
        vnc_port = int(vnc_port)-5900
    except AttributeError as e:
        LOG.error("Warning, Possible VNC port error:%s" % str(e))

    #_PIPE = subprocess.PIPE
    #vnc_process = subprocess.Popen(["gvncviewer", "localhost:%d" % vnc_port],
    #        stdout=_PIPE, stderr=_PIPE,
    #        close_fds=True)
    #vnc_process.wait()
    raw_input("Enter to suspend")

    #save memory snapshot
    output_filename = "./memory-snapshot"
    machine.save(output_filename)
    print "finish"
    return machine

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stdout.write("usage: %prog path to libvirtxml\n")
        sys.stdout.write("ex. %prog ./vm-image/vm.xml\n")
        sys.exit(1)
    main(sys.argv[1])
