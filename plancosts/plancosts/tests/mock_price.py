# # mock_pricing_api.py
# from http.server import BaseHTTPRequestHandler, HTTPServer
# import json
# import os
# import socket

# # -------------------
# # Config via env vars
# # -------------------
# MODE = os.getenv("MOCK_MODE", "normal").lower()
# #   normal     -> return one product per query (default)
# #   multiple   -> return 2 products (to trigger "Multiple prices found..." warning)
# #   none       -> return []
# #   error      -> return HTTP 500

# DEFAULT_PRICE = float(os.getenv("MOCK_BASE_PRICE", "0.0416"))

# OVERRIDE = {
#     # EC2 Compute Instance hours
#     "EC2_INSTANCE_HR": float(os.getenv("MOCK_PRICE_EC2", "0.0416")),
#     # EBS gp2/standard/sc1/st1 GB-month
#     "EBS_GB": float(os.getenv("MOCK_PRICE_EBS_GB", "0.10")),
#     # EBS io1 IOPS-month
#     "EBS_IOPS": float(os.getenv("MOCK_PRICE_EBS_IOPS", "0.0002")),
#     # EBS Snapshot GB-month (with usagetype=EBS:SnapshotUsage)
#     "SNAPSHOT_GB": float(os.getenv("MOCK_PRICE_SNAPSHOT_GB", "0.05")),
#     # ELB classic hours
#     "ELB_CLASSIC_HR": float(os.getenv("MOCK_PRICE_ELB_CLASSIC", "0.025")),
#     # ALB/NLB hours
#     "ELB_ALB_HR": float(os.getenv("MOCK_PRICE_ELB_ALB", "0.0225")),
#     "ELB_NLB_HR": float(os.getenv("MOCK_PRICE_ELB_NLB", "0.0225")),
#     # NAT Gateway hours
#     "NATGW_HR": float(os.getenv("MOCK_PRICE_NATGW_HR", "0.045")),

#     # ---------- NEW: RDS ----------
#     # RDS instance hours
#     "RDS_INSTANCE_HR": float(os.getenv("MOCK_PRICE_RDS_INSTANCE_HR", "0.0416")),
#     # RDS storage GB-month
#     "RDS_STORAGE_GB": float(os.getenv("MOCK_PRICE_RDS_STORAGE_GB", "0.10")),
#     # RDS provisioned IOPS-month
#     "RDS_IOPS": float(os.getenv("MOCK_PRICE_RDS_IOPS", "0.00004")),
# }

# def _usd(price: float) -> dict:
#     s = f"{price:.6f}"
#     s = s.rstrip("0").rstrip(".") if "." in s else s
#     return {"USD": s}

# def _product(price: float) -> dict:
#     return {
#         "onDemandPricing": [{
#             "priceDimensions": [{
#                 "pricePerUnit": _usd(price)
#             }]
#         }]
#     }

# def _response_for_filters(attrs: list[dict]) -> list[dict]:
#     """
#     Very small 'pricing engine':
#     - looks at servicecode/productFamily/usagetype filters
#     - returns one/many/none products depending on MODE
#     """
#     # Normalize attributes into a quick dict: key -> [(op, val), ...]
#     bykey: dict[str, list[tuple[str, str]]] = {}
#     for a in attrs or []:
#         k = a.get("key", "")
#         op = a.get("operation", "")
#         v = a.get("value", "")
#         bykey.setdefault(k, []).append((op, v))

#     service = next((v for _, v in bykey.get("servicecode", [])[-1:]), "")
#     family  = next((v for _, v in bykey.get("productFamily", [])[-1:]), "")
#     usg     = next((v for _, v in bykey.get("usagetype",   [])[-1:]), "")

#     price = DEFAULT_PRICE

#     # -------- Decision table ----------
#     # EC2 compute instance hours
#     if service == "AmazonEC2" and family == "Compute Instance":
#         price = OVERRIDE["EC2_INSTANCE_HR"]

#     # EBS storage GB-month (gp2/standard/etc.)
#     elif service == "AmazonEC2" and family == "Storage":
#         price = OVERRIDE["EBS_GB"]

