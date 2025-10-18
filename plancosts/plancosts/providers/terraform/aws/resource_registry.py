# plancosts/providers/terraform/aws/resource_registry.py
from __future__ import annotations

from typing import Callable, Any, Dict

# -------- aws_lb / aws_alb (alias for aws_lb) --------
AwsLbCtor = None
try:
    from .lb import Lb as AwsLbCtor  # preferred
except Exception:
    try:
        from .aws_lb import Lb as AwsLbCtor
    except Exception:
        try:
            from .lb import AwsLb as AwsLbCtor
        except Exception:
            AwsLbCtor = None  # type: ignore[assignment]

# -------- aws_autoscaling_group --------
# Prefer the new Python port in autoscaling_group.py FIRST.
AwsAsgCtor = None
try:
    from .autoscaling_group import NewAutoscalingGroup as AwsAsgCtor
except Exception:
    try:
        from .autoscaling_group import AwsAutoscalingGroup as AwsAsgCtor
    except Exception:
        try:
            from .ec2_autoscaling_group import NewAutoscalingGroup as AwsAsgCtor
        except Exception:
            try:
                from .ec2_autoscaling_group import Ec2AutoscalingGroup as AwsAsgCtor
            except Exception:
                AwsAsgCtor = None  # type: ignore[assignment]

# -------- aws_db_instance --------
AwsDbInstanceCtor = None
try:
    from .db_instance import DbInstance as AwsDbInstanceCtor
except Exception:
    try:
        from .aws_db_instance import DbInstance as AwsDbInstanceCtor
    except Exception:
        AwsDbInstanceCtor = None  # type: ignore[assignment]

# -------- aws_dynamodb_table --------
AwsDynamoTableCtor = None
try:
    from .dynamodb_table import DynamoDbTable as AwsDynamoTableCtor
except Exception:
    try:
        from .dynamodb_table import DynamoDBTable as AwsDynamoTableCtor
    except Exception:
        AwsDynamoTableCtor = None  # type: ignore[assignment]

# -------- aws_ebs_volume --------
AwsEbsVolumeCtor = None
try:
    from .ebs_volume import EbsVolume as AwsEbsVolumeCtor
except Exception:
    try:
        from .aws_ebs_volume import EbsVolume as AwsEbsVolumeCtor
    except Exception:
        AwsEbsVolumeCtor = None  # type: ignore[assignment]

# -------- aws_ebs_snapshot --------
AwsEbsSnapshotCtor = None
try:
    from .ebs_snapshot import EbsSnapshot as AwsEbsSnapshotCtor
except Exception:
    try:
        from .aws_ebs_snapshot import EbsSnapshot as AwsEbsSnapshotCtor
    except Exception:
        AwsEbsSnapshotCtor = None  # type: ignore[assignment]

# -------- aws_ebs_snapshot_copy --------
AwsEbsSnapshotCopyCtor = None
try:
    from .ebs_snapshot_copy import EbsSnapshotCopy as AwsEbsSnapshotCopyCtor
except Exception:
    try:
        from .aws_ebs_snapshot_copy import EbsSnapshotCopy as AwsEbsSnapshotCopyCtor
    except Exception:
        AwsEbsSnapshotCopyCtor = None  # type: ignore[assignment]

# -------- aws_ecs_service --------
AwsEcsServiceCtor = None
try:
    from .ecs_service import AwsEcsService as AwsEcsServiceCtor
except Exception:
    try:
        from .ecs_service import EcsService as AwsEcsServiceCtor
    except Exception:
        AwsEcsServiceCtor = None  # type: ignore[assignment]

# -------- aws_elb (Classic) --------
AwsElbCtor = None
try:
    from .elb import Elb as AwsElbCtor
except Exception:
    try:
        from .aws_elb import Elb as AwsElbCtor
    except Exception:
        AwsElbCtor = None  # type: ignore[assignment]

# -------- aws_instance --------
# IMPORTANT: Prefer the new Python port in instance.py FIRST so we get the
# (address, region, raw_values, rd) signature that the parser uses.
AwsInstanceCtor = None
try:
    from .instance import AwsInstance as AwsInstanceCtor  # preferred
except Exception:
    try:
        from .instance import Instance as AwsInstanceCtor
    except Exception:
        try:
            from .ec2_instance import Ec2Instance as AwsInstanceCtor
        except Exception:
            AwsInstanceCtor = None  # type: ignore[assignment]

