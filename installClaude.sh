#/bin/bash
installer="$(mktemp)"
install_status=1

if curl -fsSLo "$installer" https://claude.ai/install.sh && bash -n "$installer"; then
    bash "$installer"
    install_status=$?
else
    echo "Claude Code installer download or syntax check failed" >&2
fi

rm -f "$installer"
[ "$install_status" -eq 0 ]
