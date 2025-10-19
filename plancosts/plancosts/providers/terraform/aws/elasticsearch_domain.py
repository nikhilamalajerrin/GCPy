# plancosts/providers/terraform/aws/elasticsearch_domain.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from .base import BaseAwsResource, BaseAwsPriceComponent, DEFAULT_VOLUME_SIZE


class _AttrMethod:
    """
    Per-instance shim so `pc.name` works as a string for tests AND `pc.name()` still works.
    Same for `pc.unit`.
    """
    def __init__(self, getter):
        self._getter = getter

    def __call__(self):
        return self._getter()

    def __str__(self):
        return str(self._getter())

    def __repr__(self):
        return repr(self._getter())

    def __eq__(self, other):
        return self._getter() == other


class ElasticsearchDomain(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/elasticsearch_domain.go

    Builds price components for:
      - Instance (on-demand, <instance_type>) x instance_count
      - Storage (GB-months) for EBS volume
      - Storage IOPS (IOPS-months) when volume_type == io1 (PIOPS)
      - Dedicated Master Instance (if enabled)
      - Ultrawarm Instance (if enabled)
    """

    SERVICE = "AmazonES"

    def __init__(self, d: "ResourceData", u: Optional["ResourceData"] = None) -> None:
        # Address
        address = getattr(d, "Address", None) or getattr(d, "address", None)
        if callable(address):
            address = address()
        elif not isinstance(address, str):
            address = getattr(d, "address", "<resource>")

        # Region
        region = ""
        get = getattr(d, "Get", None)
        if callable(get):
            region_val = get("region")
            region = getattr(region_val, "String", lambda: "")()
        elif hasattr(d, "region"):
            region = getattr(d, "region") or ""

        # Raw values (best-effort)
        raw_values: Dict[str, Any] = {}
        raw_get = getattr(d, "RawValues", None)
        if callable(raw_get):
            try:
                rv = raw_get()
                if isinstance(rv, dict):
                    raw_values = rv
            except Exception:
                pass

        super().__init__(address=address, region=region, raw_values=raw_values)
        self.d = d  # keep for field access in price_components

    # ---------- helpers ----------
    def _pc(
        self,
        *,
        name: str,
        unit: str,
        product_family: str,
        attr_filters: Optional[Dict[str, str]] = None,
        purchase_option: Optional[str] = None,
        hourly_qty: Optional[Decimal] = None,
        monthly_qty: Optional[Decimal] = None,
    ) -> BaseAwsPriceComponent:
        """
        Build a price component with AWS/region/service prefilled to match the Go filters.
        """
        # Build the list of {"key": ..., "value"/"valueRegex": ...}
        attribute_filters: List[Dict[str, str]] = []
        for k, v in (attr_filters or {}).items():
            if isinstance(v, str) and len(v) >= 2 and v.startswith("/") and v.endswith("/"):
                attribute_filters.append({"key": k, "valueRegex": v})
            else:
                attribute_filters.append({"key": k, "value": v})

        product_filter: Dict[str, Any] = {
            "vendorName": "aws",
            "region": self.Region() or None,  # ensure it's a string, not a bound method
            "service": self.SERVICE,
            "productFamily": product_family,
            "attributeFilters": attribute_filters,
        }

        price_filter: Optional[Dict[str, Any]] = None
        if purchase_option:
            price_filter = {"purchaseOption": purchase_option}

        pc = BaseAwsPriceComponent(
            name=name,
            resource=self,
            time_unit=("hours" if unit == "hours" else "month"),
        )
        # Unit shown in tables:
        pc.unit_ = unit

        # Quantity: hourly OR monthly depending on passed value
        if hourly_qty is not None:
            pc.SetQuantityMultiplierFunc(lambda _r, _v=hourly_qty: _v)
            pc.time_unit_ = "hour"
        elif monthly_qty is not None:
            pc.SetQuantityMultiplierFunc(lambda _r, _v=monthly_qty: _v)
            pc.time_unit_ = "month"

        # Wire filters
        pc.set_product_filter_override(product_filter)
        if price_filter:
            pc.set_price_filter(price_filter)

        # ---- Compatibility shims so tests see attributes, and old code can still call methods ----
        try:
            setattr(pc, "name", _AttrMethod(pc.Name))
            setattr(pc, "unit", _AttrMethod(pc.Unit))
        except Exception:
            pass

        return pc

    # ---------- main ----------
    def price_components(self) -> List[BaseAwsPriceComponent]:
        pcs: List[BaseAwsPriceComponent] = []

        # Access Terraform fields safely
        get = getattr(self.d, "Get", None)

        def _get_first_block(field: str):
            if not callable(get):
                return None
            v = get(field)
            try:
                arr = v.Array()
                return arr[0] if arr else None
            except Exception:
                return None

        cluster_cfg = _get_first_block("cluster_config")
        ebs_opts = _get_first_block("ebs_options")

        # Defaults if blocks missing
        instance_type = ""
        instance_count = Decimal(1)
        dedicated_master_enabled = False
        dedicated_master_type = ""
        dedicated_master_count = Decimal(0)
        ultrawarm_enabled = False
        ultrawarm_type = ""
        ultrawarm_count = Decimal(0)

        # cluster_config fields
        if cluster_cfg is not None:
            try:
                instance_type = cluster_cfg.Get("instance_type").String()
            except Exception:
                pass
            try:
                instance_count = Decimal(cluster_cfg.Get("instance_count").Int() or 1)
            except Exception:
                instance_count = Decimal(1)
            try:
                dedicated_master_enabled = bool(cluster_cfg.Get("dedicated_master_enabled").Bool())
            except Exception:
                dedicated_master_enabled = False
            try:
                dedicated_master_type = cluster_cfg.Get("dedicated_master_type").String()
            except Exception:
                pass
            try:
                dedicated_master_count = Decimal(cluster_cfg.Get("dedicated_master_count").Int() or 0)
            except Exception:
                dedicated_master_count = Decimal(0)
            try:
                ultrawarm_enabled = bool(cluster_cfg.Get("warm_enabled").Bool())
            except Exception:
                ultrawarm_enabled = False
            try:
                ultrawarm_type = cluster_cfg.Get("warm_type").String()
            except Exception:
                pass
            try:
                ultrawarm_count = Decimal(cluster_cfg.Get("warm_count").Int() or 0)
            except Exception:
                ultrawarm_count = Decimal(0)

        # EBS options
        ebs_type_map = {
            "gp2": "GP2",
            "io1": "PIOPS-Storage",
            "standard": "Magnetic",
        }

        gb_val = Decimal(DEFAULT_VOLUME_SIZE)
        ebs_type = "gp2"
        iops_val = Decimal(1)

        if ebs_opts is not None:
            try:
                if ebs_opts.Get("volume_size").Exists():
                    gb_val = Decimal(str(ebs_opts.Get("volume_size").Float()))
            except Exception:
                pass
            try:
                if ebs_opts.Get("volume_type").Exists():
                    ebs_type = ebs_opts.Get("volume_type").String() or "gp2"
            except Exception:
                pass
            try:
                if ebs_opts.Get("iops").Exists():
                    iops_val = Decimal(str(ebs_opts.Get("iops").Float()))
                    if iops_val < 1:
                        iops_val = Decimal(1)
            except Exception:
                pass

        ebs_filter = ebs_type_map.get(ebs_type, "gp2")

        # ---------------- Components ----------------

        # 1) Instance
        if instance_type:
            pcs.append(
                self._pc(
                    name=f"Instance (on-demand, {instance_type})",
                    unit="hours",
                    product_family="Elastic Search Instance",
                    attr_filters={
                        "usagetype": "/ESInstance/",   # regex
                        "instanceType": instance_type,
                    },
                    purchase_option="on_demand",
                    hourly_qty=instance_count,
                )
            )

        # 2) Storage
        pcs.append(
            self._pc(
                name="Storage",
                unit="GB-months",
                product_family="Elastic Search Volume",
                attr_filters={
                    "usagetype": "/ES.+-Storage/",   # regex
                    "storageMedia": ebs_filter,
                },
                purchase_option="on_demand",
                monthly_qty=gb_val,
            )
        )

        # 3) Storage IOPS (if io1)
        if ebs_type == "io1":
            pcs.append(
                self._pc(
                    name="Storage IOPS",
                    unit="IOPS-months",
                    product_family="Elastic Search Volume",
                    attr_filters={
                        "usagetype": "/ES:PIOPS/",   # regex
                        "storageMedia": "PIOPS",
                    },
                    purchase_option="on_demand",
                    monthly_qty=iops_val,
                )
            )

        # 4) Dedicated master instances
        if dedicated_master_enabled and dedicated_master_type and dedicated_master_count > 0:
            pcs.append(
                self._pc(
                    name=f"Dedicated Master Instance (on-demand, {dedicated_master_type})",
                    unit="hours",
                    product_family="Elastic Search Instance",
                    attr_filters={
                        "usagetype": "/ESInstance/",  # regex
                        "instanceType": dedicated_master_type,
                    },
                    purchase_option="on_demand",
                    hourly_qty=dedicated_master_count,
                )
            )

        # 5) Ultrawarm
        if ultrawarm_enabled and ultrawarm_type and ultrawarm_count > 0:
            pcs.append(
                self._pc(
                    name=f"Ultrawarm Instance (on-demand, {ultrawarm_type})",
                    unit="hours",
                    product_family="Elastic Search Instance",
                    attr_filters={
                        "usagetype": "/ESInstance/",  # regex
                        "instanceType": ultrawarm_type,
                    },
                    purchase_option="on_demand",
                    hourly_qty=ultrawarm_count,
                )
            )

        self._set_price_components(pcs)
        return pcs

    # schema.Resource compatibility
    @property
    def name(self) -> str:
        return self.Address()
