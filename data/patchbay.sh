#!/bin/sh
export PYTHONPATH=/app/share/patchbay${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m patchbay "$@"