# -------- aws_nat_gateway --------
AwsNatGatewayCtor = None
try:
    from .aws_nat_gateway import NatGateway as AwsNatGatewayCtor
except Exception:
    try:
        from .nat_gateway import NatGateway as AwsNatGatewayCtor
    except Exception:
        AwsNatGatewayCtor = None  # type: ignore[assignment]

# -------- aws_rds_cluster_instance --------
AwsRdsClusterInstanceCtor = None
try:
    from .rds_cluster_instance import RdsClusterInstance as AwsRdsClusterInstanceCtor
except Exception:
    try:
        from .aws_rds_cluster_instance import RdsClusterInstance as AwsRdsClusterInstanceCtor
    except Exception:
        AwsRdsClusterInstanceCtor = None  # type: ignore[assignment]

# -------- aws_lambda_function --------
AwsLambdaFunctionCtor = None
try:
    from .lambda_function import LambdaFunction as AwsLambdaFunctionCtor
except Exception:
    try:
        from .aws_lambda_function import LambdaFunction as AwsLambdaFunctionCtor
    except Exception:
        AwsLambdaFunctionCtor = None  # type: ignore[assignment]


# -------------------- Public registry (parity with Go) --------------------

ResourceRegistry: Dict[str, Callable[..., Any]] = {}

# aws_lb + alias aws_alb
if AwsLbCtor is not None:
    ResourceRegistry["aws_lb"] = AwsLbCtor
    ResourceRegistry["aws_alb"] = AwsLbCtor  # alias
else:
    raise ImportError("lb ctor not found (expected lb.Lb / aws_lb.Lb)")

if AwsAsgCtor is not None:
    ResourceRegistry["aws_autoscaling_group"] = AwsAsgCtor
else:
    raise ImportError("autoscaling group ctor not found (expected autoscaling_group / ec2_autoscaling_group)")

if AwsDbInstanceCtor is not None:
    ResourceRegistry["aws_db_instance"] = AwsDbInstanceCtor
else:
    raise ImportError("db instance ctor not found (expected db_instance)")

if AwsDynamoTableCtor is not None:
    ResourceRegistry["aws_dynamodb_table"] = AwsDynamoTableCtor
else:
    raise ImportError("dynamodb table ctor not found (expected dynamodb_table)")

if AwsEbsSnapshotCtor is not None:
    ResourceRegistry["aws_ebs_snapshot"] = AwsEbsSnapshotCtor
else:
    raise ImportError("ebs snapshot ctor not found (expected ebs_snapshot)")

if AwsEbsSnapshotCopyCtor is not None:
    ResourceRegistry["aws_ebs_snapshot_copy"] = AwsEbsSnapshotCopyCtor
else:
    raise ImportError("ebs snapshot copy ctor not found (expected ebs_snapshot_copy)")

if AwsEbsVolumeCtor is not None:
    ResourceRegistry["aws_ebs_volume"] = AwsEbsVolumeCtor
else:
    raise ImportError("ebs volume ctor not found (expected ebs_volume)")

if AwsEcsServiceCtor is not None:
    ResourceRegistry["aws_ecs_service"] = AwsEcsServiceCtor
else:
    raise ImportError("ecs service ctor not found (expected ecs_service)")

if AwsElbCtor is not None:
    ResourceRegistry["aws_elb"] = AwsElbCtor
else:
    raise ImportError("elb ctor not found (expected elb)")

if AwsInstanceCtor is not None:
    ResourceRegistry["aws_instance"] = AwsInstanceCtor
else:
    raise ImportError("instance ctor not found (expected instance/ec2_instance)")

if AwsNatGatewayCtor is not None:
    ResourceRegistry["aws_nat_gateway"] = AwsNatGatewayCtor
else:
    raise ImportError("nat gateway ctor not found (expected aws_nat_gateway/nat_gateway)")

if AwsRdsClusterInstanceCtor is not None:
    ResourceRegistry["aws_rds_cluster_instance"] = AwsRdsClusterInstanceCtor
else:
    raise ImportError("rds cluster instance ctor not found (expected rds_cluster_instance)")

# Optional: include lambda if present
if AwsLambdaFunctionCtor is not None:
    ResourceRegistry["aws_lambda_function"] = AwsLambdaFunctionCtor

__all__ = ["ResourceRegistry"]