#     # EBS IOPS-month
#     elif service == "AmazonEC2" and family == "System Operation" and ("EBS:VolumeP-IOPS.piops" in usg or "EBS:VolumeP-IOPS.piops" in str(bykey.get("usagetype", ""))):
#         price = OVERRIDE["EBS_IOPS"]

#     # EBS Snapshot GB-month (requires EBS:SnapshotUsage)
#     elif service == "AmazonEC2" and family == "Storage Snapshot" and ("EBS:SnapshotUsage" in usg or "EBS:SnapshotUsage" in str(bykey.get("usagetype", ""))):
#         price = OVERRIDE["SNAPSHOT_GB"]

#     # ELB/ALB/NLB hours
#     elif service == "AWSELB" and ("Load Balancer" in family):
#         if family == "Load Balancer":
#             price = OVERRIDE["ELB_CLASSIC_HR"]
#         elif family == "Load Balancer-Application":
#             price = OVERRIDE["ELB_ALB_HR"]
#         elif family == "Load Balancer-Network":
#             price = OVERRIDE["ELB_NLB_HR"]

#     # NAT Gateway hours
#     elif service == "AmazonEC2" and family == "NAT Gateway" and ("NatGateway-Hours" in usg or "NatGateway-Hours" in str(bykey.get("usagetype", ""))):
#         price = OVERRIDE["NATGW_HR"]

#     # ---------- NEW: RDS pricing ----------
#     # RDS instance hours
#     elif service == "AmazonRDS" and family == "Database Instance":
#         price = OVERRIDE["RDS_INSTANCE_HR"]

#     # RDS storage GB-month
#     elif service == "AmazonRDS" and family == "Database Storage":
#         price = OVERRIDE["RDS_STORAGE_GB"]

#     # RDS provisioned IOPS-month
#     elif service == "AmazonRDS" and family == "Provisioned IOPS":
#         price = OVERRIDE["RDS_IOPS"]

#     # ------- Compose the products array based on MODE -------
#     if MODE == "none":
#         return []
#     elif MODE == "multiple":
#         return [_product(price), _product(price * 10.0)]
#     else:
#         return [_product(price)]


# class H(BaseHTTPRequestHandler):
#     def do_POST(self):
#         # Optional: simulate server error
#         if MODE == "error":
#             self.send_error(500, "Simulated server error")
#             return

#         length = int(self.headers.get("Content-Length", 0))
#         body = self.rfile.read(length).decode("utf-8")

#         try:
#             queries = json.loads(body)
#             if not isinstance(queries, list):
#                 queries = [queries]
#         except Exception:
#             queries = []

#         resp = []
#         for q in queries:
#             attrs = (((q or {}).get("variables") or {}).get("filter") or {}).get("attributes", [])
#             products = _response_for_filters(attrs)
#             resp.append({"data": {"products": products}})

#         out = json.dumps(resp).encode("utf-8")
#         self.send_response(200)
#         self.send_header("Content-Type", "application/json")
#         self.send_header("Content-Length", str(len(out)))
#         self.end_headers()
#         self.wfile.write(out)


# # -------------------
# # Self-test utilities
# # -------------------
# def _normalize_tenancy(v):
#     # Infracost 337a504: "dedicated" -> "Dedicated", else "Shared"
#     return "Dedicated" if f"{v}" == "dedicated" else "Shared"

# def _run_self_tests():
#     """
#     Minimal self-test runner (no pytest).
#     - Validates tenancy normalization via plancosts.base.filters.ValueMapping/map_filters
#     - Validates the fixture test.json has expected tenancy fields
#     - Validates the mock pricing engine returns a product for EC2 instance hours regardless of tenancy
#     """
#     from plancosts.base.filters import ValueMapping, map_filters

#     # 1) Tenancy mapping checks
#     vm_inst = ValueMapping(from_key="tenancy", to_key="tenancy", map_func=_normalize_tenancy)
#     vm_lc   = ValueMapping(from_key="placement_tenancy", to_key="tenancy", map_func=_normalize_tenancy)

