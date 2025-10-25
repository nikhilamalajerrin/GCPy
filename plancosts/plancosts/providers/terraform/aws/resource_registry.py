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

# -------- aws_launch_configuration --------
AwsLaunchConfigCtor = None
try:
    from .launch_configuration import LaunchConfiguration as AwsLaunchConfigCtor
except Exception:
    try:
        from .aws_launch_configuration import LaunchConfiguration as AwsLaunchConfigCtor
    except Exception:
        AwsLaunchConfigCtor = None  # type: ignore[assignment]

# -------- aws_launch_template --------
AwsLaunchTemplateCtor = None
try:
    from .launch_template import LaunchTemplate as AwsLaunchTemplateCtor
except Exception:
    try:
        from .aws_launch_template import LaunchTemplate as AwsLaunchTemplateCtor
    except Exception:
        AwsLaunchTemplateCtor = None  # type: ignore[assignment]

# -------- aws_db_instance --------
AwsDbInstanceCtor = None
try:
    from .db_instance import DbInstance as AwsDbInstanceCtor
except Exception:
    try:
        from .aws_db_instance import DbInstance as AwsDbInstanceCtor
    except Exception:
        AwsDbInstanceCtor = None  # type: ignore[assignment]

# -------- aws_docdb_cluster_instance --------
DocdbClusterInstanceCtor = None
try:
    from .docdb_cluster_instance import DocdbClusterInstance as DocdbClusterInstanceCtor
except Exception:
    try:
        from .docdb_cluster_instance import AwsDocdbClusterInstance as DocdbClusterInstanceCtor
    except Exception:
        DocdbClusterInstanceCtor = None  # type: ignore[assignment]

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

# -------- aws_ecs_cluster --------
AwsEcsClusterCtor = None
try:
    from .ecs_cluster import EcsCluster as AwsEcsClusterCtor
except Exception:
    try:
        from .aws_ecs_cluster import EcsCluster as AwsEcsClusterCtor
    except Exception:
        AwsEcsClusterCtor = None  # type: ignore[assignment]

# -------- aws_ecs_task_definition --------
AwsEcsTaskDefCtor = None
try:
    from .ecs_task_definition import EcsTaskDefinition as AwsEcsTaskDefCtor
except Exception:
    try:
        from .aws_ecs_task_definition import EcsTaskDefinition as AwsEcsTaskDefCtor
    except Exception:
        AwsEcsTaskDefCtor = None  # type: ignore[assignment]

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
AwsInstanceCtor = None
try:
    from .instance import AwsInstance as AwsInstanceCtor
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

# -------- aws_rds_cluster --------
AwsRdsClusterCtor = None
try:
    from .rds_cluster import RdsCluster as AwsRdsClusterCtor
except Exception:
    try:
        from .aws_rds_cluster import RdsCluster as AwsRdsClusterCtor
    except Exception:
        AwsRdsClusterCtor = None  # type: ignore[assignment]

# -------- aws_elasticsearch_domain --------
AwsEsDomainCtor = None
try:
    from .elasticsearch_domain import ElasticsearchDomain as AwsEsDomainCtor
except Exception:
    try:
        from .aws_elasticsearch_domain import ElasticsearchDomain as AwsEsDomainCtor
    except Exception:
        AwsEsDomainCtor = None  # type: ignore[assignment]

# -------- aws_lambda_function --------
AwsLambdaFunctionCtor = None
try:
    from .lambda_function import LambdaFunction as AwsLambdaFunctionCtor
except Exception:
    try:
        from .aws_lambda_function import LambdaFunction as AwsLambdaFunctionCtor
    except Exception:
        AwsLambdaFunctionCtor = None  # type: ignore[assignment]


# -------------------- Public registry --------------------

ResourceRegistry: Dict[str, Callable[..., Any]] = {}

if AwsLbCtor is not None:
    ResourceRegistry["aws_lb"] = AwsLbCtor
    ResourceRegistry["aws_alb"] = AwsLbCtor
else:
    raise ImportError("lb ctor not found (expected lb.Lb / aws_lb.Lb)")

if AwsAsgCtor is not None:
    ResourceRegistry["aws_autoscaling_group"] = AwsAsgCtor
else:
    raise ImportError("autoscaling group ctor not found")

if AwsLaunchConfigCtor is not None:
    ResourceRegistry["aws_launch_configuration"] = AwsLaunchConfigCtor

if AwsLaunchTemplateCtor is not None:
    ResourceRegistry["aws_launch_template"] = AwsLaunchTemplateCtor

if AwsDbInstanceCtor is not None:
    ResourceRegistry["aws_db_instance"] = AwsDbInstanceCtor

if DocdbClusterInstanceCtor is not None:
    ResourceRegistry["aws_docdb_cluster_instance"] = DocdbClusterInstanceCtor

if AwsDynamoTableCtor is not None:
    ResourceRegistry["aws_dynamodb_table"] = AwsDynamoTableCtor

if AwsEbsSnapshotCopyCtor is not None:
    ResourceRegistry["aws_ebs_snapshot_copy"] = AwsEbsSnapshotCopyCtor

if AwsEbsSnapshotCtor is not None:
    ResourceRegistry["aws_ebs_snapshot"] = AwsEbsSnapshotCtor

if AwsEbsVolumeCtor is not None:
    ResourceRegistry["aws_ebs_volume"] = AwsEbsVolumeCtor

if AwsEcsServiceCtor is not None:
    ResourceRegistry["aws_ecs_service"] = AwsEcsServiceCtor

if AwsEcsClusterCtor is not None:
    ResourceRegistry["aws_ecs_cluster"] = AwsEcsClusterCtor

if AwsEcsTaskDefCtor is not None:
    ResourceRegistry["aws_ecs_task_definition"] = AwsEcsTaskDefCtor

if AwsElbCtor is not None:
    ResourceRegistry["aws_elb"] = AwsElbCtor

if AwsInstanceCtor is not None:
    ResourceRegistry["aws_instance"] = AwsInstanceCtor

if AwsNatGatewayCtor is not None:
    ResourceRegistry["aws_nat_gateway"] = AwsNatGatewayCtor

if AwsRdsClusterInstanceCtor is not None:
    ResourceRegistry["aws_rds_cluster_instance"] = AwsRdsClusterInstanceCtor

if AwsRdsClusterCtor is not None:
    ResourceRegistry["aws_rds_cluster"] = AwsRdsClusterCtor

if AwsEsDomainCtor is not None:
    ResourceRegistry["aws_elasticsearch_domain"] = AwsEsDomainCtor

if AwsLambdaFunctionCtor is not None:
    ResourceRegistry["aws_lambda_function"] = AwsLambdaFunctionCtor

__all__ = ["ResourceRegistry"]
