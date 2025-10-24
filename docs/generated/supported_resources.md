---
slug: supported_resources
title: Supported resources
---

Currently this tool supports the following Terraform resources on AWS.

Support for the following is not currently included:
  * any costs that are not specified in the Terraform configuration, e.g. S3 storage costs, data out costs.
  * Any non On-Demand pricing, such as Reserved Instances.

| Terraform resource           | Notes |
| ---                          | ---   |
| `aws_alb` | |
| `aws_autoscaling_group` | |
| `aws_db_instance` | |
| `aws_docdb_cluster_instance` | |
| `aws_dynamodb_table` | |
| `aws_ebs_snapshot` | |
| `aws_ebs_snapshot_copy` | |
| `aws_ebs_volume` | |
| `aws_ecs_service` | |
| `aws_elasticsearch_domain` | |
| `aws_elb` | |
| `aws_instance` | |
| `aws_lambda_function` | |
| `aws_lb` | |
| `aws_nat_gateway` | |
| `aws_nlb` | |
| `aws_rds_cluster_instance` | |


## The resource that isn't supported

We're regularly adding support for new Terraform AWS resources — watch the repo for new releases!

You can help by:
1. Creating an issue and mentioning the resource you need and a bit about your use-case; we'll try to prioritize it.
2. Contributing new resources — we’re working on making it easy! You can join our Discord community if you need help contributing.