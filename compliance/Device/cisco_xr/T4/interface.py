import re


def validate_interface(output: str):
    errors = []
    # Split into interface blocks
    blocks = re.findall(
        # r"(?ms)^interface\s+.+?(?=^!$)", 
        r"(?ms)^interface\s+[^\n]+.*?\n!",
        output)
    
    # blocks = re.split(r"(?m)^(?=interface\s)", output)
    # blocks = [b for b in blocks if b.strip().startswith("interface")]

    for block in blocks:
        iface = re.search(r"^interface\s+([^\n]+)", block, re.M)
        if not iface:
            errors.append(f"interface missing")
            continue
        iface_name = iface.group(1).strip()
        # =====================================================
        # 1 Bundle-Ether<XX> (Parent L3)
        # =====================================================
        if re.fullmatch(r"Bundle-Ether\d+", iface_name):
            if not re.search(r"(?m)^\s*mtu\s+9216$", block):
                errors.append(f"{iface_name}: mtu 9216 missing")

            if not re.search(r"(?m)^\s*service-policy input\s+\S+", block):
                errors.append(f"{iface_name}: service-policy input missing")

            if not re.search(r"(?m)^\s*service-policy output\s+\S+", block):
                errors.append(f"{iface_name}: service-policy output missing")

            if not re.search(r"(?m)^\s*load-interval\s+30$", block):
                errors.append(f"{iface_name}: load-interval 30 missing")
        # =====================================================
        # 2️ Bundle-Ether<XX>.<YY> l2transport
        # =====================================================
        elif re.fullmatch(r"Bundle-Ether\d+\.\d+\s+l2transport", iface_name):
            if not re.search(r"(?m)^\s*description\s+.+", block):
                errors.append(f"{iface_name}: description missing")
            if not re.search(r"(?m)^\s*encapsulation\s+dot1q\s+\d+", block):
                errors.append(f"{iface_name}: encapsulation dot1q missing")
            if not re.search(
                    r"(?m)^\s*rewrite\s+ingress\s+tag\s+pop\s+1\s+symmetric$", block
                ):
                errors.append(
                        f"{iface_name}: rewrite ingress tag pop 1 symmetric missing"
                    )
        # =====================================================
        # 3 BVI<XX>
        # =====================================================
        elif re.fullmatch(r"BVI\d+", iface_name):

            if not re.search(r"(?m)^\s*description\s+.+", block):
                errors.append(f"{iface_name}: description missing")

            if not re.search(r"(?m)^\s*host-routing$", block):
                errors.append(f"{iface_name}: host-routing missing")

            if not re.search(r"(?m)^\s*mtu\s+9216$", block):
                errors.append(f"{iface_name}: mtu 9216 missing")

            if not re.search(r"(?m)^\s*vrf[ \t]+\S+", block):
                print(f"{iface_name}: vrf missing or empty")


            if not re.search(
                r"(?m)^\s*ipv4\s+address\s+\d{1,3}(?:\.\d{1,3}){3}\s+\d{1,3}(?:\.\d{1,3}){3}$",
                block
            ):
                errors.append(f"{iface_name}: ipv4 address missing")

            if not re.search(
                r"(?m)^\s*ipv6\s+address\s+[0-9a-fA-F:]+/\d+$",
                block
            ):
                errors.append(f"{iface_name}: ipv6 address missing")

            if not re.search(r"(?m)^\s*arp\s+timeout\s+300$", block):
                errors.append(f"{iface_name}: arp timeout 300 missing")

            if not re.search(r"(?m)^\s*mac-address[ \t]+a2\.a2\.a2$", block):
                errors.append(f"{iface_name}: mac-address invalid or missing")


            if not re.search(r"(?m)^\s*load-interval\s+30$", block):
                errors.append(f"{iface_name}: load-interval 30 missing")


    return {"status": "FORMAT_OK" if not errors else "FORMAT_INVALID", "errors": errors}