#     filters = map_filters([vm_inst], {"tenancy": "dedicated", "instance_type": "m5.large"})
#     assert any(f.key == "tenancy" and f.value == "Dedicated" for f in filters), "Instance tenancy 'dedicated' → 'Dedicated' failed"

#     filters = map_filters([vm_inst], {"tenancy": "default"})
#     assert any(f.key == "tenancy" and f.value == "Shared" for f in filters), "Instance tenancy 'default' → 'Shared' failed"

#     filters = map_filters([vm_lc], {"placement_tenancy": "dedicated"})
#     assert any(f.key == "tenancy" and f.value == "Dedicated" for f in filters), "LC placement_tenancy 'dedicated' → 'Dedicated' failed"

#     filters = map_filters([vm_lc], {"placement_tenancy": "default"})
#     assert any(f.key == "tenancy" and f.value == "Shared" for f in filters), "LC placement_tenancy 'default' → 'Shared' failed"

#     # 2) Fixture smoke check
#     with open("test.json", "r", encoding="utf-8") as f:
#         plan = json.load(f)
#     inst = next(r for r in plan["planned_values"]["root_module"]["resources"] if r["address"] == "aws_instance.example")
#     assert inst["values"]["tenancy"] == "default", "Fixture instance tenancy expected 'default'"
#     lc = next(r for r in plan["planned_values"]["root_module"]["resources"] if r["address"] == "aws_launch_configuration.lc1")
#     assert lc["values"]["placement_tenancy"] == "default", "Fixture LC placement_tenancy expected 'default'"

#     # 3) Mock pricing engine smoke check (no network):
#     # Build attributes with both Shared and Dedicated, expect a product list
#     attrs_shared = [
#         {"key": "servicecode", "value": "AmazonEC2", "operation": "=="},
#         {"key": "productFamily", "value": "Compute Instance", "operation": "=="},
#         {"key": "tenancy", "value": "Shared", "operation": "=="},
#     ]
#     attrs_dedicated = [
#         {"key": "servicecode", "value": "AmazonEC2", "operation": "=="},
#         {"key": "productFamily", "value": "Compute Instance", "operation": "=="},
#         {"key": "tenancy", "value": "Dedicated", "operation": "=="},
#     ]
#     assert len(_response_for_filters(attrs_shared)) >= 1, "Mock should return product for tenancy=Shared"
#     assert len(_response_for_filters(attrs_dedicated)) >= 1, "Mock should return product for tenancy=Dedicated"

#     print("SELF TESTS PASSED")


# if __name__ == "__main__":
#     if os.getenv("SELF_TEST", "0") == "1":
#         _run_self_tests()
#     else:
#         print("Mock pricing API on http://127.0.0.1:4000/  (set PLANCOSTS_API_URL=http://127.0.0.1:4000)")
#         print(f"MODE={MODE}  DEFAULT_PRICE={DEFAULT_PRICE}")
#         for k, v in OVERRIDE.items():
#             print(f"  {k}={v}")
#         HTTPServer(("127.0.0.1", 4000), H).serve_forever()

# mock_pricing_api.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re

# -------------------
# Config via env vars
# -------------------
MODE = os.getenv("MOCK_MODE", "normal").lower()
#   normal     -> return one product per query (default)
#   multiple   -> return 2 products (to trigger "Multiple prices found..." warning)
#   none       -> return []
#   error      -> return HTTP 500

DEFAULT_PRICE = float(os.getenv("MOCK_BASE_PRICE", "0.0416"))

