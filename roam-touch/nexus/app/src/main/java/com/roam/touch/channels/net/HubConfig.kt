package com.roam.touch.channels.net

/**
 * Where the hub is and how to prove we may talk to it.
 *
 * Plain HTTP is correct here and only here: the socket is bound to talos's Tailscale
 * address, so WireGuard is already the encryption layer (`API.md` §1). The token is
 * defence in depth, not the transport's security. If this ever points at a non-tailnet
 * address, that reasoning dies and so should the plaintext.
 */
data class HubConfig(
    val host: String = DEFAULT_HOST,
    val port: Int = DEFAULT_PORT,
    val token: String,
) {
    val baseUrl: String get() = "http://$host:$port/"

    /**
     * ⚠️ `http://`, not `ws://`, even though the contract writes it as `ws://…/ws`.
     *
     * OkHttp models a WebSocket request as an ordinary HTTP request that it upgrades
     * itself, and [okhttp3.HttpUrl] rejects any scheme that is not http/https outright —
     * "Expected URL scheme 'http' or 'https' but was 'ws'". Verified the hard way on the
     * device, 2026-08-12: it throws at request-build time, inside a coroutine, which
     * takes the whole process with it. Same endpoint, same wire protocol, different
     * spelling.
     */
    val wsUrl: String get() = "http://$host:$port/ws"

    companion object {
        /** talos on the tailnet. MagicDNS is not guaranteed to resolve on the phone. */
        const val DEFAULT_HOST = "100.67.237.109"
        const val DEFAULT_PORT = 8787
    }
}
