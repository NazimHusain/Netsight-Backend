# ===============================
# apps/network/urls.py
# ===============================


from django.urls import path
from . import views


urlpatterns = [
    path("me/", views.MeView.as_view()),
    path("config-access/request/", views.RequestConfigAccess.as_view()),
    path("config/details/<str:token>/", views.GetConfigRequestDetails.as_view()),
    path("config/approve/<str:token>/", views.ApproveConfigAccess.as_view()),
    path("config/reject/<str:token>/", views.RejectConfigAccess.as_view()),
    path("upload_preview/", views.UploadIPFilePreview.as_view(), name="upload-preview"),
    path('run_job/',views.RunJob.as_view()),
    # ==============Multi commads Url================
    path("multi_commands_preview/", views.MultiCommandUploadIPFilePreview.as_view(), name="upload-preview"),
    path('run_multicommands/',views.MulticommandRun.as_view()),
    # ==========================End Block=================
    # path('upload/',views.UploadIPFile.as_view()),
    path('response_list/', views.JobListView.as_view()),
    path('response/<int:job_id>/details/', views.JobStatusView.as_view()),
    path("devicetype/",views.DevicetypeListingView.as_view()),
    path("response/<int:job_id>/download/", views.DownloadJobLogs.as_view()),
    path("job/<int:job_id>/logs/<str:ip>/", views.DownloadJobLogs.as_view()),
    path("job/<int:job_id>/export/csv/",views.ExportJobCSV.as_view(), name="export-job-csv"),
    path("download-template/", views.DownloadTempFormat.as_view(),name="download-template"),
    path("job/<int:job_id>/gcts/", views.AvailableGCTs.as_view(),name="gct-check"),
    path("job/<int:job_id>/gcts/<str:gct_key>/run/", views.TriggerGCT.as_view(),name="trigger-gct"),
    path("job/<int:job_id>/gcts/<str:gct_key>/status/", views.GCTStatusAPI.as_view(),name="gct-status"),
    path("job/<int:job_id>/gcts/<str:gct_key>/download/", views.GCTDownloadAPI.as_view(), name="download-gct"),
    path("gct_preview/", views.GCTIPFilePreview.as_view(), name="gct_preview"),
    path("api/gct/run/", views.GCTRunJob.as_view(), name="gct_run"),
    path("api/gct/view/", views.GCTModelView.as_view(), name="gct_view"),

    path("api/v1/t4inventory/", views.GCTCiscoT4Inv.as_view(), name="gct_t4_inventory"),
    path("api/v1/t4inventory/<int:id>/", views.GCTCiscoT4Inv.as_view(), name="gct_t4_inventory"),
    path("api/v2/t4inventory/<int:id>/", views.GCTCiscoT4InvV2.as_view(), name="gct_t4_inventoryv2"),
    path("api/v1/t4gct/", views.GCTCiscoT4Job.as_view(), name="gct_t4_gct"),
    path("api/v1/t4excel/<int:gct_id>/", views.DownloadLatestT4Excel.as_view(), name="gct_t4_excel"),


]

