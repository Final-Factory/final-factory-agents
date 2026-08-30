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

# ONE IMAGE, TWO TAGS. ffbox and the CI runners build from this same Dockerfile; if each build
# script only tagged its own name the two would drift apart on every rebuild — measured on
# 2026-08-29, ffbox:latest 74b0815107e9 against ffghrunner:latest 5c4527331ac9, same source. Tag
# both here so whichever built last is what both use.
RUNNER_TAG=${FFGHR_IMAGE:-ffghrunner:latest}
docker tag "$TAG" "$RUNNER_TAG" && echo "tagged: $RUNNER_TAG"

echo
echo "Built $TAG."
echo "  'sh ffbox/setup.sh' handles the secrets file and the Unity Library warm-up."
echo "  Quick check:  ffbox/ffbox 'what does the belt merger do?'"
