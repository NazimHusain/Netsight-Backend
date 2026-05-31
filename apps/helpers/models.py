from django.db import models
from django.db import models
from django.utils import timezone
import json
from django.conf import settings

class AbstractDateTimeModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    class Meta:
        abstract = True

    def soft_delete(self: 'AbstractDateTimeModel') -> None:
        self.is_deleted = True
        self.save()






class Job(AbstractDateTimeModel):
    
    DEVICE_TYPES = [
        ('juniper_junos', 'Juniper JunOS'),
        ('juniper_bras', 'Juniper BRAS'),
        ('cisco_xr', 'Cisco XR'),
        ('cisco_xe', 'Cisco XE'),
        ('huawei', 'Huawei'),
        ('nokia_sros', 'Nokia'),
        ('ciena_saos', "Ciena"),
        ('generic',"Generic")
        
    ]
    created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="jobs"
)
    file = models.FileField(upload_to="uploads/jobs/",null=True, blank=True)
    total_ips = models.IntegerField(default=0)
    total_tasks = models.IntegerField(default=0)
    completed = models.IntegerField(default=0)
    success = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    device_type = models.CharField(
        max_length=50,
        choices=DEVICE_TYPES,         
        default='juniper_junos',
        null=True,
        blank=True
    )
    
    status = models.CharField(max_length=20, default="PENDING")
    completed_at  = models.DateTimeField(null=True)
    execution_mode = models.CharField(
    max_length=20,
    choices=[
        ("readonly", "Read Only"),
        ("config", "Configuration")
    ],
    default="readonly"
    )
    
    @staticmethod
    def get_device_types():
        return [
            {"id": value, "name": label}
            for value, label in Job.DEVICE_TYPES
        ]
        


class CommandExecution(AbstractDateTimeModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("SUCCESS", "Success"),
        ("FAILED", "Failed"),
    ]
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="row_tasks")
    host_ip = models.GenericIPAddressField()
    command = models.TextField()   
    output = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    error = models.TextField(null=True, blank=True)
    sequence = models.IntegerField()  
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    class Meta:
        indexes = [
            models.Index(fields=["job", "status"]),
            models.Index(fields=["host_ip"]),
        ]
        ordering = ["sequence"]


class GCTModel(AbstractDateTimeModel):
    vendor = models.CharField(max_length=255)
    nw_type = models.CharField(max_length=255)
    model = models.CharField(max_length=255)
    inventory_count = models.IntegerField(default=0)
    gct_availability = models.BooleanField(default=False)
    gct_sharedon = models.DateTimeField(null=True, blank=True)
    development_status = models.CharField(max_length=255, default="Not Started")
    deviation_count = models.IntegerField(default=0)
    remarks = models.TextField(blank=True,null=True)
    query_inv = models.TextField(blank=True,null=True)
    exec_endpoint = models.CharField(max_length=1000, blank=True, null=True)
    get_endpoint = models.CharField(max_length=1000, blank=True, null=True)
    current_status = models.CharField(max_length=255, default="Not Started")

class GCTCommand(AbstractDateTimeModel):
    gct_model = models.ForeignKey(GCTModel, on_delete=models.CASCADE, related_name="commands")
    command = models.TextField()
    
class GCTCiscoT4(AbstractDateTimeModel):
    gct_model = models.ForeignKey(GCTModel, on_delete=models.CASCADE, related_name="inventories")
    ip_address = models.CharField(max_length=255)
    circle = models.CharField(max_length=255,blank=True,null=True)
    hostname = models.CharField(max_length=255, blank=True, null=True)
    total_vrfs = models.IntegerField(default=0)
    deviated_vrfs = models.IntegerField(default=0)
    total_l2vpn = models.IntegerField(default=0)
    deviated_l2vpn = models.IntegerField(default=0)
    total_bgp = models.IntegerField(default=0)
    deviated_bgp = models.IntegerField(default=0)
    total_interfaces = models.IntegerField(default=0)
    deviated_interfaces = models.IntegerField(default=0)
    total_evi = models.IntegerField(default=0)
    deviated_evi = models.IntegerField(default=0)
    status = models.CharField(max_length=255, default="Not Started")


class CiscoT4Data(AbstractDateTimeModel):
    inv_model = models.ForeignKey(GCTCiscoT4, on_delete=models.CASCADE, related_name="gct_inv_id")
    command_output = models.TextField()
    complete_data = models.TextField()

# class IPBatch(AbstractDateTimeModel):
#     job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="Batch_tasks")
#     ips = models.JSONField()  # list of IPs
#     status = models.CharField(default="PENDING", max_length=20) # PENDING/RUNNING/DONE/ERROR
#     error = models.TextField(null=True, blank=True)
#     started_at = models.DateTimeField(null=True)
#     finished_at = models.DateTimeField(null=True)





# class IPResult(AbstractDateTimeModel):
#     job = models.ForeignKey(Job, on_delete=models.CASCADE)
#     ip = models.GenericIPAddressField()
#     status = models.CharField(max_length=10)  # DONE / ERROR
#     error = models.TextField(null=True, blank=True)







# ===============================================Multi commands Models ===========================


class DeviceExecution(AbstractDateTimeModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("SUCCESS", "Success"),
        ("FAILED", "Failed"),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="devices")
    host_ip = models.GenericIPAddressField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")

    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        unique_together = ("job", "host_ip")


class DeviceMultiCommand(AbstractDateTimeModel):
    device = models.ForeignKey(DeviceExecution, on_delete=models.CASCADE, related_name="commands")

    command = models.TextField()
    sequence = models.IntegerField()

    output = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, default="PENDING")
    error = models.TextField(null=True, blank=True)

    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["sequence"]



# ==========================END Block==================================================

    
    




class ConfigExecutionRequest(AbstractDateTimeModel):
    STATUS = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("EXPIRED", "Expired"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_config_requests"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    duration_hours = models.IntegerField(null=True, blank=True, default=0)
    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="PENDING"
    )
    reason = models.TextField(blank=True, help_text="User justification for requesting configuration access")
    admin_comment = models.TextField(
        blank=True,
        help_text="Admin comment while approving/rejecting"
    )
    class Meta:
        ordering = ["-requested_at"]
    
    def __str__(self):
        return f"{self.user.username} - {self.status}"


