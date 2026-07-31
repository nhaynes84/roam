#!/usr/bin/env swift
// roam_send.swift - Send text to Roam OLED via BLE GATT.
// Handles macOS HID-connected devices plus advertising discovery.
//
// Usage: swift roam_send.swift "Hello from Mac"
//        swift roam_send.swift --clear
//        swift roam_send.swift --scan [--debug]
// Build: swiftc -o roam-send roam_send.swift

import CoreBluetooth
import Foundation

let TEXT_SERVICE = CBUUID(string: "FF00")
let TEXT_CHAR = CBUUID(string: "FF01")
let HID_SERVICE = CBUUID(string: "1812")
let DEVICE_INFO_SERVICE = CBUUID(string: "180A")
let BATTERY_SERVICE = CBUUID(string: "180F")
let DEVICE_NAMES = ["Roam", "Roam2"]
let CONNECTED_LOOKUP_SERVICES = [TEXT_SERVICE, HID_SERVICE, DEVICE_INFO_SERVICE, BATTERY_SERVICE]
let DEFAULT_TIMEOUT: TimeInterval = 15.0
let TIMEOUT: TimeInterval = Double(ProcessInfo.processInfo.environment["ROAM_SEND_TIMEOUT"] ?? "") ?? DEFAULT_TIMEOUT

func containsRoamName(_ name: String?) -> Bool {
    guard let name else { return false }
    let lower = name.lowercased()
    return DEVICE_NAMES.contains { lower.contains($0.lowercased()) }
}

func uuidList(_ uuids: [CBUUID]) -> String {
    if uuids.isEmpty { return "none" }
    return uuids.map { $0.uuidString }.joined(separator: ",")
}

