from huey.contrib.djhuey import task
from django.conf import settings
import datetime
from utils.conn import getConnection
from apps.helpers import models as HelperModels
from django.utils import timezone
from django.db.models import F
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore
import json
import os
import logging
import re
from utils.credentials import  resolve_credentials, resolve_netmiko_device_type
from django.db import connections, transaction
from huey.contrib.djhuey import db_task




BATCH_SIZE = settings.BATCH_SIZE
GLOBAL_SSH_LIMIT = Semaphore(settings.GLOBAL_SSH_LIMIT)
THREADS = settings.THREADS


PAGING_COMMANDS = {
    "cisco_ios": "terminal length 0",
    "cisco_xr": "terminal length 0",
    "juniper_junos": "set cli screen-length 0",
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



 
# ==========================================================
# SSH Worker
# ==========================================================
def execute_on_device(ip, job, commands, creds):
    conn = None
    device_type = resolve_netmiko_device_type(job)
    with GLOBAL_SSH_LIMIT:
        try:
            conn = getConnection(
                ip=ip,
                device_type=device_type,
                username=creds["username"],
                password=creds["password"],
                jobID=job.id,
                timestamp=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            )

            if isinstance(conn, dict) and "error" in conn:
                return [{
                    "ip": ip,
                    "status": "ERROR",
                    "connection": "FAILED",
                    "command": None,
                    "output": conn["error"]
                }]

             
            # ===============================
            # CONFIG MODE
            # ===============================
            if job.execution_mode == "config":
                logging.info(f"Executing CONFIG mode for JOB ID: {job.id}")
                rows = []
                for cmd in commands:
                    output = conn.send_command(cmd, 
                                               read_timeout=420, 
                                               expect_string=r"#\s*$|>\s*$|\]\s*$"
                                               )

                    rows.append({
                        "ip": ip,
                        "status": "SUCCESS",
                        "connection": "ESTABLISHED",
                        "command": cmd,
                        "output": output
                    })
                return rows
            
            # ===============================
            # READONLY MODE
            # ===============================
            elif job.execution_mode == "readonly":
                logging.info(f"Commands Executing with Readonly Mode with Job ID: {job}")
                paging_cmd = PAGING_COMMANDS.get(device_type)
                if paging_cmd:
                    conn.send_command(paging_cmd, read_timeout=30)

                rows = []
                for cmd in commands:
                    output = conn.send_command(cmd, read_timeout=420, 
                                            strip_prompt=False,
                                            strip_command=False)
                    
                    rows.append({
                        "ip": ip,
                        "status": "SUCCESS",
                        "connection": "ESTABLISHED",
                        "command": cmd,
                        "output": output
                    })
                return rows
            else:
                logging.info(f"execution_mode not exist: {job.execution_mode}")
        except Exception as e:
            return [{
                "ip": ip,
                "status": "ERROR",
                "connection": "FAILED",
                "command": None,
                "output": str(e)
            }]
        finally:
            try:
                if conn:
                    conn.disconnect()
            except Exception:
                pass
                    
    


@task(name="process_ip_batch",retries=2, retry_delay=10)
def process_ip_batch(batch_id):

    # Always reset DB connection at task start
    safe_close_connections()
    batch = None
 
    try:
        # ---------- Fetch batch safely ----------

        batch = HelperModels.IPBatch.objects.select_related("job").get(id=batch_id)
        job = batch.job
        logging.info(f"Process started with JOB ID : {job}")
        HelperModels.IPBatch.objects.filter(id=batch_id).update(
            status="RUNNING",
            started_at=timezone.now()
        )

        creds = resolve_credentials(job)
        commands = job.command_list()
        results_file = get_results_file(job)

        #Close DB before threading
        safe_close_connections()

        # Execute Devices (Threaded)
        # --------------------------------------------------
        ip_status_map = {}
        with open(results_file, "a") as f:
            with ThreadPoolExecutor(max_workers=THREADS) as pool:
                futures = [pool.submit(execute_on_device, ip, job, commands, creds) for ip in batch.ips]
                for future in as_completed(futures):
                    try:
                        rows = future.result()
                        for row in rows:
                            # Write immediately (streaming)
                            f.write(json.dumps(row) + "\n")
                            ip = row["ip"]
                            if ip not in ip_status_map:
                                ip_status_map[ip] = {
                                    "status": "DONE",
                                    "error": None
                                }
                            if row["status"] == "ERROR":
                                ip_status_map[ip]["status"] = "ERROR"
                                ip_status_map[ip]["error"] = row["output"]
                    except Exception:
                        logging.exception("Thread execution error")



        # ---------------- Save IPResult to DB----------------
        safe_close_connections()
        with transaction.atomic():
            HelperModels.IPResult.objects.bulk_create(
                [
                    HelperModels.IPResult(
                        job=job,
                        ip=ip,
                        status=data["status"],
                        error=data["error"]
                    )
                    for ip, data in ip_status_map.items()
                ],
                batch_size=BATCH_SIZE
            )

            # ---------------- Update Job counters ----------------
            success_ips = sum(1 for v in ip_status_map.values() if v["status"] == "DONE")
            failed_ips = sum(1 for v in ip_status_map.values() if v["status"] == "ERROR")


            HelperModels.Job.objects.filter(id=job.id).update(
                completed=F("completed") + len(batch.ips),
                success=F("success") + success_ips,
                failed=F("failed") + failed_ips,
            )

            # ---------------- Mark batch done ----------------
            HelperModels.IPBatch.objects.filter(id=batch_id).update(
                    status="DONE",
                    finished_at=timezone.now()
                )

            # ---------------- Mark job done (last batch only) ----------------
            HelperModels.Job.objects.filter(
                id=job.id,
                completed__gte=F("total_ips"),
                status__in=["PENDING", "RUNNING"]
            ).update(
                status="DONE",
                completed_at=timezone.now()
            )
            logging.info("Batch %s completed successfully", batch_id)

    except Exception as exc:
            logging.exception("Batch %s crashed", batch_id)

            try:
                safe_close_connections()
                HelperModels.IPBatch.objects.filter(id=batch_id).update(
                        status="ERROR",
                        finished_at=timezone.now()
                        )
            except Exception:
                logging.exception("CRITICAL: Could not mark batch as ERROR")
            raise  # Let Huey retry
    finally:
        safe_close_connections()

    



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