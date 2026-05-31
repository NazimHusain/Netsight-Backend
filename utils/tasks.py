from huey.contrib.djhuey import task
from django.conf import settings
import datetime
from utils.conn import getConnection
from apps.helpers import models as HelperModels
from django.utils import timezone
from django.db.models import F
from threading import Semaphore
import json
import os
import logging
from utils.credentials import  resolve_credentials, resolve_netmiko_device_type
from django.db import connections, transaction, close_old_connections, connection
from huey.contrib.djhuey import db_task
from netmiko import ConnectHandler
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
# from itertools import repeat


file_lock = Lock()


PAGING_COMMANDS = {
    "juniper_junos": [
        "set cli screen-length 0",
        "set cli screen-width 0",
    ],
    "cisco_ios": "terminal length 0",
    "cisco_xr": "terminal length 0",
    "nokia_sros": "environment more false",
    "ciena_saos": "terminal length 0",
}

def get_results_file(job):
    """Create job directory and return results file path."""
    job_dir = os.path.join(settings.LOG_DIR, f"job_{job.id}")
    os.makedirs(job_dir, exist_ok=True)
    return os.path.join(job_dir, "results.jsonl")

def safe_close_connections():
    """Force close all DB connections safely."""
    try:
        connections.close_all()
    except Exception:
        logging.exception("Failed to close DB connections")


def get_paging(conn, device_type):
    """Send paging-disable commands appropriate for the vendor."""
    paging_cmd = PAGING_COMMANDS.get(device_type)
    if not paging_cmd:
        return

    if device_type == "juniper_junos":
        conn.send_command("set cli screen-length 0")
        conn.send_command("set cli screen-width 0")
        time.sleep(0.3)

    # if device_type == "juniper_junos":
    #     for page in paging_cmd:
    #         conn.send_command(page)
    else:
        conn.send_command(paging_cmd, read_timeout=30)



@task(retries=2, retry_delay=10)
def saveandupdate_ciscot4(gct_model,rows):
    gct_model.inventory_count = len(rows)
    logging.info(f"Going to save gct model")
    gct_model.save()

    for ip,hostname,circle in rows:
        if HelperModels.GCTCiscoT4.objects.filter(gct_model=gct_model, ip_address=ip).exists():
            continue
        else:
            HelperModels.GCTCiscoT4.objects.create(
                gct_model=gct_model,
                ip_address=ip,
                hostname=hostname,
                circle=circle
            )

    logging.info(f"Saved {len(rows)} entries for GCT Model {gct_model.model} into the database")

def process_row_thread(row, timestamp):
    conn = None

    try:
        if row.status != "PENDING":
            return

        job = row.job
        creds = resolve_credentials(job)
        device_type = resolve_netmiko_device_type(job)

        HelperModels.CommandExecution.objects.filter(id=row.id).update(
            status="RUNNING",
            started_at=timezone.now()
        )


        conn = getConnection(
            ip=row.host_ip,
            device_type=device_type,
            username=creds["username"],
            password=creds["password"],
            jobID=job.id,
            timestamp=timestamp
        )

        if isinstance(conn, dict) and "error" in conn:
            raise Exception(conn["error"])

        # -------- EXECUTION --------
        if job.execution_mode == "config":
            output = conn.send_command(
                row.command,
                read_timeout=420,
                expect_string=r"#\s*$|>\s*$|\]\s*$"
            )
        else:
            get_paging(conn, device_type)
            output = conn.send_command(
                row.command,
                read_timeout=420,
                strip_prompt=False,
                strip_command=False,
                
            )

        # -------- THREAD-SAFE FILE WRITE --------
        file_path = get_results_file(job)

        with file_lock:
            with open(file_path, "a") as f:
                f.write(json.dumps({
                    "ip": row.host_ip,
                    "status": "SUCCESS",
                    "command": row.command,
                    "output": output
                }) + "\n")

        # -------- SUCCESS --------
        HelperModels.CommandExecution.objects.filter(id=row.id).update(
            status="SUCCESS",
            finished_at=timezone.now()
        )

        HelperModels.Job.objects.filter(id=job.id).update(
            completed=F("completed") + 1,
            success=F("success") + 1
        )

    except Exception as e:

        logging.error(f"[ERROR] Row {row.id}: {str(e)}")

        file_path = get_results_file(row.job)

        with file_lock:
            with open(file_path, "a") as f:
                f.write(json.dumps({
                    "ip": row.host_ip,
                    "status": "ERROR",
                    "command": row.command,
                    "output": str(e)
                }) + "\n")

        HelperModels.CommandExecution.objects.filter(id=row.id).update(
            status="FAILED",
            error=str(e),
            finished_at=timezone.now()
        )

        HelperModels.Job.objects.filter(id=row.job.id).update(
            completed=F("completed") + 1,
            failed=F("failed") + 1
        )

    finally:
        try:
            if conn:
                conn.disconnect()
        except:
            pass

        close_old_connections()


