# Roam — Build & Flash Targets
# Requires: mpremote (pip install mpremote) — for MicroPython targets
#           arduino-cli (brew install arduino-cli) — for Arduino targets
#           openscad (brew install openscad) — for render target only

FQBN = rp2040:rp2040:pimoroni_pico_plus_2w:ipbtstack=ipv4btcble

.PHONY: flash reset repl deploy render clean
.PHONY: arduino-setup arduino-build arduino-flash arduino-monitor

# Flash all firmware files to Pico
flash:
	mpremote mkdir :lib 2>/dev/null || true
	mpremote cp firmware/lib/sh1106.py :lib/sh1106.py
	@for f in firmware/*.py firmware/*.json; do \
		mpremote cp "$$f" ":$$(basename $$f)"; \
	done

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

# === Arduino (P1) Targets ===

# Install board core and libraries
arduino-setup:
	arduino-cli core update-index --additional-urls https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json
	arduino-cli core install rp2040:rp2040 --additional-urls https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json
	arduino-cli lib install U8g2

# Compile Arduino firmware
arduino-build:
	arduino-cli compile --fqbn $(FQBN) arduino/

# Compile and upload via UF2 (hold BOOTSEL, plug USB)
arduino-flash:
	arduino-cli compile --fqbn $(FQBN) arduino/
	arduino-cli upload --fqbn $(FQBN) -p $$(arduino-cli board list --format json | python3 -c "import sys,json; boards=json.load(sys.stdin).get('detected_ports',[]); print(boards[0]['port']['address'] if boards else '/dev/ttyACM0')") arduino/

# Serial monitor
arduino-monitor:
	arduino-cli monitor -p $$(arduino-cli board list --format json | python3 -c "import sys,json; boards=json.load(sys.stdin).get('detected_ports',[]); print(boards[0]['port']['address'] if boards else '/dev/ttyACM0')") --config baudrate=115200
