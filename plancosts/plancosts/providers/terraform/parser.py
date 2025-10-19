# plancosts/providers/terraform/parser.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Iterable, Iterator

from .cmd import load_plan_json as _load_plan_json
from .address import strip_address_array
from plancosts.schema.resource_data import ResourceData

__all__ = ["parse_plan_json", "parse_plan_file"]

_INFRACOST_PROVIDER_NAMES = ("infracost", "infracost.io/infracost/infracost")


# ---------------- Optional centralized registry ----------------
_AWS_REGISTRY: Optional[Dict[str, Any]] = None
try:
    # Support multiple shapes of registry modules:
    # - dict at ResourceRegistry / REGISTRY / mapping
    # - callable ResourceRegistry() returning a dict
    from .aws import resource_registry as _rr  # type: ignore

    if isinstance(getattr(_rr, "ResourceRegistry", None), dict):
        _AWS_REGISTRY = getattr(_rr, "ResourceRegistry")  # a dict mapping
    elif callable(getattr(_rr, "ResourceRegistry", None)):
        _AWS_REGISTRY = _rr.ResourceRegistry()  # a factory returning a dict
    elif isinstance(getattr(_rr, "REGISTRY", None), dict):
        _AWS_REGISTRY = getattr(_rr, "REGISTRY")
    elif isinstance(getattr(_rr, "mapping", None), dict):
        _AWS_REGISTRY = getattr(_rr, "mapping")
except Exception:
    _AWS_REGISTRY = None


# ---------------- Tiny wrappers to normalize callable/dict fields ----------------
class _CallableDict:
    """
    Wrap a dict so it is ALSO callable (returns the dict).
    Exposes common dict methods used by the codebase.
    """
    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self._d: Dict[str, Any] = dict(data or {})

    def __call__(self) -> Dict[str, Any]:
        return self._d

    # Minimal dict surface
    def get(self, *a, **k): return self._d.get(*a, **k)
    def __getitem__(self, k): return self._d[k]
    def __contains__(self, k): return k in self._d
    def keys(self) -> Iterable[str]: return self._d.keys()
    def items(self) -> Iterable[tuple[str, Any]]: return self._d.items()
    def values(self) -> Iterable[Any]: return self._d.values()
    def __iter__(self) -> Iterator[str]: return iter(self._d)
    def __len__(self) -> int: return len(self._d)
    def __repr__(self) -> str: return f"_CallableDict({self._d!r})"


class _CallableFuncProxy:
    """
    Wrap a callable that returns a dict so it ALSO behaves like a dict:
    rd.raw_values.get(...) will call the function and then .get on the returned dict.
    """
    def __init__(self, fn):
        self._fn = fn

    def __call__(self):
        return self._fn()

    def _as_dict(self) -> Dict[str, Any]:
        try:
            d = self._fn()
        except Exception:
            d = {}
        return d or {}

    # Dict-like facade
    def get(self, *a, **k): return self._as_dict().get(*a, **k)
    def __getitem__(self, k): return self._as_dict()[k]
    def __contains__(self, k): return k in self._as_dict()
    def keys(self): return self._as_dict().keys()
    def items(self): return self._as_dict().items()
    def values(self): return self._as_dict().values()
    def __iter__(self): return iter(self._as_dict())
    def __len__(self): return len(self._as_dict())
    def __repr__(self): return f"_CallableFuncProxy({self._fn!r})"


# ---------------- Region helpers ----------------
def _provider_region(plan_obj: Dict[str, Any]) -> str:
    return (
        plan_obj.get("configuration", {})
        .get("provider_config", {})
        .get("aws", {})
        .get("expressions", {})
        .get("region", {})
        .get("constant_value", "")
    ) or "us-east-1"


# ---------------- Address helpers ----------------
def _address_resource_part(address: str) -> str:
    """
    Mirrors Go:
      - if the 3rd part from the end is 'data', use the last 3 parts
      - else use the last 2 parts
    """
    parts = address.split(".")
    if len(parts) >= 3 and parts[-3] == "data":
        resource_parts = parts[-3:]
    else:
        resource_parts = parts[-2:]
    return ".".join(resource_parts)


def _address_module_part(address: str) -> str:
    """
    Mirrors Go:
      - if the 3rd part from the end is 'data', trim 3 parts
      - else trim 2 parts
    (We return WITHOUT a trailing dot; we add it when composing.)
    """
    parts = address.split(".")
    if len(parts) >= 3 and parts[-3] == "data":
        module_parts = parts[:-3]
    else:
        module_parts = parts[:-2]
    return ".".join(module_parts)


def _address_module_names(address: str) -> List[str]:
    m = re.findall(r"module\.([^\[]*)", _address_module_part(address))
    return m or []


# ---------------- Config JSON helpers ----------------
def _get_configuration_json_for_module_path(configurationJSON: Dict[str, Any], module_names: List[str]) -> Dict[str, Any]:
    node: Dict[str, Any] = configurationJSON
    for name in module_names:
        node = (node.get("module_calls") or {}).get(name, {}).get("module", {}) or {}
    return node


