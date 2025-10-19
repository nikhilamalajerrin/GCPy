#!/usr/bin/env bash
set -euo pipefail

# --- prerequisites ---
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }; }
need jq
need curl
need unzip
need go
# wget can be replaced by curl -L -o, but we'll keep wget:
need wget

version="${1:-latest}"
install_path="${2:-}"

# Optional: GitHub token for higher rate limits
github_headers=()
if [[ -n "${GITHUB_ACCESS_TOKEN:-}" ]]; then
  github_headers=(-H "Authorization: token ${GITHUB_ACCESS_TOKEN}")
fi

goos="$(go env GOOS)"
goarch="$(go env GOARCH)"

# tmp dir
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

# --- resolve release and download asset(s) ---
api_base="https://api.github.com/repos/infracost/terraform-provider-infracost"
if [[ "${version}" == "latest" ]]; then
  resp="$(curl -sS "${github_headers[@]}" "${api_base}/releases/latest")"
  # Prefer tag_name (e.g., v0.1.2)
  version="$(jq -r '.tag_name // .name' <<<"${resp}")"
  jq -r --arg os "${goos}" --arg arch "${goarch}" '
    .assets[]
    | select(.name | test($os + "_" + $arch))
    | .browser_download_url
  ' <<<"${resp}" | xargs -I {} wget -q -P "${tmp_dir}" {}
else
  # Fetch all releases and pick the exact tag
  curl -sS "${github_headers[@]}" "${api_base}/releases" \
  | jq -r --arg ver "${version}" --arg os "${goos}" --arg arch "${goarch}" '
      .[]
      | select((.tag_name // .name) == $ver)
      | .assets[]
      | select(.name | test($os + "_" + $arch))
      | .browser_download_url
    ' \
  | xargs -I {} wget -q -P "${tmp_dir}" {}
fi

# Ensure we found something
shopt -s nullglob
zips=( "${tmp_dir}"/terraform-provider-infracost*.zip )
if (( ${#zips[@]} == 0 )); then
  echo "No assets found for ${version} (${goos}_${goarch})." >&2
  echo "Check the release page or adjust GOOS/GOARCH." >&2
  exit 1
fi

# Unzip; grab the provider binary filename
for zipf in "${zips[@]}"; do
  unzip -q -d "${tmp_dir}" "${zipf}"
  rm -f "${zipf}"
done


bin_path="$(ls -1 "${tmp_dir}"/terraform-provider-infracost* 2>/dev/null | head -n1)"
if [[ -z "${bin_path}" ]]; then
  echo "Provider binary not found after unzip." >&2
  exit 1
fi
chmod +x "${bin_path}"

# Strip leading "v" from version for Terraform plugin path
version="${version#v}"

# Determine install path
if [[ -z "${install_path}" ]]; then
  plugin_root_path="${HOME}/.terraform.d/plugins"
  install_path="${plugin_root_path}/infracost.io/infracost/infracost/${version}/${goos}_${goarch}"
  mkdir -p "${install_path}"
  mv -f "${bin_path}" "${install_path}/$(basename "${bin_path}")"

  # Back-compat symlink for old plugin layout
  mkdir -p "${plugin_root_path}/${goos}_${goarch}"
  ln -sfn "${install_path}/$(basename "${bin_path}")" \
          "${plugin_root_path}/${goos}_${goarch}/$(basename "${bin_path}")"
else
  mkdir -p "${install_path}"
  mv -f "${bin_path}" "${install_path}/$(basename "${bin_path}")"
fi

echo "Installed terraform-provider-infracost ${version} for ${goos}_${goarch} to:"
echo "  ${install_path}/$(basename "${bin_path}")"