@task(retries=2, retry_delay=10)
def process_multiple_rows(row_ids,timestamp):
    safe_close_connections()

    if not isinstance(row_ids, (list, tuple, set)):
        logging.info(f"Single row ID received: {row_ids}, converting to list {type(row_ids)}")
        row_ids = [row_ids]

    rows = list(
        HelperModels.CommandExecution.objects
        .select_related("job")
        .filter(id__in=row_ids)
    )
    if not rows:
        return
    
    
    def thread_worker(row):
        close_old_connections()  
        process_row_thread(row, timestamp)


    MAX_THREADS = 5

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(thread_worker, row) for row in rows]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"[THREAD ERROR]: {str(e)}")

    # -------- JOB COMPLETION CHECK --------
    job_id = rows[0].job.id if rows else None
    close_old_connections()  

    if job_id:
        total_done = HelperModels.CommandExecution.objects.filter(
            job_id=job_id,
            status__in=["SUCCESS", "FAILED"]
        ).count()
        job = HelperModels.Job.objects.get(id=job_id)

        logging.info(f"[JOB CHECK] Done: {total_done} / Total: {job.total_tasks}")
        if total_done >= job.total_tasks:
            HelperModels.Job.objects.filter(id=job_id).update(
                status="DONE",
                completed_at=timezone.now()
            )
            logging.info(f"[JOB COMPLETE] Job {job_id} marked as DONE")


# =================================================Multi Commands Task block ===================================

def execute_single_command(conn, device_type, job, device, cmd):
    try:
        if job.execution_mode == "config":
            output = conn.send_command(
                cmd.command,
                read_timeout=420,
                expect_string=r"#\s*$|>\s*$|\]\s*$"
            )
        else:
            get_paging(conn, device_type)
            output = conn.send_command(
                cmd.command,
                read_timeout=420,
                strip_prompt=False,
                strip_command=False,
            )

        # FILE WRITE
        file_path = get_results_file(job)
        with file_lock:
            with open(file_path, "a", buffering=1) as f:
                f.write(json.dumps({
                    "ip": device.host_ip,
                    "command": cmd.command,
                    "status": "SUCCESS",
                    "output": output
                }) + "\n")
        
        cmd.status = "SUCCESS"
        cmd.finished_at = timezone.now()
        cmd.save(update_fields=["status", "finished_at"])

        HelperModels.Job.objects.filter(id=job.id).update(
            completed=F("completed") + 1,
            success=F("success") + 1
        )

        return True

    except Exception as e:
        error_msg = str(e)
        logging.error(f"[CMD ERROR] {device.host_ip}: {error_msg}")

        cmd.status = "FAILED"
        cmd.error = error_msg
        cmd.finished_at = timezone.now()
        cmd.save(update_fields=["status", "error", "finished_at"])
  

        HelperModels.Job.objects.filter(id=job.id).update(
            completed=F("completed") + 1,
            failed=F("failed") + 1
        )

        return False

