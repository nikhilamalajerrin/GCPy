from __future__ import annotations
import pytest
from plancosts.providers.terraform.aws.docdb_cluster_instance import DocdbClusterInstance


# ---------------- Fake Terraform ResourceData ----------------
class _FakeRD:
    def __init__(self, address: str, values: dict[str, str]):
        self.Address = address
        self._values = dict(values)

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


# ---------------- Helper utilities ----------------
def _comp_name(c) -> str:
    n = getattr(c, "name", None)
    return n() if callable(n) else (n if isinstance(n, str) else "")


def _component_by_name(components, name: str):
    for c in components:
        if _comp_name(c) == name:
            return c
    raise AssertionError(f"Cost component '{name}' not found. Got: {[_comp_name(x) for x in components]}")


def _pf(c) -> dict:
    pf = c.product_filter() if hasattr(c, "product_filter") else {}
    assert isinstance(pf, dict)
    return pf


def _purch_opt(c) -> str | None:
    pf = c.price_filter() if hasattr(c, "price_filter") else None
    if isinstance(pf, dict):
        return pf.get("purchaseOption")
    return None


# ---------------- Tests ----------------
@pytest.mark.parametrize(
    "instance_class, expect_cpu_credits",
    [
        ("db.t3.medium", True),
        ("db.r5.large", False),
    ],
)
def test_docdb_cluster_instance_components(instance_class: str, expect_cpu_credits: bool):
    rd = _FakeRD(
        "aws_docdb_cluster_instance.db",
        {"region": "us-east-1", "instance_class": instance_class},
    )
    res = DocdbClusterInstance(rd, None)
    pcs = res.price_components()

    # 1) Database instance (on-demand, <instance_class>)
    inst = _component_by_name(pcs, f"Database instance (on-demand, {instance_class})")
    pf = _pf(inst)
    assert pf["service"] == "AmazonDocDB"
    assert pf["productFamily"] == "Database Instance"
    attrs = pf.get("attributeFilters") or []
    assert any(a.get("key") == "instanceType" and a.get("value") == instance_class for a in attrs)
    assert _purch_opt(inst) == "on_demand"

    # 2) Storage
    st = _component_by_name(pcs, "Storage")
    pf = _pf(st)
    assert pf["productFamily"] == "Database Storage"
    attrs = pf.get("attributeFilters") or []
    assert any(a.get("key") == "usagetype" and a.get("value") == "StorageUsage" for a in attrs)
    assert _purch_opt(st) == "on_demand"

    # 3) I/O
    io = _component_by_name(pcs, "I/O")
    pf = _pf(io)
    assert pf["productFamily"] == "System Operation"
    attrs = pf.get("attributeFilters") or []
    assert any(a.get("key") == "usagetype" and a.get("value") == "StorageIOUsage" for a in attrs)

    # 4) Backup storage
    bk = _component_by_name(pcs, "Backup storage")
    pf = _pf(bk)
    assert pf["productFamily"] == "Storage Snapshot"
    attrs = pf.get("attributeFilters") or []
    assert any(a.get("key") == "usagetype" and a.get("value") == "BackupUsage" for a in attrs)

    # 5) CPU credits only for db.t3.*
    names = [_comp_name(c) for c in pcs]
    has_cpu = "CPU credits" in names
    assert has_cpu == expect_cpu_credits
    if expect_cpu_credits:
        cpu = _component_by_name(pcs, "CPU credits")
        pf = _pf(cpu)
        assert pf["productFamily"] == "CPU Credits"
        attrs = pf.get("attributeFilters") or []
        assert any(a.get("key") == "usagetype" and a.get("value") == "CPUCredits:db.t3" for a in attrs)


def test_docdb_cluster_instance_region_is_passed_through():
    rd = _FakeRD(
        "aws_docdb_cluster_instance.db",
        {"region": "eu-central-1", "instance_class": "db.t3.medium"},
    )
    res = DocdbClusterInstance(rd, None)
    pcs = res.price_components()
    for c in pcs:
        assert _pf(c)["region"] == "eu-central-1"
