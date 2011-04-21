#!/usr/bin/env python
#
# Copyright 2011 Free Software Foundation, Inc.
# 
# This file is part of GNU Radio
# 
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

from gnuradio import gr, blks2
from gnuradio import uhd
from gnuradio import eng_notation
from gnuradio.eng_option import eng_option
from optparse import OptionParser

import time, struct, sys

# from current dir
from transmit_path import transmit_path

class my_top_block(gr.top_block):
    def __init__(self, options):
        gr.top_block.__init__(self)

        self._tx_freq   = options.tx_freq         # transmitter's center frequency
        self._tx_gain   = options.tx_gain         # transmitter's initial gain
        self._samp_rate = options.samp_rate       # interpolating rate for the USRP (prelim)
        if self._tx_freq is None:
            sys.stderr.write("-f FREQ or --freq FREQ or --tx-freq FREQ must be specified\n")
            raise SystemExit

        # Set up USRP sink; also adjusts interp, and bitrate
        self._setup_usrp_sink()

        # copy the final answers back into options for use by modulator
        #options.bitrate = self._bitrate

        self.txpath = transmit_path(options)

        self.connect(self.txpath, self.u)
        
    def _setup_usrp_sink(self):
        """
        Creates a UHD sink and sets the parameters
        """
        
        self.u = uhd.usrp_sink(device_addr="addr=192.168.10.2",
                               io_type=uhd.io_type.COMPLEX_FLOAT32,
                               num_channels=1)
        self.u.set_samp_rate(self._samp_rate)
        self.u.set_center_freq(self._tx_freq, 0)
        self.u.set_gain(self._tx_gain, 0)
        self.u.set_antenna("TX/RX", 0)
        self.u.set_clock_config(uhd.clock_config.external(), uhd.ALL_MBOARDS)

    def set_freq(self, target_freq):
        """
        Set the center frequency we're interested in.

        @param target_freq: frequency in Hz
        @rypte: bool

        Tuning is a two step process.  First we ask the front-end to
        tune as close to the desired frequency as it can.  Then we use
        the result of that operation and our target_frequency to
        determine the value for the digital up converter.
        """
        r = self.u.set_center_freq(self._tx_freq, 0)
        if r:
            return True

        return False
        
    def set_gain(self, gain):
        """
        Sets the analog gain in the USRP
        """
        self.gain = gain
        self.u.set_gain(gain, 0)

    def add_options(normal, expert):
        """
        Adds usrp-specific options to the Options Parser
        """
        add_freq_option(normal)
        normal.add_option("-v", "--verbose", action="store_true", default=False)

        expert.add_option("", "--tx-freq", type="eng_float", default=None,
                          help="set transmit frequency to FREQ [default=%default]", metavar="FREQ")
        expert.add_option("-g", "--tx-gain", type="eng_float", default=5,
                          help="set transmit gain [default=%default]")
        expert.add_option("-R", "--samp_rate", type="eng_float", default=500e3,
                          help="set transmit sample rate [default=%default]")
    # Make a static method to call before instantiation
    add_options = staticmethod(add_options)

    def _print_verbage(self):
        """
        Prints information about the transmit path
        """
        print "Using TX d'board %s"    % (self.u,)
        print "modulation:      %s"    % (self._modulator_class.__name__)
        print "interp:          %3d"   % (self._interp)
        print "Tx Frequency:    %s"    % (eng_notation.num_to_str(self._tx_freq))
        

def add_freq_option(parser):
    """
    Hackery that has the -f / --freq option set both tx_freq and rx_freq
    """
    def freq_callback(option, opt_str, value, parser):
        parser.values.rx_freq = value
        parser.values.tx_freq = value

    if not parser.has_option('--freq'):
        parser.add_option('-f', '--freq', type="eng_float",
                          action="callback", callback=freq_callback,
                          help="set Tx and/or Rx frequency to FREQ [default=%default]",
                          metavar="FREQ")

# /////////////////////////////////////////////////////////////////////////////
#                                   main
# /////////////////////////////////////////////////////////////////////////////

def main():

    def send_pkt(payload='', eof=False):
        return tb.txpath.send_pkt(payload, eof)

    parser = OptionParser(option_class=eng_option, conflict_handler="resolve")
    expert_grp = parser.add_option_group("Expert")
    parser.add_option("-s", "--size", type="eng_float", default=400,
                      help="set packet size [default=%default]")
    parser.add_option("-M", "--megabytes", type="eng_float", default=1.0,
                      help="set megabytes to transmit [default=%default]")
    parser.add_option("","--discontinuous", action="store_true", default=False,
                      help="enable discontinuous mode")

    my_top_block.add_options(parser, expert_grp)
    transmit_path.add_options(parser, expert_grp)
    blks2.ofdm_mod.add_options(parser, expert_grp)
    blks2.ofdm_demod.add_options(parser, expert_grp)

    (options, args) = parser.parse_args ()

    # build the graph
    tb = my_top_block(options)
    
    r = gr.enable_realtime_scheduling()
    if r != gr.RT_OK:
        print "Warning: failed to enable realtime scheduling"

    tb.start()                       # start flow graph
    
    # generate and send packets
    nbytes = int(1e6 * options.megabytes)
    n = 0
    pktno = 0
    pkt_size = int(options.size)

    while n < nbytes:
        send_pkt(struct.pack('!H', pktno) + (pkt_size - 2) * chr(pktno & 0xff))
        n += pkt_size
        sys.stderr.write('.')
        if options.discontinuous and pktno % 5 == 1:
            time.sleep(1)
        pktno += 1
        
    send_pkt(eof=True)
    tb.wait()                       # wait for it to finish

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
