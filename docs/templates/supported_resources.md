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
{% for key, value in resource_registry_map.items() -%}
| `{{ key }}` | {% if value.get('notes') %}{% for note in value['notes'] %}{{ note }} {% endfor %}{% endif %}|
{% endfor %}

## The resource that isn't supported

We're regularly adding support for new Terraform AWS resources — watch the repo for new releases!

You can help by:
1. Creating an issue and mentioning the resource you need and a bit about your use-case; we'll try to prioritize it.
2. Contributing new resources — we’re working on making it easy! You can join our Discord community if you need help contributing.