def _get_configuration_json_for_resource_address(configurationJSON: Dict[str, Any], address: str) -> Dict[str, Any]:
    module_names = _address_module_names(address)
    module_cfg = _get_configuration_json_for_module_path(configurationJSON, module_names)
    want = strip_address_array(_address_resource_part(address))
    for rj in module_cfg.get("resources") or []:
        a = rj.get("address", "")
        if a == want or strip_address_array(a) == want:
            return rj
    return {}


# ---------------- Plan parsing ----------------
def _add_raw_value(raw_values: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
    out = dict(raw_values or {})
    out[key] = value
    return out


def _parse_resource_data(plan: Dict[str, Any]) -> Dict[str, ResourceData]:
    provider_config = plan.get("configuration", {}).get("provider_config", {}) or {}
    planned_root = plan.get("planned_values", {}).get("root_module", {}) or {}
    default_region = (
        provider_config.get("aws", {}).get("expressions", {}).get("region", {}).get("constant_value", "")
        or "us-east-1"
    )

    resource_data_map: Dict[str, ResourceData] = {}

    def _wrap_callable_or_dict(val):
        # Turn either a dict or a function-returns-dict into a callable+dict object
        if callable(val):
            return _CallableFuncProxy(val)
        return _CallableDict(val if isinstance(val, dict) else {})

    def _walk_module(planned_values_module: Dict[str, Any]) -> None:
        for tr in planned_values_module.get("resources") or []:
            address = tr.get("address", "")
            rtype = tr.get("type", "")
            provider_name = tr.get("provider_name", "")
            raw = tr.get("values") or {}

            # Region from ARN overrides provider region
            region = default_region
            arn = raw.get("arn")
            if isinstance(arn, str) and arn:
                parts = arn.split(":")
                if len(parts) > 3 and parts[3]:
                    region = parts[3]

            raw = _add_raw_value(raw, "region", region)

            # Create ResourceData (3-arg or 4-arg)
            try:
                rd = ResourceData.NewResourceData(rtype, provider_name, address, raw)
            except TypeError:
                rd = ResourceData.NewResourceData(rtype, address, raw)

            # ---- Normalization: make raw_values/usage_values safe everywhere ----
            try:
                rv = getattr(rd, "raw_values", None)
                if rv is not None:
                    setattr(rd, "raw_values", _wrap_callable_or_dict(rv))
            except Exception:
                pass
            try:
                uv = getattr(rd, "usage_values", None)
                if uv is not None:
                    setattr(rd, "usage_values", _wrap_callable_or_dict(uv))
            except Exception:
                pass
            # --------------------------------------------------------------------

            resource_data_map[address] = rd

        for child in planned_values_module.get("child_modules") or []:
            _walk_module(child)

    _walk_module(planned_root)
    return resource_data_map


# ---------------- Reference wiring ----------------
def _get_reference_addresses(attribute: str, attributeJSON: Any, ref_map: Dict[str, List[str]]) -> None:
    if isinstance(attributeJSON, dict) and isinstance(attributeJSON.get("references"), list):
        for ref in attributeJSON["references"]:
            ref_map.setdefault(attribute, []).append(ref)
        return
    if isinstance(attributeJSON, list):
        for i, item in enumerate(attributeJSON):
            _get_reference_addresses(f"{attribute}.{i}", item, ref_map)
        return
    if isinstance(attributeJSON, dict):
        for k, v in attributeJSON.items():
            _get_reference_addresses(f"{attribute}.{k}", v, ref_map)


def _parse_references(resource_data_map: Dict[str, ResourceData], configurationJSON: Dict[str, Any]) -> None:
    for address, rd in resource_data_map.items():
        res_cfg = _get_configuration_json_for_resource_address(configurationJSON, address)
        expressions = res_cfg.get("expressions") or {}

        # Expose config expressions to providers that need constants (e.g., ASG overrides)
        try:
            setattr(rd, "_config_expressions", expressions)
        except Exception:
            pass

        ref_map: Dict[str, List[str]] = {}
        for attr, attrJSON in expressions.items():
            _get_reference_addresses(attr, attrJSON, ref_map)

        module_part = _address_module_part(address)
        for attr, refs in ref_map.items():
            for ref_addr in refs:
                # Go: fullRefAddress := fmt.Sprintf("%s%s", addressModulePart(address), refAddress)
                # Our module_part has no trailing dot; add one if non-empty.
                full_ref = f"{module_part}.{ref_addr}" if module_part else ref_addr
                target = resource_data_map.get(full_ref)
                if target is not None:
                    rd.AddReference(attr, target)


# ---------------- Usage resources ----------------
def _is_infracost_resource(rd: ResourceData) -> bool:
    prov = getattr(rd, "ProviderName", "") or getattr(rd, "provider_name", "")
    return prov in _INFRACOST_PROVIDER_NAMES


def _build_usage_resource_data_map(resource_data_map: Dict[str, ResourceData]) -> Dict[str, ResourceData]:
    usage_map: Dict[str, ResourceData] = {}
    for rd in resource_data_map.values():
        if _is_infracost_resource(rd):
            for ref in rd.References("resources") or []:
                usage_map[ref.Address] = rd
    return usage_map


def _strip_infracost_resources(resource_data_map: Dict[str, ResourceData]) -> Dict[str, ResourceData]:
    return {addr: rd for addr, rd in resource_data_map.items() if not _is_infracost_resource(rd)}


# ---------------- Constructors & factory ----------------
def _build_fallback_constructors() -> Dict[str, Any]:
    from .aws.instance import AwsInstance  # type: ignore
    from .aws.nat_gateway import NatGateway  # type: ignore

    m: Dict[str, Any] = {
        "aws_instance": AwsInstance,
        "aws_nat_gateway": NatGateway,
    }

    try:
        from .aws.elb import Elb  # type: ignore
        m["aws_elb"] = Elb
    except Exception:
        pass

    try:
        from .aws.lambda_function import LambdaFunction  # type: ignore
        m["aws_lambda_function"] = LambdaFunction
    except Exception:
        pass

    try:
        from .aws.dynamodb_table import DynamoDbTable  # type: ignore
        m["aws_dynamodb_table"] = DynamoDbTable
    except Exception:
        pass

    try:
        from .aws.rds_instance import RdsInstance  # type: ignore
        m["aws_db_instance"] = RdsInstance
    except Exception:
        pass

    try:
        from .aws.rds_cluster_instance import RdsClusterInstance  # type: ignore
        m["aws_rds_cluster_instance"] = RdsClusterInstance
    except Exception:
        pass

    try:
        from .aws.ecs_service import AwsEcsService as _EcsCtor  # type: ignore
    except Exception:
        try:
            from .aws.ecs_service import EcsService as _EcsCtor  # type: ignore
        except Exception:
            _EcsCtor = None  # type: ignore
    if _EcsCtor:
        m["aws_ecs_service"] = _EcsCtor
    return m


_RESOURCE_CONSTRUCTORS: Dict[str, Any] = _AWS_REGISTRY or _build_fallback_constructors()


def _create_resource_from_rd(
    rd: ResourceData,
    provider_region: str,
    usage_map: Optional[Dict[str, ResourceData]] = None,
):
    """
    Instantiate a typed resource (try Python signatures first so we always pass a safe dict):
      1) ctor(address, region, raw, rd)
      2) ctor(address, region, raw)
      3) ctor(resourceData, usageResourceData)
    """
    rtype = rd.Type
    address = rd.Address

    # raw_values is normalized to callable+dict in _parse_resource_data
    raw_obj = getattr(rd, "raw_values", _CallableDict({}))
    raw = raw_obj() if callable(raw_obj) else dict(raw_obj or {})

    # Detect region from raw/arn
    region = (raw.get("region") or provider_region)
    arn = raw.get("arn")
    if isinstance(arn, str) and arn:
        parts = arn.split(":")
        if len(parts) > 3 and parts[3]:
            region = parts[3]

    ctor = _RESOURCE_CONSTRUCTORS.get(rtype)
    if not ctor:
        return None

    try:
        return ctor(address, region, raw, rd)  # type: ignore[misc,call-arg]
    except TypeError:
        pass
    try:
        return ctor(address, region, raw)  # type: ignore[misc,call-arg]
    except TypeError:
        pass

    usage_rd = (usage_map or {}).get(address)
    return ctor(rd, usage_rd)  # type: ignore[misc,call-arg]


# ---------------- Top-level parse ----------------
def parse_plan_json(plan_json: bytes | str | Dict[str, Any]) -> List[Any]:
    if isinstance(plan_json, (bytes, bytearray)):
        plan = json.loads(plan_json.decode("utf-8"))
    elif isinstance(plan_json, str):
        plan = json.loads(plan_json)
    elif isinstance(plan_json, dict):
        plan = plan_json
    else:
        raise TypeError(f"parse_plan_json expected bytes|str|dict, got {type(plan_json).__name__}")

    provider_region = _provider_region(plan)

    rd_map = _parse_resource_data(plan)

    configurationJSON = plan.get("configuration", {}).get("root_module", {}) or {}
    _parse_references(rd_map, configurationJSON)

    usage_map = _build_usage_resource_data_map(rd_map)
    rd_map = _strip_infracost_resources(rd_map)

    out: List[Any] = []
    for rd in rd_map.values():
        r = _create_resource_from_rd(rd, provider_region, usage_map)
        if r is not None:
            out.append(r)

    try:
        out.sort(key=lambda r: r.address())
    except Exception:
        pass
    return out


def parse_plan_file(path: str) -> List[Any]:
    return parse_plan_json(_load_plan_json(path))
