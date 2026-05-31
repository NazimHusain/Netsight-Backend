import re

def validate_bgp_vrf(output: str):
    errors = []

    # Any VRF without name → hard fail
    if re.search(r"(?m)^\s*vrf\s*$", output):
        return {
            "status": "FORMAT_INVALID",
            "errors": ["vrf <NAME> missing"]
        }
     
    vrfs = re.findall(
        r"(?ms)^\s*vrf\s+(\S+)(.*?)(?=^\s*vrf\s+|\Z)",
        output
    )
    # Validate each VRF
    for vrf_name, vrf_body in vrfs:

        # RD check
        if not re.search(r"(?m)^\s*rd\s+\d+:\d+", vrf_body):
            errors.append(f"{vrf_name}: rd X:X missing")

        # Label allocation
        if not re.search(r"(?m)^\s*label-allocation-mode\s+per-vrf\s*$", vrf_body):
            errors.append(f"{vrf_name}: label-allocation-mode per-vrf missing")


        # Address-family validation
        for af in ("ipv4", "ipv6"):
            af_match = re.search(
                rf"(?ms)address-family {af} unicast(.*?)(?=^\s*!$)",
                vrf_body
            )
            if not af_match:
                errors.append(f"{vrf_name}: address-family {af} unicast missing")
                continue

            af_body = af_match.group(1)

            if not re.search(r"(?m)^\s*redistribute connected\s*$", af_body):
                errors.append(f"{vrf_name}: {af} redistribute connected missing")

            if not re.search(r"(?m)^\s*redistribute static\s*$", af_body):
                errors.append(f"{vrf_name}: {af} redistribute static missing")

    return {
        "status": "FORMAT_OK" if not errors else "FORMAT_INVALID",
        "errors": errors
    }
