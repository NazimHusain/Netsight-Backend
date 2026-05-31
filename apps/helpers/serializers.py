from rest_framework import serializers
from .models import Job,GCTModel,GCTCiscoT4, DeviceExecution, CommandExecution

# class IPTaskSerializer(serializers.ModelSerializer):
#     class Meta:
#             model = IPTask
#             fields = ['id', 'job', 'ip', 'status', 'error','command_output','started_at','finished_at']

class GCTModelSerializer(serializers.ModelSerializer):
    """
    Serializer for GCTModel
    Handles serialization and deserialization of GCT (Generic Configuration Test) model data
    """
    
    class Meta:
        model = GCTModel
        fields = [
            'id',
            'vendor',
            'nw_type',
            'model',
            'inventory_count',
            'gct_availability',
            'gct_sharedon',
            'development_status',
            'deviation_count',
            'remarks',
            'exec_endpoint',
            'get_endpoint',
            'current_status',
            'created_at',
            'updated_at',
            'is_deleted',
        ]
        # read_only_fields = ['id', 'created_at', 'updated_at']


class JobSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True)
    keyword_type = serializers.SerializerMethodField()
    class Meta:
        model = Job
        fields = ['id','total_ips','total_tasks', 'completed','device_type','status','created_at','created_by','execution_mode','keyword_type']
    
    def get_keyword_type(self, obj):

        has_device_execution = DeviceExecution.objects.filter(
            job=obj
        ).exists()

        if has_device_execution:
            return "multi"

        has_command_execution = CommandExecution.objects.filter(
            job=obj
        ).exists()

        if has_command_execution:
            return "single"

        return None

class GCTCiscoT4Serializer(serializers.ModelSerializer):
    class Meta:
        model = GCTCiscoT4
        fields = '__all__'
