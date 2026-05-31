import re


def validate_vrf(output: str):
    errors = []

    if re.search(r"(?m)^\s*vrf\s*$", output):
        return {
            "status": "FORMAT_INVALID",
            "errors": ["vrf <NAME> missing"]
        }

    vrfs = re.findall(
        r"(?ms)^\s*vrf\s+(\S+)(.*?)(?=^\s*vrf\s+|\Z)",
        output
    )
  
    for vrf_name, vrf_body in vrfs:
        for af in ("ipv4", "ipv6"):
            af_match = re.search(
                rf"(?ms)address-family {af} unicast(.*?)(?=^\s*address-family|\Z)",
                vrf_body
            )

            if not af_match:
                errors.append(f"{vrf_name}: address-family {af} unicast missing")
                continue

            body = af_match.group(1)

            # import route-target
            import_block = re.search(
                r"(?ms)^\s*import route-target(.*?)(?=^\s*(export route-target|maximum prefix|address-family|vrf)\s+|\Z)",
                body
            )

            if not import_block:
                errors.append(f"{vrf_name}: {af} import route-target missing")
            elif not re.search(r"^\s+\d+:\d+", import_block.group(1), re.M):
                errors.append(f"{vrf_name}: {af} import route-target X:X missing")


            # export route-target
            export_block = re.search(
                r"(?ms)^\s*export route-target(.*?)(?=^\s*(maximum prefix|address-family|vrf)\s+|\Z)",
                body
            )

            if not export_block:
                errors.append(f"{vrf_name}: {af} export route-target missing")
            elif not re.search(r"^\s+\d+:\d+", export_block.group(1), re.M):
                errors.append(f"{vrf_name}: {af} export route-target X:X missing")
            
            # maximum prefix
            if not re.search(r"^\s*maximum prefix \d+ \d+", body, re.M):
                errors.append(f"{vrf_name}: {af} maximum prefix X X missing")
            
    return {
        "status": "FORMAT_OK" if not errors else "FORMAT_INVALID",
        "errors": errors
    }


def parse_vrf_output(output: str):
    vrf_list = []

    vrfs = re.findall(
        r"(?ms)^\s*vrf\s+(\S+)(.*?)(?=^\s*vrf\s+|\Z)",
        output
    )

    for vrf_name, vrf_body in vrfs:
        vrf_data = {
            "vrf_name": vrf_name,
            "ipv4_unicast": False,
            "ipv6_unicast": False,
            "ipv4": {
                "import_rt": [],
                "export_rt": []
            },
            "ipv6": {
                "import_rt": [],
                "export_rt": []
            },
            "deviation": {
                "ipv4_unicast": True,
                "ipv6_unicast": True,
                "ipv4": {
                    "import_rt_missing": True,
                    "export_rt_missing": True,
                    "maximum_prefix": True
                },
                "ipv6": {
                    "import_rt_missing": True,
                    "export_rt_missing": True,
                    "maximum_prefix": True
                }
            }
        }

        for af in ("ipv4", "ipv6"):
            af_match = re.search(
                rf"(?ms)address-family {af} unicast(.*?)(?=^\s*address-family|\Z)",
                vrf_body
            )

            if not af_match:
                continue

            # AF present
            vrf_data[f"{af}_unicast"] = True
            vrf_data["deviation"][f"{af}_unicast"] = False

            body = af_match.group(1)

            # -------- IMPORT RT --------
            import_block = re.search(
                r"(?ms)^\s*import route-target(.*?)(?=^\s*(export route-target|maximum prefix|address-family|vrf)\s+|\Z)",
                body
            )

            if import_block:
                import_rts = re.findall(r"^\s+(\d+:\d+)", import_block.group(1), re.M)
                
                if import_rts:
                    vrf_data["deviation"][af]["import_rt_missing"] = False

                for rt in import_rts:
                    vrf_data[af]["import_rt"].append({
                        "value": rt,
                        "deviation": False  # valid since it matched X:X
                    })

            # -------- EXPORT RT --------
            export_block = re.search(
                r"(?ms)^\s*export route-target(.*?)(?=^\s*(maximum prefix|address-family|vrf)\s+|\Z)",
                body
            )

            if export_block:
                export_rts = re.findall(r"^\s+(\d+:\d+)", export_block.group(1), re.M)

                if export_rts:
                    vrf_data["deviation"][af]["export_rt_missing"] = False

                for rt in export_rts:
                    vrf_data[af]["export_rt"].append({
                        "value": rt,
                        "deviation": False
                    })

            # -------- MAX PREFIX --------
            if re.search(r"^\s*maximum prefix \d+ \d+", body, re.M):
                vrf_data["deviation"][af]["maximum_prefix"] = False

        vrf_list.append(vrf_data)

    return vrf_list



