from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
import logging

from plancosts.resource.filters import Filter
from plancosts.resource.resource import PriceComponent, Resource
from .base import BaseAwsPriceComponent, BaseAwsResource


log = logging.getLogger(__name__)


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


def _get_on_demand_qty(raw: Dict[str, Any], write: bool) -> Decimal:
    """
    Pull expected request units for on-demand tables from raw values.
    Keys are optional and default to 0:
      - on_demand_write_request_units_per_hour
      - on_demand_read_request_units_per_hour
    """
    key = (
        "on_demand_write_request_units_per_hour"
        if write
        else "on_demand_read_request_units_per_hour"
    )
    return _to_decimal(raw.get(key) or 0)


# ---------------- Price components ----------------
# PROVISIONED capacity (per hour)

class DdbWriteCapacityUnit(BaseAwsPriceComponent):
    """Provisioned Write capacity unit (WCU), billed hourly."""
    def __init__(self, r: "DynamoDBTable"):
        super().__init__("Write capacity unit (WCU)", r, "hour")
        # These keys are converted into product attribute filters by the base class
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            Filter(key="productFamily", value="Provisioned IOPS"),
            Filter(key="group", value="DDB-WriteUnits"),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
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
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.SetQuantityMultiplierFunc(
            lambda res: _to_decimal(res.raw_values().get("read_capacity") or 0)
        )


class DdbReplicatedWriteCapacityUnit(BaseAwsPriceComponent):
    """Replicated write capacity unit (rWCU) for Global Tables, billed hourly."""
    def __init__(self, r: "DynamoDBGlobalTable"):
        super().__init__("Replicated write capacity unit (rWCU)", r, "hour")
        # For replicated writes on provisioned tables
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            # Product family for replicated write operation SKUs
            Filter(key="productFamily", value="DDB-Operation-ReplicatedWrite"),
            Filter(key="group", value="DDB-ReplicatedWriteUnits"),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.SetQuantityMultiplierFunc(
            # for provisioned global tables, replicated capacity is parent's write_capacity
            lambda res: _to_decimal(res.raw_values().get("write_capacity") or 0)
        )


# ---------------- Price components ----------------
# ON-DEMAND request units (per request unit)

class DdbOnDemandWriteRequestUnit(BaseAwsPriceComponent):
    """On-demand Write Request Units (WRU), billed per WRU."""
    def __init__(self, r: "DynamoDBTable"):
        super().__init__("Write request unit (WRU)", r, "request")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            Filter(key="group", value="DDB-WriteUnits"),
            Filter(key="operation", value="PayPerRequestThroughput"),
        ]
        # Price rows expose unit like "WriteRequestUnits"
        self.set_price_filter({"unit": "WriteRequestUnits"})
        self.SetQuantityMultiplierFunc(
            lambda res: _get_on_demand_qty(res.raw_values(), write=True)
        )


class DdbOnDemandReadRequestUnit(BaseAwsPriceComponent):
    """On-demand Read Request Units (RRU), billed per RRU."""
    def __init__(self, r: "DynamoDBTable"):
        super().__init__("Read request unit (RRU)", r, "request")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            Filter(key="group", value="DDB-ReadUnits"),
            Filter(key="operation", value="PayPerRequestThroughput"),
        ]
        self.set_price_filter({"unit": "ReadRequestUnits"})
        self.SetQuantityMultiplierFunc(
            lambda res: _get_on_demand_qty(res.raw_values(), write=False)
        )


class DdbReplicatedWriteRequestUnit(BaseAwsPriceComponent):
    """
    On-demand replicated write request units for Global Tables (rWRU).
    Mirrors parent's on-demand write request units into replica regions.
    """
    def __init__(self, r: "DynamoDBGlobalTable"):
        super().__init__("Replicated write request unit (rWRU)", r, "request")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonDynamoDB"),
            Filter(key="group", value="DDB-ReplicatedWriteUnits"),
            Filter(key="operation", value="ReplicatedWrite"),
        ]
        self.set_price_filter({"unit": "WriteRequestUnits"})
        self.SetQuantityMultiplierFunc(
            lambda res: _to_decimal(res.raw_values().get("write_request_units_per_hour") or 0)
        )


# ---------------- Resources ----------------

class DynamoDBGlobalTable(BaseAwsResource):
    """
    Replica region sub-resource.
    - PROVISIONED: rWCU per hour (quantity = parent's write_capacity).
    - PAY_PER_REQUEST: rWRU per request (quantity = parent's expected write request units).
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)

        pcs: List[PriceComponent] = []
        mode = (raw_values or {}).get("billing_mode")
        is_provisioned = str(mode or "").upper() == "PROVISIONED"

        if is_provisioned:
            pcs.append(DdbReplicatedWriteCapacityUnit(self))
        else:
            # On-demand global table replicated writes are per request unit
            pcs.append(DdbReplicatedWriteRequestUnit(self))

        self._set_price_components(pcs)


class DynamoDBTable(BaseAwsResource):
    """
    aws_dynamodb_table:
      - PROVISIONED → WCU + RCU in the table region.
      - PAY_PER_REQUEST (on-demand) → WRU + RRU (quantities must be provided via raw values).
      - Global replicas → sub-resources per replica region:
          * PROVISIONED → rWCU
          * PAY_PER_REQUEST → rWRU
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)

        pcs: List[PriceComponent] = []
        billing_mode = (raw_values or {}).get("billing_mode")
        is_provisioned = str(billing_mode or "").upper() == "PROVISIONED"

        if is_provisioned:
            pcs.append(DdbWriteCapacityUnit(self))
            pcs.append(DdbReadCapacityUnit(self))
        else:
            # On-demand table: price by request units; quantities default to 0 if not supplied
            pcs.append(DdbOnDemandWriteRequestUnit(self))
            pcs.append(DdbOnDemandReadRequestUnit(self))

        self._set_price_components(pcs)

        # ----- Global table replicas -----
        replicas = (raw_values or {}).get("replica")
        if isinstance(replicas, list) and replicas:
            subs: List[Resource] = []
            parent_wcu = raw_values.get("write_capacity")
            parent_wru = _get_on_demand_qty(raw_values, write=True)

            for rep in replicas:
                if not isinstance(rep, dict):
                    continue
                rep_region = rep.get("region_name")
                if not rep_region:
                    continue

                # Seed replica raw values
                rep_raw = dict(rep)  # start with replica block

                # carry over billing mode explicitly
                rep_raw["billing_mode"] = billing_mode

                if is_provisioned and parent_wcu is not None:
                    # for provisioned, replicated capacity uses parent's write_capacity
                    rep_raw["write_capacity"] = parent_wcu
                elif not is_provisioned and parent_wru is not None:
                    # for on-demand, replicate parent's expected WRUs to price rWRU
                    rep_raw["write_request_units_per_hour"] = parent_wru

                rep_addr = f"{address}.global_table.{rep_region}"
                subs.append(DynamoDBGlobalTable(rep_addr, rep_region, rep_raw))

            if subs:
                self._set_sub_resources(subs)
