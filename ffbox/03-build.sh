#!/bin/sh
#
# Build the ffbox image.
#
# UNITY_IMAGE must stay in lockstep with UNITY_VERSION in the game repo's
# .github/workflows/main.yml (customImage:). Bump both together or ffbox stops predicting CI.
set -eu

cd "$(dirname "$0")"

UNITY_VERSION=${UNITY_VERSION:-6000.3.19f1}
UNITY_IMAGE=${UNITY_IMAGE:-unityci/editor:ubuntu-${UNITY_VERSION}-windows-mono-3.2.2}
TAG=${FFBOX_IMAGE:-ffbox:latest}

echo "base:  $UNITY_IMAGE"
echo "tag:   $TAG"

# --pull=false: the ~11GB base is already local and re-checking the registry on every build is a
# long stall for no benefit. Pull explicitly when you intend to move to a new Unity version.
docker build \
    --pull=false \
    --build-arg "UNITY_IMAGE=${UNITY_IMAGE}" \
    --build-arg "UNITY_VERSION=${UNITY_VERSION}" \
    -t "$TAG" \
    .

echo
echo "Built $TAG."
echo "  'sh ffbox/setup.sh' handles the secrets file and the Unity Library warm-up."
echo "  Quick check:  ffbox/ffbox 'what does the belt merger do?'"
