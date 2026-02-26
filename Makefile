# Roam — Build & Flash Targets
# Requires: mpremote (pip install mpremote)
#           openscad (brew install openscad) — for render target only

.PHONY: flash reset repl deploy render clean

# Flash all firmware files to Pico
flash:
	mpremote cp -r firmware/ :

# Soft-reset the Pico
reset:
	mpremote reset

# Open interactive REPL
repl:
	mpremote connect

# Flash + reset in one step
deploy: flash reset

# Render housing STLs
render:
	cd housing && bash render.sh

# Quick render (lower resolution)
render-fast:
	cd housing && bash render.sh --fast

# Remove rendered STLs
clean:
	rm -f housing/*.stl
