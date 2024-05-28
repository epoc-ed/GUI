import time
import numpy as np
from task.task import Task
import subprocess
import logging

class GetInfoTask(Task):
    def __init__(self, control_worker, command=''):
        super().__init__(control_worker, "GetInfo")
        self.conrol = control_worker
        self.command = command

    def run(self):
        while True:
            if self.control.tem_status['eos.GetMagValue'][0] != 0:
                prev_timestamp = self.control.tem_update_times['stage.GetPos'][0]
                break
            # self.control.send_to_tem("#more")
            self.tem_moreinfo()
            time.sleep(0.5)

        while True:
            # self.control.send_to_tem("#more")
            self.tem_moreinfo()
            if prev_timestamp != self.control.tem_update_times['stage.GetPos'][0]: break
            time.sleep(0.5)
        
        buffer = ''
        stoptime = time.localtime() # time.gmttime()
        buffer += "# TEM Record\n"
        buffer += "# TIMESTAMP: " + time.strftime("%Y/%m/%d %H:%M:%S", stoptime) + "\n"
        # buffer += f"# angular Speed:           {self.phi_dot:6.2f} deg/s\n"
        buffer += f"# magnification:           {self.control.tem_status['eos.GetMagValue_MAG'][0]:<6d} x\n"
        buffer += f"# detector distance:       {self.control.tem_status['eos.GetMagValue_DIFF'][0]:<6d} mm\n"
        # BEAM
        buffer += f"# spot_size:               {self.control.tem_status['eos.GetSpotSize']+1}\n"
        buffer += f"# alpha_angle:             {self.control.tem_status['eos.GetAlpha']+1}\n"
        # APERTURE
        buffer += f"# CL#:                     {self.control.tem_status['apt.GetSize(1)']}\n"
        buffer += f"# SA#:                     {self.control.tem_status['apt.GetSize(4)']}\n"
        # LENS
        buffer += f"# brightness:              {self.control.tem_status['lens.GetCL3']}\n"
        buffer += f"# diff_focus:              {self.control.tem_status['lens.GetIL1']}\n"
        buffer += f"# IL_stigm:                {self.control.tem_status['defl.GetILs']}\n"
        buffer += f"# PL_align:                {self.control.tem_status['defl.GetPLA']}\n"
        # STAGE
        buffer += f"# stage_position (nm/deg.):{self.control.tem_status['stage.GetPos']}\n"

        logging.info(buffer)
        
        # x = input(f'Write TEM status on a file? If YES, give a filename or "Y" ({filename}_[timecode].log). [N]\n')
        # if x != 'N' and x != '':
        #     if x != 'Y': filename = x
        if self.command != 'N':
            if self.command == 'Y' or self.command == '':
                filename = 'TEMstatus' + time.strftime("_%Y%m%d-%H%M%S.log", stoptime)
            else:
                filename = self.command + time.strftime("_%Y%m%d-%H%M%S.log", stoptime)
            print(f'Status written: {filename}')
            logfile = open(filename, 'w')
            logfile.write(buffer)
            logfile.close()
            
        logging.info("End of GetInfo task")
