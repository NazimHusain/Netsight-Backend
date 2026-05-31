from netmiko_jump_client import NetmikoJumpClient
import time
import sys
import logging
import os
from django.conf import settings
from datetime import datetime
       
def getConnection(ip, device_type,username,password,jobID, timestamp, retries=0):            
        logging.info(f"Trying to connect with {ip}")
        logging.info(f"[conn.py] Connecting {ip} | device_type={device_type}")
         # Base LOG directory
        base_dir = settings.LOG_DIR  # e.g. "IP_logs"
        os.makedirs(base_dir, exist_ok=True)

        # Job folder
        job_dir = os.path.join(base_dir, f"job_{jobID}")
        os.makedirs(job_dir, exist_ok=True)

        # Timestamp folder inside Job folder
        session_dir = os.path.join(job_dir, timestamp)
        os.makedirs(session_dir, exist_ok=True)

        # IP log file path
        logfile = os.path.join(session_dir, f"{ip}.log")

        try:
            net_device = {
            # 'device_type': 'autodetect',
            'device_type': device_type,
            'ip':ip,
            'username': username,
            'password':password,
            'session_log': logfile,
            'session_log_file_mode':"append",
            'auth_timeout':60,
            'conn_timeout':60,
            'global_delay_factor':10.0,
            'fast_cli': False,
            'banner_timeout': 60,
            
            
        }
            connection = NetmikoJumpClient(net_device)
        except Exception as err:
            logging.info(f" error occured as {err}")                
            exception_type = type(err).__name__              
            logging.info(f"ErrorReport{ip} , {exception_type}")         
            logging.info(err) 
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logging.info(f" error.Exception line:{exc_tb.tb_lineno},Error:{err}") 
            if retries >=3:                    
                return {
                "error": str(err),
                "ip": ip
                }
            time.sleep(2)
            retries=retries+1
            return getConnection(ip, device_type,username,password,jobID,timestamp, retries)  
   
        else:
            logging.info("connection established")
            return connection


