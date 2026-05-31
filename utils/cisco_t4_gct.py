from apps.helpers import models as HelperModels
from django.conf import settings
import json
import os
from huey.contrib.djhuey import task
from compliance import  dispatcher as Validator
from compliance import  validation_excel as GeneratorExcel





@task()
def run_gct_validation(job_id,gct_key):
    job = HelperModels.Job.objects.get(id=job_id)

    job_dir = os.path.join(settings.LOG_DIR, f"job_{job.id}")
    input_file = os.path.join(job_dir, "results.jsonl")

    # vendor/gct specific folder (future-proof)
    gct_dir = os.path.join(job_dir, "gct")
    os.makedirs(gct_dir, exist_ok=True)
   
    # GCT-specific Excel file
    excel_file = os.path.join(gct_dir, f"{gct_key}.xlsx")
        

    validated_rows = []

    with open(input_file) as f:
        for line in f:
            row = json.loads(line)

            if row["status"] != "SUCCESS":
                continue

            result = Validator.validate_structure(
                device_type=job.device_type,
                command=row["command"],
                output=row["output"]
            )
            if result["status"] == "SKIPPED":
                continue

            validated_rows.append({
                "ip": row["ip"],
                "command": row["command"],
                "status": result["status"],
                "errors": result.get("errors", [])
            })

    GeneratorExcel.write_validation_excel(validated_rows, excel_file)
