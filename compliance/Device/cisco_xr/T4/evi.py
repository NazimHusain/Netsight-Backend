import re


def validate_evi(output: str):
    errors = []

    # Find all EVI IDs
    evis = set(re.findall(r"evpn\s+evi\s+(\d+)", output))

    if not evis:
        return {"status": "FORMAT_INVALID", "errors": ["No EVI found"]}

    for evi in sorted(evis):

        if not re.search(rf"^evpn\s+evi\s+{evi}\s+bgp\s*$", output, re.MULTILINE):
            errors.append(f"{evi} bgp missing")

        if not re.search(
            rf"^evpn\s+evi\s+{evi}\s+bgp\s+route-target\s+\d+\.\d+\.\d+\.\d+:\d+\s*$",
            output,
            re.MULTILINE,
        ):
            errors.append(f"{evi} bgp route-target missing")

        if not re.search(
            rf"^evpn\s+evi\s+{evi}\s+control-word-disable\s*$", output, re.MULTILINE
        ):
            errors.append(f"{evi} control-word-disable missing")

    return {"status": "FORMAT_OK" if not errors else "FORMAT_INVALID", "errors": errors}

