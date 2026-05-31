import re
import logging

from compliance.Device.cisco_xr.T4 import (
    vrf,
    bgp_vrf,
    l2vpn,
    evi,
    interface
)

def validate_structure(device_type, command: str, output: str):
    logging.info(f"Validation Structure for Device: {device_type}")
    cmd = command.lower().strip()

    # ---- VRF ----
    if cmd.startswith("show running-config vrf"):
        return vrf.validate_vrf(output)

    # ---- BGP VRF ----
    if cmd.startswith("sh run router bgp 9730"):
        return bgp_vrf.validate_bgp_vrf(output)

    # ---- L2VPN ----
    if cmd.startswith("sh run l2vpn | begin bridge"):
        return l2vpn.validate_l2vpn(output)

    # ---- Interface ----
    if cmd.startswith("show running-config interface"):
        return interface.validate_interface(output)

    # ---- EVPN (FIXED & CORRECT) ----
    if "sh run form" in cmd and "evpn evi" in cmd:
        return evi.validate_evi(output)
    
    # if "evpn evi" in cmd:
    #     return evi.validate_evi(output)


    return {
        "status": "SKIPPED",
        "errors": ["No structure template for this command"]
    }