def process_device_thread(device_id, execution_timestamp):
    close_old_connections()  # added
    conn = None

    try:

        updated = HelperModels.DeviceExecution.objects.filter(
            id=device_id,
            status="PENDING"
        ).update(
            status="RUNNING",
            started_at=timezone.now()
        )
    
        if not updated:
            return

        device = (
                    HelperModels.DeviceExecution.objects
                    .select_related("job")
                    .get(id=device_id)
                )
        job = device.job


        creds = resolve_credentials(job)
        device_type = resolve_netmiko_device_type(job)

        logging.info(f"Processing device {device.host_ip} for job {job.id} with device type {device_type},creds {creds}")

        conn = getConnection(
            ip=device.host_ip,
            device_type=device_type,
            username=creds["username"],
            password=creds["password"],
            jobID=job.id,
            timestamp=execution_timestamp
        )

        if isinstance(conn, dict):
            raise Exception(conn.get("error"))
        
        commands = HelperModels.DeviceMultiCommand.objects.filter(
            device=device
        ).order_by("sequence")


        device_failed = False

        for cmd in commands:
            success = execute_single_command(conn, device_type, job, device, cmd)
            if not success:
                device_failed = True
    
        final_status = "FAILED" if device_failed else "SUCCESS"

        HelperModels.DeviceExecution.objects.filter(id=device.id).update(
            status=final_status,
            finished_at=timezone.now()
            )
    except Exception as e:
        error_msg = str(e)

        logging.error(f"[DEVICE ERROR] {device.host_ip}: {error_msg}")

        now = timezone.now()
        HelperModels.DeviceExecution.objects.filter(id=device.id).update(
            status="FAILED",
            finished_at=now
        )
        
        # ----------------------------------------
        # MARK ALL REMAINING COMMANDS AS SKIPPED
        # ----------------------------------------

        pending_updated = (
        HelperModels.DeviceMultiCommand.objects
        .filter(
            device=device,
            status="PENDING"
        )
        .update(
            status="FAILED",
            error=f"Device execution failed: {error_msg}",
            finished_at=now
        )
        )

        # ----------------------------------------
        # UPDATE JOB COUNTERS
        # ----------------------------------------

        if pending_updated > 0:
            HelperModels.Job.objects.filter(id=job.id ).update(
            completed=F("completed") + pending_updated)

    finally:
        if conn:
            try:
                conn.disconnect()
            except:
                pass

        close_old_connections()




@task(retries=2, retry_delay=10)
def process_device_batch(device_ids, job_id, execution_timestamp):

    
    device_ids = list(
        HelperModels.DeviceExecution.objects
        .filter(id__in=device_ids)
        .values_list("id", flat=True)
    )

    MAX_THREADS = 5 

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        executor.map(lambda device_id: process_device_thread(device_id,execution_timestamp),device_ids)
        # executor.map(process_device_thread,device_ids,repeat(execution_timestamp))


    #  SAFE FINALIZATION (ATOMIC CHECK)
    updated = HelperModels.Job.objects.filter(
        id=job_id,
        completed__gte=F("total_tasks"),
        status="RUNNING"
    ).update(
        status="DONE",
        completed_at=timezone.now()
    )

    if updated:
        logging.info(f"Job {job_id} completed")



@task()
def process_job(job_id):
    execution_timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    device_ids = list(
        HelperModels.DeviceExecution.objects
        .filter(job_id=job_id)
        .values_list("id", flat=True)
    )

    BATCH_SIZE = 100  

    for i in range(0, len(device_ids), BATCH_SIZE):
        batch = device_ids[i:i + BATCH_SIZE]

        process_device_batch.schedule(
            (batch, job_id, execution_timestamp),
            delay=0
        )







# ====================================End Multi Commands Block==================================================





@db_task()
def expire_request(request_id):
    try:
        req = HelperModels.ConfigExecutionRequest.objects.get(id=request_id)

        # Only expire if still approved
        if req.status == "APPROVED" and req.expires_at <= timezone.now():
            req.status = "EXPIRED"
            req.save()
            print(f"Request {request_id} expired")

    except HelperModels.ConfigExecutionRequest.DoesNotExist:
        print(f"Request {request_id} not found")
        pass




############################### CISCO T4 ################################

def create_connection(ip, username, password, dir_path, device_type, retries=0):
    os.makedirs(dir_path, exist_ok=True)
    try:
        net_device = {
            "device_type": device_type,
            "ip": ip,
            "username": username,
            "password": password,
            "session_log": f"{dir_path}/{ip}.txt",
            # "session_log_file_mode": "append",
            "auth_timeout": 40,
            "conn_timeout": 40,
            "global_delay_factor": 10,
        }
        return ConnectHandler(**net_device)
    except Exception as err:
        logging.error(f"{ip} connection error: {err}")
        if retries >= 3:
            return None
        return create_connection(
            ip, username, password, dir_path, device_type, retries + 1
        )

