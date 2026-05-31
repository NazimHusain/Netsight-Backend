from django.contrib import admin
from .models import Job, ConfigExecutionRequest,CommandExecution,GCTModel,GCTCommand, DeviceExecution, DeviceMultiCommand,GCTCiscoT4,CiscoT4Data
from django.utils.html import format_html

@admin.register(ConfigExecutionRequest)
class ConfigExecutionRequestAdmin(admin.ModelAdmin):
    list_display = ('id','status', 'user','requested_at','approved_by','approved_at','expires_at','duration_hours','reason','admin_comment')

@admin.register(Job)
class JobDeviceAdmin(admin.ModelAdmin):
    list_display = ('id','created_by', 'device_type', 'total_ips','total_tasks', 'completed', 'status',"success","failed","completed_at")
   

@admin.register(CommandExecution)
class CommandExecutionAdmin(admin.ModelAdmin):
    list_display = ('id','job', 'host_ip','command','status','error','sequence','started_at','finished_at')
    search_fields = (
        'host_ip',
        'job__id',
    )

@admin.register(GCTModel)
class GCTModelAdmin(admin.ModelAdmin):
    list_display = ('id','vendor', 'nw_type','model','inventory_count','gct_availability','gct_sharedon','development_status','deviation_count','current_status')
    search_fields = (
        'vendor',
        'nw_type',
        'model'
    )

@admin.register(GCTCommand)
class GCTCommandAdmin(admin.ModelAdmin):
    list_display = ('id', 'command')
    search_fields = (
        'id',
        'command',
    )

@admin.register(GCTCiscoT4)   
class GCTCiscoT4Admin(admin.ModelAdmin):
    list_display = ('id','ip_address', 'circle','hostname','status')
    search_fields = (
        'id',
        'ip_address',
        'circle',
        'hostname',
    )

@admin.register(CiscoT4Data)   
class CiscoT4DataAdmin(admin.ModelAdmin):
    list_display = ('id','inv_model')
    search_fields = (
        'id',
    )




@admin.register(DeviceExecution)
class DeviceExecutionAdmin(admin.ModelAdmin):
    list_display = ('id','job', 'host_ip','status','started_at','finished_at')
    search_fields = (
        'host_ip',
        'job__id',
    )


@admin.register(DeviceMultiCommand)
class DeviceMultiCommandAdmin(admin.ModelAdmin):
    list_display = ('id','device', 'command','sequence','output','status','error','started_at','finished_at')
    search_fields = (
        'host_ip',
        'job__id',
    )