# Roam — Build & Flash Targets
# Requires: mpremote (pip install mpremote) — for MicroPython targets
#           arduino-cli (brew install arduino-cli) — for Arduino targets
#           openscad (brew install openscad) — for render target only

FQBN    = rp2040:rp2040:pimoroni_pico_plus_2w:ipbtstack=ipv4btcble
FQBN_P2 = Seeeduino:nrf52:xiaonRF52840Sense
SEEED_URL = https://files.seeedstudio.com/arduino/package_seeeduino_boards_index.json
P2_PORT = $(shell arduino-cli board list --format json | python3 -c 'import sys,json; fqbn="$(FQBN_P2)"; ports=json.load(sys.stdin).get("detected_ports",[]); matches=[p["port"]["address"] for p in ports if any(b.get("fqbn")==fqbn for b in p.get("matching_boards",[]))]; print(matches[0] if matches else "/dev/ttyACM0")')
P2_BUILD_DIR = /tmp/roam-p2-build
P2_OUTPUT_DIR = /tmp/roam-p2-out
P2_DFU_ZIP = $(P2_OUTPUT_DIR)/p2.ino.zip
P2_NRFUTIL = $(HOME)/Library/Arduino15/packages/Seeeduino/hardware/nrf52/1.1.12/tools/adafruit-nrfutil/macos/adafruit-nrfutil

.PHONY: flash reset repl deploy render clean step
.PHONY: arduino-setup arduino-build arduino-flash arduino-monitor
.PHONY: p2-setup p2-build p2-flash p2-flash-sealed p2-monitor

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

# Export STEP files for Shapr3D (requires housing/.venv)
step:
	housing/.venv/bin/python3 housing/export_step.py

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

# === P2 (XIAO nRF52840 Sense) Targets ===

# Install Seeed nRF52 board core and libraries
p2-setup:
	arduino-cli core update-index --additional-urls $(SEEED_URL)
	arduino-cli core install Seeeduino:nrf52 --additional-urls $(SEEED_URL)
	arduino-cli lib install U8g2

# Compile P2 firmware
p2-build:
	arduino-cli compile --fqbn $(FQBN_P2) p2/

# Compile and upload P2 via normal Arduino upload.
p2-flash:
	arduino-cli compile --fqbn $(FQBN_P2) p2/
	arduino-cli upload --fqbn $(FQBN_P2) -p $(P2_PORT) p2/

# Compile and upload P2 when Roam is sealed and reset is inaccessible.
# The first nrfutil command uses 1200-baud touch only; it is expected to exit
# non-zero after the app port disappears. Then upload to the bootloader PID.
p2-flash-sealed:
	mkdir -p $(P2_BUILD_DIR) $(P2_OUTPUT_DIR)
	rm -f $(P2_OUTPUT_DIR)/p2.ino.elf $(P2_OUTPUT_DIR)/p2.ino.hex $(P2_OUTPUT_DIR)/p2.ino.zip
	arduino-cli compile --fqbn $(FQBN_P2) --build-path $(P2_BUILD_DIR) --output-dir $(P2_OUTPUT_DIR) p2/
	@tmp=$$(mktemp); \
	if $(P2_NRFUTIL) dfu serial -pkg $(P2_DFU_ZIP) -p $(P2_PORT) -b 115200 --singlebank --touch 1200 > "$$tmp" 2>&1; then \
		cat "$$tmp"; \
		rm -f "$$tmp"; \
		exit 0; \
	fi; \
	status=$$?; \
	cat "$$tmp"; \
	rm -f "$$tmp"; \
	echo "Initial touch/upload exited $$status; looking for P2 bootloader..."; \
	port=""; \
	for i in $$(seq 1 40); do \
		port=$$(arduino-cli board list --format json | python3 -c 'import sys,json; ports=json.load(sys.stdin).get("detected_ports",[]); matches=[p["port"]["address"] for p in ports if p.get("port",{}).get("properties",{}).get("pid","").lower()=="0x0045"]; print(matches[0] if matches else "")'); \
		if [ -n "$$port" ]; then break; fi; \
		sleep 0.5; \
	done; \
	if [ -z "$$port" ]; then echo "P2 bootloader port not found; expected Seeed PID 0x0045"; exit 1; fi; \
	echo "Uploading to P2 bootloader on $$port"; \
	$(P2_NRFUTIL) --verbose dfu serial -pkg $(P2_DFU_ZIP) -p "$$port" -b 115200 --singlebank

# P2 serial monitor
p2-monitor:
	arduino-cli monitor -p $(P2_PORT) --config baudrate=115200
