from django.conf import settings


def resolve_netmiko_device_type(job):
    """
    Maps UI device_type → Netmiko driver
    """
    device = settings.NETMIKO_DEVICE_MAP.get(job.device_type)

    if not device:
        raise ValueError(f"No Netmiko mapping for {job.device_type}")

    return device



def resolve_credentials(job):
    """
    Select credentials based on execution_mode + device_type
    """

    if job.execution_mode == "config":
        cred_source = settings.DEVICE_CONFIG_CREDENTIALS
    else:
        cred_source = settings.DEVICE_CREDENTIALS

    creds = cred_source.get(job.device_type)

    if not creds:
        raise ValueError(
            f"No credentials for device={job.device_type}, mode={job.execution_mode}"
        )

    return creds