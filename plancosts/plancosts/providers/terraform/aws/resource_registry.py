# plancosts/providers/terraform/aws/resource_registry.py
from __future__ import annotations

from typing import Any, Dict
from plancosts.schema.registry_item import RegistryItem

# -------- aws_lb / aws_alb --------
try:
    from .lb import Lb as _AwsLbCtor
except Exception:
    try:
        from .aws_lb import Lb as _AwsLbCtor
    except Exception:
        _AwsLbCtor = None

# -------- aws_autoscaling_group --------
try:
    from .autoscaling_group import NewAutoscalingGroup as _AwsAsgCtor
except Exception:
    try:
        from .autoscaling_group import AwsAutoscalingGroup as _AwsAsgCtor
    except Exception:
        _AwsAsgCtor = None

# -------- aws_db_instance --------
try:
    from .db_instance import DbInstance as _AwsDbInstanceCtor
except Exception:
    try:
        from .aws_db_instance import DbInstance as _AwsDbInstanceCtor
    except Exception:
        _AwsDbInstanceCtor = None

# -------- aws_docdb_cluster_instance --------
try:
    from .docdb_cluster_instance import DocdbClusterInstance as _DocdbClusterInstanceCtor
except Exception:
    _DocdbClusterInstanceCtor = None

# -------- aws_dynamodb_table --------
try:
    from .dynamodb_table import DynamoDbTable as _AwsDynamoTableCtor
except Exception:
    _AwsDynamoTableCtor = None

# -------- aws_ebs_snapshot --------
try:
    from .ebs_snapshot import EbsSnapshot as _AwsEbsSnapshotCtor
except Exception:
    _AwsEbsSnapshotCtor = None

# -------- aws_ebs_snapshot_copy --------
try:
    from .ebs_snapshot_copy import EbsSnapshotCopy as _AwsEbsSnapshotCopyCtor
except Exception:
    _AwsEbsSnapshotCopyCtor = None

# -------- aws_ebs_volume --------
try:
    from .ebs_volume import EbsVolume as _AwsEbsVolumeCtor
except Exception:
    _AwsEbsVolumeCtor = None

# -------- aws_ecs_service --------
try:
    from .ecs_service import AwsEcsService as _AwsEcsServiceCtor
except Exception:
    try:
        from .ecs_service import EcsService as _AwsEcsServiceCtor
    except Exception:
        _AwsEcsServiceCtor = None

# -------- aws_elb --------
try:
    from .elb import Elb as _AwsElbCtor
except Exception:
    _AwsElbCtor = None

# -------- aws_elasticsearch_domain --------
try:
    from .elasticsearch_domain import ElasticsearchDomain as _AwsEsDomainCtor
except Exception:
    _AwsEsDomainCtor = None

# -------- aws_instance --------
try:
    from .instance import AwsInstance as _AwsInstanceCtor
except Exception:
    try:
        from .instance import Instance as _AwsInstanceCtor
    except Exception:
        _AwsInstanceCtor = None

# -------- aws_lambda_function --------
try:
    from .lambda_function import LambdaFunction as _AwsLambdaFunctionCtor
except Exception:
    _AwsLambdaFunctionCtor = None

# -------- aws_nat_gateway --------
try:
    from .nat_gateway import NatGateway as _AwsNatGatewayCtor
except Exception:
    _AwsNatGatewayCtor = None

# -------- aws_rds_cluster_instance --------
try:
    from .rds_cluster_instance import RdsClusterInstance as _AwsRdsClusterInstanceCtor
except Exception:
    _AwsRdsClusterInstanceCtor = None


# ---------------- Registry Items ----------------
def _make(name: str, ctor: Any, *, aliases=None, notes=None) -> RegistryItem:
    if ctor is None:
        return None
    return RegistryItem(name=name, rfunc=ctor, aliases=aliases or [], notes=notes or [])


ResourceRegistry: Dict[str, RegistryItem] = {}

for item in [
    _make("aws_autoscaling_group", _AwsAsgCtor),
    _make("aws_db_instance", _AwsDbInstanceCtor),
    _make("aws_docdb_cluster_instance", _DocdbClusterInstanceCtor),
    _make("aws_dynamodb_table", _AwsDynamoTableCtor),
    _make("aws_ebs_snapshot_copy", _AwsEbsSnapshotCopyCtor),
    _make("aws_ebs_snapshot", _AwsEbsSnapshotCtor),
    _make("aws_ebs_volume", _AwsEbsVolumeCtor),
    _make("aws_ecs_service", _AwsEcsServiceCtor),
    _make("aws_elasticsearch_domain", _AwsEsDomainCtor),
    _make("aws_elb", _AwsElbCtor),
    _make("aws_instance", _AwsInstanceCtor),
    _make("aws_lambda_function", _AwsLambdaFunctionCtor),
    _make("aws_lb", _AwsLbCtor, aliases=["aws_alb", "aws_nlb"]),
    _make("aws_nat_gateway", _AwsNatGatewayCtor),
    _make("aws_rds_cluster_instance", _AwsRdsClusterInstanceCtor),
]:
    if item:
        ResourceRegistry[item.name] = item
        # 🔁 Register aliases explicitly for Terraform parser lookup
        for alias in item.aliases:
            ResourceRegistry[alias] = item


__all__ = ["ResourceRegistry"]

