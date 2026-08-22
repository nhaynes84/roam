import Foundation

/// Tiny KV seam so store logic is testable without touching real UserDefaults.
protocol KVStore: AnyObject, Sendable {
    func int(forKey key: String) -> Int?
    func set(_ value: Int, forKey key: String)
    func intDict(forKey key: String) -> [String: Int]
    func set(_ value: [String: Int], forKey key: String)
    func strings(forKey key: String) -> [String]
    func set(_ value: [String], forKey key: String)
    func stringDict(forKey key: String) -> [String: String]
    func set(_ value: [String: String], forKey key: String)
}

final class DefaultsKV: KVStore, @unchecked Sendable {
    private let defaults: UserDefaults
    init(_ defaults: UserDefaults = .standard) { self.defaults = defaults }

    func int(forKey key: String) -> Int? {
        defaults.object(forKey: key) == nil ? nil : defaults.integer(forKey: key)
    }
    func set(_ value: Int, forKey key: String) { defaults.set(value, forKey: key) }
    func intDict(forKey key: String) -> [String: Int] {
        (defaults.dictionary(forKey: key) as? [String: Int]) ?? [:]
    }
    func set(_ value: [String: Int], forKey key: String) { defaults.set(value, forKey: key) }
    func strings(forKey key: String) -> [String] {
        defaults.array(forKey: key) as? [String] ?? []
    }
    func set(_ value: [String], forKey key: String) { defaults.set(value, forKey: key) }
    func stringDict(forKey key: String) -> [String: String] {
        (defaults.dictionary(forKey: key) as? [String: String]) ?? [:]
    }
    func set(_ value: [String: String], forKey key: String) { defaults.set(value, forKey: key) }
}

final class MemoryKV: KVStore, @unchecked Sendable {
    private var ints: [String: Int] = [:]
    private var dicts: [String: [String: Int]] = [:]
    private var lists: [String: [String]] = [:]
    private var strs: [String: [String: String]] = [:]
    func int(forKey key: String) -> Int? { ints[key] }
    func set(_ value: Int, forKey key: String) { ints[key] = value }
    func intDict(forKey key: String) -> [String: Int] { dicts[key] ?? [:] }
    func set(_ value: [String: Int], forKey key: String) { dicts[key] = value }
    func strings(forKey key: String) -> [String] { lists[key] ?? [] }
    func set(_ value: [String], forKey key: String) { lists[key] = value }
    func stringDict(forKey key: String) -> [String: String] { strs[key] ?? [:] }
    func set(_ value: [String: String], forKey key: String) { strs[key] = value }
}
