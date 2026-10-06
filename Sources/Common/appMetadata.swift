public let stableWinMuxAppId: String = "com.tobiashochguertel.winmux"
#if DEBUG
    public let winMuxAppId: String = "com.tobiashochguertel.winmux.debug"
    public let winMuxAppName: String = "WinMux-Debug"
#else
    public let winMuxAppId: String = stableWinMuxAppId
    public let winMuxAppName: String = "WinMux"
#endif
