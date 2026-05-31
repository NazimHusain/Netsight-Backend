import re

def validate_l2vpn(output: str):
    errors = []

    # Extract each bridge-domain block
    bridge_domains = re.findall(
        r"(?ms)^\s*bridge-domain\s+(\d+)(.*?)(?=^\s*bridge-domain\s+|\Z)",
        output
    )
    if not bridge_domains:
        errors.append("bridge-domain <X> missing")
        return {"status": "FORMAT_INVALID", "errors": errors}
    
    for bd_id, bd_body in bridge_domains:

        # interface Bundle-Ether<X>.<Y>
        if not re.search(r"(?m)^\s*interface\s+Bundle-Ether\d+\.\d+\s*$", bd_body):
            errors.append(f"bridge-domain {bd_id}: interface Bundle-Ether<X>.<Y> missing")
        
        # routed interface BVI<X>
        if not re.search(r"(?m)^\s*routed\s+interface\s+BVI\d+\s*$", bd_body):
            errors.append(f"bridge-domain {bd_id}: routed interface BVI<X> missing")
        
        if not re.search(r"(?m)^\s*evi\s+\d+\s*$", bd_body):
            errors.append(f"bridge-domain {bd_id}: evi <X> missing")

    return {
        "status": "FORMAT_OK" if not errors else "FORMAT_INVALID",
        "errors": errors
    }
