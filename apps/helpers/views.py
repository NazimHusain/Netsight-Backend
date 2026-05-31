
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.files.storage import FileSystemStorage
from .models import Job,ConfigExecutionRequest, CommandExecution,GCTModel,GCTCiscoT4,DeviceExecution,DeviceMultiCommand,CiscoT4Data
from utils import tasks
from utils.excel_readers import Ip_specific_command_reader, read_ips_from_excel, Ip_related_command_reader
import pandas as pd
import io
import json
from django.db.models import F, Min, Max
from rest_framework.request import Request
from collections import defaultdict
from .serializers import JobSerializer,GCTModelSerializer,GCTCiscoT4Serializer
import zipfile,oracledb
from django.conf import settings
import os
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from django.http import FileResponse, HttpResponse
import csv
from .utility import sanitize_for_excel,sanitize_command
import re
from openpyxl import Workbook
from openpyxl.styles import Alignment 
from datetime import datetime

from apps.helpers.utility import send_config_request_email
from django.utils import timezone
from datetime import timedelta
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from rest_framework import status
from compliance.registry import GCT_REGISTRY
from utils import cisco_t4_gct as GCT_Validator
signer = TimestampSigner()
BATCH_SIZE = settings.BATCH_SIZE


class DevicetypeListingView(APIView):
    permission_classes = []
    authentication_classes = []
    def get(self, request):
        return Response(Job.get_device_types(), status=200)
    

# class UploadIPFilePreview(APIView):
#     authentication_classes = [TokenAuthentication]
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         file = request.FILES.get("file")

#         if not file:
#             return Response({"error": "File not provided"}, status=400)

#         job, created = Job.objects.get_or_create(
#             created_by=request.user,
#             status="DRAFT",
#             defaults={"file": file}
#         )

#         # Replace file if DRAFT already exists
#         if job.file:
#             job.file.delete(save=False)

#         job.file = file
#         job.save()  #VERY IMPORTANT

#         try:
#             file_path = job.file.path
#             ips = read_ips_from_excel(file_path)
#             commands = read_commands(file_path)
#         except Exception as e:
#             return Response(
#                 {"error": f"Failed to process file: {str(e)}"},
#                 status=400
#             )
        
#         max_commands = settings.MAX_COMMANDS
        
#         if len(commands) > max_commands:
#             return Response(
#                 {
#                     "error": f"Maximum {settings.MAX_COMMANDS} commands allowed. "
#                             f"Uploaded file contains {len(commands)} commands."
#                 },
#                 status=400
#             )

       
#         job.total_ips = len(ips)
#         job.commands = commands
#         job.save(update_fields=["total_ips", "commands"])


#         return Response({
#             "job_id": job.id,
#             "total_ips": len(ips),
#             "commands": commands
#         }, status=200)
    

