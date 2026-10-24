#!/bin/sh
export PYTHONPATH=/app/share/easyshell${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m easyshell "$@"
