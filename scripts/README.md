# Scripts

When adding a new resource to **infracost**, a `productFilter` must uniquely
identify a product (i.e., a unique `productHash`) for pricing. A good filter
typically includes `service`, `productFamily`, and a small set of
`attribute` key/value pairs.

Because cloud catalogs are huge and many attributes repeat, these scripts help
you quickly discover the right combination using the Infracost Pricing GraphQL
API and `jq`.

> **Note:** The GraphQL API returns a limited page of results. For discovering
> the *service* name, we first search the raw AWS pricing index JSON locally.

---

## Requirements

- `jq` (JSON CLI)
- Either:
  - [`graphqurl` (gq)](https://github.com/hasura/graphqurl), **or**
  - `curl` (our scripts auto-fallback to `curl` if `gq` is not installed)

On macOS, you can run:

```sh
source requirements.sh
