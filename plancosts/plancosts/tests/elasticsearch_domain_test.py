from __future__ import annotations

from decimal import Decimal
import pytest

from plancosts.providers.terraform.aws.elasticsearch_domain import ElasticsearchDomain


# ----------------- minimal fake Terraform ResourceData -----------------
class _Val:
    def __init__(self, v):
        self.v = v

    # Terraform-ish helpers used by our provider code
    def String(self):
        return str(self.v)

    def Int(self):
        try:
            return int(self.v)
        except Exception:
            return 0

    def Bool(self):
        return bool(self.v)

    def Float(self):
        try:
            return float(self.v)
        except Exception:
            return 0.0

    def Exists(self):
        # Simulate tftypes presence
        return self.v is not None

    # for blocks/arrays
    def Array(self):
        arr = self.v or []
        return [ _Block(x) for x in arr ]


class _Block:
    def __init__(self, d: dict):
        self.d = d or {}

    def Get(self, k: str) -> _Val:
        return _Val(self.d.get(k))


class _FakeRD:
    """
    A light stub that supports:
      - Address
      - Get("field") returning _Val
      - RawValues (optional)
    """
    def __init__(self, address: str, values: dict):
        self._address = address
        self._values = dict(values or {})

    def Address(self):
        return self._address

    def Get(self, k: str) -> _Val:
        v = self._values.get(k)
        return _Val(v)

    def RawValues(self):
        return dict(self._values)


# ----------------- helpers -----------------
def _component_by_name(components, name: str):
    for c in components:
        if getattr(c, "name", None) == name:
            return c
    raise AssertionError(f"Cost component '{name}' not found. Got: {[getattr(x,'name', '<no-name>') for x in components]}")


# ----------------- tests -----------------

def test_elasticsearch_domain_gp2_with_master_and_ultrawarm():
    rd = _FakeRD(
        "aws_elasticsearch_domain.example",
        {
            "region": "us-east-1",
            "cluster_config": [
                {
                    "instance_type": "c4.2xlarge.elasticsearch",
                    "instance_count": 3,
                    "dedicated_master_enabled": True,
                    "dedicated_master_type": "c4.8xlarge.elasticsearch",
                    "dedicated_master_count": 1,
                    "warm_enabled": True,
                    "warm_count": 2,
                    "warm_type": "ultrawarm1.medium.elasticsearch",
                }
            ],
            "ebs_options": [
                {
                    "ebs_enabled": True,
                    "volume_size": 400,
                    "volume_type": "gp2",
                }
            ],
        },
    )

    res = ElasticsearchDomain(rd, None)
    pcs = res.price_components()

    # Instance hours: 3 instances -> hourly quantity, unit=hours
    inst = _component_by_name(pcs, "Instance (on-demand, c4.2xlarge.elasticsearch)")
    assert inst.unit == "hours"
    # Quantity() is monthly-normalized; for hourly unit we expect 3 * 730
    assert inst.quantity() == Decimal(3) * Decimal(730)

    # Storage GB-months: 400
    storage = _component_by_name(pcs, "Storage")
    assert storage.unit == "GB-months"
    assert storage.quantity() == Decimal(400)

    # Dedicated master: 1 instance
    master = _component_by_name(pcs, "Dedicated Master Instance (on-demand, c4.8xlarge.elasticsearch)")
    assert master.unit == "hours"
    assert master.quantity() == Decimal(1) * Decimal(730)

    # Ultrawarm: 2 instances
    uw = _component_by_name(pcs, "Ultrawarm Instance (on-demand, ultrawarm1.medium.elasticsearch)")
    assert uw.unit == "hours"
    assert uw.quantity() == Decimal(2) * Decimal(730)

    # Region should be carried through on all components
    for c in pcs:
        pf = c.product_filter()
        assert pf.get("region") == "us-east-1"


def test_elasticsearch_domain_io1_with_iops():
    rd = _FakeRD(
        "aws_elasticsearch_domain.example",
        {
            "region": "us-east-1",
            "cluster_config": [
                {
                    "instance_type": "c4.2xlarge.elasticsearch",
                    "instance_count": 3,
                }
            ],
            "ebs_options": [
                {
                    "ebs_enabled": True,
                    "volume_size": 1000,
                    "volume_type": "io1",
                    "iops": 10,
                }
            ],
        },
    )

    res = ElasticsearchDomain(rd, None)
    pcs = res.price_components()

    # Instance
    inst = _component_by_name(pcs, "Instance (on-demand, c4.2xlarge.elasticsearch)")
    assert inst.unit == "hours"
    assert inst.quantity() == Decimal(3) * Decimal(730)

    # Storage for io1 (PIOPS-Storage media)
    storage = _component_by_name(pcs, "Storage")
    assert storage.unit == "GB-months"
    assert storage.quantity() == Decimal(1000)
    # Storage IOPS component should exist
    iops = _component_by_name(pcs, "Storage IOPS")
    assert iops.unit == "IOPS-months"
    assert iops.quantity() == Decimal(10)

    for c in pcs:
        pf = c.product_filter()
        assert pf.get("region") == "us-east-1"


def test_elasticsearch_domain_standard_storage_only():
    rd = _FakeRD(
        "aws_elasticsearch_domain.example",
        {
            "region": "us-east-1",
            "cluster_config": [
                {
                    "instance_type": "c4.2xlarge.elasticsearch",
                    "instance_count": 3,
                }
            ],
            "ebs_options": [
                {
                    "ebs_enabled": True,
                    "volume_size": 123,
                    "volume_type": "standard",
                }
            ],
        },
    )

    res = ElasticsearchDomain(rd, None)
    pcs = res.price_components()

    inst = _component_by_name(pcs, "Instance (on-demand, c4.2xlarge.elasticsearch)")
    assert inst.unit == "hours"
    assert inst.quantity() == Decimal(3) * Decimal(730)

    storage = _component_by_name(pcs, "Storage")
    assert storage.unit == "GB-months"
    assert storage.quantity() == Decimal(123)

    # No IOPS for standard volume type
    names = [c.name for c in pcs]
    assert "Storage IOPS" not in names

    for c in pcs:
        pf = c.product_filter()
        assert pf.get("region") == "us-east-1"