class UploadIPFilePreview(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")

        if not file:
            return Response({"error": "File not provided"}, status=400)

        job, created = Job.objects.get_or_create(
            created_by=request.user, status="DRAFT"
        )

        if job.file:
            job.file.delete(save=False)

        job.file = file
        job.save()

        try:
            file_path = job.file.path
            data = Ip_specific_command_reader(file_path)
        except Exception as e:
            return Response({"error": f"Failed to process file: {str(e)}"}, status=400)

        max_commands = settings.MAX_COMMANDS

        if len(data) > max_commands:
            return Response(
                {
                    "error": f"Maximum {settings.MAX_COMMANDS} commands allowed. "
                    f"Uploaded file contains {len(data)} commands."
                },
                status=400,
            )

        total_tasks = len(data)
        total_ips = len({item["ip"] for item in data})

        job.total_tasks = total_tasks
        job.total_ips = total_ips
        job.save(update_fields=["total_tasks", "total_ips"])
        return Response(
            {"job_id": job.id, "total_ips": len(data), "task": data}, status=200
        )
    

    
# class RunJob(APIView):
#     authentication_classes = [TokenAuthentication]
#     permission_classes = [IsAuthenticated]


#     def post(self, request):
#         job_id = request.data.get("job_id")
#         device_type = request.data.get("device_type")
#         raw_commands = request.data.getlist("commands")
#         execution_mode = request.data.get("execution_mode", "readonly")
#         print("Execution mode from request:", execution_mode)
       


#         job = get_object_or_404(Job, id=job_id, created_by=request.user)

#         # Security check
#         access = ConfigExecutionRequest.objects.filter(
#         user=request.user,
#         status="APPROVED",
#         expires_at__gt=timezone.now() 
#         ).exists()
#         if execution_mode == "config" and not access:
#             return Response({"error": "Config access not approved or expired"},status=403)

#         if job.status != "DRAFT":
#             return Response({"error": "Job already executed"}, status=400)
        
#         file_path = job.file.path
#         ips = read_ips_from_excel(file_path)

#         commands = [sanitize_command(cmd) for cmd in raw_commands if cmd.strip()]
#         job.execution_mode = execution_mode
#         job.device_type = device_type
#         job.commands = json.dumps(commands)
#         job.status = "RUNNING"
#         job.save()
#         print("Execution mode saved in DB:", job.execution_mode)
        
#         batches = []
#         for i in range(0, len(ips), BATCH_SIZE):
#             batches.append(
#                 IPBatch(
#                     job=job,
#                     ips=ips[i:i + BATCH_SIZE]
#                 )
#             )

#         IPBatch.objects.bulk_create(batches)

#         for batch in IPBatch.objects.filter(job=job):
#             tasks.process_ip_batch.schedule((batch.id,), delay=0)


#         return Response({
#             "message": "Job scheduled successfully",
#             "job_id": job.id,
#             "total_ips": len(ips),
#             "batches": len(batches)
#         })


class RunJob(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job_id = request.data.get("job_id")
        device_type = request.data.get("device_type")
        execution_mode = request.data.get("execution_mode", "readonly")
        tasks_raw = request.data.get("tasks")
        if not tasks_raw:
            return Response({"error": "No tasks provided"}, status=400)
        try:
            task_list = json.loads(tasks_raw)
        except Exception:
            return Response({"error": "Invalid tasks format"}, status=400)

        if not job_id or not task_list:
            return Response({"error": "Invalid request"}, status=400)

        job = get_object_or_404(Job, id=job_id, created_by=request.user)
     
        # Security check
        access = ConfigExecutionRequest.objects.filter(
            user=request.user, status="APPROVED", expires_at__gt=timezone.now()
        ).exists()
        if execution_mode == "config" and not access:
            return Response(
                {"error": "Config access not approved or expired"}, status=403
            )

        if job.status != "DRAFT":
            return Response({"error": "Job already executed"}, status=400)

        # ---------------- UPDATE JOB ----------------
        job.device_type = device_type
        job.execution_mode = execution_mode
        job.status = "RUNNING"
        job.save()
        # ---------------- BULK INSERT ----------------
        bulk_data = []
        for t in task_list:
            ip = t.get("ip")
            cmd = t.get("command")
            seq = t.get("sequence", 1)

            if not ip or not cmd:
                continue

            clean_cmd = sanitize_command(cmd)

            bulk_data.append(
                CommandExecution(
                    job=job,
                    host_ip=ip,
                    command=clean_cmd,
                    sequence=seq,
                    status="PENDING",
                )
            )

        CommandExecution.objects.bulk_create(bulk_data, batch_size=1000)
        # ---------------- SET TOTAL COMMANDS ----------------
        job.total_ips = len(bulk_data)
        job.save(update_fields=["total_ips"])

        # # ---------------- FAST SCHEDULING ----------------
        task_ids = CommandExecution.objects.filter(job=job).values_list("id", flat=True)

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

        BATCH_SIZE = 500
        for i in range(0, len(task_ids), BATCH_SIZE):
            batch = task_ids[i:i+BATCH_SIZE]

            tasks.process_multiple_rows.schedule(
                (batch, timestamp),
                delay=0
            )

        return Response(
            {
                "message": "Job scheduled successfully",
                "job_id": job.id,
                "total_tasks": len(bulk_data),
            }
        )

class JobListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    serializer_class = JobSerializer
    
    def get(self, request):
        if request.user.is_superuser:
            job_qs = Job.objects.filter(is_deleted=False)
        else:
            job_qs = Job.objects.filter(created_by=request.user, is_deleted = False)

        job_qs = job_qs.order_by("-id")
        serialized = self.serializer_class(job_qs, many=True, context = {"request": request})
       
        return Response(serialized.data, 200)


    

# class JobStatusView1(APIView):
#     authentication_classes = [TokenAuthentication]
#     permission_classes = [IsAuthenticated]

#     def get(self, request, job_id):
#         status_filter = request.GET.get("status")
#         ip_filter = request.GET.get("ip")

#         if request.user.is_staff or request.user.is_superuser:
#             job = get_object_or_404(Job, id=job_id)
#         else:
#             job = get_object_or_404(Job, id=job_id, created_by=request.user)

#         # ---------------- IP RESULTS ----------------
#         results_qs = IPResult.objects.filter(job=job)

#         if status_filter:
#             results_qs = results_qs.filter(status=status_filter)

#         if ip_filter:
#             results_qs = results_qs.filter(ip__icontains=ip_filter)

#         results = results_qs.values("ip", "status", "error")

#         # ---------------- BATCH TIMES ----------------
#         batches = IPBatch.objects.filter(job=job)

#         start_times = list(
#             batches.exclude(started_at__isnull=True)
#                    .values_list("started_at", flat=True)
#         )
#         end_times = list(
#             batches.exclude(finished_at__isnull=True)
#                    .values_list("finished_at", flat=True)
#         )

#         job_started_at = min(start_times) if start_times else None
#         job_finished_at = max(end_times) if end_times else None

#         if job_started_at and job_finished_at:
#             total_time = round(
#                 (job_finished_at - job_started_at).total_seconds() / 60, 2
#             )
#         else:
#             total_time = None

#         # ---------------- RESPONSE ----------------
#         return Response({
#             "summary": {
#                 "total_ips": job.total_ips,
#                 "success_count": job.success,
#                 "error_count": job.failed,
#                 "job_started_at": job_started_at,
#                 "job_finished_at": job_finished_at,
#                 "total_time": total_time,
#                 "status": job.status,
#             },
#             "details": list(results)
#         })


# class JobStatusView(APIView):
#     authentication_classes = [TokenAuthentication]
#     permission_classes = [IsAuthenticated]

#     def get(self, request, job_id):
#         status_filter = request.GET.get("status")
#         ip_filter = request.GET.get("ip")

#         if request.user.is_staff or request.user.is_superuser:
#             job = get_object_or_404(Job, id=job_id)
#         else:
#             job = get_object_or_404(Job, id=job_id, created_by=request.user)

#         qs = CommandExecution.objects.filter(job=job)
#         if status_filter:
#             qs = qs.filter(status=status_filter.upper())

#         if ip_filter:
#             qs = qs.filter(host_ip__icontains=ip_filter)

#         results = qs.annotate(ip=F("host_ip")).values("ip", "status", "error")
#         agg = qs.aggregate(start=Min("started_at"), end=Max("finished_at"))
#         start = agg["start"]
#         end = agg["end"]

#         total_time = None
#         if start and end:
#             total_time = round((end - start).total_seconds() / 60, 2)

#         # ---------------- RESPONSE ----------------
#         return Response(
#             {
#                 "summary": {
#                     "total_ips": job.total_ips,
#                     "success_count": job.success,
#                     "error_count": job.failed,
#                     "job_started_at": start,
#                     "job_finished_at": end,
#                     "total_time": total_time,
#                     "status": job.status,
#                 },
#                 "details": list(results),
#             }
#         )
    


class JobStatusView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]


    def get(self, request, job_id):
        status_filter = request.GET.get("status")
        ip_filter = request.GET.get("ip")

        if request.user.is_staff or request.user.is_superuser:
            job = get_object_or_404(Job, id=job_id)
        else:
            job = get_object_or_404(Job, id=job_id, created_by=request.user)

        # ---------------- DETECT TYPE ----------------
        is_multi = DeviceMultiCommand.objects.filter(device__job=job).exists()

        # ---------------- BUILD QUERY ----------------
        if is_multi:
            qs = DeviceMultiCommand.objects.filter(device__job=job)

            if status_filter:
                qs = qs.filter(status=status_filter.upper())

            if ip_filter:
                qs = qs.filter(device__host_ip__icontains=ip_filter)
                
            qs = qs.annotate(ip=F("device__host_ip"))
        else:
            qs = CommandExecution.objects.filter(job=job)

            if status_filter:
                qs = qs.filter(status=status_filter.upper())

            if ip_filter:
                qs = qs.filter(host_ip__icontains=ip_filter)

            qs = qs.annotate(ip=F("host_ip"))
        
        # ---------------- COMMON OUTPUT ----------------
        results = qs.values("ip", "status", "error")

        if is_multi:
            agg = DeviceExecution.objects.filter(job=job).aggregate(
                start=Min("started_at"),
                end=Max("finished_at")
            )
        else:
            agg = qs.aggregate(
                start=Min("started_at"),
                end=Max("finished_at")
            )

        start = agg["start"]
        end = agg["end"]

        total_time = None
        if start and end:
            total_time = round((end - start).total_seconds() / 60, 2)
        
         # ---------------- RESPONSE ----------------
        return Response(
            {
                "summary": {
                    "total_ips": job.total_ips,
                    "success_count": job.success,
                    "error_count": job.failed,
                    "job_started_at": start,
                    "job_finished_at": end,
                    "total_time": total_time,
                    "status": job.status,
                },
                "details": list(results),
            }
        )
    
# ========================================Multi Commands Exection Block==============================


class MultiCommandUploadIPFilePreview(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")

        if not file:
            return Response({"error": "File not provided"}, status=400)

        job, created = Job.objects.get_or_create(
            created_by=request.user, status="DRAFT"
        )

        if job.file:
            job.file.delete(save=False)

        job.file = file
        job.save()

        try:
            file_path = job.file.path
            ip_command_map  = Ip_related_command_reader(file_path)
        except Exception as e:
            return Response({"error": f"Failed to process file: {str(e)}"}, status=400)
        
        if not ip_command_map:
            return Response(
                {"error": "No valid data found in file"},
                status=400
            )
        
        total_devices = len(ip_command_map)
        total_commands = sum(len(cmds) for cmds in ip_command_map.values())

        max_commands = settings.MULTI_DEVICE

        if total_devices> max_commands:
            return Response(
                {
                    "error": f"Maximum {settings.MAX_COMMANDS} Host IP's allowed. "
                    f"Uploaded file contains {len(total_devices )} Host IP's."
                },
                status=400,
            )
        
        job.total_ips = total_devices
        job.total_tasks = total_commands
        job.save(update_fields=["total_ips", "total_tasks"])
        return Response(
            {"job_id": job.id, "total_ips": total_devices ,"tasks": ip_command_map }, status=200
        )
    


class MulticommandRun(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job_id = request.data.get("job_id")
        device_type = request.data.get("device_type")
        execution_mode = request.data.get("execution_mode", "readonly")
        tasks_data = request.data.get("tasks")

        if isinstance(tasks_data, str):
            try:
                tasks_data = json.loads(tasks_data)
            except Exception:
                return Response({"error": "Invalid tasks format"}, status=400)

        if not tasks_data:
            return Response({"error": "No tasks provided"}, status=400)

        job = get_object_or_404(Job, id=job_id, created_by=request.user)

        # Security check
        access = ConfigExecutionRequest.objects.filter(
            user=request.user,
            status="APPROVED",
            expires_at__gt=timezone.now()
        ).exists()

        if execution_mode == "config" and not access:
            return Response(
                {"error": "Config access not approved or expired"},
                status=403
            )

        if job.status != "DRAFT":
            return Response({"error": "Job already executed"}, status=400)

       

        # ---------------- UPDATE JOB ----------------
        job.device_type = device_type
        job.execution_mode = execution_mode
        job.status = "RUNNING"

        # deduplicate IPs
        unique_ips = list(set(tasks_data.keys()))
        job.total_ips = len(unique_ips)
        job.total_tasks = sum(len(v) for v in tasks_data.values())
        job.save()

       # -------- CREATE DEVICES --------
        device_objs = [
            DeviceExecution(job=job, host_ip=ip)
            for ip in unique_ips if ip
        ]

        DeviceExecution.objects.bulk_create(device_objs, batch_size=1000)

        devices = DeviceExecution.objects.filter(job=job).only("id", "host_ip")
        device_map = {d.host_ip: d for d in devices}

        # -------- CREATE COMMANDS --------
        command_objs = []

        for ip, commands in tasks_data.items():
            device = device_map.get(ip)
            if not device:
                continue

            for seq, cmd in enumerate(commands, start=1):
                command_objs.append(
                    DeviceMultiCommand(
                        device=device,
                        command=sanitize_command(cmd),
                        sequence=seq
                    )
                )

        DeviceMultiCommand.objects.bulk_create(command_objs, batch_size=1000)

        logging.info(f"Going for scheduling multi command.")
        tasks.process_job.schedule((job.id,), delay=0)
        


        return Response({
            "message": "Job scheduled successfully",
            "job_id": job.id,
            "total_devices": len(unique_ips),
            "total_commands": len(command_objs),
        })



# ==========================GCT API ====================================================

class GCTIPFilePreview(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")

        if not file:
            return Response({"error": "File not provided"}, status=400)

        job, created = Job.objects.get_or_create(
            created_by=request.user, status="DRAFT", defaults={"file": file}
        )

        if job.file:
            job.file.delete(save=False)

        job.file = file
        job.save()

        ips = read_ips_from_excel(job.file.path)

        return Response({
            "job_id": job.id,
            "total_ips": len(ips)
        }, status=200)


class GCTModelView(APIView):
    # authentication_classes = [TokenAuthentication]
    # permission_classes = [IsAuthenticated]

    def get(self,*args,**kwargs):
        data = GCTModel.objects.all()
        serializer = GCTModelSerializer(data, many=True)
        return Response(serializer.data, status=200)
    

chitragupt_db = oracledb.create_pool(
    user="inventory",
    password="inventory#123",
    dsn="10.240.129.226:1521/nocpdb.airtel.com",  # or use a full DSN string
    min=2,        # minimum connections in pool
    max=10,       # maximum connections
    increment=1,  # connections added when needed
)
    

from rest_framework.pagination import PageNumberPagination


class InventoryPagination(PageNumberPagination):
    page_size = 100


class GCTCiscoT4InvV2(APIView):
    # authentication_classes = [TokenAuthentication]
    # permission_classes = [IsAuthenticated]

    def get(self,request,id,*args,**kwargs):
        gct_model = get_object_or_404(GCTModel, id=id)
        ip_inv = GCTCiscoT4.objects.filter(gct_model=gct_model)

        paginator = InventoryPagination()
        page = paginator.paginate_queryset(ip_inv, request)


        serializer = GCTCiscoT4Serializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

 
class GCTCiscoT4Inv(APIView):
    # authentication_classes = [TokenAuthentication]
    # permission_classes = [IsAuthenticated]

    def get(self,request,id,*args,**kwargs):
        gct_model = get_object_or_404(GCTModel, id=id)
        ip_inv = GCTCiscoT4.objects.filter(gct_model=gct_model)
        serializer = GCTCiscoT4Serializer(ip_inv, many=True)
        return Response(serializer.data, status=200)

    def post(self, request):
        model_id = request.data.get("id")
        gct_model = get_object_or_404(GCTModel, id=model_id)
        query = gct_model.query_inv
        rows = []
        with chitragupt_db.acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

        logging.info(f"Fetched {rows} rows for GCT Model {gct_model.model} from Oracle DB")

        tasks.saveandupdate_ciscot4.schedule((gct_model, rows), delay=0)

        return Response({
            "message": "Cisco T4 inventory query executed, results are being processed",
            "total_ips": len(rows)
        }, status=200)

import ast


class DownloadLatestT4Excel(APIView):

    def get(self, request, gct_id):

        # ✅ Step 1: Get device
        gct_obj = get_object_or_404(GCTCiscoT4, id=gct_id)

        latest_entry = (
            CiscoT4Data.objects
            .filter(inv_model=gct_obj)
            .order_by('-created_at')
            .first()
        )

        if not latest_entry:
            return HttpResponse("No data found", status=404)

        try:
            parsed_data = ast.literal_eval(latest_entry.complete_data)
        except Exception:
            return HttpResponse("Invalid complete_data format", status=500)

        data = parsed_data.get("data", {})

        # ✅ Device metadata (important for your format)
        ip = gct_obj.ip_address
        circle = gct_obj.circle
        vendor = "CISCO"
        technology = "T4"
        model = gct_obj.hostname

        rows = []

        # ===================== ✅ VRF =====================
        for vrf in data.get("vrf", []):
            vrf_name = vrf.get("vrf_name")

            for af in ("ipv4", "ipv6"):

                # unicast
                rows.append({
                    "ip": ip,
                    "circle": circle,
                    "vendor": vendor,
                    "technology": technology,
                    "model": model,
                    "type": "VRF",
                    "name": vrf_name,
                    "parameter": f"{af} unicast",
                    "value": vrf.get(f"{af}_unicast"),
                    "deviation": vrf["deviation"][f"{af}_unicast"],
                    "reason": None
                })

                # import rt
                import_rts = vrf[af]["import_rt"]
                import_value = ",".join(rt["value"] for rt in import_rts)

                rows.append({
                    "ip": ip,
                    "circle": circle,
                    "vendor": vendor,
                    "technology": technology,
                    "model": model,
                    "type": "VRF",
                    "name": vrf_name,
                    "parameter": f"{af} import rt",
                    "value": import_value,
                    "deviation": vrf["deviation"][af]["import_rt_missing"],
                    "reason": "import route-target missing"
                    if vrf["deviation"][af]["import_rt_missing"] else None
                })

                # export rt
                export_rts = vrf[af]["export_rt"]
                export_value = ",".join(rt["value"] for rt in export_rts)

                rows.append({
                    "ip": ip,
                    "circle": circle,
                    "vendor": vendor,
                    "technology": technology,
                    "model": model,
                    "type": "VRF",
                    "name": vrf_name,
                    "parameter": f"{af} export rt",
                    "value": export_value,
                    "deviation": vrf["deviation"][af]["export_rt_missing"],
                    "reason": "export route-target missing"
                    if vrf["deviation"][af]["export_rt_missing"] else None
                })

        # ===================== ✅ BGP VRF =====================
        for vrf in data.get("bgp_vrf", {}).get("data", []):
            vrf_name = vrf.get("vrf")

            rows.append({
                "ip": ip,
                "circle": circle,
                "vendor": vendor,
                "technology": technology,
                "model": model,
                "type": "BGP_VRF",
                "name": vrf_name,
                "parameter": "RD",
                "value": vrf["rd"]["value"],
                "deviation": vrf["rd"]["status"] != "OK",
                "reason": vrf["rd"]["reason"]
            })

            rows.append({
                "ip": ip,
                "circle": circle,
                "vendor": vendor,
                "technology": technology,
                "model": model,
                "type": "BGP_VRF",
                "name": vrf_name,
                "parameter": "label-allocation-mode",
                "value": vrf["label_allocation_mode"]["value"],
                "deviation": vrf["label_allocation_mode"]["status"] != "OK",
                "reason": vrf["label_allocation_mode"]["reason"]
            })

        # ===================== ✅ L2VPN =====================
        for bd in data.get("l2vpn", {}).get("data", []):
            bd_name = f"BD{bd['bridge_domain']}"

            for k, v in bd.items():
                if isinstance(v, dict):
                    rows.append({
                        "ip": ip,
                        "circle": circle,
                        "vendor": vendor,
                        "technology": technology,
                        "model": model,
                        "type": "L2VPN",
                        "name": bd_name,
                        "parameter": k,
                        "value": v["value"],
                        "deviation": v["status"] != "OK",
                        "reason": v["reason"]
                    })

        # ===================== ✅ EVI =====================
        for evi in data.get("evi", {}).get("data", []):
            evi_id = evi["evi"]

            for k, v in evi.items():
                if isinstance(v, dict):
                    rows.append({
                        "ip": ip,
                        "circle": circle,
                        "vendor": vendor,
                        "technology": technology,
                        "model": model,
                        "type": "EVI",
                        "name": evi_id,
                        "parameter": k,
                        "value": v["value"],
                        "deviation": v["status"] != "OK",
                        "reason": v["reason"]
                    })

        # ===================== ✅ INTERFACES =====================
        for iface_type, iface_dict in data.get("interfaces", {}).items():
            for iface_name, params in iface_dict.items():
                for param, val in params.items():
                    if isinstance(val, dict):
                        rows.append({
                            "ip": ip,
                            "circle": circle,
                            "vendor": vendor,
                            "technology": technology,
                            "model": model,
                            "type": iface_type,
                            "name": iface_name,
                            "parameter": param,
                            "value": val.get("value"),
                            "deviation": val.get("deviation"),
                            "reason": None
                        })

        # ✅ Convert to DataFrame
        df = pd.DataFrame(rows)

        # ✅ Return Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="t4_{gct_id}.xlsx"'

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="T4_REPORT")

        return response



class GCTCiscoT4Job(APIView):
    # authentication_classes = [TokenAuthentication]
    # permission_classes = [IsAuthenticated]

    def post(self, request):
        model_id = request.data.get("id")
        gct_model = get_object_or_404(GCTModel, id=model_id)
        gct_model.current_status = "RUNNING"
        gct_model.save(update_fields=["current_status"])
        # logging.info(f"Fetched {rows} rows for GCT Model {gct_model.model} from Oracle DB")

        ip_inv = GCTCiscoT4.objects.filter(gct_model=gct_model)

        tasks.run_multithreaded.schedule((ip_inv,'nocsemsr','CDE#cde3','cisco_xr',f'/app/DCT_BE/IP_logs/T4Logs/Logs{datetime.now().strftime("%d%m%Y_%H%M%S")}',gct_model), delay=0)

        return Response({
            "message": "Cisco T4 Job scheduled, results are being processed",
            "total_ips": len(ip_inv)
        }, status=200)
        

        
        
        



BATCH_SIZE = 5000  
class GCTRunJob(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job_id = request.data.get("job_id")
        device_type = request.data.get("device_type")
        commands = request.data.getlist("commands")

        print("COMMANDS RECEIVED:", commands, len(commands))
       

        if not job_id or not commands:
            return Response({"error": "Invalid request"}, status=400)

        job = get_object_or_404(Job, id=job_id, created_by=request.user)

        if job.status != "DRAFT":
            return Response({"error": "Job already executed"}, status=400)
    
        job.device_type = device_type
        job.status = "RUNNING"
        job.save()

        file_path = job.file.path
        ips = read_ips_from_excel(file_path)

        # ---------------- BULK INSERT ----------------
        bulk_data = []
        total_tasks = 0
        sequence = 1

        for ip in ips:
            for cmd in commands:
                bulk_data.append(
                    CommandExecution(
                        job=job,
                        host_ip=ip,
                        command=sanitize_command(cmd),
                        sequence=sequence,
                        status="PENDING",
                    )
                )

                sequence += 1
                total_tasks += 1

                if len(bulk_data) >= BATCH_SIZE:
                    CommandExecution.objects.bulk_create(
                        bulk_data, batch_size=BATCH_SIZE
                    )
                    bulk_data = []

        if bulk_data:
            CommandExecution.objects.bulk_create(
                bulk_data, batch_size=BATCH_SIZE
            )

        # ---------------- UPDATE JOB STATS ----------------
        job.total_ips = len(ips)
        job.total_tasks = total_tasks
        job.save(update_fields=["total_ips", "total_tasks"])
    
    

        # ---------------- FAST SCHEDULING ----------------
        task_ids = (
            CommandExecution.objects
            .filter(job=job)
            .values_list("id", flat=True)
            .iterator(chunk_size=1000)
        )
        # for tid in task_ids:
        tasks.process_multiple_rows.schedule((task_ids,), delay=0)

        # ---------------- RESPONSE ----------------
        return Response({
            "message": "GCT Job scheduled successfully",
            "job_id": job.id,
            "total_tasks": total_tasks,
        })
    

# =========================END OF GCT API====================================  
    

class DownloadJobLogs(APIView):
    permission_classes = []
    authentication_classes = []
    def get(self, request, job_id, ip=None):
    
        ip_filter = ip  

        base_path = os.path.join(settings.LOG_DIR, f"job_{job_id}")

        if not os.path.exists(base_path):
            return HttpResponse("Logs not found", status=404)
        
         # Select only timestamp folders (YYYYMMDD_HHMMSS)
        timestamp_folders = [
            f for f in os.listdir(base_path)
            if os.path.isdir(os.path.join(base_path, f))
            and re.match(r"\d{8}_\d{6}", f)
        ]
        
        if not timestamp_folders:
            return HttpResponse("No timestamp folder found", status=404)
        

        timestamp_folder = sorted(timestamp_folders)[-1]
        timestamp_path = os.path.join(base_path, timestamp_folder)
        
        # ZIP filename
        if ip_filter:
            zip_filename = f"job_{job_id}_{ip_filter}_log.zip"
        else:
            zip_filename = f"job_{job_id}_logs.zip"

        zip_path = os.path.join(settings.LOG_DIR, zip_filename)

        try:# Create zip
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                if ip_filter:
                    # specific IP log
                    filename   = ip_filter if ip_filter.endswith(".log") else f"{ip_filter}.log"
                    file_path = os.path.join(timestamp_path, filename)
                    if not os.path.exists(file_path):
                        return HttpResponse("IP log not found", status=404)

                    zipf.write(file_path,filename)
                else:
                    for file in os.listdir(timestamp_path):
                        file_path = os.path.join(timestamp_path, file)

                        if os.path.isfile(file_path):  # only files
                            zipf.write(file_path, file)  # no subfolders

            # Return zip file
            response = FileResponse(open(zip_path, "rb"), content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
            return response

        finally:
            # Cleanup zip file
            if os.path.exists(zip_path):
                os.remove(zip_path)

def split_output_safely(text, limit=32767):
    lines = text.splitlines(keepends=True)

    chunks = []
    current_chunk = ""

    for line in lines:
        # If adding line exceeds limit → push current chunk
        if len(current_chunk) + len(line) > limit:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks



import os
import io
import json
import re

from django.http import HttpResponse
from django.conf import settings
from rest_framework.views import APIView

from openpyxl import Workbook


# ✅ Excel-safe sanitizer
def sanitize_for_excel(value):
    if value is None:
        return ""
    value = str(value)

    # Remove invalid XML characters
    value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", value)

    return value


class ExportJobCSV(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request, job_id):

        file_path = os.path.join(settings.LOG_DIR, f"job_{job_id}", "results.jsonl")

        if not os.path.exists(file_path):
            return HttpResponse("No data found", status=404)

        # ✅ Write-only (handles huge data safely)
        wb = Workbook(write_only=True)
        ws = wb.create_sheet(title="Job Results")

        # ✅ Header
        ws.append(["IP", "Status", "Connection", "Command", "Output"])

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    r = json.loads(line)

                    ip = sanitize_for_excel(r.get("ip"))
                    status = sanitize_for_excel(r.get("status"))
                    connection = sanitize_for_excel(r.get("connection"))
                    command = sanitize_for_excel(r.get("command"))
                    output_text = sanitize_for_excel(r.get("output") or "")

                    # ✅ extra safety
                    output_text = output_text.replace("\x00", "")

                    # ✅ split output into lines
                    lines = output_text.splitlines() or [""]

                    # ✅ repeat values for every line (NO MERGE)
                    for line_text in lines:
                        ws.append([
                            ip,
                            status,
                            connection,
                            command,
                            line_text
                        ])

                    # ✅ optional spacing between devices
                    ws.append(["", "", "", "", ""])

        except Exception as e:
            return HttpResponse(f"Error processing file: {str(e)}", status=500)

        # ✅ save to memory
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # ✅ response
        response = HttpResponse(
            output,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="job_{job_id}.xlsx"'

        return response


class DownloadTempFormat(APIView):
    permission_classes = []
    authentication_classes = []
    def get(self, request):
        file_path = os.path.join(
            settings.BASE_DIR,
            "apps",
            "templates",
            "IP_Nodes.xlsx"
        )
        return FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename="node_ip.xlsx"
        )
    

class AvailableGCTs(APIView):
    def get(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
        
        vendor = job.device_type
        gcts = []
        for key, meta in GCT_REGISTRY.get(vendor, {}).items():
            excel_path = os.path.join(
                settings.LOG_DIR,
                f"job_{job_id}",
                "gct",
                f"{key}.xlsx"
            )

            if not meta["task"]:
                status = "NOT_AVAILABLE"
            elif os.path.exists(excel_path):
                status = "COMPLETED"
            else:
                status = "NOT_RUN"

            gcts.append({
                "key": key,
                "label": meta["label"],
                "status": status
            })

        return Response({
            "vendor": vendor,
            "gcts": gcts
        })


class TriggerGCT(APIView):
    """
    POST /api/jobs/{id}/gcts/{gct}/run/
    Starts GCT validation for a specific GCT key
    """

    def post(self, request, job_id, gct_key):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)

        vendor = job.device_type
        # GCT_Validator.run_gct_validation.schedule(job.id, gct_key,delay=1 )
        GCT_Validator.run_gct_validation.schedule(args=(job.id, gct_key), kwargs={}, delay=1)
        #   validate_job.schedule((job.id, gct))

        return Response({
            "status": "PROCESSING",
            "message": f"GCT '{gct_key}' validation started for job {job_id}"
        })
    

class GCTStatusAPI(APIView):
    def get(self, request, job_id, gct_key):
        excel_path = os.path.join(
                settings.LOG_DIR,
                f"job_{job_id}",
                "gct",
                f"{gct_key}.xlsx"
            )

        if os.path.exists(excel_path):
            return Response({
                "status": "COMPLETED",
                "download_ready": True
            })

        return Response({
            "status": "RUNNING",
            "download_ready": False
        })
    

class GCTDownloadAPI(APIView):
    def get(self, request, job_id, gct_key):
        excel_path = os.path.join(
                settings.LOG_DIR,
                f"job_{job_id}",
                "gct",
                f"{gct_key}.xlsx"
            )

        if not os.path.exists(excel_path):
            return Response(
                {"error": "File not ready"},
                status=404
            )

        return FileResponse(
            open(excel_path, "rb"),
            as_attachment=True,
            filename=f"{job_id}_job_{gct_key}.xlsx"
        )



class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = ConfigExecutionRequest.objects.filter(
            user=request.user,
            status="APPROVED",
            expires_at__gt=timezone.now()
        ).first()
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "name":request.user.first_name,
            "is_staff": request.user.is_staff,
            "config_access": bool(access),
            "config_expires": access.expires_at if access else None
        })
    
class RequestConfigAccess(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        existing = ConfigExecutionRequest.objects.filter(
            user=request.user,
            status="PENDING"
        ).exists()

        if existing:
            return Response({"error": "Request already pending"}, status=400)
        
        duration= request.data.get("duration")


        req = ConfigExecutionRequest.objects.create(
            user=request.user,
            reason=request.data.get("reason", ""),
            duration_hours = int(duration)
        )
        send_config_request_email(req.id)

        return Response({"message": "Request sent to admin"})
    
class ApproveConfigAccess(APIView):
    permission_classes = [] 
    # permission_classes = [IsAuthenticated]
    def post(self, request, token):
        try:
            request_id = signer.unsign(token, max_age=86400)
        except SignatureExpired:
            return Response({"error": "Link expired"}, status=400)
        except BadSignature:
            return Response({"error": "Invalid token"}, status=400)
        
        req = ConfigExecutionRequest.objects.get(id=request_id)
    
        if req.status != "PENDING":
            return Response({"error": "Request already processed"}, status=400)
        
        user = req.user
        user.is_staff = True
        user.save()


        req.status = "APPROVED"
        req.approved_at = timezone.now()
        req.expires_at = timezone.now() + timedelta(hours=req.duration_hours)
        # req.approved_by = request.user
        req.approved_by_id = 1
        req.save()

        # Schedule expiry
        tasks.expire_request.schedule(
            args=(req.id,),
            eta=req.expires_at
        )
        return Response({
            "message": "Config access approved",
            "expires_at": req.expires_at
        })



class RejectConfigAccess(APIView):
    permission_classes = []
    def post(self, request, token):
        try:
            request_id = signer.unsign(token, max_age=86400)
        except:
            return Response({"error": "Invalid token"}, status=400)
        req = ConfigExecutionRequest.objects.get(id=request_id)
        if req.status != "PENDING":
            return Response({"error": "Already processed"}, status=400)
        req.status = "REJECTED"
        req.save()
        return Response({"message": "Rejected"})
    

class GetConfigRequestDetails(APIView):
    permission_classes = []
    def get(self, request, token):
        try:
            request_id = signer.unsign(token, max_age=86400)
        except:
            return Response({"error": "Invalid token"}, status=400)
        req = ConfigExecutionRequest.objects.get(id=request_id)
        return Response({
            "user": req.user.username,
            "email": req.user.email,
            "reason": req.reason,
            "duration": int(req.duration_hours * 60)
        })