# ============================================================
# ✅ YOUR EXISTING FUNCTIONS — UNCHANGED
# ============================================================
def parse_vrf_output(output: str):
    vrf_list = []

    vrfs = re.findall(
        r"(?ms)^\s*vrf\s+(\S+)(.*?)(?=^\s*vrf\s+|\Z)",
        output
    )

    for vrf_name, vrf_body in vrfs:
        vrf_data = {
            "vrf_name": vrf_name,
            "ipv4_unicast": False,
            "ipv6_unicast": False,
            "ipv4": {
                "import_rt": [],
                "export_rt": []
            },
            "ipv6": {
                "import_rt": [],
                "export_rt": []
            },
            "deviation": {
                "ipv4_unicast": True,
                "ipv6_unicast": True,
                "ipv4": {
                    "import_rt_missing": True,
                    "export_rt_missing": True,
                    "maximum_prefix": True
                },
                "ipv6": {
                    "import_rt_missing": True,
                    "export_rt_missing": True,
                    "maximum_prefix": True
                }
            }
        }

        for af in ("ipv4", "ipv6"):
            af_match = re.search(
                rf"(?ms)address-family {af} unicast(.*?)(?=^\s*address-family|\Z)",
                vrf_body
            )

            if not af_match:
                continue

            # AF present
            vrf_data[f"{af}_unicast"] = True
            vrf_data["deviation"][f"{af}_unicast"] = False

            body = af_match.group(1)

            # -------- IMPORT RT --------
            import_block = re.search(
                r"(?ms)^\s*import route-target(.*?)(?=^\s*(export route-target|maximum prefix|address-family|vrf)\s+|\Z)",
                body
            )

            if import_block:
                import_rts = re.findall(r"^\s+(\d+:\d+)", import_block.group(1), re.M)
                
                if import_rts:
                    vrf_data["deviation"][af]["import_rt_missing"] = False

                for rt in import_rts:
                    vrf_data[af]["import_rt"].append({
                        "value": rt,
                        "deviation": False  # valid since it matched X:X
                    })

            # -------- EXPORT RT --------
            export_block = re.search(
                r"(?ms)^\s*export route-target(.*?)(?=^\s*(maximum prefix|address-family|vrf)\s+|\Z)",
                body
            )

            if export_block:
                export_rts = re.findall(r"^\s+(\d+:\d+)", export_block.group(1), re.M)

                if export_rts:
                    vrf_data["deviation"][af]["export_rt_missing"] = False

                for rt in export_rts:
                    vrf_data[af]["export_rt"].append({
                        "value": rt,
                        "deviation": False
                    })

            # -------- MAX PREFIX --------
            if re.search(r"^\s*maximum prefix \d+ \d+", body, re.M):
                vrf_data["deviation"][af]["maximum_prefix"] = False

        vrf_list.append(vrf_data)

    return vrf_list