OVERRIDE = {
    # EC2 Compute Instance hours
    "EC2_INSTANCE_HR": float(os.getenv("MOCK_PRICE_EC2", "0.0416")),
    # EBS gp2/standard/sc1/st1 GB-month
    "EBS_GB": float(os.getenv("MOCK_PRICE_EBS_GB", "0.10")),
    # EBS io1 IOPS-month
    "EBS_IOPS": float(os.getenv("MOCK_PRICE_EBS_IOPS", "0.0002")),
    # EBS Snapshot GB-month
    "SNAPSHOT_GB": float(os.getenv("MOCK_PRICE_SNAPSHOT_GB", "0.05")),
    # ELB classic hours
    "ELB_CLASSIC_HR": float(os.getenv("MOCK_PRICE_ELB_CLASSIC", "0.025")),
    # ALB/NLB hours
    "ELB_ALB_HR": float(os.getenv("MOCK_PRICE_ELB_ALB", "0.0225")),
    "ELB_NLB_HR": float(os.getenv("MOCK_PRICE_ELB_NLB", "0.0225")),
    # NAT Gateway hours
    "NATGW_HR": float(os.getenv("MOCK_PRICE_NATGW_HR", "0.045")),

    # ---------- RDS ----------
    "RDS_INSTANCE_HR": float(os.getenv("MOCK_PRICE_RDS_INSTANCE_HR", "0.0416")),
    "RDS_STORAGE_GB": float(os.getenv("MOCK_PRICE_RDS_STORAGE_GB", "0.10")),
    "RDS_IOPS": float(os.getenv("MOCK_PRICE_RDS_IOPS", "0.00004")),
}

def _usd(price: float) -> dict:
    s = f"{price:.6f}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return {"USD": s}

def _product(price: float) -> dict:
    return {
        "onDemandPricing": [{
            "priceDimensions": [{
                "pricePerUnit": _usd(price)
            }]
        }]
    }

# ---------- Attribute helpers (REGEX-aware) ----------

def _attrs_index(attrs):
    """
    Build an index: key -> list of dicts {op, value, raw}
    """
    idx = {}
    for a in attrs or []:
        k = a.get("key", "")
        v = a.get("value", "")
        op = a.get("operation", "==").upper()
        idx.setdefault(k, []).append({"op": op, "value": v, "raw": a})
    return idx

def _match_value(op, expected, candidate):
    if op == "REGEX":
        # Strip optional leading/trailing slashes for convenience
        pat = expected
        if isinstance(pat, str) and len(pat) >= 2 and pat[0] == "/" and pat[-1] == "/":
            pat = pat[1:-1]
        try:
            return re.search(pat, str(candidate)) is not None
        except re.error:
            return False
    # default exact match
    return str(candidate) == str(expected)

def _get_last(idx, key):
    arr = idx.get(key, [])
    return arr[-1]["value"] if arr else ""

def _has(idx, key, expected=None, op=None):
    """
    True if any attribute with this key matches expected under op (or any if expected is None)
    """
    for item in idx.get(key, []):
        if op and item["op"] != op.upper():
            continue
        if expected is None:
            return True
        if _match_value(item["op"], expected, item["value"]):
            return True
    return False

