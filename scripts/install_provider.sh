#!/usr/bin/env bash
set -euo pipefail

# --- prerequisites ------------------------------------------------------------
need() {
  command -v "$1" >/dev/null 2>&1 || { echo "This script requires '$1'"; exit 1; }
}
need jq
need curl
need unzip
need wget
need go

# --- inputs -------------------------------------------------------------------
version="${1:-latest}"
install_path="${2:-}"

# Support either GITHUB_ACCESS_TOKEN or GITHUB_TOKEN (prefer the former to match original script)
auth_token="${GITHUB_ACCESS_TOKEN:-${GITHUB_TOKEN:-}}"
headers=()
if [[ -n "${auth_token}" ]]; then
  headers=(-H "Authorization: token ${auth_token}")
fi

goos="$(go env GOOS)"
goarch="$(go env GOARCH)"

# --- temp workspace -----------------------------------------------------------
tmp_dir="$(mktemp -d)"
cleanup() { rm -rf "${tmp_dir}"; }
trap cleanup EXIT

# --- fetch release assets -----------------------------------------------------
api_base="https://api.github.com/repos/infracost/terraform-provider-infracost/releases"

if [[ "${version}" == "latest" ]]; then
  resp="$(curl -sSL "${headers[@]}" "${api_base}/latest")"
  # Release "name" often equals "vX.Y.Z"
  version="$(jq -r '.name' <<<"${resp}")"

  echo "Installing terraform-provider-infracost ${version} for ${goos}_${goarch} ..."
  jq -r \
    --arg os "${goos}" \
    --arg arch "${goarch}" \
    '.assets[] | select(.name | contains("\($os)_\($arch)")) | .browser_download_url' \
    <<< "${resp}" \
  | wget -q -P "${tmp_dir}" -i -
else
  echo "Installing terraform-provider-infracost ${version} for ${goos}_${goarch} ..."
  curl -sSL "${headers[@]}" "${api_base}" \
  | jq -r \
      --arg v "${version}" \
      --arg os "${goos}" \
      --arg arch "${goarch}" \
      '.[] | select(.name == $v) | .assets[] | select(.name | contains("\($os)_\($arch)")) | .browser_download_url' \
  | wget -q -P "${tmp_dir}" -i -
fi

# Ensure we downloaded something
shopt -s nullglob
zips=( "${tmp_dir}"/terraform-provider-infracost*.zip )
if (( ${#zips[@]} == 0 )); then
  echo "No matching release asset found for ${goos}_${goarch} (version: ${version})."
  exit 1
fi

# --- unzip & pick binary ------------------------------------------------------
for z in "${zips[@]}"; do
  unzip -q -d "${tmp_dir}" "${z}"
  rm -f "${z}"
done

# Find the provider binary (supports names like terraform-provider-infracost_vX_Y_Z)
bin_path=""
for f in "${tmp_dir}"/terraform-provider-infracost*; do
  if [[ -f "${f}" && ! "${f}" =~ \.zip$ ]]; then
    bin_path="${f}"
    break
  fi
done

if [[ -z "${bin_path}" ]]; then
  echo "Failed to locate provider binary after unzip."
  exit 1
fi
chmod +x "${bin_path}"

# --- determine install location ----------------------------------------------
if [[ -z "${install_path}" ]]; then
  plugin_root_path="${HOME}/.terraform.d/plugins"
  install_path="${plugin_root_path}/infracost.io/infracost/infracost/${version}/${goos}_${goarch}"
  mkdir -p "${install_path}"
  mv "${bin_path}" "${install_path}/terraform-provider-infracost"

  # Legacy path symlink for older Terraform versions
  mkdir -p "${plugin_root_path}/${goos}_${goarch}"
  ln -sfn "${install_path}/terraform-provider-infracost" \
          "${plugin_root_path}/${goos}_${goarch}/terraform-provider-infracost"
else
  mkdir -p "${install_path}"
  mv "${bin_path}" "${install_path}/terraform-provider-infracost"
fi

echo "Installed terraform-provider-infracost ${version} -> ${install_path}/terraform-provider-infracost"