def validate_interface_new(output: str):
    result = {
        "Bundle-Ether": {},
        "Bundle-Ether.l2transport": {},
        "BVI": {}
    }

    blocks = re.findall(r"(?ms)^interface\s+[^\n]+.*?\n!", output)

    for block in blocks:
        iface_match = re.search(r"^interface\s+([^\n]+)", block, re.M)
        if not iface_match:
            continue

        iface_name = iface_match.group(1).strip()

        # =====================================================
        # 1️⃣ Bundle-Ether<XX>
        # =====================================================
        if re.fullmatch(r"Bundle-Ether\d+", iface_name):

            data = {}

            mtu = re.search(r"(?m)^\s*mtu\s+(\d+)", block)
            val = mtu.group(1) if mtu else None
            data["mtu"] = {"value": val, "deviation": val != "9216"}

            spi = re.search(r"(?m)^\s*service-policy input\s+(\S+)", block)
            val = spi.group(1) if spi else None
            data["service_policy_input"] = {"value": val, "deviation": val is None}

            spo = re.search(r"(?m)^\s*service-policy output\s+(\S+)", block)
            val = spo.group(1) if spo else None
            data["service_policy_output"] = {"value": val, "deviation": val is None}

            data["load_interval_30"] = bool(
                re.search(r"(?m)^\s*load-interval\s+30$", block)
            )

            result["Bundle-Ether"][iface_name] = data

        # =====================================================
        # 2️⃣ Bundle-Ether<XX>.<YY> l2transport
        # =====================================================
        elif re.fullmatch(r"Bundle-Ether\d+\.\d+\s+l2transport", iface_name):

            clean_name = iface_name.replace(" l2transport", "")
            data = {}

            desc = re.search(r"(?m)^\s*description\s+(.+)", block)
            val = desc.group(1) if desc else None
            data["description"] = {"value": val, "deviation": val is None}

            enc = re.search(r"(?m)^\s*encapsulation\s+dot1q\s+(\d+)", block)
            val = enc.group(1) if enc else None
            data["encapsulation_dot1q"] = {"value": val, "deviation": val is None}

            data["rewrite_pop_1_symmetric"] = bool(
                re.search(r"(?m)^\s*rewrite\s+ingress\s+tag\s+pop\s+1\s+symmetric$", block)
            )

            result["Bundle-Ether.l2transport"][clean_name] = data

        # =====================================================
        # 3️⃣ BVI<XX>
        # =====================================================
        elif re.fullmatch(r"BVI\d+", iface_name):

            data = {}

            desc = re.search(r"(?m)^\s*description\s+(.+)", block)
            val = desc.group(1) if desc else None
            data["description"] = {"value": val, "deviation": val is None}

            vrf = re.search(r"(?m)^\s*vrf\s+(\S+)", block)
            val = vrf.group(1) if vrf else None
            data["vrf"] = {"value": val, "deviation": val is None}

            mtu = re.search(r"(?m)^\s*mtu\s+(\d+)", block)
            val = mtu.group(1) if mtu else None
            data["mtu"] = {"value": val, "deviation": val != "9216"}

            ipv4 = re.search(
                r"(?m)^\s*ipv4\s+address\s+(\S+\s+\S+)", block
            )
            val = ipv4.group(1) if ipv4 else None
            data["ipv4_address"] = {"value": val, "deviation": val is None}

            ipv6 = re.search(
                r"(?m)^\s*ipv6\s+address\s+(\S+)", block
            )
            val = ipv6.group(1) if ipv6 else None
            data["ipv6_address"] = {"value": val, "deviation": val is None}

            data["arp_timeout_300"] = bool(
                re.search(r"(?m)^\s*arp\s+timeout\s+300$", block)
            )

            data["mac_address_valid"] = bool(
                re.search(r"(?m)^\s*mac-address\s+a2\.a2\.a2$", block)
            )

            data["host_routing"] = bool(
                re.search(r"(?m)^\s*host-routing$", block)
            )

            data["load_interval_30"] = bool(
                re.search(r"(?m)^\s*load-interval\s+30$", block)
            )

            result["BVI"][iface_name] = data

    return result


def validate_l2vpn(output: str):
    bridge_domains_data = []

    bridge_domains = re.findall(
        r"(?ms)^\s*bridge-domain\s+(\d+)(.*?)(?=^\s*bridge-domain\s+|\Z)",
        output
    )

    if not bridge_domains:
        return {
            "status": "FORMAT_INVALID",
            "data": [],
            "errors": ["bridge-domain <X> missing"]
        }

    for bd_id, bd_body in bridge_domains:
        bd_data = {
            "bridge_domain": bd_id,
            "interface_bundle_ether": {
                "value": None,
                "status": "DEVIATION",
                "reason": "interface Bundle-Ether<X>.<Y> missing"
            },
            "routed_bvi": {
                "value": None,
                "status": "DEVIATION",
                "reason": "routed interface BVI<X> missing"
            },
            "evi": {
                "value": None,
                "status": "DEVIATION",
                "reason": "evi <X> missing"
            }
        }

        # interface Bundle-Ether<X>.<Y>
        bundle_match = re.search(
            r"(?m)^\s*interface\s+(Bundle-Ether\d+\.\d+)\s*$",
            bd_body
        )
        if bundle_match:
            bd_data["interface_bundle_ether"] = {
                "value": bundle_match.group(1),
                "status": "OK",
                "reason": None
            }

        # routed interface BVI<X>
        bvi_match = re.search(
            r"(?m)^\s*routed\s+interface\s+(BVI\d+)\s*$",
            bd_body
        )
        if bvi_match:
            bd_data["routed_bvi"] = {
                "value": bvi_match.group(1),
                "status": "OK",
                "reason": None
            }

        # evi <X>
        evi_match = re.search(
            r"(?m)^\s*evi\s+(\d+)\s*$",
            bd_body
        )
        if evi_match:
            bd_data["evi"] = {
                "value": evi_match.group(1),
                "status": "OK",
                "reason": None
            }

        bridge_domains_data.append(bd_data)

    overall_status = (
        "FORMAT_OK"
        if all(
            field["status"] == "OK"
            for bd in bridge_domains_data
            for key, field in bd.items()
            if isinstance(field, dict)
        )
        else "FORMAT_INVALID"
    )

    return {
        "status": overall_status,
        "data": bridge_domains_data
    }