class RoamSender: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    var central: CBCentralManager!
    let text: String
    let debug: Bool
    let scanOnly: Bool
    var peripheral: CBPeripheral?
    var done = false
    var success = false
    let startTime = Date()
    var discovered: [UUID: String] = [:]
    var connectedSeen: [UUID: String] = [:]
    var attemptedConnect = false

    init(text: String, debug: Bool, scanOnly: Bool) {
        self.text = text
        self.debug = debug
        self.scanOnly = scanOnly
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
    }

    func debugLog(_ message: String) {
        if debug || scanOnly {
            fputs("\(message)\n", stderr)
        }
    }

    func serviceUUIDs(from advertisementData: [String: Any]) -> [CBUUID] {
        return advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []
    }

    func localName(from advertisementData: [String: Any]) -> String? {
        return advertisementData[CBAdvertisementDataLocalNameKey] as? String
    }

    func describe(_ peripheral: CBPeripheral, advertisedName: String?, services: [CBUUID], rssi: NSNumber? = nil) -> String {
        let bestName = peripheral.name ?? advertisedName ?? "?"
        let rssiText = rssi.map { " rssi=\($0)" } ?? ""
        return "\(bestName) id=\(peripheral.identifier) services=\(uuidList(services))\(rssiText)"
    }

    func connect(_ candidate: CBPeripheral, source: String) {
        if attemptedConnect { return }
        attemptedConnect = true
        fputs("Found (\(source)): \(candidate.name ?? "?") (\(candidate.identifier))\n", stderr)
        peripheral = candidate
        candidate.delegate = self
        central.stopScan()
        central.connect(candidate)
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard central.state == .poweredOn else {
            switch central.state {
            case .unauthorized:
                fputs("ERROR: Bluetooth permission denied. Grant in System Settings > Privacy & Security > Bluetooth.\n", stderr)
                done = true
            case .unsupported:
                fputs("ERROR: Bluetooth is unsupported on this Mac.\n", stderr)
                done = true
            case .poweredOff:
                fputs("ERROR: Bluetooth is powered off.\n", stderr)
                done = true
            default:
                debugLog("Bluetooth state: \(central.state.rawValue)")
            }
            return
        }

        // First: check already-connected peripherals. macOS may have Roam connected as HID.
        var seen = Set<UUID>()
        var textServiceCandidate: CBPeripheral?
        var namedCandidate: CBPeripheral?

        for service in CONNECTED_LOOKUP_SERVICES {
            let connected = central.retrieveConnectedPeripherals(withServices: [service])
            debugLog("Connected lookup \(service.uuidString): \(connected.count)")
            for p in connected where !seen.contains(p.identifier) {
                seen.insert(p.identifier)
                connectedSeen[p.identifier] = p.name ?? "?"
                debugLog("  connected: \(p.name ?? "?") id=\(p.identifier)")
                if service == TEXT_SERVICE {
                    textServiceCandidate = textServiceCandidate ?? p
                }
                if containsRoamName(p.name) {
                    namedCandidate = namedCandidate ?? p
                }
            }
        }

        if scanOnly {
            fputs("Scanning for BLE devices...\n", stderr)
            central.scanForPeripherals(withServices: nil,
                                       options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
            return
        }

        if let p = namedCandidate {
            connect(p, source: "connected")
            return
        }
        if let p = textServiceCandidate {
            connect(p, source: "connected text service")
            return
        }

        fputs(scanOnly ? "Scanning for BLE devices...\n" : "Scanning for Roam...\n", stderr)
        central.scanForPeripherals(withServices: nil,
                                   options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        let advName = localName(from: advertisementData)
        let services = serviceUUIDs(from: advertisementData)
        let bestName = peripheral.name ?? advName
        let hasTextService = services.contains(TEXT_SERVICE)
        let hasRoamName = containsRoamName(bestName)
        let hasInterestingService = hasTextService || services.contains(HID_SERVICE)

        if hasRoamName || hasInterestingService || debug {
            let description = describe(peripheral, advertisedName: advName, services: services, rssi: RSSI)
            discovered[peripheral.identifier] = description
            debugLog("  discovered: \(description)")
        }

        if scanOnly { return }

        if hasRoamName || hasTextService {
            connect(peripheral, source: hasTextService ? "scan text service" : "scan name")
        }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        fputs("Connected\n", stderr)
        peripheral.discoverServices([TEXT_SERVICE])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        fputs("ERROR: Connection failed - \(error?.localizedDescription ?? "unknown")\n", stderr)
        done = true
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let err = error {
            fputs("ERROR: Service discovery failed - \(err.localizedDescription)\n", stderr)
            done = true
            return
        }

        if debug, let services = peripheral.services {
            fputs("Services: \(services.map { $0.uuid.uuidString }.joined(separator: ","))\n", stderr)
        }

        guard let svc = peripheral.services?.first(where: { $0.uuid == TEXT_SERVICE }) else {
            fputs("ERROR: Text service (0xFF00) not found on device. Reflash Roam with P2 firmware that advertises/enables bleText.\n", stderr)
            done = true
            return
        }
        peripheral.discoverCharacteristics([TEXT_CHAR], for: svc)
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let err = error {
            fputs("ERROR: Characteristic discovery failed - \(err.localizedDescription)\n", stderr)
            done = true
            return
        }

        guard let char = service.characteristics?.first(where: { $0.uuid == TEXT_CHAR }) else {
            fputs("ERROR: Text characteristic (0xFF01) not found\n", stderr)
            done = true
            return
        }

        guard let encoded = text.data(using: .utf8) else {
            fputs("ERROR: Failed to encode text\n", stderr)
            done = true
            return
        }
        let data = Data(encoded.prefix(127))

        let writeType: CBCharacteristicWriteType = char.properties.contains(.write) ? .withResponse : .withoutResponse
        peripheral.writeValue(data, for: char, type: writeType)

        if writeType == .withoutResponse {
            reportSent()
            success = true
            done = true
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let err = error {
            fputs("ERROR: Write failed - \(err.localizedDescription)\n", stderr)
            done = true
            return
        }
        reportSent()
        success = true
        done = true
    }

    func reportSent() {
        let display = text.count > 60 ? String(text.prefix(60)) + "..." : text
        fputs("Sent: \"\(display)\"\n", stderr)
    }

    func checkTimeout() {
        if Date().timeIntervalSince(startTime) <= TIMEOUT { return }
        central.stopScan()

        if scanOnly {
            let label = debug ? "devices seen" : "Roam candidates seen"
            fputs("Scan complete. \(label): \(discovered.count)\n", stderr)
            for item in discovered.values.sorted() {
                fputs("  \(item)\n", stderr)
            }
            success = true
            done = true
            return
        }

        fputs("ERROR: Timeout - Roam not found by CoreBluetooth\n", stderr)
        if !connectedSeen.isEmpty {
            fputs("Connected BLE peripherals seen by service lookup:\n", stderr)
            for name in connectedSeen.values.sorted() {
                fputs("  \(name)\n", stderr)
            }
        }
        if !discovered.isEmpty {
            fputs("Advertising candidates seen:\n", stderr)
            for item in discovered.values.sorted() {
                fputs("  \(item)\n", stderr)
            }
        }
        fputs("Tip: run roam-send --scan --debug while Roam is awake/advertising, or reflash P2 firmware with FF00 advertising.\n", stderr)
        done = true
    }
}

// --- Main ---
let rawArgs = Array(CommandLine.arguments.dropFirst())
let debug = rawArgs.contains("--debug") || ProcessInfo.processInfo.environment["ROAM_SEND_DEBUG"] == "1"
let scanOnly = rawArgs.contains("--scan")
let args = rawArgs.filter { $0 != "--debug" && $0 != "--scan" }
var text = ""

if args.contains("--help") || args.contains("-h") {
    fputs("Usage: roam-send \"text to display\"\n", stderr)
    fputs("       roam-send --clear\n", stderr)
    fputs("       roam-send --scan [--debug]\n", stderr)
    exit(0)
} else if args.contains("--clear") {
    text = ""
} else if let first = args.first {
    text = first
} else if scanOnly {
    text = ""
} else {
    if isatty(STDIN_FILENO) == 0 {
        text = (readLine(strippingNewline: true) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    } else {
        fputs("Usage: roam-send \"text to display\"\n", stderr)
        exit(1)
    }
}

let sender = RoamSender(text: text, debug: debug, scanOnly: scanOnly)
while !sender.done {
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.1))
    sender.checkTimeout()
}

exit(sender.success ? 0 : 1)
