#!/usr/bin/env swift
// roam_send.swift — Send text to Roam OLED via BLE GATT
// Handles macOS HID-connected devices via retrieveConnectedPeripherals
//
// Usage: swift roam_send.swift "Hello from Mac"
//        swift roam_send.swift --clear
// Build: swiftc -o roam-send roam_send.swift

import CoreBluetooth
import Foundation

let TEXT_SERVICE = CBUUID(string: "FF00")
let TEXT_CHAR = CBUUID(string: "FF01")
let DEVICE_NAME = "Roam"
let TIMEOUT: TimeInterval = 10.0

class RoamSender: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    var central: CBCentralManager!
    let text: String
    var peripheral: CBPeripheral?
    var done = false
    var success = false
    let startTime = Date()

    init(text: String) {
        self.text = text
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard central.state == .poweredOn else {
            if central.state == .unauthorized {
                fputs("ERROR: Bluetooth permission denied. Grant in System Settings > Privacy > Bluetooth.\n", stderr)
                done = true
            }
            return
        }

        // First: check already-connected peripherals (handles HID-connected case)
        let connected = central.retrieveConnectedPeripherals(withServices: [TEXT_SERVICE])
        for p in connected {
            if p.name?.contains(DEVICE_NAME) == true {
                fputs("Found (connected): \(p.name ?? "?") (\(p.identifier))\n", stderr)
                peripheral = p
                p.delegate = self
                central.connect(p)
                return
            }
        }

        // Fallback: scan for advertising device
        fputs("Scanning for '\(DEVICE_NAME)'...\n", stderr)
        central.scanForPeripherals(withServices: [TEXT_SERVICE], options: nil)
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        if peripheral.name?.contains(DEVICE_NAME) == true {
            fputs("Found (scan): \(peripheral.name ?? "?") (\(peripheral.identifier))\n", stderr)
            central.stopScan()
            self.peripheral = peripheral
            peripheral.delegate = self
            central.connect(peripheral)
        }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        fputs("Connected\n", stderr)
        peripheral.discoverServices([TEXT_SERVICE])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        fputs("ERROR: Connection failed — \(error?.localizedDescription ?? "unknown")\n", stderr)
        done = true
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let err = error {
            fputs("ERROR: Service discovery failed — \(err.localizedDescription)\n", stderr)
            done = true
            return
        }

        guard let svc = peripheral.services?.first(where: { $0.uuid == TEXT_SERVICE }) else {
            fputs("ERROR: Text service (0xFF00) not found on device\n", stderr)
            done = true
            return
        }
        peripheral.discoverCharacteristics([TEXT_CHAR], for: svc)
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let err = error {
            fputs("ERROR: Characteristic discovery failed — \(err.localizedDescription)\n", stderr)
            done = true
            return
        }

        guard let char = service.characteristics?.first(where: { $0.uuid == TEXT_CHAR }) else {
            fputs("ERROR: Text characteristic (0xFF01) not found\n", stderr)
            done = true
            return
        }

        guard let data = text.data(using: .utf8)?.prefix(127) else {
            fputs("ERROR: Failed to encode text\n", stderr)
            done = true
            return
        }

        peripheral.writeValue(Data(data), for: char, type: .withoutResponse)

        let display = text.count > 60 ? String(text.prefix(60)) + "..." : text
        fputs("Sent: \"\(display)\"\n", stderr)
        success = true
        done = true
    }

    func checkTimeout() {
        if Date().timeIntervalSince(startTime) > TIMEOUT {
            fputs("ERROR: Timeout — device not found\n", stderr)
            central.stopScan()
            done = true
        }
    }
}

// --- Main ---
var text = ""
let args = CommandLine.arguments.dropFirst()

if args.contains("--clear") {
    text = ""
} else if args.contains("--help") || args.contains("-h") {
    fputs("Usage: roam-send \"text to display\"\n", stderr)
    fputs("       roam-send --clear\n", stderr)
    exit(0)
} else if let first = args.first {
    text = first
} else {
    // Read from stdin if piped
    if isatty(STDIN_FILENO) == 0 {
        text = (readLine(strippingNewline: true) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    } else {
        fputs("Usage: roam-send \"text to display\"\n", stderr)
        exit(1)
    }
}

let sender = RoamSender(text: text)
while !sender.done {
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.1))
    sender.checkTimeout()
}

exit(sender.success ? 0 : 1)