def validate_evi(output: str):
    data = []

    # Find all EVI IDs
    evis = sorted(set(re.findall(r"evpn\s+evi\s+(\d+)", output)))

    if not evis:
        return {
            "status": "FORMAT_INVALID",
            "data": [],
            "errors": ["No EVI found"]
        }

    for evi in evis:
        evi_data = {
            "evi": evi,
            "bgp": {
                "value": None,
                "status": "DEVIATION",
                "reason": "bgp missing"
            },
            "route_target": {
                "value": None,
                "status": "DEVIATION",
                "reason": "bgp route-target missing"
            },
            "control_word_disable": {
                "value": None,
                "status": "DEVIATION",
                "reason": "control-word-disable missing"
            }
        }

        # evpn evi <X> bgp
        if re.search(
            rf"^evpn\s+evi\s+{evi}\s+bgp\s*$",
            output,
            re.MULTILINE
        ):
            evi_data["bgp"] = {
                "value": True,
                "status": "OK",
                "reason": None
            }

        # evpn evi <X> bgp route-target <A.B.C.D:NN>
        rt_match = re.search(
            rf"^evpn\s+evi\s+{evi}\s+bgp\s+route-target\s+(\d+\.\d+\.\d+\.\d+:\d+)\s*$",
            output,
            re.MULTILINE
        )
        if rt_match:
            evi_data["route_target"] = {
                "value": rt_match.group(1),
                "status": "OK",
                "reason": None
            }

        # evpn evi <X> control-word-disable
        if re.search(
            rf"^evpn\s+evi\s+{evi}\s+control-word-disable\s*$",
            output,
            re.MULTILINE
        ):
            evi_data["control_word_disable"] = {
                "value": True,
                "status": "OK",
                "reason": None
            }

        data.append(evi_data)

    overall_status = (
        "FORMAT_OK"
        if all(
            field["status"] == "OK"
            for evi in data
            for field in evi.values()
            if isinstance(field, dict)
        )
        else "FORMAT_INVALID"
    )

    return {
        "status": overall_status,
        "data": data
    }