def validate_interface_new(output: str):
    result = {
        "Bundle-Ether": {},
        "Bundle-Ether.l2transport": {},
        "BVI": {}
    }

    blocks = re.findall(r"(?ms)^interface\s+[^\n]+.*?\n!", output)

    for block in blocks:
        iface_match = re.search(r"^interface\s+([^\n]+)", block, re.M)
        if not iface_match:
            continue

        iface_name = iface_match.group(1).strip()

        # =====================================================
        # 1️⃣ Bundle-Ether<XX>
        # =====================================================
        if re.fullmatch(r"Bundle-Ether\d+", iface_name):

            data = {}

            mtu = re.search(r"(?m)^\s*mtu\s+(\d+)", block)
            val = mtu.group(1) if mtu else None
            data["mtu"] = {"value": val, "deviation": val != "9216"}

            spi = re.search(r"(?m)^\s*service-policy input\s+(\S+)", block)
            val = spi.group(1) if spi else None
            data["service_policy_input"] = {"value": val, "deviation": val is None}

            spo = re.search(r"(?m)^\s*service-policy output\s+(\S+)", block)
            val = spo.group(1) if spo else None
            data["service_policy_output"] = {"value": val, "deviation": val is None}

            data["load_interval_30"] = bool(
                re.search(r"(?m)^\s*load-interval\s+30$", block)
            )

            result["Bundle-Ether"][iface_name] = data

        # =====================================================
        # 2️⃣ Bundle-Ether<XX>.<YY> l2transport
        # =====================================================
        elif re.fullmatch(r"Bundle-Ether\d+\.\d+\s+l2transport", iface_name):

            clean_name = iface_name.replace(" l2transport", "")
            data = {}

            desc = re.search(r"(?m)^\s*description\s+(.+)", block)
            val = desc.group(1) if desc else None
            data["description"] = {"value": val, "deviation": val is None}

            enc = re.search(r"(?m)^\s*encapsulation\s+dot1q\s+(\d+)", block)
            val = enc.group(1) if enc else None
            data["encapsulation_dot1q"] = {"value": val, "deviation": val is None}

            data["rewrite_pop_1_symmetric"] = bool(
                re.search(r"(?m)^\s*rewrite\s+ingress\s+tag\s+pop\s+1\s+symmetric$", block)
            )

            result["Bundle-Ether.l2transport"][clean_name] = data

        # =====================================================
        # 3️⃣ BVI<XX>
        # =====================================================
        elif re.fullmatch(r"BVI\d+", iface_name):

            data = {}

            desc = re.search(r"(?m)^\s*description\s+(.+)", block)
            val = desc.group(1) if desc else None
            data["description"] = {"value": val, "deviation": val is None}

            vrf = re.search(r"(?m)^\s*vrf\s+(\S+)", block)
            val = vrf.group(1) if vrf else None
            data["vrf"] = {"value": val, "deviation": val is None}

            mtu = re.search(r"(?m)^\s*mtu\s+(\d+)", block)
            val = mtu.group(1) if mtu else None
            data["mtu"] = {"value": val, "deviation": val != "9216"}

            ipv4 = re.search(
                r"(?m)^\s*ipv4\s+address\s+(\S+\s+\S+)", block
            )
            val = ipv4.group(1) if ipv4 else None
            data["ipv4_address"] = {"value": val, "deviation": val is None}

            ipv6 = re.search(
                r"(?m)^\s*ipv6\s+address\s+(\S+)", block
            )
            val = ipv6.group(1) if ipv6 else None
            data["ipv6_address"] = {"value": val, "deviation": val is None}

            data["arp_timeout_300"] = bool(
                re.search(r"(?m)^\s*arp\s+timeout\s+300$", block)
            )

            data["mac_address_valid"] = bool(
                re.search(r"(?m)^\s*mac-address\s+a2\.a2\.a2$", block)
            )

            data["host_routing"] = bool(
                re.search(r"(?m)^\s*host-routing$", block)
            )

            data["load_interval_30"] = bool(
                re.search(r"(?m)^\s*load-interval\s+30$", block)
            )

            result["BVI"][iface_name] = data

    return result





