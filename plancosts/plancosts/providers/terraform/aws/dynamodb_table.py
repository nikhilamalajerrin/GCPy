from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
import logging

from plancosts.resource.filters import Filter
from plancosts.resource.resource import PriceComponent, Resource
from .base import BaseAwsPriceComponent, BaseAwsResource


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


# ---------------- Price components ----------------

class DdbWriteCapacityUnit(BaseAwsPriceComponent):
    """Provisioned Write capacity unit (WCU), billed hourly."""
    def __init__(self, r: "DynamoDBTable"):
        super().__init__("Write capacity unit (WCU)", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            Filter(key="productFamily", value="Provisioned IOPS"),
            Filter(key="group", value="DDB-WriteUnits"),
        ]
        self.set_price_filter({
            "purchaseOption": "on_demand",
        })
        self.SetQuantityMultiplierFunc(
            lambda res: _to_decimal(res.raw_values().get("write_capacity") or 0)
        )


class DdbReadCapacityUnit(BaseAwsPriceComponent):
    """Provisioned Read capacity unit (RCU), billed hourly."""
    def __init__(self, r: "DynamoDBTable"):
        super().__init__("Read capacity unit (RCU)", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            Filter(key="productFamily", value="Provisioned IOPS"),
            Filter(key="group", value="DDB-ReadUnits"),
        ]
        self.set_price_filter({
            "purchaseOption": "on_demand",
        })
        self.SetQuantityMultiplierFunc(
            lambda res: _to_decimal(res.raw_values().get("read_capacity") or 0)
        )


class DdbReplicatedWriteCapacityUnit(BaseAwsPriceComponent):
    """Replicated write capacity unit (rWCU) for Global Tables, billed hourly."""
    def __init__(self, r: "DynamoDBGlobalTable"):
        super().__init__("Replicated write capacity unit (rWCU)", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            Filter(key="productFamily", value="DDB-Operation-ReplicatedWrite"),
            Filter(key="group", value="DDB-ReplicatedWriteUnits"),
        ]
        self.set_price_filter({
            "purchaseOption": "on_demand",
        })
        self.SetQuantityMultiplierFunc(
            lambda res: _to_decimal(res.raw_values().get("write_capacity") or 0)
        )


# ---------------- Resources ----------------

class DynamoDBGlobalTable(BaseAwsResource):
    """Replica region for a Global Table (exposes rWCU only)."""
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([DdbReplicatedWriteCapacityUnit(self)])


class DynamoDBTable(BaseAwsResource):
    """
    aws_dynamodb_table:
      - PROVISIONED → WCU + RCU in the table region.
      - PAY_PER_REQUEST/on-demand → not supported (warn only).
      - Global replicas → sub-resources per replica region (rWCU).
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)

        pcs: List[PriceComponent] = []
        billing_mode = (raw_values or {}).get("billing_mode")

        if str(billing_mode or "").upper() != "PROVISIONED":
            logging.getLogger(__name__).warning(
                "No support for on-demand DynamoDB for %s", address
            )
        else:
            pcs.append(DdbWriteCapacityUnit(self))
            pcs.append(DdbReadCapacityUnit(self))

        self._set_price_components(pcs)

        # Global table replicas → add sub-resources with rWCU
        replicas = (raw_values or {}).get("replica")
        if isinstance(replicas, list) and replicas:
            subs: List[Resource] = []
            parent_wcu = raw_values.get("write_capacity")
            for rep in replicas:
                if not isinstance(rep, dict):
                    continue
                rep_region = rep.get("region_name")
                if not rep_region:
                    continue
                rep_raw = dict(rep)
                if parent_wcu is not None:
                    rep_raw["write_capacity"] = parent_wcu
                rep_addr = f"{address}.global_table.{rep_region}"
                subs.append(DynamoDBGlobalTable(rep_addr, rep_region, rep_raw))
            if subs:
                self._set_sub_resources(subs)