def validate_bgp_vrf(output: str):
    data = []

    if re.search(r"(?m)^\s*vrf\s*$", output):
        return {
            "status": "FORMAT_INVALID",
            "data": [],
            "errors": ["vrf <NAME> missing"]
        }

    vrfs = re.findall(
        r"(?ms)^\s*vrf\s+(\S+)(.*?)(?=^\s*vrf\s+|\Z)",
        output
    )

    if not vrfs:
        return {
            "status": "FORMAT_INVALID",
            "data": [],
            "errors": ["No VRF found"]
        }

    for vrf_name, vrf_body in vrfs:
        vrf_data = {
            "vrf": vrf_name,
            "rd": {
                "value": None,
                "status": "DEVIATION",
                "reason": "rd X:X missing"
            },
            "label_allocation_mode": {
                "value": None,
                "status": "DEVIATION",
                "reason": "label-allocation-mode per-vrf missing"
            },
            "address_family": {
                "ipv4": {
                    "redistribute_connected": {
                        "value": None,
                        "status": "DEVIATION",
                        "reason": "redistribute connected missing"
                    },
                    "redistribute_static": {
                        "value": None,
                        "status": "DEVIATION",
                        "reason": "redistribute static missing"
                    }
                },
                "ipv6": {
                    "redistribute_connected": {
                        "value": None,
                        "status": "DEVIATION",
                        "reason": "redistribute connected missing"
                    },
                    "redistribute_static": {
                        "value": None,
                        "status": "DEVIATION",
                        "reason": "redistribute static missing"
                    }
                }
            }
        }

        rd_match = re.search(r"(?m)^\s*rd\s+(\d+:\d+)\s*$", vrf_body)
        if rd_match:
            vrf_data["rd"] = {
                "value": rd_match.group(1),
                "status": "OK",
                "reason": None
            }

        if re.search(r"(?m)^\s*label-allocation-mode\s+per-vrf\s*$", vrf_body):
            vrf_data["label_allocation_mode"] = {
                "value": "per-vrf",
                "status": "OK",
                "reason": None
            }

        for af in ("ipv4", "ipv6"):
            af_match = re.search(
                rf"(?ms)address-family\s+{af}\s+unicast(.*?)(?=^\s*!$)",
                vrf_body
            )

            if not af_match:
                vrf_data["address_family"][af] = {
                    "status": "DEVIATION",
                    "reason": f"address-family {af} unicast missing"
                }
                continue

            af_body = af_match.group(1)

            if re.search(r"(?m)^\s*redistribute\s+connected\s*$", af_body):
                vrf_data["address_family"][af]["redistribute_connected"] = {
                    "value": True,
                    "status": "OK",
                    "reason": None
                }

            if re.search(r"(?m)^\s*redistribute\s+static\s*$", af_body):
                vrf_data["address_family"][af]["redistribute_static"] = {
                    "value": True,
                    "status": "OK",
                    "reason": None
                }

        data.append(vrf_data)

    # ✅ FIXED overall status
    overall_status = (
        "FORMAT_OK"
        if all(
            field.get("status") == "OK"
            for vrf in data
            for section in vrf.values()
            if isinstance(section, dict)
            for field in section.values()
            if isinstance(field, dict) and "status" in field
        )
        else "FORMAT_INVALID"
    )

    return {
        "status": overall_status,
        "data": data
    }


# ============================================================

def compute_and_update_counts(gct_obj, data):
    main = data.get("data", {})

    # ===== INIT ALL COUNTERS ===== #
    total_l2vpn = deviated_l2vpn = 0
    total_evi = deviated_evi = 0
    total_bgp = deviated_bgp = 0
    total_vrfs = deviated_vrfs = 0
    total_interfaces = deviated_interfaces = 0

    # =================================
    # ✅ L2VPN
    # =================================
    for item in main.get("l2vpn", {}).get("data", []):
        total_l2vpn += 1

        if (
            item.get("interface_bundle_ether", {}).get("status") == "DEVIATION" or
            item.get("routed_bvi", {}).get("status") == "DEVIATION" or
            item.get("evi", {}).get("status") == "DEVIATION"
        ):
            deviated_l2vpn += 1

    # =================================
    # ✅ EVI
    # =================================
    for item in main.get("evi", {}).get("data", []):
        total_evi += 1

        if item.get("route_target", {}).get("status") == "DEVIATION":
            deviated_evi += 1

    # =================================
    # ✅ BGP VRF
    # =================================
    for item in main.get("bgp_vrf", {}).get("data", []):
        total_bgp += 1

        if item.get("label_allocation_mode", {}).get("status") == "DEVIATION":
            deviated_bgp += 1

    # =================================
    # ✅ VRF (separate block)
    # =================================
    for vrf in main.get("vrf", []):
        total_vrfs += 1

        deviation_block = vrf.get("deviation", {})

        if any([
            deviation_block.get("ipv4_unicast"),
            deviation_block.get("ipv6_unicast"),
            any(deviation_block.get("ipv4", {}).values()),
            any(deviation_block.get("ipv6", {}).values())
        ]):
            deviated_vrfs += 1

    # =================================
    # ✅ INTERFACES
    # =================================
    interfaces = main.get("interfaces", {})

    for category, items in interfaces.items():
        for intf_name, intf_data in items.items():
            total_interfaces += 1

            # ✅ Check any field having deviation=True
            for k, v in intf_data.items():
                if isinstance(v, dict) and v.get("deviation") is True:
                    deviated_interfaces += 1
                    break

    # =================================
    # ✅ FINAL STATUS
    # =================================
    if any([
        deviated_vrfs,
        deviated_l2vpn,
        deviated_bgp,
        deviated_interfaces,
        deviated_evi
    ]):
        status = "DEVIATION"
    else:
        status = "COMPLIANT"

    # =================================
    # ✅ UPDATE MODEL
    # =================================
    gct_obj.total_vrfs = total_vrfs
    gct_obj.deviated_vrfs = deviated_vrfs

    gct_obj.total_l2vpn = total_l2vpn
    gct_obj.deviated_l2vpn = deviated_l2vpn

    gct_obj.total_bgp = total_bgp
    gct_obj.deviated_bgp = deviated_bgp

    gct_obj.total_interfaces = total_interfaces
    gct_obj.deviated_interfaces = deviated_interfaces

    gct_obj.total_evi = total_evi
    gct_obj.deviated_evi = deviated_evi

    gct_obj.status = status

    gct_obj.save()