def _response_for_filters(attrs: list[dict]) -> list[dict]:
    """
    'Pricing engine':
    - respects operation REGEX for attributes
    - returns one/many/none products depending on MODE
    """
    idx = _attrs_index(attrs)

    service = _get_last(idx, "servicecode")
    family  = _get_last(idx, "productFamily")

    price = DEFAULT_PRICE

    # -------- Decision table ----------
    # EC2 compute instance hours
    if service == "AmazonEC2" and family == "Compute Instance":
        price = OVERRIDE["EC2_INSTANCE_HR"]

    # EBS storage GB-month (gp2/standard/etc.)
    elif service == "AmazonEC2" and family == "Storage":
        price = OVERRIDE["EBS_GB"]

    # EBS IOPS-month
    elif service == "AmazonEC2" and family == "System Operation" and (
        _has(idx, "usagetype", "/EBS:VolumeP-IOPS.piops/", op="REGEX")
        or _has(idx, "usagetype", "EBS:VolumeP-IOPS.piops")
    ):
        price = OVERRIDE["EBS_IOPS"]

    # EBS Snapshot GB-month (commit 149bbf8: must accept REGEX)
    elif service == "AmazonEC2" and family == "Storage Snapshot" and (
        _has(idx, "usagetype", "/EBS:SnapshotUsage/", op="REGEX")
        or _has(idx, "usagetype", "EBS:SnapshotUsage")
    ):
        price = OVERRIDE["SNAPSHOT_GB"]

    # ELB/ALB/NLB hours
    elif service == "AWSELB" and ("Load Balancer" in family):
        if family == "Load Balancer":
            price = OVERRIDE["ELB_CLASSIC_HR"]
        elif family == "Load Balancer-Application":
            price = OVERRIDE["ELB_ALB_HR"]
        elif family == "Load Balancer-Network":
            price = OVERRIDE["ELB_NLB_HR"]

    # NAT Gateway hours
    elif service == "AmazonEC2" and family == "NAT Gateway" and (
        _has(idx, "usagetype", "/NatGateway-Hours/", op="REGEX")
        or _has(idx, "usagetype", "NatGateway-Hours")
    ):
        price = OVERRIDE["NATGW_HR"]

    # ---------- RDS pricing ----------
    elif service == "AmazonRDS" and family == "Database Instance":
        price = OVERRIDE["RDS_INSTANCE_HR"]
    elif service == "AmazonRDS" and family == "Database Storage":
        price = OVERRIDE["RDS_STORAGE_GB"]
    elif service == "AmazonRDS" and family == "Provisioned IOPS":
        price = OVERRIDE["RDS_IOPS"]

    # ------- Compose the products array based on MODE -------
    if MODE == "none":
        return []
    elif MODE == "multiple":
        return [_product(price), _product(price * 10.0)]
    else:
        return [_product(price)]

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        # Optional: simulate server error
        if MODE == "error":
            self.send_error(500, "Simulated server error")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")

        try:
            queries = json.loads(body)
            if not isinstance(queries, list):
                queries = [queries]
        except Exception:
            queries = []

        resp = []
        for q in queries:
            attrs = (((q or {}).get("variables") or {}).get("filter") or {}).get("attributes", [])
            products = _response_for_filters(attrs)
            resp.append({"data": {"products": products}})

        out = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

# -------------------
# Self-tests (no pytest)
# -------------------
# --- keep the server implementation you already have from the prior step ---
# (regex-aware, tenancy self-tests, etc.)
# Just ensure _run_self_tests() includes the extra assertions below.

def _run_self_tests():
    from plancosts.base.filters import ValueMapping, map_filters

    # (1) Tenancy mapping (unchanged)
    vm_inst = ValueMapping(from_key="tenancy", to_key="tenancy", map_func=lambda v: "Dedicated" if f"{v}"=="dedicated" else "Shared")
    vm_lc   = ValueMapping(from_key="placement_tenancy", to_key="tenancy", map_func=lambda v: "Dedicated" if f"{v}"=="dedicated" else "Shared")
    assert any(f.key=="tenancy" and f.value=="Dedicated" for f in map_filters([vm_inst], {"tenancy":"dedicated"}))
    assert any(f.key=="tenancy" and f.value=="Shared"     for f in map_filters([vm_inst], {"tenancy":"default"}))
    assert any(f.key=="tenancy" and f.value=="Dedicated" for f in map_filters([vm_lc],  {"placement_tenancy":"dedicated"}))
    assert any(f.key=="tenancy" and f.value=="Shared"     for f in map_filters([vm_lc],  {"placement_tenancy":"default"}))

    # (2) Snapshot regex still works
    attrs_snapshot_regex = [
        {"key":"servicecode","value":"AmazonEC2","operation":"=="},
        {"key":"productFamily","value":"Storage Snapshot","operation":"=="},
        {"key":"usagetype","value":"/EBS:SnapshotUsage/","operation":"REGEX"},
    ]
    assert _response_for_filters(attrs_snapshot_regex), "Snapshot REGEX should return product"

    # (3) NEW: Fixture has *no* root_block_device sizes so default 8GB path is exercised
    with open("test.json", "r", encoding="utf-8") as f:
        plan = json.load(f)

    inst = next(r for r in plan["planned_values"]["root_module"]["resources"] if r["address"]=="aws_instance.example")
    lc   = next(r for r in plan["planned_values"]["root_module"]["resources"] if r["address"]=="aws_launch_configuration.lc1")

    # Instance: either missing root_block_device, or present but no size fields
    rbd_inst = inst["values"].get("root_block_device")
    assert (rbd_inst in (None, [], {}) or (isinstance(rbd_inst, list) and rbd_inst and not any(k in rbd_inst[0] for k in ("size","volume_size")))), \
        "Fixture should omit root_block_device size for instance"

    # Launch configuration: same check
    rbd_lc = lc["values"].get("root_block_device")
    assert (rbd_lc in (None, [], {}) or (isinstance(rbd_lc, list) and rbd_lc and not any(k in rbd_lc[0] for k in ("size","volume_size")))), \
        "Fixture should omit root_block_device size for launch configuration"

    print("SELF TESTS PASSED")