# ============================================================
# 🧵 DEVICE WORKER (ONLY NEW PART)
# ============================================================
def process_device(ip, username, password, device_type, log_dir):
    logging.info(f"Processing {ip} with device type {device_type}")
    result = {
        "status": "FAILED",
        "data": {},
    }
    command_output = {}

    try:
        conn = create_connection(
            ip=ip.ip_address,
            username=username,
            password=password,
            dir_path=log_dir,
            device_type=device_type
        )

        if not conn:
            result["error"] = "Connection failed"
            return result

        # ====================================================
        # 🔧 COMMAND PLACEHOLDERS (YOU WILL FILL)
        # ====================================================
        CMD_L2VPN = "show run l2vpn | begin bridge"
        CMD_EVI = "show run form | i evpn evi"
        CMD_BGP_VRF = "show run router bgp 9730"
        CMD_INTERFACE = "show running-config interface"
        CMD_VRF = "show running-config vrf"
        # ====================================================

        with conn:
            output_l2vpn = conn.send_command(CMD_L2VPN) if CMD_L2VPN else ""
            output_evi = conn.send_command(CMD_EVI) if CMD_EVI else ""
            output_bgp_vrf = conn.send_command(CMD_BGP_VRF) if CMD_BGP_VRF else ""
            output_interface = conn.send_command(CMD_INTERFACE) if CMD_INTERFACE else ""
            output_vrf = conn.send_command(CMD_VRF) if CMD_VRF else ""

        command_output = {
            CMD_L2VPN : output_l2vpn,
            CMD_EVI : output_evi,
            CMD_BGP_VRF : output_bgp_vrf,
            CMD_INTERFACE : output_interface,
            CMD_VRF : output_vrf
        }

        

        # ====================================================
        # ✅ CALL YOUR FUNCTIONS — LOGIC UNTOUCHED
        # ====================================================
        result["data"] = {
            "l2vpn": validate_l2vpn(output_l2vpn),
            "evi": validate_evi(output_evi),
            "bgp_vrf": validate_bgp_vrf(output_bgp_vrf),
            "interfaces": validate_interface_new(output_interface),
            "vrf": parse_vrf_output(output_vrf),
        }

        compute_and_update_counts(gct_obj=ip, data=result)  # Pass None since we are not updating a model here
        

        result["status"] = "SUCCESS"
        

    except Exception as exc:
        logging.exception(f"{ip} failed: {exc}")
        result["error"] = str(exc)

    HelperModels.CiscoT4Data.objects.create(inv_model=ip,command_output=command_output,complete_data=result)

    return result

# ============================================================
# 🧵 MULTITHREAD CONTROLLER (ONLY NEW PART)
# ============================================================


@task(retries=2, retry_delay=10)
def run_multithreaded(
    ip_inv,
    username,
    password,
    device_type,
    log_dir,
    gct_model,
    max_workers=100
):
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {
            executor.submit(
                process_device,
                ip,
                username,
                password,
                device_type,
                log_dir
            ): ip
            for ip in ip_inv
        }

        for future in as_completed(future_to_ip):
            results.append(future.result())

    gct_model.current_status = "RESULTS_READY"
    gct_model.deviation_count = HelperModels.GCTCiscoT4.objects.filter(gct_model=gct_model, status="DEVIATION").count()
    gct_model.save(update_fields=["current_status", "deviation_count"])
    logging.info(f"GCT Job {gct_model.id} completed with {gct_model.deviation_count} deviations")