def _normalize_tenancy(v):
    return "Dedicated" if f"{v}" == "dedicated" else "Shared"

def _run_self_tests():
    from plancosts.base.filters import ValueMapping, map_filters

    # 1) Tenancy mapping (previous commit) still OK
    vm_inst = ValueMapping(from_key="tenancy", to_key="tenancy", map_func=_normalize_tenancy)
    vm_lc   = ValueMapping(from_key="placement_tenancy", to_key="tenancy", map_func=_normalize_tenancy)
    assert any(f.key=="tenancy" and f.value=="Dedicated" for f in map_filters([vm_inst], {"tenancy":"dedicated"}))
    assert any(f.key=="tenancy" and f.value=="Shared"     for f in map_filters([vm_inst], {"tenancy":"default"}))
    assert any(f.key=="tenancy" and f.value=="Dedicated" for f in map_filters([vm_lc],  {"placement_tenancy":"dedicated"}))
    assert any(f.key=="tenancy" and f.value=="Shared"     for f in map_filters([vm_lc],  {"placement_tenancy":"default"}))

    # 2) Fixture smoke (your test.json)
    with open("test.json", "r", encoding="utf-8") as f:
        plan = json.load(f)
    inst = next(r for r in plan["planned_values"]["root_module"]["resources"] if r["address"]=="aws_instance.example")
    lc   = next(r for r in plan["planned_values"]["root_module"]["resources"] if r["address"]=="aws_launch_configuration.lc1")
    assert inst["values"]["tenancy"] == "default"
    assert lc["values"]["placement_tenancy"] == "default"

    # 3) NEW: Snapshot filters accept REGEX (commit 149bbf8)
    attrs_snapshot_regex = [
        {"key":"servicecode","value":"AmazonEC2","operation":"=="},
        {"key":"productFamily","value":"Storage Snapshot","operation":"=="},
        {"key":"usagetype","value":"/EBS:SnapshotUsage/","operation":"REGEX"},
    ]
    prods = _response_for_filters(attrs_snapshot_regex)
    assert isinstance(prods, list) and len(prods) >= 1, "Snapshot REGEX usagetype should return a product"

    # Keep previous exact form also working
    attrs_snapshot_exact = [
        {"key":"servicecode","value":"AmazonEC2","operation":"=="},
        {"key":"productFamily","value":"Storage Snapshot","operation":"=="},
        {"key":"usagetype","value":"EBS:SnapshotUsage","operation":"=="},
    ]
    prods2 = _response_for_filters(attrs_snapshot_exact)
    assert isinstance(prods2, list) and len(prods2) >= 1, "Snapshot exact usagetype should return a product"

    print("SELF TESTS PASSED")

if __name__ == "__main__":
    if os.getenv("SELF_TEST", "0") == "1":
        _run_self_tests()
    else:
        print("Mock pricing API on http://127.0.0.1:4000/  (set PLANCOSTS_API_URL=http://127.0.0.1:4000)")
        print(f"MODE={MODE}  DEFAULT_PRICE={DEFAULT_PRICE}")
        for k, v in OVERRIDE.items():
            print(f"  {k}={v}")
        HTTPServer(("127.0.0.1", 4000), H).serve_forever()
